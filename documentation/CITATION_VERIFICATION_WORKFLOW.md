# Citation Verification Workflow

This document explains how CiteCheck processes different types of legal citations for verification against source cases.

## Overview

CiteCheck extracts three types of content for verification:
1. **Direct quotations** → Direct text search in cited case
2. **Parenthetical explanations** → Text/AI search in cited case (from signaled citations)
3. **Unquoted statements** → AI semantic search in cited case

## Citation Types & Verification Strategy

### 1. Signaled Citation WITH Parenthetical (PREFERRED)

**Example:**
```
See Baltimore v. State, 689 S.W.3d 331 (holding that "a mere modicum" is insufficient).
```

**Parsed Output:**
```json
{
  "text": "See Baltimore v. State, 689 S.W.3d 331 (holding that \"a mere modicum\" is insufficient).",
  "citations": [{
    "text": "Baltimore v. State, 689 S.W.3d 331",
    "signal": "see",
    "parenthetical": {
      "content": "\"a mere modicum\" is insufficient",
      "has_quotations": true,
      "quotations": [{"text": "a mere modicum"}]
    },
    "needs_review": false
  }]
}
```

**Verification Strategy:**
1. Search for parenthetical content in cited case
2. If parenthetical has quotations → direct text search for "a mere modicum"
3. If no quotations → AI semantic search for "is insufficient"

---

### 2. Signaled Citation WITHOUT Parenthetical (NEEDS REVIEW)

**Example:**
```
See Baltimore v. State, 689 S.W.3d 331.
```

**Parsed Output:**
```json
{
  "text": "See Baltimore v. State, 689 S.W.3d 331.",
  "citations": [{
    "text": "Baltimore v. State, 689 S.W.3d 331",
    "signal": "see",
    "parenthetical": null,
    "needs_review": true
  }]
}
```

**Verification Strategy:**
1. ⚠️ **FLAG FOR REVIEW** - signaled citations should have parentheticals
2. Use AI semantic search with the full statement/quotation from the sentence
3. Requires manual review or advanced AI analysis

---

### 3. Direct Citation (No Signal) with Statement

**Example:**
```
The evidence is legally insufficient to support the conviction. Baltimore v. State, 689 S.W.3d 331, 340.
```

**Parsed Output:**
```json
{
  "text": "The evidence is legally insufficient to support the conviction. Baltimore v. State, 689 S.W.3d 331, 340.",
  "type": "statement",
  "unquoted_text": "The evidence is legally insufficient to support the conviction.",
  "quotations": [],
  "citations": [{
    "text": "Baltimore v. State, 689 S.W.3d 331, 340",
    "signal": null,
    "pinpoint": "340",
    "parenthetical": null,
    "needs_review": false
  }]
}
```

**Verification Strategy:**
1. Use AI semantic search in cited case at page 340
2. Search for semantic match of "The evidence is legally insufficient to support the conviction"

---

### 4. Direct Citation with Quotation

**Example:**
```
"A mere modicum of evidence is not sufficient." Baltimore v. State, 689 S.W.3d 331, 340.
```

**Parsed Output:**
```json
{
  "text": "\"A mere modicum of evidence is not sufficient.\" Baltimore v. State, 689 S.W.3d 331, 340.",
  "type": "quotation",
  "quotations": [{
    "type": "inline",
    "text": "A mere modicum of evidence is not sufficient."
  }],
  "unquoted_text": "",
  "citations": [{
    "text": "Baltimore v. State, 689 S.W.3d 331, 340",
    "signal": null,
    "pinpoint": "340",
    "parenthetical": null,
    "needs_review": false
  }]
}
```

**Verification Strategy:**
1. Direct text search for "A mere modicum of evidence is not sufficient."
2. Search in cited case at page 340

---

### 5. Mixed Statement with Embedded Quote

**Example:**
```
The court held that "a mere modicum" is insufficient to support conviction. Baltimore v. State, 689 S.W.3d 331.
```

**Parsed Output:**
```json
{
  "text": "The court held that \"a mere modicum\" is insufficient to support conviction. Baltimore v. State, 689 S.W.3d 331.",
  "type": "quotation",
  "quotations": [{
    "type": "inline",
    "text": "a mere modicum"
  }],
  "unquoted_text": "The court held that [...] is insufficient to support conviction.",
  "citations": [{
    "text": "Baltimore v. State, 689 S.W.3d 331",
    "signal": null,
    "parenthetical": null,
    "needs_review": false
  }]
}
```

