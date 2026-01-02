from typing import Dict, List
from .pdf_extractor import PDFExtractor
from .citation_analyzer import CitationAnalyzer


class BriefProcessor:
    """Main processor for analyzing legal briefs."""

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.extractor = PDFExtractor(pdf_path)
        self.analyzer = CitationAnalyzer()

    def process_brief(self) -> Dict:
        """
        Process the brief and extract citations with their supporting text.
        Returns a dictionary with the parsed argument section.
        """
        # Extract the Argument section with block quote detection
        argument_section = self.extractor.extract_section_with_blockquotes("Argument", "Prayer")

        if not argument_section:
            argument_section = self.extractor.extract_section_with_blockquotes("ARGUMENT", "PRAYER")

        if not argument_section:
            raise ValueError("Could not find Argument section in the brief")

        # Normalize text for citation extraction
        raw_text = argument_section['text']
        normalized_text = self.analyzer.normalize_text(raw_text)

        # Extract citations with their context
        items = self.analyzer.extract_citations_with_context(normalized_text)

        # Get block quotes for verification
        block_quotes = argument_section.get('block_quotes', [])

        # Link block quotes to their citations
        # A block quote is associated with a citation if the citation's
        # preceding_text contains the block quote text
        self._link_block_quotes_to_citations(items, block_quotes)

        # Count statistics
        total_statements = sum(1 for item in items if item['content_type'] == 'statement')
        total_inline_quotations = sum(1 for item in items if item['content_type'] == 'quotation')
        total_block_quotations = sum(1 for item in items if item['content_type'] == 'block_quotation')

        result = {
            'metadata': {
                'start_page': argument_section['start_page'],
                'end_page': argument_section['end_page'],
                'total_citations': len(items),
                'total_statements': total_statements,
                'total_inline_quotations': total_inline_quotations,
                'total_block_quotations': total_block_quotations,
                'body_margin': argument_section.get('body_margin'),
                'para_indent': argument_section.get('para_indent'),
            },
            'items': items,
            'block_quotes': block_quotes,
        }

        return result

    def _link_block_quotes_to_citations(self, items: List[Dict], block_quotes: List[Dict]):
        """
        Link block quotes to their citations.

        A block quote is associated with a citation if the citation's
        preceding_text contains a significant portion of the block quote.
        Updates items in place to add block_quote field.

        When a block quote is found, any inline quotations are cleared since
        they're just quotes within the block quote, not separate quotations.

        Also extracts introductory text before the block quote (text ending
        in : — , ; … ... but not .)
        """
        # Characters that can end introductory text for block quotes
        intro_endings = (':', '—', ',', ';', '…', '...')

        for item in items:
            preceding = item['preceding_text']
            preceding_normalized = ' '.join(preceding.split())

            for bq in block_quotes:
                bq_text = bq['text']
                bq_identifier = ' '.join(bq_text.split()[:10])  # First 10 words

                if bq_identifier in preceding_normalized:
                    # Found a block quote in this citation's context
                    # Find where the block quote starts to extract intro text
                    bq_start_idx = preceding_normalized.find(bq_identifier)

                    intro_text = ''
                    if bq_start_idx > 0:
                        potential_intro = preceding_normalized[:bq_start_idx].strip()
                        # Check if it ends with an intro-ending character
                        if potential_intro and potential_intro.rstrip().endswith(intro_endings):
                            intro_text = potential_intro

                    item['block_quote'] = {
                        'text': bq_text,
                        'intro_text': intro_text,
                        'start_page': bq['start_page'],
                        'end_page': bq['end_page'],
                    }
                    # Block quote supersedes inline quotes - they're part of
                    # the block quote, not separate quotations
                    item['quotations'] = []
                    item['has_quotation'] = False
                    item['content_type'] = 'block_quotation'
                    break  # Only link one block quote per citation

    def close(self):
        """Close the PDF extractor."""
        self.extractor.close()
