#!/usr/bin/env python3
"""Test script for PDF annotation."""
import sys
sys.path.insert(0, '/home/mb/github/citecheck/backend')

from app.brief_processor import BriefProcessor
from app.pdf_annotator import PDFAnnotator

# Use the sample brief
pdf_path = "/home/mb/github/citecheck/Sample_Briefs/Daniel Bible brief (final).pdf"
output_path = "/home/mb/github/citecheck/test_annotated_output.pdf"

print(f"Processing: {pdf_path}")

# Process the brief
processor = BriefProcessor(pdf_path)
processed_data = processor.process_brief()
processor.close()

print(f"Found {processed_data['metadata']['total_citations']} citations")
print(f"Pages {processed_data['metadata']['start_page']} - {processed_data['metadata']['end_page']}")

# Annotate the PDF
annotator = PDFAnnotator(pdf_path)
annotator.annotate_brief(processed_data, output_path)
annotator.close()

print(f"Annotated PDF saved to: {output_path}")
