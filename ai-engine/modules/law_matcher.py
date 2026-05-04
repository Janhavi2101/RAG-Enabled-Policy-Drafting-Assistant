import re
from collections import defaultdict


GROUP_KEYS = [
    "scope",
    "definitions",
    "rights",
    "obligations",
    "prohibitions",
    "conditions",
    "exceptions",
    "procedures",
    "licensing_requirements",
    "recordkeeping_requirements",
    "reporting_requirements",
    "authority_powers",
    "penalties",
    "all",
]


IMPORTANT_QUERY_TERMS = {
    "registration",
    "licensing",
    "license",
    "records",
    "record",
    "documentation",
    "reporting",
    "report",
    "consent",
    "rights",
    "eligibility",
    "inspection",
    "compliance",
    "penalty",
    "penalties",
    "authority",
    "procedure",
    "procedures",
    "standards",
    "governance",
    "obligation",
    "obligations",
    "prohibition",
    "prohibitions",
}


def _tokenize(*values):
    tokens = set()
    for value in values:
        if not value:
            continue

        if isinstance(value, (list, set, tuple)):
            for item in value:
                tokens.update(_tokenize(item))
            continue

        for token in re.findall(r"[a-z0-9_]{3,}", str(value).lower()):
            tokens.add(token)

    return tokens


def _normalized_text(value):
    return str(value or "").strip().lower()


def _soft_field_match(intent_value, rule_value):
    """
    Returns a soft score for metadata similarity.
    Exact match gets the highest score.
    Partial token overlap gets a smaller score.
    """
    intent_text = _normalized_text(intent_value)
    rule_text = _normalized_text(rule_value)

    if not intent_text or not rule_text:
        return 0.0

    if intent_text == rule_text:
        return 1.0

    intent_tokens = _tokenize(intent_text)
    rule_tokens = _tokenize(rule_text)

    if not intent_tokens or not rule_tokens:
        return 0.0

    overlap = len(intent_tokens & rule_tokens)
    union = len(intent_tokens | rule_tokens)

    if union == 0:
        return 0.0

    return overlap / union


def _important_overlap_score(query_tokens, rule_tokens):
    overlap = query_tokens & rule_tokens
    score = 0.0

    for token in overlap:
        if token in IMPORTANT_QUERY_TERMS:
            score += 1.5
        else:
            score += 0.5

    return score


def _specificity_bonus(rule):
    bonus = 0.0

    if rule.get("section"):
        bonus += 1.0
    if rule.get("sub_section"):
        bonus += 0.75
    if rule.get("citation"):
        bonus += 1.0
    if rule.get("type"):
        bonus += 0.5
    if rule.get("summary"):
        bonus += 0.5
    if rule.get("text"):
        bonus += 0.5

    return bonus


def _authority_bonus(rule):
    bonus = 0.0

    if rule.get("law_family") == "core_healthcare":
        bonus += 2.0

    source_type = _normalized_text(rule.get("source_type"))
    if source_type in {"act", "rule", "regulation", "code"}:
        bonus += 1.0

    return bonus


