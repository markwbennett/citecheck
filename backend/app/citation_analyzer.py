import re
from typing import List, Dict, Optional, Tuple
from enum import Enum
from eyecite import get_citations, clean_text
from eyecite.models import (
    FullCaseCitation,
    ShortCaseCitation,
    SupraCitation,
    IdCitation,
)


class ContentType(Enum):
    STATEMENT = "statement"
    QUOTATION = "quotation"


class CitationAnalyzer:
    """Analyze legal text to identify citations and their supporting statements/quotations."""

    # Common citation signals
    SIGNALS = [
        'see', 'see also', 'see generally', 'cf.', 'compare', 'contra',
        'but see', 'but cf.', 'see, e.g.,', 'e.g.,', 'accord'
    ]

    # Legal abbreviations that don't end sentences
    LEGAL_ABBREVS = [
        'v.', 'vs.', 'Inc.', 'Ltd.', 'Corp.', 'Co.', 'No.', 'Nos.',
        'App.', 'Crim.', 'Civ.', 'Ct.', 'Dist.', 'Supp.', 'Rev.',
        'Stat.', 'Ann.', 'Gen.', 'Ass.', 'Ch.', 'Cl.', 'Div.',
        'Ed.', 'Ex.', 'Fed.', 'Gov.', 'Int.', 'Jr.', 'Sr.', 'Mr.',
        'Mrs.', 'Ms.', 'Dr.', 'Prof.', 'Rep.', 'Sen.', 'St.',
        'Tex.', 'Cal.', 'N.Y.', 'Fla.', 'U.S.', 'S.W.', 'N.W.',
        'S.E.', 'N.E.', 'So.', 'P.', 'F.', 'L.', 'R.', 'S.', 'W.',
    ]

    def __init__(self):
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for signal and quotation detection."""
        signals_regex = '|'.join([re.escape(sig) for sig in self.SIGNALS])
        self.signal_pattern = re.compile(rf'\b({signals_regex})\s*$', re.IGNORECASE)

        # Inline quote pattern - handles straight and curly double quotes
        # U+0022 = ", U+201C = ", U+201D = "
        # Note: Single curly quotes (U+2018, U+2019) are used for nested quotes
        self.inline_quote_pattern = re.compile(r'["\u201c\u201d]([^"\u201c\u201d]+)["\u201c\u201d]')

        # Parenthetical explanation pattern
        self.parenthetical_pattern = re.compile(
            r'\('
            r'(?:holding|stating|finding|noting|explaining|observing|concluding|reasoning|'
            r'emphasizing|recognizing|determining|clarifying|reaffirming|affirming|reversing)'
            r'\s+that\s+'
            r'([^)]+)'
            r'\)',
            re.IGNORECASE
        )

    def normalize_text(self, text: str) -> str:
        """Normalize text for citation extraction using eyecite's clean_text."""
        return clean_text(text, ['all_whitespace', 'underscores'])

    def _find_sentence_start(self, text: str, end_pos: int) -> int:
        """
        Find the start of the sentence that precedes end_pos.

        We need to find TWO sentence boundaries:
        1. The one that ends the sentence right before end_pos (e.g., "jury.")
        2. The one that ends the sentence BEFORE that (e.g., "341.")

        We return the position after boundary #2, which is where our sentence starts.
        """
        search_text = text[:end_pos]
        best_pos = 0  # Default to start of text
        boundaries_found = 0

        i = len(search_text) - 1
        while i >= 0:
            char = search_text[i]

            if char in '.!?':
                # Check what comes after this punctuation
                after_punct = search_text[i+1:].lstrip()

                # If nothing after or starts with capital, might be sentence end
                if not after_punct or (after_punct and after_punct[0].isupper()):
                    # Check if it's a legal abbreviation
                    is_abbrev = False
                    for abbrev in self.LEGAL_ABBREVS:
                        abbrev_start = i - len(abbrev) + 1
                        if abbrev_start >= 0:
                            potential = search_text[abbrev_start:i+1]
                            if potential.lower() == abbrev.lower():
                                is_abbrev = True
                                break

                    if not is_abbrev:
                        boundaries_found += 1
                        if boundaries_found == 2:
                            # Second boundary: end of the previous sentence
                            # Our sentence starts after this boundary
                            best_pos = i + 1
                            while best_pos < len(search_text) and search_text[best_pos].isspace():
                                best_pos += 1
                            break

            i -= 1

        return best_pos

    def extract_citations_with_context(self, text: str) -> List[Dict]:
        """
        Extract all citations and the text that precedes each one.

        Returns list of dicts, each containing:
        - preceding_text: The statement/quotation before the citation
        - citation: The citation itself
        - signal: Any citation signal (see, cf., etc.)
        - parenthetical: Any parenthetical explanation
        - has_quotation: Whether preceding text contains a quotation
        - quotations: List of quotations in preceding text
        """
        results = []
        found_citations = get_citations(text)

        if not found_citations:
            return results

        last_end = 0
        last_full_citation = None
        last_proposition = None  # Track last real proposition for string cites
        string_cite_group = 0    # Group number for string cites

        for cite in found_citations:
            # Get the full citation span, including case name for FullCaseCitation
            start_pos, end_pos = self._get_full_citation_span(cite, text)
            citation_text = text[start_pos:end_pos]

            # Get the sentence before this citation
            # First, get all text from last citation to this one
            full_preceding = text[last_end:start_pos]

            # Find where the current sentence starts
            sentence_start = self._find_sentence_start(text, start_pos)

            # Use the later of: last citation end, or sentence start
            actual_start = max(last_end, sentence_start)
            preceding_text = text[actual_start:start_pos].strip()

            # Strip leading punctuation that may be trailing from previous citation
            preceding_text = preceding_text.lstrip('.,;:!? \t\n')

            # Strip common citation annotations at the beginning
            # e.g., "(emphasis added)", "(cleaned up)", "(internal citations omitted)"
            annotation_pattern = re.compile(
                r'^\([^)]*(?:added|omitted|altered|supplied|cleaned up|quotation marks?|'
                r'citations?|internal|emphasis|footnote)[^)]*\)\s*\.?\s*',
                re.IGNORECASE
            )
            preceding_text = annotation_pattern.sub('', preceding_text)

            # Check for signal at end of preceding text
            signal = self._extract_signal(preceding_text)
            if signal:
                # Remove signal from preceding text
                preceding_text = self.signal_pattern.sub('', preceding_text).strip()

            # Detect string cites: when preceding text is just punctuation/whitespace
            # Pattern: "Proposition. Cite1; cite2; see cite3."
            is_string_cite = False
            stripped_preceding = preceding_text.strip(';,. \t\n')
            if not stripped_preceding or stripped_preceding in ['and', 'or', 'but']:
                # This is part of a string cite - use the last real proposition
                is_string_cite = True
                if last_proposition:
                    preceding_text = last_proposition
            else:
                # This is a new proposition
                last_proposition = preceding_text
                string_cite_group += 1

            # Check for parenthetical after citation
            parenthetical = self._find_parenthetical_after(text, end_pos)

            # Determine citation type
            if isinstance(cite, FullCaseCitation):
                cite_type = 'full_case'
                last_full_citation = citation_text
            elif isinstance(cite, ShortCaseCitation):
                cite_type = 'short_case'
            elif isinstance(cite, IdCitation):
                cite_type = 'id'
            elif isinstance(cite, SupraCitation):
                cite_type = 'supra'
            else:
                cite_type = 'unknown'

            # Find quotations in preceding text
            quotations = self._find_quotations(preceding_text)

            # Flag if signaled but missing parenthetical
            needs_review = signal is not None and parenthetical is None

            result = {
                'preceding_text': preceding_text,
                'citation': {
                    'text': citation_text,
                    'type': cite_type,
                    'start': start_pos,
                    'end': end_pos,
                    'signal': signal,
                    'parenthetical': parenthetical,
                    'needs_review': needs_review,
                },
                'has_quotation': len(quotations) > 0,
                'quotations': quotations,
                'content_type': ContentType.QUOTATION.value if quotations else ContentType.STATEMENT.value,
                'is_string_cite': is_string_cite,
                'string_cite_group': string_cite_group,
            }

            # For id. citations, track what they refer to
            if cite_type == 'id' and last_full_citation:
                result['citation']['refers_to'] = last_full_citation

            results.append(result)

            # Update position (include parenthetical if present)
            if parenthetical:
                last_end = parenthetical['end']
            else:
                last_end = end_pos

        return results

    def _extract_signal(self, text: str) -> Optional[str]:
        """Extract citation signal from end of text."""
        match = self.signal_pattern.search(text)
        if match:
            return match.group(1).lower()
        return None

    def _find_quotations(self, text: str) -> List[Dict]:
        """Find quotations in text."""
        quotations = []
        for match in self.inline_quote_pattern.finditer(text):
            quotations.append({
                'text': match.group(1),
                'start': match.start(),
                'end': match.end()
            })
        return quotations

    def _find_parenthetical_after(self, text: str, position: int, lookahead: int = 200) -> Optional[Dict]:
        """Find a parenthetical explanation after the citation."""
        end = min(len(text), position + lookahead)
        following_text = text[position:end]

        match = self.parenthetical_pattern.search(following_text)
        if match:
            parenthetical_content = match.group(1).strip()
            quotations = self._find_quotations(parenthetical_content)

            return {
                'full_text': match.group(0),
                'content': parenthetical_content,
                'has_quotations': len(quotations) > 0,
                'quotations': quotations,
                'start': position + match.start(),
                'end': position + match.end()
            }
        return None

    def _get_full_citation_span(self, cite, text: str) -> Tuple[int, int]:
        """
        Get the full span of a citation, including case name for full/short citations.

        For FullCaseCitation: uses full_span_start/full_span_end which includes
            case name, reporter, pin cite, court, and year.
        For ShortCaseCitation: looks backwards to find the case short name
            before the reporter citation.
        For IdCitation, SupraCitation: uses span() which already includes pin cite.
        """
        span_start, span_end = cite.span()

        if isinstance(cite, FullCaseCitation):
            # Use eyecite's full span which includes case name, reporter, pin cite, court, year
            if cite.full_span_start is not None:
                # full_span_end is often None; use span_end as fallback
                end = cite.full_span_end if cite.full_span_end is not None else span_end
                return cite.full_span_start, end
            # Fallback to basic span if full span not available
            return span_start, span_end

        elif isinstance(cite, ShortCaseCitation):
            # Short citations have format: "Brown, 50 S.W.3d at 100"
            # eyecite's span() only gets "50 S.W.3d at 100"
            # We need to look backwards to find the case name
            if cite.full_span_start is not None:
                end = cite.full_span_end if cite.full_span_end is not None else span_end
                return cite.full_span_start, end

            # Try to find the antecedent case name before the comma
            antecedent = None
            if hasattr(cite, 'metadata') and hasattr(cite.metadata, 'antecedent_guess'):
                antecedent = cite.metadata.antecedent_guess

            if antecedent:
                # Look backwards from span_start to find the case name
                # Pattern: "CaseName, " immediately before the reporter citation
                lookback = min(span_start, 100)  # Look back up to 100 chars
                preceding = text[span_start - lookback:span_start]

                # Search for the antecedent followed by comma and optional space
                pattern = re.compile(
                    rf'\b({re.escape(antecedent)})\s*,\s*$',
                    re.IGNORECASE
                )
                match = pattern.search(preceding)
                if match:
                    new_start = span_start - lookback + match.start()
                    return new_start, span_end

            return span_start, span_end

        else:
            # IdCitation, SupraCitation, etc. - span() already includes pin cite
            return span_start, span_end
