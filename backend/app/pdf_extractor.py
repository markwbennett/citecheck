import fitz  # PyMuPDF
import pdfplumber
import re
from typing import List, Dict, Tuple, Optional
from collections import Counter


class PDFExtractor:
    """Extract text from PDF files with page-spanning text handling."""

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)
        self._body_margin = None  # Calculated on first use
        self._para_indent = None  # First-line paragraph indent

    def extract_text_with_pages(self) -> List[Dict[str, any]]:
        """
        Extract text from PDF, preserving page numbers and handling page breaks.
        Returns list of dicts with page_num and text.
        """
        pages_data = []

        for page_num in range(len(self.doc)):
            page = self.doc[page_num]
            text = page.get_text()
            pages_data.append({
                'page_num': page_num + 1,  # 1-indexed for human readability
                'text': text
            })

        return pages_data

    def extract_full_text(self) -> str:
        """Extract all text from PDF as single string."""
        full_text = ""
        for page in self.doc:
            full_text += page.get_text()
        return full_text

    def find_section_boundaries(self, start_heading: str, end_heading: str) -> Optional[Tuple[int, int]]:
        """
        Find the page numbers where a section starts and ends.
        Headings must be on a line alone (e.g., "Argument" or "ARGUMENT" on its own line).
        Returns tuple of (start_page, end_page) or None if not found.
        """
        start_page = None
        end_page = None

        # Pattern for heading on a line alone (with optional whitespace)
        start_pattern = re.compile(
            rf'^\s*{re.escape(start_heading)}\s*$',
            re.IGNORECASE | re.MULTILINE
        )
        end_pattern = re.compile(
            rf'^\s*{re.escape(end_heading)}\s*$',
            re.IGNORECASE | re.MULTILINE
        )

        for page_num in range(len(self.doc)):
            page = self.doc[page_num]
            text = page.get_text()

            if start_page is None and start_pattern.search(text):
                start_page = page_num + 1

            if start_page is not None and end_pattern.search(text):
                end_page = page_num + 1
                break

        if start_page is not None and end_page is None:
            # If we found start but not end, assume it goes to the last page
            end_page = len(self.doc)

        return (start_page, end_page) if start_page else None

    def extract_section(self, start_heading: str, end_heading: str) -> Optional[Dict[str, any]]:
        """
        Extract a section from the PDF between two headings.
        Headings must be on a line alone.
        Handles text that spans across pages.
        """
        boundaries = self.find_section_boundaries(start_heading, end_heading)
        if not boundaries:
            return None

        start_page, end_page = boundaries
        section_text = ""

        # Pattern for heading on a line alone
        start_pattern = re.compile(
            rf'^\s*{re.escape(start_heading)}\s*$',
            re.IGNORECASE | re.MULTILINE
        )
        end_pattern = re.compile(
            rf'^\s*{re.escape(end_heading)}\s*$',
            re.IGNORECASE | re.MULTILINE
        )

        # Extract text from all pages in the section
        for page_num in range(start_page - 1, end_page):
            page = self.doc[page_num]
            text = page.get_text()

            # On the first page, extract from after the heading line
            if page_num == start_page - 1:
                match = start_pattern.search(text)
                if match:
                    # Get text after the heading line
                    text = text[match.end():]

            # On the last page, extract up to the end heading line
            if page_num == end_page - 1:
                match = end_pattern.search(text)
                if match:
                    # Get text before the ending heading line
                    text = text[:match.start()]

            section_text += text

        # Clean up the text - merge hyphenated words at line breaks
        section_text = self._merge_hyphenated_words(section_text)

        return {
            'text': section_text,
            'start_page': start_page,
            'end_page': end_page
        }

    def _merge_hyphenated_words(self, text: str) -> str:
        """Merge words that are hyphenated across line breaks."""
        # Replace "word-\n" with "word"
        text = re.sub(r'(\w+)-\s*\n\s*(\w+)', r'\1\2', text)
        return text

    def _calculate_margins(self, start_page: int = 0, end_page: int = None):
        """
        Calculate body margin and paragraph indent from page layout.
        Analyzes x0 (left margin) values to find the two most common positions.
        """
        if end_page is None:
            end_page = len(self.doc)

        x0_counts = Counter()

        for page_num in range(start_page, min(end_page, len(self.doc))):
            page = self.doc[page_num]
            blocks = page.get_text("blocks")

            for block in blocks:
                x0, y0, x1, y1, text, block_no, block_type = block
                # Only count text blocks with substantial content
                if block_type == 0 and text.strip() and len(text.strip()) > 30:
                    x0_rounded = round(x0)
                    x0_counts[x0_rounded] += 1

        # Find the two most common margins (body and paragraph indent)
        most_common = x0_counts.most_common(3)
        if len(most_common) >= 2:
            # Body margin is typically the most common (flush left lines)
            # Para indent is slightly larger (first lines of paragraphs)
            margins = sorted([m[0] for m in most_common[:2]])
            self._body_margin = margins[0]
            self._para_indent = margins[1]
        elif len(most_common) == 1:
            self._body_margin = most_common[0][0]
            self._para_indent = self._body_margin + 20  # Estimate

    def extract_section_with_blockquotes(self, start_heading: str, end_heading: str) -> Optional[Dict]:
        """
        Extract a section with block quote detection.
        Returns section text plus list of block quote positions.

        Block quotes are detected as consecutive lines where ALL lines are
        indented beyond the body margin (not just the first line like paragraphs).
        """
        boundaries = self.find_section_boundaries(start_heading, end_heading)
        if not boundaries:
            return None

        start_page, end_page = boundaries

        # Calculate margins for this section
        self._calculate_margins(start_page - 1, end_page)

        # Collect all text blocks with positions
        all_blocks = []

        start_pattern = re.compile(
            rf'^\s*{re.escape(start_heading)}\s*$',
            re.IGNORECASE | re.MULTILINE
        )
        end_pattern = re.compile(
            rf'^\s*{re.escape(end_heading)}\s*$',
            re.IGNORECASE | re.MULTILINE
        )

        for page_num in range(start_page - 1, end_page):
            page = self.doc[page_num]
            blocks = page.get_text("blocks")

            for block in blocks:
                x0, y0, x1, y1, text, block_no, block_type = block
                if block_type != 0 or not text.strip():
                    continue

                # Skip header/footer (page numbers typically have very different x0)
                if abs(x0 - self._body_margin) > 100:
                    continue

                # Check if we should skip (before start heading or after end heading)
                if page_num == start_page - 1:
                    page_text = page.get_text()
                    match = start_pattern.search(page_text)
                    if match:
                        # Skip blocks before the heading
                        heading_y = self._find_text_y_position(page, start_heading)
                        if heading_y and y0 < heading_y:
                            continue

                if page_num == end_page - 1:
                    page_text = page.get_text()
                    match = end_pattern.search(page_text)
                    if match:
                        heading_y = self._find_text_y_position(page, end_heading)
                        if heading_y and y0 > heading_y:
                            continue

                # Determine if this block is indented
                is_indented = x0 > self._body_margin + 3  # Small tolerance

                all_blocks.append({
                    'text': text.strip(),
                    'x0': x0,
                    'y0': y0,
                    'page': page_num + 1,
                    'is_indented': is_indented
                })

        # Detect block quotes: consecutive indented blocks
        block_quotes = []
        current_quote_blocks = []

        for i, block in enumerate(all_blocks):
            if block['is_indented']:
                current_quote_blocks.append(block)
            else:
                # Check if we just finished a block quote (2+ consecutive indented blocks)
                if len(current_quote_blocks) >= 2:
                    quote_text = ' '.join(b['text'] for b in current_quote_blocks)
                    block_quotes.append({
                        'text': quote_text,
                        'start_page': current_quote_blocks[0]['page'],
                        'end_page': current_quote_blocks[-1]['page'],
                    })
                current_quote_blocks = []

        # Don't forget the last group
        if len(current_quote_blocks) >= 2:
            quote_text = ' '.join(b['text'] for b in current_quote_blocks)
            block_quotes.append({
                'text': quote_text,
                'start_page': current_quote_blocks[0]['page'],
                'end_page': current_quote_blocks[-1]['page'],
            })

        # Build the full section text
        section_text = ' '.join(b['text'] for b in all_blocks)
        section_text = self._merge_hyphenated_words(section_text)

        return {
            'text': section_text,
            'start_page': start_page,
            'end_page': end_page,
            'block_quotes': block_quotes,
            'body_margin': self._body_margin,
            'para_indent': self._para_indent,
        }

    def _find_text_y_position(self, page, text: str) -> Optional[float]:
        """Find the y-position of text on a page."""
        search_results = page.search_for(text)
        if search_results:
            return search_results[0].y0
        return None

    def close(self):
        """Close the PDF document."""
        self.doc.close()