**Verification Strategy (PERFORM BOTH):**
1. ✅ Direct text search for "a mere modicum" (the quote)
2. ✅ AI semantic search for "The court held that [...] is insufficient to support conviction" (the statement)

**Important:** When a sentence contains quotations, ALWAYS perform both searches to fully verify the citation.

---

### 6. Signaled Citation with Quotation in Parenthetical

**Example:**
```
See Gross v. State, 380 S.W.3d 181 (stating that "the evidence must be sufficient").
```

**Parsed Output:**
```json
{
  "text": "See Gross v. State, 380 S.W.3d 181 (stating that \"the evidence must be sufficient\").",
  "citations": [{
    "text": "Gross v. State, 380 S.W.3d 181",
    "signal": "see",
    "parenthetical": {
      "content": "\"the evidence must be sufficient\"",
      "has_quotations": true,
      "quotations": [{"text": "the evidence must be sufficient"}]
    },
    "needs_review": false
  }]
}
```

**Verification Strategy:**
1. Direct text search for "the evidence must be sufficient" (from parenthetical)
2. Search in Gross v. State

---

## Verification Algorithm

```python
def verify_citation(item, cited_case_text):
    for citation in item['citations']:
        # Get the case text
        case_text = fetch_case(citation['text'])

        # STRATEGY 1: Signaled with parenthetical
        if citation['signal'] and citation['parenthetical']:
            content = citation['parenthetical']['content']

            # Search parenthetical content
            if citation['parenthetical']['has_quotations']:
                # Direct text search for quotes in parenthetical
                for quote in citation['parenthetical']['quotations']:
                    result = direct_search(case_text, quote['text'])

                # ALSO do AI search for unquoted parts of parenthetical if any
                # (This handles mixed parentheticals)

            else:
                # AI semantic search for parenthetical content
                result = ai_search(case_text, content)

        # STRATEGY 2: Signaled without parenthetical (FLAG)
        elif citation['signal'] and not citation['parenthetical']:
            # NEEDS REVIEW
            flag_for_review(citation, reason="Missing parenthetical")

            # Fallback: Search main sentence content
            # Do BOTH searches if sentence has quotations
            for quote in item['quotations']:
                result = direct_search(case_text, quote['text'])

            if item['unquoted_text']:
                result = ai_search(case_text, item['unquoted_text'])

        # STRATEGY 3: Direct citation (no signal)
        else:
            # ALWAYS do both searches when applicable:

            # 1. Direct text search for ALL quotations
            for quote in item['quotations']:
                result = direct_search(case_text, quote['text'])

            # 2. AI semantic search for unquoted statement
            if item['unquoted_text']:
                result = ai_search(case_text, item['unquoted_text'])

            # NOTE: If sentence has quotations, BOTH searches are performed
```

### Key Rule: ALWAYS Perform Both Searches

**If a sentence contains quotations:**
- ✅ Direct search for the quoted text
- ✅ AI search for the unquoted statement

**Example:**
```
"The court held that 'mere modicum' is insufficient."
→ Direct search: "mere modicum"
→ AI search: "The court held that [...] is insufficient."
```

This ensures complete verification of the citation.

## Special Flags

### `needs_review: true`
Set when a signaled citation lacks a parenthetical explanation. This violates legal citation conventions and requires special handling.

**Reasons for review:**
- Signaled citation without parenthetical explanation
- May indicate citation error or incomplete brief
- Requires AI semantic analysis or manual review

## JSON Output Fields Summary

| Field | Purpose |
|-------|---------|
| `quotations` | Quoted text for direct string search |
| `unquoted_text` | Paraphrased statement for AI semantic search |
| `citations[].signal` | Citation signal (see, cf., etc.) |
| `citations[].parenthetical.content` | The text to search for in signaled citations |
| `citations[].parenthetical.quotations` | Quotes within the parenthetical |
| `citations[].needs_review` | Flag for missing parentheticals |
| `citations[].pinpoint` | Specific page reference |

## Implementation Notes

1. **Prefer parenthetical content** for signaled citations
2. **Flag all signaled citations without parentheticals**
3. **Use direct search for quotations**, AI search for statements
4. **Check pinpoint pages first** when available
5. **Track verification confidence** based on match quality
