#!/usr/bin/env python3
"""
Extract legal propositions and their supporting citations from PDF briefs.

Core principle: A citation supports a proposition. The proposition is either:
1. The sentence/text BEFORE the citation (most common)
2. A parenthetical AFTER the citation (when there's a signal like "see")
3. A block quote that precedes the citation
"""

import re
import json
import sys
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass, asdict, field
from enum import Enum

import fitz  # PyMuPDF
from eyecite import get_citations, clean_text
from eyecite.models import (
    FullCaseCitation,
    ShortCaseCitation,
    SupraCitation,
    IdCitation,
)


class PropositionType(Enum):
    STATEMENT = "statement"
    QUOTE = "quote"
    BLOCK_QUOTE = "block_quote"
    PARENTHETICAL = "parenthetical"


@dataclass
class Citation:
    text: str
    citation_type: str
    case_name: Optional[str] = None
    start: int = 0
    end: int = 0
    refers_to: Optional[str] = None


@dataclass
class Proposition:
    text: str
    proposition_type: str
    citations: List[Citation] = field(default_factory=list)
    signal: Optional[str] = None


class BriefExtractor:
    """Extract propositions and citations from legal briefs."""

    # Citation signals - sorted by length (longest first) to match greedily
    SIGNALS = sorted([
        'see, e.g.,', 'see also', 'see generally', 'but see', 'but cf.',
        'see', 'cf.', 'compare', 'contra', 'e.g.,', 'accord', 'citing'
    ], key=len, reverse=True)

    # Parenthetical verbs that introduce propositions
    PAREN_VERBS = [
        'holding', 'stating', 'finding', 'noting', 'explaining', 'observing',
        'concluding', 'reasoning', 'emphasizing', 'recognizing', 'determining',
        'clarifying', 'reaffirming', 'affirming', 'reversing', 'quoting',
        'citing', 'discussing', 'describing', 'providing', 'defining',
        'establishing', 'requiring', 'permitting', 'allowing', 'prohibiting'
    ]

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)
        self.pages_text = self._extract_pages_text()

    def _extract_pages_text(self) -> List[Dict]:
        """Extract text page by page."""
        pages = []
        for i, page in enumerate(self.doc):
            pages.append({
                'page_num': i + 1,
                'text': page.get_text()
            })
        return pages

    def find_section(self, start_heading: str, end_headings: List[str]) -> Optional[Dict]:
        """Find a section between headings."""
        start_pattern = re.compile(
            rf'^\s*{re.escape(start_heading)}\s*$',
            re.IGNORECASE | re.MULTILINE
        )

        start_page = None
        end_page = None

        for i, page_data in enumerate(self.pages_text):
            if start_pattern.search(page_data['text']):
                start_page = i
                break

        if start_page is None:
            return None

        for end_heading in end_headings:
            end_pattern = re.compile(
                rf'^\s*{re.escape(end_heading)}\s*$',
                re.IGNORECASE | re.MULTILINE
            )
            for i in range(start_page, len(self.pages_text)):
                if end_pattern.search(self.pages_text[i]['text']):
                    end_page = i
                    break
            if end_page:
                break

        if end_page is None:
            end_page = len(self.pages_text) - 1

        section_text = ""
        for i in range(start_page, end_page + 1):
            page_text = self.pages_text[i]['text']

            if i == start_page:
                match = start_pattern.search(page_text)
                if match:
                    page_text = page_text[match.end():]

            if i == end_page:
                for end_heading in end_headings:
                    end_pattern = re.compile(
                        rf'^\s*{re.escape(end_heading)}\s*$',
                        re.IGNORECASE | re.MULTILINE
                    )
                    match = end_pattern.search(page_text)
                    if match:
                        page_text = page_text[:match.start()]
                        break

            section_text += page_text

        return {
            'text': section_text,
            'start_page': start_page + 1,
            'end_page': end_page + 1
        }

    def _get_case_name(self, cite) -> Optional[str]:
        """Extract clean case name from citation."""
        if not hasattr(cite, 'metadata') or not cite.metadata:
            return None
        if not hasattr(cite.metadata, 'plaintiff') or not cite.metadata.plaintiff:
            return None

        plaintiff = cite.metadata.plaintiff
        defendant = cite.metadata.defendant or ''

        # Clean plaintiff - remove preceding junk (e.g., "State—Irby")
        for sep in ['—', '–', '-']:
            if sep in plaintiff:
                parts = plaintiff.split(sep)
                # Take the last part if it looks like a name
                if len(parts[-1].strip()) > 2:
                    plaintiff = parts[-1].strip()
                    break

        # Clean defendant - remove trailing citation info
        if defendant and ',' in defendant:
            defendant = defendant.split(',')[0].strip()

        # Clean plaintiff - remove docket numbers
        if plaintiff and ',' in plaintiff:
            plaintiff = plaintiff.split(',')[0].strip()

        return f"{plaintiff} v. {defendant}"

    def extract_toa_citations(self) -> List[Dict]:
        """Extract case citations from Table/Index of Authorities."""
        section = self.find_section("Index of Authorities",
                                    ["Statutes", "Rules", "Statement", "Argument", "Reply"])
        if not section:
            section = self.find_section("Table of Authorities",
                                        ["Statutes", "Rules", "Statement", "Argument"])
        if not section:
            return []

        text = section['text']

        # Look for "Cases" subsection
        cases_match = re.search(r'Cases\s*\n(.*?)(?:Statutes|Rules|Other|$)',
                                text, re.DOTALL | re.IGNORECASE)
        if cases_match:
            text = cases_match.group(1)

        citations = get_citations(clean_text(text, ['all_whitespace', 'underscores']))

        toa_cites = []
        for cite in citations:
            if isinstance(cite, FullCaseCitation):
                case_name = self._get_case_name(cite)
                toa_cites.append({
                    'case_name': case_name,
                    'volume': cite.groups.get('volume', ''),
                    'reporter': cite.groups.get('reporter', ''),
                    'page': cite.groups.get('page', ''),
                })

        return toa_cites

    def _find_signal_before(self, text: str, pos: int) -> Optional[Tuple[str, int]]:
        """
        Find citation signal immediately before position.
        Returns (signal, start_of_signal) or None.
        """
        # Look at the 30 chars before the citation
        lookback = min(pos, 30)
        preceding = text[pos - lookback:pos].rstrip()

        for signal in self.SIGNALS:
            if preceding.lower().endswith(signal.lower()):
                signal_start = pos - lookback + len(preceding) - len(signal)
                return (signal, signal_start)

        return None

    def _find_parenthetical_after(self, text: str, pos: int) -> Optional[Tuple[str, int, int]]:
        """
        Find explanatory parenthetical after citation.
        Returns (content, start, end) or None.
        """
        # Look for opening paren within 50 chars
        search_text = text[pos:pos + 50]
        paren_match = re.match(r'\s*\(', search_text)

        if not paren_match:
            return None

        paren_start = pos + paren_match.end() - 1  # Position of '('

        # Check if this is an explanatory parenthetical (starts with verb)
        after_paren = text[paren_start + 1:paren_start + 50].lstrip()

        is_explanatory = False
        for verb in self.PAREN_VERBS:
            if after_paren.lower().startswith(verb):
                is_explanatory = True
                break

        if not is_explanatory:
            return None

        # Find the matching close paren
        depth = 1
        i = paren_start + 1
        while i < len(text) and depth > 0:
            if text[i] == '(':
                depth += 1
            elif text[i] == ')':
                depth -= 1
            i += 1

        if depth != 0:
            return None

        paren_end = i
        content = text[paren_start + 1:paren_end - 1].strip()

        return (content, paren_start, paren_end)

    def _find_preceding_text_unit(self, text: str, cite_start: int,
                                   signal_start: Optional[int] = None) -> str:
        """
        Find the text unit (sentence or clause) that precedes the citation.

        This is the core proposition extraction logic.
        """
        # Start position is either the signal start or the citation start
        end_pos = signal_start if signal_start is not None else cite_start

        # Look back up to 2000 chars
        lookback_start = max(0, end_pos - 2000)
        search_text = text[lookback_start:end_pos]

        # Find sentence boundaries working backwards
        # A sentence ends with . ! ? followed by whitespace and capital letter
        # But NOT abbreviations like "U.S." "v." "S.W.2d" etc.

        best_boundary = 0  # Default to start of search text

        i = len(search_text) - 1
        while i >= 0:
            char = search_text[i]

            if char in '.!?':
                # Check what follows
                following = search_text[i + 1:].lstrip()

                # If followed by capital letter or quote+capital, might be sentence end
                if following and (following[0].isupper() or
                                  (following[0] in '"\'""\'' and len(following) > 1 and following[1].isupper())):

                    # Check if this is an abbreviation
                    if not self._is_abbreviation(search_text, i):
                        # Found a sentence boundary
                        best_boundary = i + 1
                        break

            i -= 1

        # Extract the proposition text
        proposition = search_text[best_boundary:].strip()

        # Clean up leading punctuation/whitespace
        proposition = re.sub(r'^[\s.,;:\-–—]+', '', proposition)

        # Strip any leading citation text from prior citations
        proposition = self._strip_leading_citations(proposition)

        return proposition

    def _strip_leading_citations(self, text: str) -> str:
        """
        Strip leading citation text that bleeds from prior citations.

        Handles patterns like:
        - "Id. at 91; [actual proposition]"
        - "Garcia, 792 S.W.2d at 91–92; [actual proposition]"
        - Short case cites: "Brown, 50 S.W.3d at 100; [actual proposition]"
        """
        # Keep stripping leading citations until none found
        changed = True
        while changed:
            changed = False
            original = text

            # Pattern 1: Id. citations with optional pin cite
            # "Id." or "Id. at 91" or "Id. at 91–92"
            id_pattern = re.compile(
                r'^Id\.(?:\s+at\s+\d+(?:[–-]\d+)?)?[;,.\s]*',
                re.IGNORECASE
            )
            text = id_pattern.sub('', text).strip()

            # Pattern 2: Short case cite (CaseName, Vol Reporter at Page)
            # "Brown, 50 S.W.3d at 100;"
            short_cite_pattern = re.compile(
                r'^[A-Z][a-z]+(?:\s+v\.\s+[A-Z][a-z]+)?,\s*'
                r'\d+\s+[A-Z][a-z.]+(?:\d+[a-z]*)\s+at\s+\d+(?:[–-]\d+)?[;,.\s]*',
                re.IGNORECASE
            )
            text = short_cite_pattern.sub('', text).strip()

            # Pattern 3: Full case cite at start
            # "Garcia, 792 S.W.2d at 91–92; In re..."
            full_cite_pattern = re.compile(
                r'^[A-Z][a-z]+,\s*\d+\s+[A-Z]\.?[A-Za-z.]+\d*\s+(?:at\s+)?\d+(?:[–-]\d+)?[;,.\s]*',
                re.IGNORECASE
            )
            text = full_cite_pattern.sub('', text).strip()

            # Pattern 4: Supra citations
            # "Brown, supra, at 100;"
            supra_pattern = re.compile(
                r'^[A-Z][a-z]+,\s*supra(?:,?\s+at\s+\d+(?:[–-]\d+)?)?[;,.\s]*',
                re.IGNORECASE
            )
            text = supra_pattern.sub('', text).strip()

            # Pattern 5: Citation connectors/signals at start
            # "see" "accord" "but see" etc. when they're orphaned
            connector_pattern = re.compile(
                r'^(?:see\s+also|see|accord|cf\.|but\s+see|e\.g\.,?)[;,.\s]*$',
                re.IGNORECASE
            )
            if connector_pattern.match(text):
                text = ''

            # Pattern 6: Orphaned "and", "or"
            text = re.sub(r'^(?:and|or)[;,.\s]+', '', text, flags=re.IGNORECASE).strip()

            if text != original:
                changed = True

        return text

    def _is_abbreviation(self, text: str, period_pos: int) -> bool:
        """
        Check if the period at period_pos is part of an abbreviation.
        """
        # Get the "word" ending at this period
        start = period_pos
        while start > 0 and (text[start - 1].isalnum() or text[start - 1] in '.-'):
            start -= 1

        word = text[start:period_pos + 1].lower()

        # Common legal abbreviations
        abbrevs = {
            'v.', 'vs.', 'inc.', 'ltd.', 'corp.', 'co.', 'no.', 'nos.',
            'app.', 'crim.', 'civ.', 'ct.', 'dist.', 'supp.', 'rev.',
            'stat.', 'ann.', 'gen.', 'ass.', 'ch.', 'cl.', 'div.',
            'ed.', 'ex.', 'fed.', 'gov.', 'jr.', 'sr.', 'mr.', 'mrs.',
            'ms.', 'dr.', 'prof.', 'rep.', 'sen.', 'st.', 'tex.', 'cal.',
            'n.y.', 'fla.', 'u.s.', 's.w.', 'n.w.', 's.e.', 'n.e.',
            'so.', 'f.', 'l.', 'r.', 's.', 'w.', 'p.', 'proc.', 'evid.',
            'art.', 'n.', 'id.', 'e.g.', 'cf.', 'i.e.', 'et.', 'al.',
            'cir.', 'pet.', "ref'd", "dism'd", 'op.', 'cert.', 'reh.',
            'aff.', 'mem.', 'op.',
            # Reporters
            's.w.2d', 's.w.3d', 'n.w.2d', 'n.e.2d', 's.e.2d', 'so.2d',
            'so.3d', 'f.2d', 'f.3d', 'f.4th', 'u.s.', 'l.ed.', 'l.ed.2d',
            's.ct.', 'tex.app.', 'tex.crim.app.',
        }

        if word in abbrevs:
            return True

        # Check for reporter patterns like "3d" after a number
        if re.match(r'\d+[a-z]*\.', word):
            return True

        # Single letter followed by period is usually abbreviation
        if len(word) == 2 and word[0].isalpha():
            return True

        # Check for state abbreviations (two capitals + period)
        if len(word) == 3 and word[:2].isupper():
            return True

        return False

    def extract_argument_propositions(self) -> List[Proposition]:
        """Extract propositions and citations from Argument section."""
        # Try different section headings
        section = None
        for start in ["Reply Argument", "Argument", "ARGUMENT", "REPLY ARGUMENT"]:
            section = self.find_section(start, ["Conclusion", "Prayer", "CONCLUSION", "PRAYER"])
            if section:
                break

        if not section:
            return []

        text = section['text']
        cleaned_text = clean_text(text, ['all_whitespace', 'underscores'])

        citations = get_citations(cleaned_text)
        if not citations:
            return []

        propositions = []
        last_full_citation_name = None
        last_cite_end = 0

        for cite in citations:
            start, end = cite.span()

            # Get full span for case citations
            if isinstance(cite, FullCaseCitation):
                if cite.full_span_start is not None:
                    start = cite.full_span_start
                if cite.full_span_end is not None:
                    end = cite.full_span_end

            citation_text = cleaned_text[start:end]

            # Get case name and track for Id. references
            case_name = self._get_case_name(cite)
            if isinstance(cite, FullCaseCitation) and case_name:
                last_full_citation_name = case_name

            # Check for signal before citation
            signal_result = self._find_signal_before(cleaned_text, start)
            signal = signal_result[0] if signal_result else None
            signal_start = signal_result[1] if signal_result else None

            # Check for parenthetical after citation
            paren_result = self._find_parenthetical_after(cleaned_text, end)

            # Determine proposition text and type
            if signal and paren_result:
                # Signal + parenthetical: proposition is in the parenthetical
                prop_text = paren_result[0]
                prop_type = PropositionType.PARENTHETICAL.value
                cite_end_for_tracking = paren_result[2]
            else:
                # Proposition is the text before the citation
                prop_text = self._find_preceding_text_unit(
                    cleaned_text, start, signal_start
                )
                cite_end_for_tracking = end

                # Determine type based on content
                if self._has_substantial_quote(prop_text):
                    prop_type = PropositionType.QUOTE.value
                elif len(prop_text) > 300:
                    prop_type = PropositionType.BLOCK_QUOTE.value
                else:
                    prop_type = PropositionType.STATEMENT.value

            # Create citation object
            cit = Citation(
                text=citation_text,
                citation_type=self._get_citation_type(cite),
                case_name=case_name,
                start=start,
                end=end,
                refers_to=last_full_citation_name if isinstance(cite, IdCitation) else None,
            )

            # Create proposition
            prop = Proposition(
                text=prop_text,
                proposition_type=prop_type,
                citations=[cit],
                signal=signal,
            )

            propositions.append(prop)
            last_cite_end = cite_end_for_tracking

        return propositions

    def _has_substantial_quote(self, text: str) -> bool:
        """Check if text contains a substantial quotation."""
        # Look for quoted text of at least 20 characters
        quote_pattern = r'["\u201c][^"\u201d]{20,}["\u201d]'
        return bool(re.search(quote_pattern, text))

    def _get_citation_type(self, cite) -> str:
        if isinstance(cite, FullCaseCitation):
            return "full_case"
        elif isinstance(cite, ShortCaseCitation):
            return "short_case"
        elif isinstance(cite, IdCitation):
            return "id"
        elif isinstance(cite, SupraCitation):
            return "supra"
        return "unknown"

    def extract_all(self) -> Dict:
        """Extract all propositions and citations."""
        toa_citations = self.extract_toa_citations()
        propositions = self.extract_argument_propositions()

        # Get unique case names
        toa_cases = set(c['case_name'] for c in toa_citations if c['case_name'])
        argument_cases = set()
        for prop in propositions:
            for cit in prop.citations:
                if cit.case_name:
                    argument_cases.add(cit.case_name)

        return {
            'toa_citations': toa_citations,
            'propositions': [asdict(p) for p in propositions],
            'summary': {
                'toa_case_count': len(toa_cases),
                'argument_unique_cases': len(argument_cases),
                'total_citations': len(propositions),
                'toa_cases': sorted(list(toa_cases)),
                'argument_cases': sorted(list(argument_cases)),
            }
        }

    def close(self):
        self.doc.close()


