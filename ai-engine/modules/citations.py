import re


def extract_citations(grouped_rules):
    """
    Extract unique citations from rules.
    """

    citations = []
    seen = set()

    for category, rules in grouped_rules.items():
        if category == "all":
            continue
        for r in rules:

            key = (r.get("citation") or r.get("law"), r.get("section"))

            if key not in seen:
                seen.add(key)

                citations.append({
                    "law": r.get("law"),
                    "section": r.get("section"),
                    "year": r.get("year", ""),
                    "citation": r.get("citation"),
                })

    return citations


def extract_inline_references(policy_text):
    citations = []
    seen = set()
    text = policy_text or ""

    patterns = [
        r"Articles?\s+\d+(?:\s*,\s*\d+)*(?:\s*,?\s*and\s+\d+)?",
        r"[A-Z][A-Za-z&,\-\s]+Act,\s*\d{4}(?:\s*\[[^\]]+\])?",
        r"Section\s+[0-9A-Za-z().-]+(?:\s+of\s+the\s+[A-Z][A-Za-z&,\-\s]+Act,\s*\d{4})?",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, text):
            citation = " ".join(match.group(0).split())
            if len(citation) < 8:
                continue
            if citation.lower().startswith("section "):
                window_start = max(0, match.start() - 80)
                window_end = min(len(text), match.end() + 80)
                window = text[window_start:window_end]
                if re.search(r"Act,\s*\d{4}\s*\[[^\]]*Section", window):
                    continue
            key = citation.lower()
            if key in seen:
                continue
            seen.add(key)
            citations.append({
                "law": None,
                "section": None,
                "year": "",
                "citation": citation,
                "source": "draft_text",
            })

    return citations


def merge_citations(*citation_groups):
    merged = []
    seen = set()

    for group in citation_groups:
        for citation in group or []:
            key = (
                (citation.get("citation") or "").strip().lower(),
                str(citation.get("section") or "").strip().lower(),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(citation)

    return merged


def format_references(citations):
    """
    Format citations like research paper references.
    """

    lines = []

    for i, c in enumerate(citations, start=1):
        line = c.get("citation") or f"Section {c['section']}, {c['law']}"

        if c["year"]:
            line += f", {c['year']}"

        if c.get("source") == "draft_text":
            line += " [draft-cited, not KB-verified]"

        lines.append(f"[{i}] {line}")

    return "\n".join(lines)