def _score_rule(intent, rule):
    score = 0.0

    # Strong metadata alignment
    jurisdiction_match = _soft_field_match(intent.get("jurisdiction"), rule.get("jurisdiction"))
    domain_match = _soft_field_match(intent.get("domain"), rule.get("domain"))
    subdomain_match = _soft_field_match(intent.get("subdomain"), rule.get("subdomain"))

    score += jurisdiction_match * 8.0
    score += domain_match * 6.0
    score += subdomain_match * 10.0

    # Authority / trust bonus
    score += _authority_bonus(rule)

    target_tags = set(rule.get("applies_to", [])) | set(rule.get("entity_tags", []))
    requested_targets = set(intent.get("applies_to", []))

    if intent.get("entity_type"):
        requested_targets.add(intent["entity_type"])

    score += len(target_tags & requested_targets) * 5.0

    query_tokens = _tokenize(
        intent.get("policy_type"),
        intent.get("query_text"),
        intent.get("special_conditions", []),
        intent.get("keywords", []),
        intent.get("subdomain"),
        requested_targets,
    )

    rule_tokens = _tokenize(
        rule.get("law"),
        rule.get("topic"),
        rule.get("term"),
        rule.get("keywords", []),
        rule.get("summary"),
        rule.get("text"),
        rule.get("section"),
        rule.get("sub_section"),
    )

    score += _important_overlap_score(query_tokens, rule_tokens)

    preferred_types = {
        "right",
        "obligation",
        "prohibition",
        "procedure",
        "licensing_requirement",
        "reporting_requirement",
        "recordkeeping_requirement",
        "authority_power",
        "penalty",
        "definition",
        "scope",
        "condition",
        "exception",
    }

    if str(rule.get("type", "")).lower() in preferred_types:
        score += 1.5

    score += _specificity_bonus(rule)

    retrieval_boost = float(rule.get("retrieval_boost", 1.0) or 1.0)
    score *= retrieval_boost

    return round(score, 4)


def _diversify_results(scored_rules, per_law_cap=12, limit=80):
    diversified = []
    counts_by_law = defaultdict(int)

    for rule in scored_rules:
        law_name = rule.get("law") or "Unknown Law"
        if counts_by_law[law_name] >= per_law_cap:
            continue
        diversified.append(rule)
        counts_by_law[law_name] += 1

        if len(diversified) >= limit:
            break

    return diversified


def match_laws(intent, legal_kb, limit=80, per_law_cap=12):
    scored_rules = []

    for rule in legal_kb:
        score = _score_rule(intent, rule)
        if score <= 0:
            continue

        enriched_rule = dict(rule)
        enriched_rule["match_score"] = score
        scored_rules.append(enriched_rule)

    scored_rules.sort(
        key=lambda rule: (
            rule.get("match_score", 0),
            rule.get("law_family") == "core_healthcare",
            bool(rule.get("section")),
            bool(rule.get("sub_section")),
        ),
        reverse=True,
    )

    return _diversify_results(scored_rules, per_law_cap=per_law_cap, limit=limit)


def group_rules(rules):
    grouped = {key: [] for key in GROUP_KEYS}

    type_to_bucket = {
        "scope": "scope",
        "definition": "definitions",
        "right": "rights",
        "obligation": "obligations",
        "prohibition": "prohibitions",
        "condition": "conditions",
        "exception": "exceptions",
        "procedure": "procedures",
        "licensing_requirement": "licensing_requirements",
        "recordkeeping_requirement": "recordkeeping_requirements",
        "reporting_requirement": "reporting_requirements",
        "authority_power": "authority_powers",
        "penalty": "penalties",
    }

    for rule in rules:
        rule_type = str(rule.get("type", "")).lower()
        bucket = type_to_bucket.get(rule_type)

        if bucket:
            grouped[bucket].append(rule)

        # soft fallback grouping from keywords when type is weak/missing
        text_blob = " ".join([
            str(rule.get("topic") or ""),
            str(rule.get("term") or ""),
            " ".join(rule.get("keywords", [])[:10]),
            str(rule.get("summary") or ""),
        ]).lower()

        if not bucket:
            if any(word in text_blob for word in ["define", "means", "definition"]):
                grouped["definitions"].append(rule)
            if any(word in text_blob for word in ["register", "license", "licensing"]):
                grouped["licensing_requirements"].append(rule)
            if any(word in text_blob for word in ["record", "register", "documentation"]):
                grouped["recordkeeping_requirements"].append(rule)
            if any(word in text_blob for word in ["report", "notify", "submit"]):
                grouped["reporting_requirements"].append(rule)
            if any(word in text_blob for word in ["penalty", "punish", "fine", "imprisonment"]):
                grouped["penalties"].append(rule)
            if any(word in text_blob for word in ["shall", "must", "required"]):
                grouped["obligations"].append(rule)
            if any(word in text_blob for word in ["shall not", "prohibited", "forbidden", "no person shall"]):
                grouped["prohibitions"].append(rule)
            if any(word in text_blob for word in ["procedure", "process", "application"]):
                grouped["procedures"].append(rule)
            if any(word in text_blob for word in ["right", "entitled"]):
                grouped["rights"].append(rule)
            if any(word in text_blob for word in ["scope", "applicability", "applies to"]):
                grouped["scope"].append(rule)

        grouped["all"].append(rule)

    return grouped




