#!/usr/bin/env python3
"""
Test script for the brief processor.
Tests PDF extraction and citation analysis.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "backend"))

from backend.app.brief_processor import BriefProcessor


def test_brief_processing(pdf_path: str):
    """Test processing a legal brief."""

    print(f"Processing: {pdf_path}")
    print("-" * 80)

    processor = BriefProcessor(pdf_path)

    try:
        print("Extracting and analyzing Argument section...")
        processed_data = processor.process_brief()

        # Print metadata
        print("\n📊 METADATA")
        print("-" * 80)
        metadata = processed_data['metadata']
        print(f"Argument Section: Pages {metadata['start_page']} - {metadata['end_page']}")
        print(f"Body margin: {metadata.get('body_margin')}, Para indent: {metadata.get('para_indent')}")
        print(f"Total Citations: {metadata['total_citations']}")
        print(f"  - Statements: {metadata['total_statements']}")
        print(f"  - Inline Quotations: {metadata.get('total_inline_quotations', 0)}")
        print(f"  - Block Quotations: {metadata.get('total_block_quotations', 0)}")

        # Print sample items
        print("\n📝 SAMPLE CITATIONS WITH CONTEXT (First 5)")
        print("-" * 80)
        for i, item in enumerate(processed_data['items'][:5], 1):
            print(f"\n{i}. [{item['content_type'].upper()}]")

            # Truncate long text
            preceding = item['preceding_text']
            if len(preceding) > 200:
                preceding = preceding[:200] + "..."
            print(f"   Text: {preceding}")

            cite = item['citation']
            signal_str = f"[{cite['signal']}] " if cite.get('signal') else ""
            print(f"   Citation: {signal_str}{cite['text']} ({cite['type']})")

            if cite.get('parenthetical'):
                print(f"   Parenthetical: {cite['parenthetical']['content'][:100]}...")

            if cite.get('needs_review'):
                print(f"   ⚠️ NEEDS REVIEW: Signaled citation without parenthetical")

            if item['quotations']:
                print(f"   Quotations: {[q['text'][:50] + '...' if len(q['text']) > 50 else q['text'] for q in item['quotations']]}")

        # Print sample block quotes
        block_quotes = processed_data.get('block_quotes', [])
        if block_quotes:
            print("\n📜 SAMPLE BLOCK QUOTES (First 3)")
            print("-" * 80)
            for i, bq in enumerate(block_quotes[:3], 1):
                text_preview = bq['text'][:200].replace('\n', ' ')
                page_info = f"Page {bq['start_page']}" if bq['start_page'] == bq['end_page'] else f"Pages {bq['start_page']}-{bq['end_page']}"
                print(f"\n{i}. [{page_info}]")
                print(f"   {text_preview}...")

        # Save full JSON output
        output_file = "processed_brief.json"
        with open(output_file, 'w') as f:
            json.dump(processed_data, f, indent=2)
        print(f"\n💾 Full output saved to: {output_file}")

        processor.close()
        print("\n✅ Processing completed successfully!")

    except Exception as e:
        print(f"\n❌ Error processing brief: {e}")
        import traceback
        traceback.print_exc()
        processor.close()
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_processor.py <path_to_pdf>")
        sys.exit(1)

    pdf_path = sys.argv[1]

    if not Path(pdf_path).exists():
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    test_brief_processing(pdf_path)
