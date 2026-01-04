#!/usr/bin/env python3
"""
Validate legal brief propositions against cited cases.

For each proposition:
1. If it's a direct quote, search for the quote in the case text
2. If not a quote, use semantic comparison to verify the proposition
3. Focus on the pin-cited page when available

Outputs an HTML report with validation results.
"""

import re
import json
import sys
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import html

from dotenv import load_dotenv

# Load .env from script directory
load_dotenv(Path(__file__).parent / '.env')

# subprocess is used for calling claude CLI
import subprocess


class ValidationResult(Enum):
    VERIFIED = "verified"      # Green check - found/supported
    FAILED = "failed"          # Red X - not found/contradicted
    UNCERTAIN = "uncertain"    # Yellow ? - unclear


@dataclass
class PropositionValidation:
    """Result of validating a single proposition."""
    proposition_text: str
    proposition_type: str  # "quote" or "statement"
    citations: List[Dict]
    result: ValidationResult
    explanation: str
    matched_text: Optional[str] = None  # The text found in the case
    page_checked: Optional[str] = None  # The page number checked


def extract_quotes(text: str) -> List[str]:
    """Extract quoted text from a proposition."""
    # Match text in various quote styles
    patterns = [
        r'"([^"]+)"',           # Standard double quotes
        r'"([^"]+)"',           # Curly double quotes
        r"'([^']+)'",           # Single quotes (for nested)
    ]

    quotes = []
    for pattern in patterns:
        quotes.extend(re.findall(pattern, text))

    return quotes


def is_quote_proposition(prop: Dict) -> bool:
    """Determine if a proposition is primarily a direct quote."""
    text = prop.get('text', '')
    prop_type = prop.get('type', '')

    # Block quotes are always quotes
    if prop_type == 'block_quote':
        return True

    # Check for substantial quoted content
    quotes = extract_quotes(text)
    if quotes:
        # If more than 50% of the text is quoted, treat as quote
        quoted_len = sum(len(q) for q in quotes)
        if quoted_len > len(text) * 0.4:
            return True

    return False


def normalize_for_matching(text: str) -> str:
    """
    Normalize text for quote matching.

    Handles common "clean up" differences:
    - Whitespace normalization
    - Quote style variations
    - Ellipsis variations
    - Bracket insertions [like this]
    - Punctuation inside/outside quotes
    """
    if not text:
        return ""

    # Normalize whitespace
    text = ' '.join(text.split())

    # Normalize quotes
    text = text.replace('"', '"').replace('"', '"')
    text = text.replace(''', "'").replace(''', "'")

    # Normalize ellipses
    text = re.sub(r'\.{3,}', '...', text)
    text = re.sub(r'\s*\.\.\.\s*', ' ... ', text)

    # Remove bracketed insertions for matching
    text = re.sub(r'\[[^\]]*\]', '', text)

    # Normalize dashes
    text = text.replace('—', '-').replace('–', '-')

    # Remove extra spaces
    text = ' '.join(text.split())

    return text.lower()


def extract_page_text(html_path: str, page_num: str) -> Optional[str]:
    """
    Extract text from a specific page in the HTML case file.

    HTML files have page markers like: <a id="p595" ... >*595</a>
    """
    if not os.path.exists(html_path):
        return None

    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except (IOError, UnicodeDecodeError):
        return None

    # Find the page marker
    page_pattern = rf'id="p{page_num}"[^>]*>.*?</a>'
    page_match = re.search(page_pattern, content)

    if not page_match:
        # Try without the exact format
        page_pattern = rf'\*{page_num}</a>'
        page_match = re.search(page_pattern, content)

    if not page_match:
        return None

    start_pos = page_match.end()

    # Find the next page marker
    next_page = int(page_num) + 1
    next_pattern = rf'id="p{next_page}"'
    next_match = re.search(next_pattern, content[start_pos:])

    if next_match:
        end_pos = start_pos + next_match.start()
    else:
        # Take next 5000 chars if no next page found
        end_pos = start_pos + 5000

    # Extract and clean the HTML
    page_html = content[start_pos:end_pos]

    # Remove HTML tags
    page_text = re.sub(r'<[^>]+>', ' ', page_html)

    # Decode HTML entities
    page_text = html.unescape(page_text)

    # Normalize whitespace
    page_text = ' '.join(page_text.split())

    return page_text