#prev working version without section-aware drafting and hybrid retrieval:
'''import re


GROUP_KEYS = [
    "scope",
    "definitions",
    "rights",
    "obligations",
    "prohibitions",
    "conditions",
    "exceptions",
    "procedures",
    "licensing_requirements",
    "recordkeeping_requirements",
    "reporting_requirements",
    "authority_powers",
    "penalties",
    "all",
]


def _tokenize(*values):
    tokens = set()
    for value in values:
        if not value:
            continue
        if isinstance(value, list):
            for item in value:
                tokens.update(_tokenize(item))
            continue
        for token in re.findall(r"[a-z0-9]{3,}", str(value).lower()):
            tokens.add(token)
    return tokens


def _score_rule(intent, rule):
    score = 0.0

    if rule.get("jurisdiction") == intent.get("jurisdiction"):
        score += 8

    if rule.get("domain") == intent.get("domain"):
        score += 6

    if intent.get("subdomain") and rule.get("subdomain") == intent.get("subdomain"):
        score += 10

    if rule.get("law_family") == "core_healthcare":
        score += 2

    target_tags = set(rule.get("applies_to", [])) | set(rule.get("entity_tags", []))
    requested_targets = set(intent.get("applies_to", []))

    if intent.get("entity_type"):
        requested_targets.add(intent["entity_type"])

    score += len(target_tags & requested_targets) * 5

    query_tokens = _tokenize(
        intent.get("policy_type"),
        intent.get("query_text"),
        intent.get("special_conditions", []),
        intent.get("keywords", []),
        intent.get("subdomain"),
        requested_targets,
    )
    rule_tokens = _tokenize(
        rule.get("law"),
        rule.get("topic"),
        rule.get("term"),
        rule.get("keywords", []),
        rule.get("summary"),
        rule.get("text"),
    )
    score += len(rule_tokens & query_tokens) * 0.6

    preferred_types = {
        "right",
        "obligation",
        "prohibition",
        "procedure",
        "licensing_requirement",
        "reporting_requirement",
        "recordkeeping_requirement",
        "authority_power",
        "penalty",
    }
    if rule.get("type") in preferred_types:
        score += 1.5

    return score * float(rule.get("retrieval_boost", 1.0) or 1.0)


def match_laws(intent, legal_kb, limit=80):
    scored_rules = []

    for rule in legal_kb:
        score = _score_rule(intent, rule)
        if score <= 0:
            continue

        enriched_rule = dict(rule)
        enriched_rule["match_score"] = round(score, 3)
        scored_rules.append(enriched_rule)

    scored_rules.sort(
        key=lambda rule: (
            rule.get("match_score", 0),
            rule.get("law_family") == "core_healthcare",
            rule.get("section") is not None,
        ),
        reverse=True,
    )
    return scored_rules[:limit]


def group_rules(rules):
    grouped = {key: [] for key in GROUP_KEYS}

    type_to_bucket = {
        "scope": "scope",
        "definition": "definitions",
        "right": "rights",
        "obligation": "obligations",
        "prohibition": "prohibitions",
        "condition": "conditions",
        "exception": "exceptions",
        "procedure": "procedures",
        "licensing_requirement": "licensing_requirements",
        "recordkeeping_requirement": "recordkeeping_requirements",
        "reporting_requirement": "reporting_requirements",
        "authority_power": "authority_powers",
        "penalty": "penalties",
    }

    for rule in rules:
        bucket = type_to_bucket.get(str(rule.get("type", "")).lower())
        if bucket:
            grouped[bucket].append(rule)
        grouped["all"].append(rule)

    return grouped
'''