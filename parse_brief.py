#!/usr/bin/env python3
"""
Parse legal briefs into structured JSON.

Structure:
{
  "argument": {
    "paragraphs": [
      {
        "type": "body",
        "sentences": [
          {
            "text": "The court erred.",
            "citations": [
              {
                "text": "Smith v. State, 123 S.W.3d 456 (Tex. 2020)",
                "case_name": "Smith v. State",
                "volume": "123",
                "reporter": "S.W.3d",
                "page": "456",
                "type": "full_case",
                "span": [15, 55],
                "signal": "see",
                "parenthetical": "holding that..."
              }
            ]
          }
        ]
      },
      {
        "type": "block_quote",
        "intro": "As the Court explained:",
        "text": "Evidence must be considered...",
        "citations": [...]
      }
    ]
  }
}
"""

import re
import json
import sys
import os
import requests
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from enum import Enum

import fitz  # PyMuPDF
from eyecite import get_citations, clean_text
from eyecite.models import (
    FullCaseCitation,
    ShortCaseCitation,
    SupraCitation,
    IdCitation,
)


# Legal abbreviations that don't end sentences
LEGAL_ABBREVS = {
    'v.', 'vs.', 'inc.', 'ltd.', 'corp.', 'co.', 'no.', 'nos.',
    'app.', 'crim.', 'civ.', 'ct.', 'dist.', 'supp.', 'rev.',
    'stat.', 'ann.', 'gen.', 'ass.', 'ch.', 'cl.', 'div.',
    'ed.', 'ex.', 'fed.', 'gov.', 'jr.', 'sr.', 'mr.', 'mrs.',
    'ms.', 'dr.', 'prof.', 'rep.', 'sen.', 'st.', 'tex.', 'cal.',
    'n.y.', 'fla.', 'u.s.', 's.w.', 'n.w.', 's.e.', 'n.e.',
    'so.', 'f.', 'l.', 'r.', 's.', 'w.', 'p.', 'proc.', 'evid.',
    'art.', 'n.', 'e.g.', 'cf.', 'i.e.', 'et.', 'al.',
    'cir.', 'pet.', 'op.', 'cert.', 'reh.', 'aff.', 'mem.',
    's.w.2d', 's.w.3d', 'n.w.2d', 'n.e.2d', 's.e.2d', 'so.2d',
    'so.3d', 'f.2d', 'f.3d', 'f.4th', 'l.ed.', 'l.ed.2d', 's.ct.',
}

# Citation signals
SIGNALS = [
    'see, e.g.,', 'see also', 'see generally', 'but see', 'but cf.',
    'see', 'cf.', 'compare', 'contra', 'e.g.,', 'accord', 'citing'
]
SIGNALS_SORTED = sorted(SIGNALS, key=len, reverse=True)

# Parenthetical verbs
PAREN_VERBS = [
    'holding', 'stating', 'finding', 'noting', 'explaining', 'observing',
    'concluding', 'reasoning', 'emphasizing', 'recognizing', 'determining',
    'clarifying', 'reaffirming', 'affirming', 'reversing', 'quoting',
    'citing', 'discussing', 'describing', 'providing', 'defining',
]

# Wetslaw case law base directory
WETSLAW_BASE = "/mnt/wetslaw/data/case.law"

# Reporter to directory slug mapping
REPORTER_SLUGS = {
    # South Western Reporter
    'S.W.': 'sw',
    'S.W.2d': 'sw2d',
    'S.W.3d': 'sw3d',
    # Other regional reporters
    'N.W.': 'nw',
    'N.W.2d': 'nw2d',
    'N.E.': 'ne',
    'N.E.2d': 'ne2d',
    'N.E.3d': 'ne3d',
    'S.E.': 'se',
    'S.E.2d': 'se2d',
    'So.': 'so',
    'So.2d': 'so2d',
    'So.3d': 'so3d',
    'P.': 'p',
    'P.2d': 'p2d',
    'P.3d': 'p3d',
    # Federal reporters
    'F.': 'f',
    'F.2d': 'f2d',
    'F.3d': 'f3d',
    'F.4th': 'f4th',
    'F. Supp.': 'f-supp',
    'F. Supp. 2d': 'f-supp-2d',
    'F. Supp. 3d': 'f-supp-3d',
    # Supreme Court
    'U.S.': 'us',
    'S. Ct.': 's-ct',
    'L. Ed.': 'l-ed',
    'L. Ed. 2d': 'l-ed-2d',
    # Texas specific
    'Tex.': 'tex',
    'Tex. Crim.': 'tex-crim',
    'Tex. Crim. App.': 'tex-crim',
    'Tex. App.': 'tex-ct-app',
    'Tex. Civ. App.': 'tex-civ-app',
}


def get_reporter_slug(reporter: str) -> Optional[str]:
    """Convert a reporter name to its directory slug."""
    return REPORTER_SLUGS.get(reporter)


