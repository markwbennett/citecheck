import fitz  # PyMuPDF
import re
from typing import Dict, List, Tuple, Optional


class PDFAnnotator:
    """Annotate PDFs with colored underlines for statements, quotations, and citations."""

    # Color definitions (RGB tuples, normalized to 0-1)
    COLORS = {
        'statement': (0, 0.6, 0),        # Dark green
        'quotation': (0, 0, 0.8),        # Blue
        'block_quotation': (0.5, 0, 0.5), # Purple
        'citation': (0.8, 0, 0),          # Red
    }

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

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)

    def annotate_brief(self, processed_data: Dict, output_path: str):
        """
        Annotate the PDF with colored underlines based on processed data.

        Strategy: Find citations in the PDF first, then read backward to find
        the preceding sentence and underline it.

        Args:
            processed_data: The structured data from BriefProcessor
            output_path: Path where the annotated PDF will be saved
        """
        # Get the page range for the Argument section
        start_page = processed_data['metadata']['start_page'] - 1  # Convert to 0-indexed
        end_page = processed_data['metadata']['end_page'] - 1

        for item in processed_data['items']:
            content_type = item['content_type']
            citation = item['citation']
            citation_text = citation['text']
            is_signaled = citation.get('signal') is not None

            # First, find the citation in the PDF
            citation_location = self._find_citation_in_pdf(
                citation_text, start_page, end_page
            )

            if citation_location:
                page_num, citation_rects = citation_location

                # Underline the citation (red, possibly double)
                for rect in citation_rects:
                    self._create_underline_annotation(
                        self.doc[page_num], rect,
                        self.COLORS['citation'], is_signaled
                    )

                # Now read backward from citation to find preceding sentence
                if content_type == 'block_quotation' and 'block_quote' in item:
                    # For block quotes, find and underline the block quote
                    bq = item['block_quote']
                    self._annotate_block_quote(bq, page_num, citation_rects[0], start_page, end_page)
                else:
                    # For statements/quotations, find preceding sentence
                    preceding_rects = self._find_preceding_sentence(
                        page_num, citation_rects[0], start_page
                    )
                    color = self.COLORS.get(content_type, self.COLORS['statement'])
                    for rect_info in preceding_rects:
                        self._create_underline_annotation(
                            self.doc[rect_info['page']], rect_info['rect'], color
                        )
            else:
                # Fallback: use chunk-based search if citation not found
                self._add_underline_chunked(
                    citation_text, 'citation', start_page, end_page, is_signaled
                )

        # Save annotated PDF to temp file first, then extract argument pages
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp_path = tmp.name

        self.doc.save(tmp_path)
        self.doc.close()

        # Open temp file and extract only argument pages
        tmp_doc = fitz.open(tmp_path)
        pages_to_keep = list(range(start_page, end_page + 1))
        tmp_doc.select(pages_to_keep)
        tmp_doc.save(output_path)
        tmp_doc.close()

        # Clean up temp file
        os.unlink(tmp_path)

        # Reopen original doc (for close() method)
        self.doc = fitz.open(self.pdf_path)

    def _find_citation_in_pdf(self, citation_text: str, start_page: int,
                               end_page: int) -> Optional[Tuple[int, List]]:
        """
        Find a citation in the PDF and return its location.

        Returns: (page_num, list_of_rects) or None if not found
        """
        # Try to find a unique identifier from the citation
        # Usually the reporter citation (e.g., "50 S.W.3d 285")
        search_terms = self._get_citation_search_terms(citation_text)

        for page_num in range(start_page, min(end_page + 1, len(self.doc))):
            page = self.doc[page_num]

            for term in search_terms:
                rects = page.search_for(term)
                if rects:
                    return (page_num, rects)

        return None

    def _get_citation_search_terms(self, citation_text: str) -> List[str]:
        """
        Extract searchable terms from a citation.
        Returns list of terms to search for, in order of specificity.
        """
        terms = []

        # Try the full citation first (for short citations like "Id. at 100")
        normalized = re.sub(r'\s+', ' ', citation_text).strip()
        if len(normalized) <= 30:
            terms.append(normalized)

        # Extract reporter citation pattern (e.g., "50 S.W.3d 285")
        reporter_match = re.search(
            r'\d+\s+[A-Z][A-Za-z.]+(?:\s*\d*[a-z]*d?)?\s+\d+',
            citation_text
        )
        if reporter_match:
            terms.append(reporter_match.group())

        # Try first 30 chars
        if len(normalized) > 30:
            chunk = normalized[:30]
            last_space = chunk.rfind(' ')
            if last_space > 15:
                chunk = chunk[:last_space]
            terms.append(chunk)

        return terms

    def _find_preceding_sentence(self, citation_page: int, citation_rect,
                                  start_page: int) -> List[Dict]:
        """
        Find the sentence preceding a citation by reading backward.

        Returns list of dicts: [{'page': page_num, 'rect': rect}, ...]
        """
        result = []

        # Get words with positions for the citation page
        page = self.doc[citation_page]
        words = page.get_text("words")  # List of (x0, y0, x1, y1, word, block_no, line_no, word_no)

        if not words:
            return result

        # Find the word closest to the citation (just before it)
        citation_y = citation_rect.y0
        citation_x = citation_rect.x0

        # Find words that are before the citation (above or to the left on same line)
        preceding_words = []
        for w in words:
            x0, y0, x1, y1, word, block_no, line_no, word_no = w
            # Word is before citation if:
            # - It's on a line above, OR
            # - It's on the same line but to the left
            if y1 < citation_y - 2:  # Above (with small tolerance)
                preceding_words.append(w)
            elif abs(y0 - citation_y) < 10 and x1 < citation_x:  # Same line, to the left
                preceding_words.append(w)

        if not preceding_words:
            return result

        # Sort by position (top to bottom, left to right)
        preceding_words.sort(key=lambda w: (w[1], w[0]))

        # Find sentence start by looking backward for sentence-ending punctuation
        sentence_start_idx = 0
        for i in range(len(preceding_words) - 1, -1, -1):
            word = preceding_words[i][4]
            if self._is_sentence_end(word, preceding_words, i):
                sentence_start_idx = i + 1
                break

        # Get words from sentence start to end (just before citation)
        sentence_words = preceding_words[sentence_start_idx:]

        # Create rects for these words
        for w in sentence_words:
            x0, y0, x1, y1 = w[0], w[1], w[2], w[3]
            rect = fitz.Rect(x0, y0, x1, y1)
            result.append({'page': citation_page, 'rect': rect})

        return result

    def _is_sentence_end(self, word: str, words: List, idx: int) -> bool:
        """Check if a word ends a sentence."""
        if not word:
            return False

        # Must end with sentence-ending punctuation
        if not word.rstrip().endswith(('.', '!', '?')):
            return False

        # Check if it's a legal abbreviation
        word_clean = word.rstrip()
        for abbrev in self.LEGAL_ABBREVS:
            if word_clean.lower().endswith(abbrev.lower()):
                return False

        # Check if next word starts with capital (if there is a next word)
        if idx + 1 < len(words):
            next_word = words[idx + 1][4]
            if next_word and next_word[0].isupper():
                return True
            # If next word is lowercase, probably not a sentence end
            return False

        return True

    def _annotate_block_quote(self, bq: Dict, citation_page: int,
                               citation_rect, start_page: int, end_page: int):
        """Annotate a block quote and its intro text."""
        bq_text = bq['text']
        intro_text = bq.get('intro_text', '')

        # Use block quote's page range if available
        bq_start = bq.get('start_page', start_page + 1) - 1
        bq_end = bq.get('end_page', end_page + 1) - 1

        # Underline block quote
        self._add_underline_chunked(bq_text, 'block_quotation', bq_start, bq_end)

        # Underline intro text if present
        if intro_text:
            self._add_underline_chunked(intro_text, 'statement', start_page, end_page)

    def _normalize_for_search(self, text: str) -> str:
        """Normalize text for PDF search by collapsing whitespace."""
        # Replace all whitespace sequences with single spaces
        return re.sub(r'\s+', ' ', text).strip()

    def _get_search_chunks(self, text: str, max_chunk_len: int = 50) -> List[str]:
        """
        Break text into searchable chunks.
        Returns a list of text chunks that can be searched independently.
        """
        normalized = self._normalize_for_search(text)

        if len(normalized) <= max_chunk_len:
            return [normalized] if normalized else []

        chunks = []

        # Try to split on sentence boundaries first
        # Look for sentence-ending punctuation followed by space and capital letter
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', normalized)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            if len(sentence) <= max_chunk_len:
                chunks.append(sentence)
            else:
                # For long sentences, take the first max_chunk_len chars
                # Try to end at a word boundary
                chunk = sentence[:max_chunk_len]
                last_space = chunk.rfind(' ')
                if last_space > max_chunk_len // 2:
                    chunk = chunk[:last_space]
                chunks.append(chunk.strip())

        return chunks if chunks else [normalized[:max_chunk_len]]

    def _add_underline_chunked(self, text: str, annotation_type: str, start_page: int,
                               end_page: int, double_underline: bool = False):
        """
        Add underline annotation to text using chunk-based search (fallback method).

        Args:
            text: The text to underline
            annotation_type: 'statement', 'quotation', or 'citation'
            start_page: First page to search (0-indexed)
            end_page: Last page to search (0-indexed)
            double_underline: Whether to add double underline (for signaled citations)
        """
        color = self.COLORS.get(annotation_type, (0, 0, 0))

        # Get searchable chunks from the text
        chunks = self._get_search_chunks(text)

        # Search for each chunk in the specified page range
        for page_num in range(start_page, min(end_page + 1, len(self.doc))):
            page = self.doc[page_num]

            for chunk in chunks:
                if not chunk:
                    continue

                # Search for text instances on this page
                text_instances = page.search_for(chunk)

                for inst in text_instances:
                    # Create underline annotation
                    self._create_underline_annotation(page, inst, color, double_underline)

    def _create_underline_annotation(self, page, rect, color: Tuple[float, float, float],
                                      double_underline: bool = False):
        """
        Create an underline annotation on the page.

        Args:
            page: The PDF page object
            rect: The rectangle coordinates (fitz.Rect) where text is located
            color: RGB color tuple (0-1 range)
            double_underline: Whether to add a second underline below the first
        """
        # Draw underline as a line annotation at the bottom of the text
        underline_y = rect.y1 + 1  # 1 point below text bottom
        p1 = fitz.Point(rect.x0, underline_y)
        p2 = fitz.Point(rect.x1, underline_y)

        annot = page.add_line_annot(p1, p2)
        annot.set_colors(stroke=color)
        annot.set_border(width=1)
        annot.update()

        # Add second underline if signaled citation (draw a line below the first)
        if double_underline:
            underline_y2 = rect.y1 + 4  # 4 points below text bottom
            p1 = fitz.Point(rect.x0, underline_y2)
            p2 = fitz.Point(rect.x1, underline_y2)

            annot2 = page.add_line_annot(p1, p2)
            annot2.set_colors(stroke=color)
            annot2.set_border(width=1)
            annot2.update()

    def close(self):
        """Close the PDF document."""
        self.doc.close()