def extract_case_text(json_path: str, html_path: Optional[str] = None) -> Optional[str]:
    """
    Extract full opinion text from the case files.

    Tries JSON first, falls back to HTML if JSON text is empty.
    """
    text_from_json = None

    if json_path and os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Get opinions from casebody
            opinions = data.get('casebody', {}).get('opinions', [])

            texts = []
            for op in opinions:
                text = op.get('text', '')
                if text:
                    texts.append(text)

            if texts:
                text_from_json = '\n\n'.join(texts)
        except (IOError, json.JSONDecodeError):
            pass

    if text_from_json:
        return text_from_json

    # Fall back to HTML if JSON text is empty
    if html_path is None and json_path:
        html_path = json_path.replace('/json/', '/html/').replace('.json', '.html')

    if html_path and os.path.exists(html_path):
        try:
            with open(html_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Strip HTML tags
            text = re.sub(r'<[^>]+>', ' ', content)
            text = html.unescape(text)
            text = ' '.join(text.split())
            return text
        except (IOError, UnicodeDecodeError):
            pass

    return None


def find_quote_in_case(quote: str, case_text: str, page_text: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Search for a quote in the case text.

    Returns (found, matched_text)
    """
    norm_quote = normalize_for_matching(quote)

    # First try the specific page if available
    if page_text:
        norm_page = normalize_for_matching(page_text)
        if norm_quote in norm_page:
            return True, quote

        # Try with more aggressive normalization (remove all punctuation)
        super_norm_quote = re.sub(r'[^\w\s]', '', norm_quote)
        super_norm_page = re.sub(r'[^\w\s]', '', norm_page)
        if super_norm_quote in super_norm_page:
            return True, quote

    # Try the full case text
    if case_text:
        norm_case = normalize_for_matching(case_text)
        if norm_quote in norm_case:
            return True, quote

        # Try with more aggressive normalization
        super_norm_quote = re.sub(r'[^\w\s]', '', norm_quote)
        super_norm_case = re.sub(r'[^\w\s]', '', norm_case)
        if super_norm_quote in super_norm_case:
            return True, quote

    return False, None


def verify_semantic(proposition: str, case_text: str, case_name: str,
                   pin_cite: Optional[str] = None) -> Tuple[ValidationResult, str]:
    """
    Use Claude Code CLI to verify if the proposition is supported by the case text.
    """
    import tempfile

    # Truncate case text if too long
    max_case_len = 15000
    if len(case_text) > max_case_len:
        case_text = case_text[:max_case_len] + "\n[... truncated ...]"

    pin_info = f" at {pin_cite}" if pin_cite else ""

    prompt = f"""Analyze whether this legal proposition is supported by the case text.

PROPOSITION FROM BRIEF:
"{proposition}"

CITED CASE ({case_name}{pin_info}):
{case_text}

Determine if the case supports this proposition. Consider:
1. Does the case discuss this legal principle?
2. Is the proposition an accurate statement of what the case holds?
3. If a pin cite is given, is the proposition found near that page?

Respond with exactly one of these verdicts on the first line:
VERIFIED - The case clearly supports this proposition
FAILED - The case does not support this or contradicts it
UNCERTAIN - Cannot determine from available text

Then provide a brief (1-2 sentence) explanation."""

    try:
        # Write prompt to temp file to avoid shell escaping issues
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(prompt)
            prompt_file = f.name

        # Call claude CLI with --print flag for non-interactive output
        result = subprocess.run(
            ['claude', '--print', '-p', prompt],
            capture_output=True,
            text=True,
            timeout=60
        )

        os.unlink(prompt_file)

        if result.returncode != 0:
            return ValidationResult.UNCERTAIN, f"CLI error: {result.stderr[:100]}"

        result_text = result.stdout.strip()
        lines = result_text.split('\n', 1)
        verdict_line = lines[0].upper()
        explanation = lines[1].strip() if len(lines) > 1 else ""

        if 'VERIFIED' in verdict_line:
            return ValidationResult.VERIFIED, explanation
        elif 'FAILED' in verdict_line:
            return ValidationResult.FAILED, explanation
        else:
            return ValidationResult.UNCERTAIN, explanation

    except subprocess.TimeoutExpired:
        return ValidationResult.UNCERTAIN, "Claude CLI timed out"
    except Exception as e:
        return ValidationResult.UNCERTAIN, f"Error: {str(e)}"


def validate_proposition(prop: Dict) -> PropositionValidation:
    """Validate a single proposition against its cited cases."""

    prop_text = prop.get('text', '')
    prop_type = 'quote' if is_quote_proposition(prop) else 'statement'
    citations = prop.get('citations', [])

    if not citations:
        return PropositionValidation(
            proposition_text=prop_text,
            proposition_type=prop_type,
            citations=[],
            result=ValidationResult.UNCERTAIN,
            explanation="No citations to validate against"
        )

    # Use the first citation with local paths
    cite = None
    for c in citations:
        if c.get('local_json_path'):
            cite = c
            break

    if not cite:
        return PropositionValidation(
            proposition_text=prop_text,
            proposition_type=prop_type,
            citations=citations,
            result=ValidationResult.UNCERTAIN,
            explanation="No local case files available"
        )

    json_path = cite.get('local_json_path')
    html_path = cite.get('local_html_path')
    pin_cite = cite.get('pin_cite', '')
    case_name = cite.get('case_name', 'Unknown')

    # Extract case text
    case_text = extract_case_text(json_path, html_path)
    if not case_text:
        return PropositionValidation(
            proposition_text=prop_text,
            proposition_type=prop_type,
            citations=citations,
            result=ValidationResult.UNCERTAIN,
            explanation=f"Could not read case file: {json_path}"
        )

    # Extract page-specific text if pin cite available
    page_text = None
    page_num = None
    if pin_cite and html_path:
        # Extract page number from pin cite
        page_match = re.search(r'(\d+)', str(pin_cite))
        if page_match:
            page_num = page_match.group(1)
            page_text = extract_page_text(html_path, page_num)

    # Validate based on type
    if prop_type == 'quote':
        # For quotes, search for the text
        quotes = extract_quotes(prop_text)
        if not quotes:
            # The whole text might be the quote (block quote)
            quotes = [prop_text]

        for quote in quotes:
            if len(quote) < 20:  # Skip very short quotes
                continue
            found, matched = find_quote_in_case(quote, case_text, page_text)
            if found:
                return PropositionValidation(
                    proposition_text=prop_text,
                    proposition_type=prop_type,
                    citations=citations,
                    result=ValidationResult.VERIFIED,
                    explanation=f"Quote found in {case_name}",
                    matched_text=matched,
                    page_checked=page_num
                )

        # Quote not found - try semantic as fallback
        result, explanation = verify_semantic(prop_text, case_text, case_name, pin_cite)
        return PropositionValidation(
            proposition_text=prop_text,
            proposition_type=prop_type,
            citations=citations,
            result=result,
            explanation=f"Quote not found verbatim. {explanation}",
            page_checked=page_num
        )

    else:
        # For statements, use semantic verification
        # Use page text if available, otherwise full case
        text_to_check = page_text if page_text else case_text
        result, explanation = verify_semantic(prop_text, text_to_check, case_name, pin_cite)

        return PropositionValidation(
            proposition_text=prop_text,
            proposition_type=prop_type,
            citations=citations,
            result=result,
            explanation=explanation,
            page_checked=page_num
        )


def generate_html_report(validations: List[PropositionValidation],
                         brief_name: str, output_path: str) -> None:
    """Generate an HTML report of validation results."""

    # Count results
    verified = sum(1 for v in validations if v.result == ValidationResult.VERIFIED)
    failed = sum(1 for v in validations if v.result == ValidationResult.FAILED)
    uncertain = sum(1 for v in validations if v.result == ValidationResult.UNCERTAIN)

    html_content = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Citation Validation: {html.escape(brief_name)}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        h1 {{
            color: #333;
            border-bottom: 2px solid #333;
            padding-bottom: 10px;
        }}
        .summary {{
            background: white;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .summary span {{
            margin-right: 20px;
            font-weight: bold;
        }}
        .verified {{ color: #22c55e; }}
        .failed {{ color: #ef4444; }}
        .uncertain {{ color: #eab308; }}

        .proposition {{
            background: white;
            padding: 20px;
            margin-bottom: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            border-left: 4px solid #ccc;
        }}
        .proposition.verified {{ border-left-color: #22c55e; }}
        .proposition.failed {{ border-left-color: #ef4444; }}
        .proposition.uncertain {{ border-left-color: #eab308; }}

        .icon {{
            font-size: 24px;
            float: right;
            margin-left: 10px;
        }}
        .prop-type {{
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
            margin-bottom: 5px;
        }}
        .prop-text {{
            font-size: 16px;
            line-height: 1.5;
            margin-bottom: 10px;
        }}
        .citations {{
            font-size: 14px;
            color: #555;
            margin-bottom: 10px;
        }}
        .citation {{
            background: #f0f0f0;
            padding: 2px 6px;
            border-radius: 3px;
            margin-right: 5px;
            display: inline-block;
            margin-bottom: 3px;
        }}
        .explanation {{
            font-size: 14px;
            color: #666;
            font-style: italic;
            padding-top: 10px;
            border-top: 1px solid #eee;
        }}
        .page-info {{
            font-size: 12px;
            color: #888;
        }}
    </style>
</head>
<body>
    <h1>Citation Validation Report</h1>
    <p><strong>Brief:</strong> {html.escape(brief_name)}</p>

    <div class="summary">
        <span class="verified">✓ Verified: {verified}</span>
        <span class="failed">✗ Failed: {failed}</span>
        <span class="uncertain">? Uncertain: {uncertain}</span>
        <span>Total: {len(validations)}</span>
    </div>
'''

    for i, v in enumerate(validations, 1):
        result_class = v.result.value
        if v.result == ValidationResult.VERIFIED:
            icon = '✓'
        elif v.result == ValidationResult.FAILED:
            icon = '✗'
        else:
            icon = '?'

        # Format citations
        cite_html = ''
        for c in v.citations[:3]:  # Show first 3 citations
            name = c.get('case_name') or 'Unknown'
            pin = c.get('pin_cite') or ''
            if pin:
                cite_html += f'<span class="citation">{html.escape(str(name))} at {html.escape(str(pin))}</span>'
            else:
                cite_html += f'<span class="citation">{html.escape(str(name))}</span>'

        page_info = f' (checked page {v.page_checked})' if v.page_checked else ''

        html_content += f'''
    <div class="proposition {result_class}">
        <span class="icon {result_class}">{icon}</span>
        <div class="prop-type">{html.escape(v.proposition_type)}</div>
        <div class="prop-text">{html.escape(v.proposition_text)}</div>
        <div class="citations">{cite_html}</div>
        <div class="explanation">{html.escape(v.explanation)}<span class="page-info">{page_info}</span></div>
    </div>
'''

    html_content += '''
</body>
</html>
'''

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)


def validate_brief(parsed_json_path: str, output_html_path: Optional[str] = None) -> List[PropositionValidation]:
    """
    Validate all propositions in a parsed brief.

    Args:
        parsed_json_path: Path to the _parsed.json file
        output_html_path: Path for the HTML report (default: same name with _validated.html)

    Returns:
        List of validation results
    """
    # Load parsed brief
    with open(parsed_json_path, 'r', encoding='utf-8') as f:
        parsed = json.load(f)

    propositions = parsed.get('propositions', [])

    print(f"Validating {len(propositions)} propositions...")

    validations = []
    for i, prop in enumerate(propositions, 1):
        print(f"  [{i}/{len(propositions)}] ", end='', flush=True)

        validation = validate_proposition(prop)
        validations.append(validation)

        # Print result indicator
        if validation.result == ValidationResult.VERIFIED:
            print("✓")
        elif validation.result == ValidationResult.FAILED:
            print("✗")
        else:
            print("?")

    # Generate HTML report
    if output_html_path is None:
        output_html_path = parsed_json_path.replace('_parsed.json', '_validated.html')

    brief_name = os.path.basename(parsed_json_path).replace('_parsed.json', '')
    generate_html_report(validations, brief_name, output_html_path)

    print(f"\nResults:")
    print(f"  Verified: {sum(1 for v in validations if v.result == ValidationResult.VERIFIED)}")
    print(f"  Failed: {sum(1 for v in validations if v.result == ValidationResult.FAILED)}")
    print(f"  Uncertain: {sum(1 for v in validations if v.result == ValidationResult.UNCERTAIN)}")
    print(f"\nReport: {output_html_path}")

    return validations


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_brief.py <parsed_json_path> [output_html_path]")
        print("\nExample:")
        print("  python validate_brief.py Sample_Briefs/005_parsed.json")
        sys.exit(1)

    parsed_json_path = sys.argv[1]
    output_html_path = sys.argv[2] if len(sys.argv) > 2 else None

    validate_brief(parsed_json_path, output_html_path)


if __name__ == "__main__":
    main()