def get_local_case_paths(volume: str, reporter: str, page: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Get the local file paths for a case.

    Returns:
        Tuple of (json_path, html_path), either may be None if reporter not supported
    """
    slug = get_reporter_slug(reporter)
    if not slug:
        return None, None

    # Pad page to 4 digits
    page_padded = page.zfill(4)

    json_path = f"{WETSLAW_BASE}/{slug}/{volume}/json/{page_padded}-01.json"
    html_path = f"{WETSLAW_BASE}/{slug}/{volume}/html/{page_padded}-01.html"

    return json_path, html_path


def check_local_case_exists(volume: str, reporter: str, page: str) -> Tuple[bool, bool]:
    """
    Check if local case files exist.

    Returns:
        Tuple of (json_exists, html_exists)
    """
    json_path, html_path = get_local_case_paths(volume, reporter, page)

    json_exists = json_path and os.path.exists(json_path)
    html_exists = html_path and os.path.exists(html_path)

    return json_exists, html_exists


class CourtListenerClient:
    """Client for CourtListener API with caching."""

    SEARCH_URL = "https://www.courtlistener.com/api/rest/v4/search/"

    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token or os.environ.get('COURTLISTENER_API_TOKEN')
        self._cache: Dict[str, Optional[Dict]] = {}

    def lookup_citation(self, volume: str, reporter: str, page: str) -> Optional[Dict[str, Any]]:
        """Look up a citation and return the CourtListener search result."""
        if not self.api_token:
            return None

        cache_key = f"{volume}|{reporter}|{page}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Build exact citation string with quotes
        cite_str = f'"{volume} {reporter} {page}"'

        try:
            response = requests.get(
                self.SEARCH_URL,
                headers={"Authorization": f"Token {self.api_token}"},
                params={"type": "o", "citation": cite_str},
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('count', 0) > 0 and data.get('results'):
                    result = data['results'][0]
                    self._cache[cache_key] = result
                    return result

            self._cache[cache_key] = None
            return None

        except (requests.RequestException, json.JSONDecodeError):
            self._cache[cache_key] = None
            return None

    def batch_lookup(self, citations: List[Tuple[str, str, str]]) -> int:
        """
        Look up multiple citations (one request per citation, but with caching).

        Args:
            citations: List of (volume, reporter, page) tuples

        Returns:
            Number of citations found
        """
        if not self.api_token:
            return 0

        found = 0
        for vol, rep, page in citations:
            cache_key = f"{vol}|{rep}|{page}"
            if cache_key not in self._cache:
                result = self.lookup_citation(vol, rep, page)
                if result:
                    found += 1

        return found

    def get_case_name(self, volume: str, reporter: str, page: str) -> Optional[str]:
        """Get just the case name from CourtListener."""
        record = self.lookup_citation(volume, reporter, page)
        if record:
            return record.get('caseName')
        return None

    def get_cluster(self, cluster_id: int) -> Optional[Dict[str, Any]]:
        """Fetch full cluster data from CourtListener."""
        if not self.api_token:
            return None

        try:
            response = requests.get(
                f"https://www.courtlistener.com/api/rest/v4/clusters/{cluster_id}/",
                headers={"Authorization": f"Token {self.api_token}"},
                timeout=30,
            )
            if response.status_code == 200:
                return response.json()
        except requests.RequestException:
            pass
        return None

    def get_opinion(self, opinion_id: int) -> Optional[Dict[str, Any]]:
        """Fetch full opinion data from CourtListener."""
        if not self.api_token:
            return None

        try:
            response = requests.get(
                f"https://www.courtlistener.com/api/rest/v4/opinions/{opinion_id}/",
                headers={"Authorization": f"Token {self.api_token}"},
                timeout=30,
            )
            if response.status_code == 200:
                return response.json()
        except requests.RequestException:
            pass
        return None

    def download_case(self, volume: str, reporter: str, page: str) -> Tuple[bool, bool]:
        """
        Download case from CourtListener and save to wetslaw directory.

        Returns:
            Tuple of (json_saved, html_saved)
        """
        if not self.api_token:
            return False, False

        # First look up the case to get cluster_id
        record = self.lookup_citation(volume, reporter, page)
        if not record:
            return False, False

        cluster_id = record.get('cluster_id')
        if not cluster_id:
            return False, False

        # Get full cluster data
        cluster = self.get_cluster(cluster_id)
        if not cluster:
            return False, False

        # Get paths
        json_path, html_path = get_local_case_paths(volume, reporter, page)
        if not json_path or not html_path:
            return False, False

        # Ensure directories exist
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        os.makedirs(os.path.dirname(html_path), exist_ok=True)

        json_saved = False
        html_saved = False

        # Get opinions
        opinions_data = []
        html_parts = []
        sub_opinions = cluster.get('sub_opinions', [])

        for sub_op in sub_opinions:
            # sub_op is a URL like "https://www.courtlistener.com/api/rest/v4/opinions/123/"
            op_id = sub_op.rstrip('/').split('/')[-1]
            try:
                op_id = int(op_id)
                opinion = self.get_opinion(op_id)
                if opinion:
                    # Collect opinion text
                    op_text = opinion.get('plain_text') or ''
                    op_html = opinion.get('html_with_citations') or opinion.get('html') or ''
                    op_type = opinion.get('type', 'majority')

                    opinions_data.append({
                        'type': op_type,
                        'text': op_text,
                        'author': opinion.get('author_str', ''),
                    })

                    if op_html:
                        html_parts.append(op_html)
            except (ValueError, TypeError):
                continue

        # Build JSON in FLP-compatible format
        flp_json = {
            'id': cluster_id,
            'name': cluster.get('case_name_full') or cluster.get('case_name', ''),
            'name_abbreviation': cluster.get('case_name', ''),
            'decision_date': cluster.get('date_filed', ''),
            'docket_number': '',  # Not directly available
            'first_page': page,
            'last_page': '',
            'citations': [{'type': 'official', 'cite': f"{volume} {reporter} {page}"}],
            'court': {
                'name': '',
                'name_abbreviation': '',
            },
            'casebody': {
                'judges': cluster.get('judges', ''),
                'parties': cluster.get('case_name_full', ''),
                'opinions': opinions_data,
                'attorneys': cluster.get('attorneys', ''),
            },
            'source': 'courtlistener',
            'cluster_id': cluster_id,
            'absolute_url': cluster.get('absolute_url', ''),
        }

        # Save JSON
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(flp_json, f, indent=2, ensure_ascii=False)
            json_saved = True
        except (IOError, OSError):
            pass

        # Build and save HTML
        if html_parts:
            html_content = f'''<section class="casebody" data-case-id="{cluster_id}" data-firstpage="{page}">
  <section class="head-matter">
    <h4 class="parties">{cluster.get('case_name_full', cluster.get('case_name', ''))}</h4>
    <p class="court">{cluster.get('court', '')}</p>
    <p class="decisiondate">{cluster.get('date_filed', '')}</p>
  </section>
  <article class="opinion" data-type="majority">
    {''.join(html_parts)}
  </article>
</section>'''
            try:
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                html_saved = True
            except (IOError, OSError):
                pass

        return json_saved, html_saved


def normalize_case_name(name: str) -> str:
    """
    Normalize a case name for comparison.

    Handles variations like:
    - "Roderick Beham v. State" -> "Beham v. State"
    - "Debra Dando v. Joan Yukins, Warden" -> "Dando v. Yukins"
    """
    if not name:
        return ""

    # Split on " v. " or " v "
    parts = re.split(r'\s+v\.?\s+', name, maxsplit=1)
    if len(parts) != 2:
        return name.strip()

    plaintiff, defendant = parts

    # For plaintiff: take last word (the surname)
    # But preserve "United States", "State", etc.
    plaintiff_words = plaintiff.strip().split()
    if len(plaintiff_words) > 1:
        # Check if it's a government entity
        if plaintiff_words[0].lower() in ('united', 'people', 'state', 'commonwealth', 'in'):
            # Keep as-is
            pass
        else:
            # Take last word only
            plaintiff = plaintiff_words[-1]

    # For defendant: take first substantive word (the surname)
    # Remove trailing titles like "Warden", court names, etc.
    defendant = defendant.split(',')[0].strip()
    defendant_words = defendant.strip().split()
    if len(defendant_words) > 1:
        if defendant_words[0].lower() in ('the', 'state', 'united', 'people', 'commonwealth'):
            # Keep as-is for "The State", "United States", etc.
            pass
        else:
            # Take last word (surname)
            defendant = defendant_words[-1]

    return f"{plaintiff} v. {defendant}"


def cases_match(set1: set, set2: set) -> bool:
    """Check if two sets of case names match after normalization."""
    norm1 = {normalize_case_name(c) for c in set1}
    norm2 = {normalize_case_name(c) for c in set2}
    return norm1 == norm2


# Global CourtListener client (initialized lazily)
_cl_client: Optional[CourtListenerClient] = None

def get_cl_client(api_token: Optional[str] = None) -> CourtListenerClient:
    """Get or create the CourtListener client."""
    global _cl_client
    if _cl_client is None:
        _cl_client = CourtListenerClient(api_token)
    return _cl_client


@dataclass
class Citation:
    text: str
    case_name: Optional[str]
    volume: Optional[str]
    reporter: Optional[str]
    page: Optional[str]
    pin_cite: Optional[str]
    cite_type: str  # full_case, short_case, id, supra
    span: Tuple[int, int]  # position within sentence
    signal: Optional[str] = None
    parenthetical: Optional[str] = None
    refers_to: Optional[str] = None  # for id. citations
    cl_record: Optional[Dict[str, Any]] = None  # Full CourtListener record


@dataclass
class Sentence:
    text: str
    citations: List[Citation] = field(default_factory=list)


@dataclass
class Paragraph:
    para_type: str  # "body" or "block_quote"
    sentences: List[Sentence] = field(default_factory=list)
    # For block quotes:
    intro: Optional[str] = None  # prefatory text before quote
    quote_text: Optional[str] = None  # the quoted text


class BriefParser:
    """Parse a legal brief into structured JSON."""

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)
        self._body_margin = None
        self._block_indent = None

    def prefetch_citations(self, cl_client: CourtListenerClient) -> int:
        """
        Pre-fetch all citations from the document via CourtListener batch API.

        This does a quick pass through the document to find all citations,
        then batches them to CourtListener in one request.

        Returns:
            Number of citations found in CourtListener
        """
        # Get all text from document
        full_text = ""
        for page in self.doc:
            full_text += page.get_text() + "\n"

        # Normalize and extract citations with eyecite
        normalized = self.normalize_for_eyecite(full_text)
        eyecite_cites = get_citations(normalized)

        # Collect unique (volume, reporter, page) tuples
        cite_tuples = set()
        for cite in eyecite_cites:
            if hasattr(cite, 'groups'):
                vol = cite.groups.get('volume')
                rep = cite.groups.get('reporter')
                page = cite.groups.get('page')
                if vol and rep and page:
                    cite_tuples.add((vol, rep, page))

        # Batch lookup
        if cite_tuples:
            return cl_client.batch_lookup(list(cite_tuples))
        return 0

    def normalize_for_eyecite(self, text: str) -> str:
        """Normalize text for eyecite processing."""
        # Convert em-dashes and en-dashes to spaced hyphens
        # This prevents eyecite from joining words across dashes
        text = re.sub(r'[—–]', ' -- ', text)
        return clean_text(text, ['all_whitespace', 'underscores'])

    def find_section_by_prefix(self, start_prefix: str, end_headings: List[str]) -> Optional[Dict]:
        """Find a section where heading starts with prefix (e.g., 'Argument on sole ground:')."""
        start_pattern = re.compile(
            rf'^\s*{re.escape(start_prefix)}\b[^\n]*$',
            re.IGNORECASE | re.MULTILINE
        )

        start_page = None
        end_page = None

        for i in range(len(self.doc)):
            page = self.doc[i]
            text = page.get_text()
            match = start_pattern.search(text)
            if match:
                start_page = i
                break

        if start_page is None:
            return None

        for end_heading in end_headings:
            end_pattern = re.compile(
                rf'^\s*{re.escape(end_heading)}\s*$',
                re.IGNORECASE | re.MULTILINE
            )
            for i in range(start_page, len(self.doc)):
                if end_pattern.search(self.doc[i].get_text()):
                    end_page = i
                    break
            if end_page:
                break

        if end_page is None:
            end_page = len(self.doc) - 1

        return {
            'start_page': start_page,
            'end_page': end_page,
            'start_pattern': start_pattern,
            'end_headings': end_headings,
        }

    def find_section(self, start_heading: str, end_headings: List[str]) -> Optional[Dict]:
        """Find a section between headings."""
        start_pattern = re.compile(
            rf'^\s*{re.escape(start_heading)}\s*$',
            re.IGNORECASE | re.MULTILINE
        )

        start_page = None
        end_page = None

        for i in range(len(self.doc)):
            page = self.doc[i]
            text = page.get_text()
            if start_pattern.search(text):
                start_page = i
                break

        if start_page is None:
            return None

        for end_heading in end_headings:
            end_pattern = re.compile(
                rf'^\s*{re.escape(end_heading)}\s*$',
                re.IGNORECASE | re.MULTILINE
            )
            for i in range(start_page, len(self.doc)):
                if end_pattern.search(self.doc[i].get_text()):
                    end_page = i
                    break
            if end_page:
                break

        if end_page is None:
            end_page = len(self.doc) - 1

        return {
            'start_page': start_page,
            'end_page': end_page,
            'start_pattern': start_pattern,
            'end_headings': end_headings,
        }

    def _calculate_margins(self, start_page: int, end_page: int):
        """Calculate body margin and block quote indent from page layout."""
        from collections import Counter
        x0_counts = Counter()

        for page_num in range(start_page, end_page + 1):
            page = self.doc[page_num]
            blocks = page.get_text("blocks")

            for block in blocks:
                x0, y0, x1, y1, text, block_no, block_type = block
                if block_type == 0 and text.strip() and len(text.strip()) > 30:
                    x0_rounded = round(x0)
                    x0_counts[x0_rounded] += 1

        most_common = x0_counts.most_common(3)
        if len(most_common) >= 2:
            margins = sorted([m[0] for m in most_common[:2]])
            self._body_margin = margins[0]
            self._block_indent = margins[1]
        elif len(most_common) == 1:
            self._body_margin = most_common[0][0]
            self._block_indent = self._body_margin + 36  # ~0.5 inch

    def extract_paragraphs(self, section: Dict) -> List[Dict]:
        """Extract paragraphs from section, identifying block quotes by indentation."""
        start_page = section['start_page']
        end_page = section['end_page']
        start_pattern = section['start_pattern']
        end_headings = section['end_headings']

        self._calculate_margins(start_page, end_page)

        # First pass: collect all blocks with their positions
        all_blocks = []
        in_section = False

        for page_num in range(start_page, end_page + 1):
            page = self.doc[page_num]
            blocks = page.get_text("blocks")
            page_text = page.get_text()

            # Check if we've hit end heading
            for end_heading in end_headings:
                end_pattern = re.compile(
                    rf'^\s*{re.escape(end_heading)}\s*$',
                    re.IGNORECASE | re.MULTILINE
                )
                if end_pattern.search(page_text):
                    end_y = self._find_text_y(page, end_heading)
                    if end_y:
                        blocks = [b for b in blocks if b[1] < end_y]

            # Skip blocks before start heading on first page
            if page_num == start_page:
                heading_y = None
                if start_pattern.search(page_text):
                    for match in start_pattern.finditer(page_text):
                        heading_y = self._find_text_y(page, match.group().strip())
                        break
                if heading_y:
                    blocks = [b for b in blocks if b[1] > heading_y]
                in_section = True
            else:
                in_section = True

            if not in_section:
                continue

            for block in blocks:
                x0, y0, x1, y1, text, block_no, block_type = block

                if block_type != 0 or not text.strip():
                    continue

                # Skip headers/footers (far from body margin)
                if self._body_margin and abs(x0 - self._body_margin) > 100:
                    continue

                all_blocks.append({
                    'text': text.strip(),
                    'x0': x0,
                    'page': page_num + 1,
                })

        # Second pass: identify block quotes vs body paragraphs
        # Block quotes are 2+ consecutive blocks ALL at indented level (>25pt from body)
        # First-line indents are single blocks at moderate indent (~20-40pt) followed by body
        paragraphs = []
        i = 0

        while i < len(all_blocks):
            block = all_blocks[i]
            indent = block['x0'] - self._body_margin if self._body_margin else 0

            # Check if this starts a block quote (significantly indented, 25+ pt)
            if indent > 25:
                # Look ahead to see if next blocks are also indented
                quote_blocks = [block]
                j = i + 1
                while j < len(all_blocks):
                    next_indent = all_blocks[j]['x0'] - self._body_margin if self._body_margin else 0
                    if next_indent > 25:
                        quote_blocks.append(all_blocks[j])
                        j += 1
                    else:
                        break

                # If 2+ consecutive indented blocks, it's a block quote
                if len(quote_blocks) >= 2:
                    paragraphs.append({
                        'type': 'block_quote',
                        'blocks': quote_blocks,
                    })
                    i = j
                    continue
                # Otherwise, single indented block - might be first-line indent
                # Fall through to body handling

            # Body paragraph: collect blocks until we hit a definite block quote
            body_blocks = [block]
            j = i + 1
            while j < len(all_blocks):
                next_block = all_blocks[j]
                next_indent = next_block['x0'] - self._body_margin if self._body_margin else 0

                # Check if next block starts a block quote sequence
                if next_indent > 25:
                    # Look ahead to see if it's really a block quote
                    k = j + 1
                    is_block_quote = False
                    while k < len(all_blocks):
                        kth_indent = all_blocks[k]['x0'] - self._body_margin if self._body_margin else 0
                        if kth_indent > 25:
                            is_block_quote = True
                            break
                        elif kth_indent <= 10:
                            # Next block is body - this indented block is just first-line indent
                            break
                        k += 1

                    if is_block_quote:
                        break  # End body paragraph here

                body_blocks.append(next_block)
                j += 1

            paragraphs.append({
                'type': 'body',
                'blocks': body_blocks,
            })
            i = j

        return paragraphs

    def _find_text_y(self, page, text: str) -> Optional[float]:
        """Find y position of text on page."""
        results = page.search_for(text[:50])  # First 50 chars
        if results:
            return results[0].y0
        return None

    def segment_sentences(self, text: str) -> List[str]:
        """Segment text into sentences, respecting legal abbreviations."""
        sentences = []
        current = []
        i = 0

        while i < len(text):
            char = text[i]
            current.append(char)

            if char in '.!?':
                # Check if this is end of sentence
                # Look at what comes after
                rest = text[i+1:].lstrip()

                if not rest:
                    # End of text
                    sentences.append(''.join(current).strip())
                    current = []
                elif rest[0].isupper() or rest[0] in '"\u201c\u201d\u2018\u2019\'':
                    # Might be new sentence - check if abbreviation
                    word_before = self._get_word_ending_at(text, i)

                    # Check for multi-part abbreviations like U.S., S.W.2d, etc.
                    # If current word is single letter + period, check if next
                    # char would form a known abbreviation pattern
                    is_abbrev = word_before.lower() in LEGAL_ABBREVS

                    if not is_abbrev and len(word_before) == 2:
                        # Single letter + period (e.g., "U.")
                        # Check if followed by another letter + period (e.g., "S.")
                        if rest and len(rest) >= 2 and rest[0].isalpha() and rest[1] == '.':
                            # This is likely part of multi-letter abbreviation
                            combined = word_before + rest[0] + '.'
                            if combined.lower() in LEGAL_ABBREVS:
                                is_abbrev = True
                            # Also check common patterns like U.S., N.Y., S.W., N.E.
                            if word_before[0].upper() in 'UNSEW' and rest[0].upper() in 'SYEWTC':
                                is_abbrev = True

                    if not is_abbrev:
                        sentences.append(''.join(current).strip())
                        current = []

            i += 1

        if current:
            remaining = ''.join(current).strip()
            if remaining:
                sentences.append(remaining)

        return sentences

    def _get_word_ending_at(self, text: str, pos: int) -> str:
        """Get the word ending at position pos (including the char at pos)."""
        start = pos
        while start > 0 and (text[start-1].isalnum() or text[start-1] in '.-'):
            start -= 1
        return text[start:pos+1]

    def extract_citations_from_sentence(self, sentence: str,
                                         last_full_cite: Optional[str] = None,
                                         cl_client: Optional[CourtListenerClient] = None) -> Tuple[List[Citation], Optional[str]]:
        """Extract citations from a sentence."""
        # Normalize for eyecite
        normalized = self.normalize_for_eyecite(sentence)

        eyecite_cites = get_citations(normalized)
        citations = []
        new_last_full = last_full_cite

        for cite in eyecite_cites:
            start, end = cite.span()

            # Get full span for case citations
            if isinstance(cite, FullCaseCitation):
                if cite.full_span_start is not None:
                    start = cite.full_span_start
                if cite.full_span_end is not None:
                    end = cite.full_span_end

            cite_text = normalized[start:end]

            # Get volume/reporter/page
            volume = cite.groups.get('volume') if hasattr(cite, 'groups') else None
            reporter = cite.groups.get('reporter') if hasattr(cite, 'groups') else None
            page = cite.groups.get('page') if hasattr(cite, 'groups') else None
            pin_cite = None
            if hasattr(cite, 'metadata') and cite.metadata:
                pin_cite = getattr(cite.metadata, 'pin_cite', None)

            # Try CourtListener lookup first for full citations
            cl_record = None
            case_name = None
            if cl_client and volume and reporter and page:
                cl_record = cl_client.lookup_citation(volume, reporter, page)
                if cl_record:
                    case_name = cl_record.get('caseName')

            # Fall back to eyecite case name if CourtListener didn't find it
            if not case_name:
                case_name = self._get_case_name(cite)

            if isinstance(cite, FullCaseCitation) and case_name:
                new_last_full = case_name

            # Check for signal before citation
            signal = self._find_signal_before(normalized, start)

            # Check for parenthetical after citation
            parenthetical = self._find_parenthetical_after(normalized, end)

            # Determine citation type
            if isinstance(cite, FullCaseCitation):
                cite_type = 'full_case'
            elif isinstance(cite, ShortCaseCitation):
                cite_type = 'short_case'
            elif isinstance(cite, IdCitation):
                cite_type = 'id'
            elif isinstance(cite, SupraCitation):
                cite_type = 'supra'
            else:
                cite_type = 'unknown'

            citation = Citation(
                text=cite_text,
                case_name=case_name,
                volume=volume,
                reporter=reporter,
                page=page,
                pin_cite=pin_cite,
                cite_type=cite_type,
                span=(start, end),
                signal=signal,
                parenthetical=parenthetical,
                refers_to=last_full_cite if cite_type == 'id' else None,
                cl_record=cl_record,
            )
            citations.append(citation)

        return citations, new_last_full

    def _get_case_name(self, cite) -> Optional[str]:
        """Extract clean case name from citation."""
        if not hasattr(cite, 'metadata') or not cite.metadata:
            return None
        if not hasattr(cite.metadata, 'plaintiff') or not cite.metadata.plaintiff:
            return None

        plaintiff = cite.metadata.plaintiff.strip()
        defendant = (cite.metadata.defendant or '').strip()

        # Clean plaintiff - remove trailing punctuation
        plaintiff = plaintiff.rstrip('.,;:')

        # Clean defendant - remove trailing citation info
        if defendant and ',' in defendant:
            defendant = defendant.split(',')[0].strip()
        defendant = defendant.rstrip('.,;:')

        # Handle [sic] annotations - they indicate misspelling, remove them
        # e.g., "Rodgriguez [sic]" -> "Rodgriguez"
        plaintiff = re.sub(r'\s*\[sic\]\s*', '', plaintiff, flags=re.IGNORECASE)
        defendant = re.sub(r'\s*\[sic\]\s*', '', defendant, flags=re.IGNORECASE)

        # Remove page numbers that bled into names (e.g., "40 State" -> "State")
        plaintiff = re.sub(r'^\d+\s+', '', plaintiff)
        defendant = re.sub(r'^\d+\s+', '', defendant)

        # Skip if plaintiff is just [sic] or empty after cleaning
        if not plaintiff or plaintiff.lower() == '[sic]':
            return None

        if defendant:
            return f"{plaintiff} v. {defendant}"
        return plaintiff

    def _find_signal_before(self, text: str, pos: int) -> Optional[str]:
        """Find citation signal before position."""
        lookback = min(pos, 30)
        preceding = text[pos-lookback:pos].rstrip().lower()

        for signal in SIGNALS_SORTED:
            if preceding.endswith(signal.lower()):
                return signal
        return None

    def _find_parenthetical_after(self, text: str, pos: int) -> Optional[str]:
        """Find explanatory parenthetical after citation."""
        search = text[pos:pos+200]

        # Look for opening paren
        match = re.match(r'\s*\(', search)
        if not match:
            return None

        paren_start = pos + match.end()
        after_paren = text[paren_start:paren_start+50].lstrip().lower()

        # Check if starts with explanatory verb
        is_explanatory = any(after_paren.startswith(v) for v in PAREN_VERBS)
        if not is_explanatory:
            return None

        # Find matching close paren
        depth = 1
        i = paren_start
        while i < len(text) and depth > 0:
            if text[i] == '(':
                depth += 1
            elif text[i] == ')':
                depth -= 1
            i += 1

        if depth == 0:
            return text[paren_start:i-1].strip()
        return None

    def parse_argument_section(self, cl_client: Optional[CourtListenerClient] = None) -> Dict:
        """Parse the argument section into structured JSON."""
        # Find argument section - try exact headings first, then prefix matches
        section = None

        # Try exact matches first
        for start in ["Reply Argument", "Argument", "ARGUMENT", "REPLY ARGUMENT"]:
            section = self.find_section(start,
                ["Conclusion", "Prayer", "CONCLUSION", "PRAYER"])
            if section:
                break

        # Try prefix matches (e.g., "Argument on sole ground:")
        if not section:
            section = self.find_section_by_prefix("Argument",
                ["Conclusion", "Prayer", "CONCLUSION", "PRAYER"])

        if not section:
            return {"error": "Could not find Argument section"}

        # Extract paragraphs with block quote detection
        raw_paragraphs = self.extract_paragraphs(section)

        # Process each paragraph
        paragraphs = []
        last_full_cite = None

        for raw_para in raw_paragraphs:
            para_text = ' '.join(b['text'] for b in raw_para['blocks'])
            para_text = self._clean_text(para_text)

            if raw_para['type'] == 'block_quote':
                # For block quotes, find intro text from previous body paragraph
                intro = None
                if paragraphs and paragraphs[-1]['type'] == 'body':
                    last_body = paragraphs[-1]
                    if last_body['sentences']:
                        last_sent = last_body['sentences'][-1]['text']
                        # Check if ends with intro punctuation
                        if re.search(r'[:;,—]\s*$', last_sent):
                            intro = last_sent
                            # Remove from previous paragraph
                            last_body['sentences'] = last_body['sentences'][:-1]

                # Extract citations from block quote
                citations, last_full_cite = self.extract_citations_from_sentence(
                    para_text, last_full_cite, cl_client
                )

                para = {
                    'type': 'block_quote',
                    'intro': intro,
                    'text': para_text,
                    'citations': [self._citation_to_dict(c) for c in citations],
                }
            else:
                # Body paragraph - segment into sentences
                sentences_text = self.segment_sentences(para_text)
                sentences = []

                for sent_text in sentences_text:
                    # Normalize the sentence so spans are consistent
                    normalized_sent = self.normalize_for_eyecite(sent_text)
                    citations, last_full_cite = self.extract_citations_from_sentence(
                        normalized_sent, last_full_cite, cl_client
                    )
                    sentences.append({
                        'text': normalized_sent,
                        'citations': [self._citation_to_dict(c) for c in citations],
                    })

                para = {
                    'type': 'body',
                    'sentences': sentences,
                }

            paragraphs.append(para)

        return {
            'argument': {
                'start_page': section['start_page'] + 1,
                'end_page': section['end_page'] + 1,
                'paragraphs': paragraphs,
            }
        }

    def _clean_text(self, text: str) -> str:
        """Clean text of common artifacts."""
        # Merge hyphenated words at line breaks
        text = re.sub(r'(\w+)-\s+(\w+)', r'\1\2', text)
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _citation_to_dict(self, cite: Citation) -> Dict:
        """Convert Citation dataclass to dict."""
        d = asdict(cite)
        # Convert span tuple to list for JSON
        d['span'] = list(d['span'])
        return d

    def extract_toa_cases(self, cl_client: Optional[CourtListenerClient] = None) -> List[str]:
        """Extract case names from Table of Authorities."""
        section = self.find_section("Index of Authorities",
            ["Statutes", "Rules", "Statement", "Argument", "Reply"])
        if not section:
            section = self.find_section("Table of Authorities",
                ["Statutes", "Rules", "Statement", "Argument"])
        if not section:
            return []

        # Get text from section
        text = ""
        for page_num in range(section['start_page'], section['end_page'] + 1):
            text += self.doc[page_num].get_text()

        # Look for Cases subsection
        cases_match = re.search(r'Cases\s*\n(.*?)(?:Statutes|Rules|Other|\Z)',
                               text, re.DOTALL | re.IGNORECASE)
        if cases_match:
            text = cases_match.group(1)

        normalized = self.normalize_for_eyecite(text)
        citations = get_citations(normalized)

        cases = []
        for cite in citations:
            if isinstance(cite, FullCaseCitation):
                # Try CourtListener first
                name = None
                if cl_client:
                    vol = cite.groups.get('volume') if hasattr(cite, 'groups') else None
                    rep = cite.groups.get('reporter') if hasattr(cite, 'groups') else None
                    page = cite.groups.get('page') if hasattr(cite, 'groups') else None
                    if vol and rep and page:
                        name = cl_client.get_case_name(vol, rep, page)

                # Fall back to eyecite
                if not name:
                    name = self._get_case_name(cite)

                if name:
                    cases.append(name)

        return sorted(set(cases))

    def extract_argument_cases(self, parsed: Dict) -> List[str]:
        """Extract unique case names from parsed argument."""
        cases = set()

        for para in parsed.get('argument', {}).get('paragraphs', []):
            citations = []
            if para['type'] == 'block_quote':
                citations = para.get('citations', [])
            else:
                for sent in para.get('sentences', []):
                    citations.extend(sent.get('citations', []))

            for cite in citations:
                if cite.get('case_name'):
                    cases.add(cite['case_name'])

        return sorted(cases)

    def close(self):
        self.doc.close()


def propagate_cl_records(parsed: Dict) -> None:
    """
    Propagate CL records from full citations to short and id. citations.

    Rules:
    - Short citations: Match by volume/reporter to first full citation,
      validate page is plausible (>= start page, not absurdly far)
    - Id. citations: Use most recent full/short citation's CL record,
      validate pin cite if present. Inherit pin cite from last cite if none.
    """
    # Track full citations by volume/reporter key
    full_cites_by_key: Dict[str, Dict] = {}  # "vol|reporter" -> citation dict
    last_cite: Optional[Dict] = None  # Most recent citation with CL record
    last_pin_cite: Optional[str] = None  # Most recent pin cite

    def get_start_page(cl_record: Dict) -> Optional[int]:
        """Extract start page from CL record."""
        citations = cl_record.get('citation', [])
        if isinstance(citations, list):
            for c in citations:
                if isinstance(c, str):
                    # Parse "184 S.W.3d 242" format
                    parts = c.split()
                    if len(parts) >= 3:
                        try:
                            return int(parts[-1])
                        except ValueError:
                            pass
        return None

    def is_valid_pin_cite(pin_cite: str, start_page: int) -> bool:
        """Check if pin cite is plausible for the case."""
        if not pin_cite:
            return True  # No pin cite to validate

        # Extract page number from pin cite (e.g., "at 685" -> 685)
        match = re.search(r'(\d+)', pin_cite)
        if not match:
            return True  # Can't parse, assume valid

        pin_page = int(match.group(1))

        # Page must be >= start page
        if pin_page < start_page:
            return False

        # Page shouldn't be absurdly far from start (500 pages max)
        # Note: Some reporters have multiple cases per volume, so pin cites
        # can legitimately be far from the start page
        if pin_page > start_page + 500:
            return False

        return True

    def process_citations(citations: List[Dict]) -> None:
        nonlocal last_cite, last_pin_cite

        for cite in citations:
            cite_type = cite.get('cite_type')
            volume = cite.get('volume')
            reporter = cite.get('reporter')
            page = cite.get('page')
            pin_cite = cite.get('pin_cite')

            if cite_type == 'full_case':
                # Track this full citation
                if volume and reporter:
                    key = f"{volume}|{reporter}"
                    full_cites_by_key[key] = cite

                if cite.get('cl_record'):
                    last_cite = cite
                    last_pin_cite = pin_cite or page

            elif cite_type == 'short_case':
                # Find matching full citation by volume/reporter
                if volume and reporter:
                    key = f"{volume}|{reporter}"
                    full_cite = full_cites_by_key.get(key)

                    if full_cite and full_cite.get('cl_record'):
                        cl_record = full_cite['cl_record']
                        start_page = get_start_page(cl_record)

                        # Validate page number
                        if start_page and page:
                            try:
                                if int(page) >= start_page:
                                    cite['cl_record'] = cl_record
                                    cite['case_name'] = cite.get('case_name') or full_cite.get('case_name')
                            except ValueError:
                                pass
                        else:
                            # Can't validate, propagate anyway
                            cite['cl_record'] = cl_record
                            cite['case_name'] = cite.get('case_name') or full_cite.get('case_name')

                if cite.get('cl_record'):
                    last_cite = cite
                    last_pin_cite = pin_cite or page

            elif cite_type == 'id':
                # Use most recent citation's CL record
                if last_cite and last_cite.get('cl_record'):
                    cl_record = last_cite['cl_record']
                    start_page = get_start_page(cl_record)

                    # Get pin cite - use cite's own or inherit from last
                    effective_pin = pin_cite or last_pin_cite

                    # Validate pin cite if present
                    if start_page and effective_pin:
                        if is_valid_pin_cite(effective_pin, start_page):
                            cite['cl_record'] = cl_record
                            cite['case_name'] = cite.get('case_name') or last_cite.get('case_name')
                            # Set pin_cite to effective value (whether own or inherited)
                            if not pin_cite and effective_pin:
                                cite['pin_cite'] = effective_pin
                    else:
                        # Can't validate, propagate anyway
                        cite['cl_record'] = cl_record
                        cite['case_name'] = cite.get('case_name') or last_cite.get('case_name')
                        if not pin_cite and effective_pin:
                            cite['pin_cite'] = effective_pin

                    # Update last_pin_cite for next id.
                    if pin_cite:
                        last_pin_cite = pin_cite
                    elif effective_pin:
                        last_pin_cite = effective_pin

    # Process all paragraphs
    for para in parsed.get('argument', {}).get('paragraphs', []):
        if para['type'] == 'block_quote':
            process_citations(para.get('citations', []))
        else:
            for sent in para.get('sentences', []):
                process_citations(sent.get('citations', []))


def add_local_case_paths(parsed: Dict, cl_client: Optional['CourtListenerClient'] = None,
                         download_missing: bool = True) -> Dict[str, int]:
    """
    Add local file paths to all citations and optionally download missing cases.

    Uses the CL record's start page (not the cited page) for file paths, so that
    short cites and id cites point to the same file as the full citation.

    Args:
        parsed: The parsed brief data
        cl_client: CourtListener client for downloading missing cases
        download_missing: Whether to download missing cases from CL

    Returns:
        Stats dict with counts of local/downloaded/missing files
    """
    stats = {
        'local_exists': 0,
        'downloaded': 0,
        'not_available': 0,
        'no_cl_record': 0,
        'unsupported_reporter': 0,
    }

    # Track processed cases to avoid duplicate work (by cluster_id)
    processed_clusters: set = set()

    def get_start_page_from_cl(cl_record: Dict, reporter: str) -> Optional[str]:
        """Extract start page from CL record for the matching reporter."""
        citations = cl_record.get('citation', [])
        if isinstance(citations, list):
            for c in citations:
                if isinstance(c, str) and reporter in c:
                    # Parse "265 S.W.3d 580" format
                    parts = c.split()
                    if len(parts) >= 3:
                        return parts[-1]  # Last part is page
        return None

    def process_citation(cite: Dict) -> None:
        cl_record = cite.get('cl_record')

        # Must have CL record to get authoritative start page
        if not cl_record:
            stats['no_cl_record'] += 1
            return

        cluster_id = cl_record.get('cluster_id')

        # Get volume/reporter from the citation
        volume = cite.get('volume')
        reporter = cite.get('reporter')

        # For id cites, get volume/reporter from CL record
        if cite.get('cite_type') == 'id' and (not volume or not reporter):
            # Extract from CL citation list
            citations = cl_record.get('citation', [])
            for c in citations:
                if isinstance(c, str):
                    parts = c.split()
                    if len(parts) >= 3:
                        volume = parts[0]
                        reporter = ' '.join(parts[1:-1])
                        break

        if not volume or not reporter:
            stats['no_cl_record'] += 1
            return

        # Get start page from CL record (authoritative)
        start_page = get_start_page_from_cl(cl_record, reporter)
        if not start_page:
            # Fallback to citation's page for full cites
            start_page = cite.get('page')

        if not start_page:
            stats['no_cl_record'] += 1
            return

        # Check if reporter is supported
        slug = get_reporter_slug(reporter)
        if not slug:
            stats['unsupported_reporter'] += 1
            return

        # Get paths using the START page (not pin cite page)
        json_path, html_path = get_local_case_paths(volume, reporter, start_page)
        cite['local_json_path'] = json_path
        cite['local_html_path'] = html_path

        # Skip if already processed this cluster
        if cluster_id and cluster_id in processed_clusters:
            # Still count as exists if files are there
            if os.path.exists(json_path):
                stats['local_exists'] += 1
            return
        if cluster_id:
            processed_clusters.add(cluster_id)

        # Check if files exist
        json_exists = os.path.exists(json_path)
        html_exists = os.path.exists(html_path)

        if json_exists and html_exists:
            stats['local_exists'] += 1
            return

        # Try to download if missing
        if download_missing and cl_client:
            json_saved, html_saved = cl_client.download_case(volume, reporter, start_page)
            if json_saved or html_saved:
                stats['downloaded'] += 1
                return

        stats['not_available'] += 1

    # Process all citations in argument paragraphs
    for para in parsed.get('argument', {}).get('paragraphs', []):
        if para['type'] == 'block_quote':
            for cite in para.get('citations', []):
                process_citation(cite)
        else:
            for sent in para.get('sentences', []):
                for cite in sent.get('citations', []):
                    process_citation(cite)

    # Also process propositions (which contain copies of citations)
    for prop in parsed.get('propositions', []):
        for cite in prop.get('citations', []):
            process_citation(cite)

    return stats


def extract_propositions(parsed: Dict) -> List[Dict]:
    """
    Extract propositions from parsed argument structure.

    A proposition is the text that a citation supports. It can be:
    1. Text before the citation in the same sentence
    2. The previous sentence (if current is citation-only)
    3. A parenthetical after a signaled citation
    4. A block quote
    """
    propositions = []
    prev_sentence_text = None

    for para in parsed.get('argument', {}).get('paragraphs', []):
        if para['type'] == 'block_quote':
            # Block quote is its own proposition
            if para.get('citations'):
                prop = {
                    'text': para.get('text', ''),
                    'intro': para.get('intro'),
                    'type': 'block_quote',
                    'citations': para['citations'],
                }
                propositions.append(prop)
            prev_sentence_text = para.get('text', '')

        else:  # body paragraph
            for sent in para.get('sentences', []):
                sent_text = sent['text']
                citations = sent.get('citations', [])

                if not citations:
                    # No citations - just track as potential proposition for next sentence
                    prev_sentence_text = sent_text
                    continue

                # Determine what proposition these citations support
                prop_text, prop_type = _extract_proposition_from_sentence(
                    sent_text, citations, prev_sentence_text
                )

                if prop_text:
                    prop = {
                        'text': prop_text,
                        'type': prop_type,
                        'citations': citations,
                    }

                    # Check for parenthetical propositions
                    for cite in citations:
                        if cite.get('signal') and cite.get('parenthetical'):
                            # This citation has its own parenthetical proposition
                            paren_prop = {
                                'text': cite['parenthetical'],
                                'type': 'parenthetical',
                                'citations': [cite],
                            }
                            propositions.append(paren_prop)

                    propositions.append(prop)

                prev_sentence_text = sent_text

    return propositions


def _extract_proposition_from_sentence(
    sent_text: str,
    citations: List[Dict],
    prev_sentence: Optional[str]
) -> Tuple[Optional[str], str]:
    """
    Extract the proposition text from a sentence with citations.

    Returns (proposition_text, proposition_type)
    """
    if not citations:
        return None, ''

    # Find where the first citation starts and last citation ends
    first_cite = min(citations, key=lambda c: c['span'][0])
    last_cite = max(citations, key=lambda c: c['span'][1])
    cite_start = first_cite['span'][0]
    cite_end = last_cite['span'][1]

    # Get text before the first citation
    text_before = sent_text[:cite_start].strip()

    # Get text after the last citation
    text_after = sent_text[cite_end:].strip()

    # Check for mid-sentence citation pattern:
    # "[intro] -- [citations] -- [conclusion]"
    # Detected by: text_before ends with "--" and text_after starts with "--"
    if text_before.endswith('--') and text_after.startswith('--'):
        # Mid-sentence citation - use the complete sentence as proposition
        intro = text_before[:-2].strip()  # Remove trailing --
        conclusion = text_after[2:].strip()  # Remove leading --
        prop_text = f"{intro} {conclusion}".strip()
        prop_type = 'quote' if _has_quotation(prop_text) else 'statement'
        return prop_text, prop_type

    # Remove signal from text_before if present
    signal = first_cite.get('signal')
    if signal and text_before.lower().endswith(signal.lower()):
        text_before = text_before[:-len(signal)].strip()

    # Clean up trailing punctuation and dashes
    text_before = text_before.rstrip('.,;:-– ')

    # Is there meaningful text before the citation?
    # "Meaningful" = more than just a signal or short connector
    meaningful_threshold = 20  # characters

    if len(text_before) >= meaningful_threshold:
        # Proposition is in this sentence
        prop_type = 'quote' if _has_quotation(text_before) else 'statement'
        return text_before, prop_type

    # Text before citation is too short - use previous sentence
    if prev_sentence:
        prop_type = 'quote' if _has_quotation(prev_sentence) else 'statement'
        return prev_sentence, prop_type

    # No previous sentence available
    # Use whatever text we have, even if short
    if text_before:
        return text_before, 'statement'

    return None, ''


def _has_quotation(text: str) -> bool:
    """Check if text contains a substantial quotation."""
    # Look for quoted text of 15+ characters
    quote_pattern = r'["\u201c][^"\u201d]{15,}["\u201d]'
    return bool(re.search(quote_pattern, text))


def main():
    if len(sys.argv) < 2:
        print("Usage: python parse_brief.py <pdf_path> [--no-cl]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    use_cl = '--no-cl' not in sys.argv

    parser = BriefParser(pdf_path)

    try:
        # Initialize CourtListener client if API token available
        cl_client = None
        if use_cl:
            cl_client = get_cl_client()
            if cl_client.api_token:
                print("Fetching citations from CourtListener...", end=" ", flush=True)
                found = parser.prefetch_citations(cl_client)
                print(f"found {found} cases")
            else:
                print("No COURTLISTENER_API_TOKEN set, using eyecite only")
                cl_client = None

        # Parse argument section
        parsed = parser.parse_argument_section(cl_client)

        # Propagate CL records to id. and short citations
        propagate_cl_records(parsed)

        # Get case lists
        toa_cases = parser.extract_toa_cases(cl_client)
        arg_cases = parser.extract_argument_cases(parsed)

        # Add summary
        parsed['summary'] = {
            'toa_cases': toa_cases,
            'toa_case_count': len(toa_cases),
            'argument_cases': arg_cases,
            'argument_case_count': len(arg_cases),
            'cases_match': cases_match(set(toa_cases), set(arg_cases)),
        }

        # Print summary
        print(f"\n=== {pdf_path} ===\n")
        print(f"TOA cases: {len(toa_cases)}")
        print(f"Argument cases: {len(arg_cases)}")
        print(f"Cases match: {parsed['summary']['cases_match']}")

        if not cases_match(set(toa_cases), set(arg_cases)):
            print(f"\nIn TOA only: {set(toa_cases) - set(arg_cases)}")
            print(f"In Argument only: {set(arg_cases) - set(toa_cases)}")

        print(f"\nParagraphs: {len(parsed['argument']['paragraphs'])}")

        # Count sentences and citations
        sent_count = 0
        cite_count = 0
        block_quotes = 0
        for para in parsed['argument']['paragraphs']:
            if para['type'] == 'block_quote':
                block_quotes += 1
                cite_count += len(para.get('citations', []))
            else:
                sent_count += len(para.get('sentences', []))
                for sent in para.get('sentences', []):
                    cite_count += len(sent.get('citations', []))

        print(f"Sentences: {sent_count}")
        print(f"Block quotes: {block_quotes}")
        print(f"Citations: {cite_count}")

        # Extract propositions
        propositions = extract_propositions(parsed)
        parsed['propositions'] = propositions

        print(f"Propositions: {len(propositions)}")

        # Show sample propositions
        print("\nSample propositions:")
        for i, prop in enumerate(propositions[:5], 1):
            text = prop['text'][:100] + "..." if len(prop['text']) > 100 else prop['text']
            cite_names = [c.get('case_name') or c.get('text', '')[:25] for c in prop['citations'][:2]]
            print(f"  {i}. [{prop['type']}] {text}")
            print(f"     -> {cite_names}")

        # Add local case paths and download missing cases
        if cl_client:
            print("\nAdding local case paths...", end=" ", flush=True)
            path_stats = add_local_case_paths(parsed, cl_client, download_missing=True)
            print(f"local: {path_stats['local_exists']}, "
                  f"downloaded: {path_stats['downloaded']}, "
                  f"missing: {path_stats['not_available']}, "
                  f"no CL: {path_stats['no_cl_record']}, "
                  f"unsupported: {path_stats['unsupported_reporter']}")

        # Save JSON
        output_file = pdf_path.replace('.pdf', '_parsed.json').replace('.PDF', '_parsed.json')
        with open(output_file, 'w') as f:
            json.dump(parsed, f, indent=2, ensure_ascii=False)
        print(f"\nOutput: {output_file}")

    finally:
        parser.close()


if __name__ == "__main__":
    main()
