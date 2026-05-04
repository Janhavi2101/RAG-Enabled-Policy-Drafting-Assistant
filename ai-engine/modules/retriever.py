import re
from typing import Dict, List, Optional


def _tokenize(*values):
    tokens = set()

    for value in values:
        if not value:
            continue

        if isinstance(value, (list, tuple, set)):
            for item in value:
                tokens.update(_tokenize(item))
            continue

        for token in re.findall(r"[a-z0-9_]{3,}", str(value).lower()):
            tokens.add(token)

    return tokens


class HybridRetriever:
    """
    Lightweight retriever for dict-based legal KB entries.

    Current behavior:
    - metadata filtering
    - lexical overlap scoring
    - lightweight field-aware ranking

    Returns:
    - list of rule dictionaries compatible with match_laws()
    """

    def __init__(self, legal_kb: List[dict]):
        self.legal_kb = legal_kb or []

    def retrieve(
        self,
        query: str,
        metadata_filter: Optional[Dict] = None,
        k: int = 10,
    ) -> List[dict]:
        metadata_filter = metadata_filter or {}
        query_tokens = _tokenize(query)

        scored = []

        for rule in self.legal_kb:
            if not self._passes_metadata_filter(rule, metadata_filter):
                continue

            score = self._score_rule(query_tokens, rule, metadata_filter)

            if score <= 0:
                continue

            enriched = dict(rule)
            enriched["retriever_score"] = round(score, 4)
            scored.append(enriched)

        scored.sort(
            key=lambda r: (
                r.get("retriever_score", 0),
                bool(r.get("section")),
                bool(r.get("sub_section")),
            ),
            reverse=True,
        )

        return scored[:k]

    def _passes_metadata_filter(self, rule: dict, metadata_filter: Dict) -> bool:
        for key, expected in metadata_filter.items():
            if expected in (None, "", [], {}):
                continue

            rule_value = rule.get(key)

            if isinstance(expected, (list, tuple, set)):
                if rule_value not in expected:
                    return False
            else:
                if str(rule_value or "").lower() != str(expected).lower():
                    return False

        return True

    def _score_rule(self, query_tokens: set, rule: dict, metadata_filter: Dict) -> float:
        score = 0.0

        rule_tokens = _tokenize(
            rule.get("law"),
            rule.get("topic"),
            rule.get("term"),
            rule.get("summary"),
            rule.get("text"),
            rule.get("keywords", []),
            rule.get("section"),
            rule.get("sub_section"),
            rule.get("type"),
        )

        overlap = query_tokens & rule_tokens
        score += len(overlap) * 1.0

        important_fields = [
            rule.get("topic"),
            rule.get("term"),
            " ".join(rule.get("keywords", [])[:10]) if isinstance(rule.get("keywords"), list) else rule.get("keywords"),
            rule.get("section"),
            rule.get("sub_section"),
        ]

        important_tokens = _tokenize(*important_fields)
        score += len(query_tokens & important_tokens) * 1.5

        if rule.get("law_family") == "core_healthcare":
            score += 2.0

        if rule.get("section"):
            score += 0.75

        if rule.get("sub_section"):
            score += 0.5

        if rule.get("citation"):
            score += 0.75

        if rule.get("type"):
            score += 0.5

        subdomain_filter = metadata_filter.get("subdomain")
        domain_filter = metadata_filter.get("domain")
        section_filter = metadata_filter.get("section")

        if subdomain_filter and str(rule.get("subdomain", "")).lower() == str(subdomain_filter).lower():
            score += 4.0

        if domain_filter and str(rule.get("domain", "")).lower() == str(domain_filter).lower():
            score += 2.5

        if section_filter:
            section_text = " ".join([
                str(rule.get("topic") or ""),
                str(rule.get("term") or ""),
                str(rule.get("section") or ""),
                str(rule.get("sub_section") or ""),
                " ".join(rule.get("keywords", [])[:8]) if isinstance(rule.get("keywords"), list) else "",
            ]).lower()

            if str(section_filter).lower() in section_text:
                score += 3.0

        return score