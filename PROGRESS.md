# CiteCheck Progress Summary

## Overview
Legal brief citation extraction and verification system using eyecite + CourtListener API.

## Core File
`parse_brief.py` - Parses legal briefs into structured JSON with citations, propositions, and CourtListener metadata.

## What Works

### Citation Extraction
- **Full citations**: Extracted via eyecite, looked up in CourtListener by `volume reporter page`
- **Short citations**: Matched to first full citation by volume/reporter, CL record propagated
- **Id. citations**: Inherit CL record from most recent citation, pin_cite inherited if not explicit
- **Page validation**: Pin cites validated against start page (must be ≥ start, ≤ start + 500)

### CourtListener Integration
- Uses search API: `GET /api/rest/v4/search/?type=o&citation="vol reporter page"`
- Full CL record attached to each citation including:
  - `caseName`, `absolute_url` (link to opinion text)
  - `dateFiled`, `court`, `citation` (parallel cites)
- Caching prevents duplicate API calls
- Env var: `COURTLISTENER_API_TOKEN`

### Case Name Handling
- CL provides authoritative names (fixes eyecite issues like "Inc v. NCI Bldg. Sys")
- Normalization for comparison: "Roderick Beham v. State" ↔ "Beham v. State"
- `cases_match()` function handles name variants

### Proposition Extraction
- Links each citation to its supporting proposition text
- Handles: text before citation, previous sentence, mid-sentence citations, block quotes, parentheticals

### Brief Structure Parsing
- Finds Argument section by heading (including prefix matches like "Argument on sole ground:")
- Segments into paragraphs, sentences
- Detects block quotes by indentation
- Em-dash normalization for eyecite compatibility

## Usage
```bash
# With CourtListener
COURTLISTENER_API_TOKEN=xxx python3 parse_brief.py brief.pdf

# Without CourtListener (eyecite only)
python3 parse_brief.py brief.pdf --no-cl
```

## Test Results
- 005.pdf: 44 citations, 100% have CL records (full/short/id)
- Match rate with normalization: ~60% (remaining mismatches are drafting errors like "overruled by X" citations)

## Known Limitations
- Case history citations ("overruled by", "rev'd on other grounds") counted as citations but shouldn't be in TOA
- Corporate names with Inc./L.P. may normalize oddly but still match
- Requires venv with: eyecite, PyMuPDF (fitz), requests