def consolidate_propositions(propositions: List[Dict]) -> List[Dict]:
    """
    Consolidate propositions that share the same text (string cites).
    """
    consolidated = {}

    for prop in propositions:
        text = prop['text'].strip()
        if not text or len(text) < 10:
            continue

        key = text[:200]  # Use first 200 chars as key

        if key in consolidated:
            # Add citations to existing proposition
            consolidated[key]['citations'].extend(prop['citations'])
        else:
            consolidated[key] = {
                'proposition': text,
                'type': prop['proposition_type'],
                'citations': list(prop['citations']),
                'signal': prop.get('signal'),
            }

    return list(consolidated.values())


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_propositions.py <pdf_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]

    extractor = BriefExtractor(pdf_path)
    try:
        results = extractor.extract_all()

        # Create clean output
        props = consolidate_propositions(results['propositions'])

        clean_output = {
            'brief_info': {
                'toa_case_count': results['summary']['toa_case_count'],
                'argument_case_count': results['summary']['argument_unique_cases'],
                'cases_match': set(results['summary']['toa_cases']) == set(results['summary']['argument_cases']),
            },
            'cases_cited': results['summary']['toa_cases'],
            'propositions': props,
        }

        # Print summary
        print(f"\n=== {pdf_path} ===\n")

        print("Cases cited:")
        for case in clean_output['cases_cited']:
            print(f"  - {case}")

        print(f"\nSummary:")
        print(f"  TOA cases: {clean_output['brief_info']['toa_case_count']}")
        print(f"  Argument cases: {clean_output['brief_info']['argument_case_count']}")
        print(f"  Cases match: {clean_output['brief_info']['cases_match']}")
        print(f"  Propositions: {len(clean_output['propositions'])}")

        print("\nSample propositions:")
        for i, prop in enumerate(clean_output['propositions'][:10], 1):
            print(f"\n{i}. [{prop['type']}]")
            if prop.get('signal'):
                print(f"   Signal: {prop['signal']}")
            text = prop['proposition'][:250]
            if len(prop['proposition']) > 250:
                text += "..."
            print(f"   {text}")
            for cit in prop['citations'][:3]:
                name = cit.get('case_name') or cit.get('text', '')[:50]
                print(f"   -> {name}")
            if len(prop['citations']) > 3:
                print(f"   -> ... and {len(prop['citations']) - 3} more")

        # Save JSON
        output_file = pdf_path.replace('.pdf', '_extracted.json').replace('.PDF', '_extracted.json')
        with open(output_file, 'w') as f:
            json.dump(clean_output, f, indent=2, ensure_ascii=False)
        print(f"\nOutput: {output_file}")

    finally:
        extractor.close()


if __name__ == "__main__":
    main()
