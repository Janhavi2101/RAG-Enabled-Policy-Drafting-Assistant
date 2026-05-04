import re


def _normalize(text):
    return " ".join((text or "").lower().split())


def _tokenize(text):
    return set(re.findall(r"[a-z0-9_]{4,}", _normalize(text)))


def _rule_keywords(rule):
    keywords = list(rule.get("keywords", []))

    if rule.get("topic"):
        keywords.append(rule["topic"])
    if rule.get("term"):
        keywords.append(rule["term"])
    if rule.get("type"):
        keywords.append(rule["type"])
    if rule.get("section"):
        keywords.append(str(rule["section"]))

    cleaned = []
    for keyword in keywords[:12]:
        keyword = _normalize(keyword)
        if keyword:
            cleaned.append(keyword)

    return cleaned


def _rule_coverage_score(policy_text, rule):
    """
    Returns a simple coverage score instead of a binary yes/no.
    """
    policy_lower = _normalize(policy_text)
    policy_tokens = _tokenize(policy_text)
    keywords = _rule_keywords(rule)

    if not keywords:
        return 0.0

    exact_hits = 0
    token_hits = 0

    for keyword in keywords:
        if keyword in policy_lower:
            exact_hits += 1

        keyword_tokens = _tokenize(keyword)
        token_hits += len(keyword_tokens & policy_tokens)

    score = exact_hits * 1.5 + token_hits * 0.5
    return round(score, 3)


def _rule_is_covered(policy_text, rule, threshold=1.5):
    return _rule_coverage_score(policy_text, rule) >= threshold


def _check_structure(policy_text, intent):
    findings = []
    text = _normalize(policy_text)

    expected_section_markers = [
        "purpose",
        "scope",
        "compliance",
    ]

    subdomain = (intent.get("subdomain") or "").lower()

    if subdomain == "clinical_establishments":
        expected_section_markers.extend([
            "registration",
            "records",
            "penalties",
        ])
    elif subdomain == "mental_health":
        expected_section_markers.extend([
            "rights",
            "grievance",
        ])
    elif subdomain == "organ_transplant":
        expected_section_markers.extend([
            "licensing",
            "documentation",
        ])

    for marker in expected_section_markers:
        if marker not in text:
            findings.append({
                "severity": "medium",
                "category": "structure",
                "issue": f"The draft may be missing a section or heading related to '{marker}'.",
                "requirement": f"Ensure the policy explicitly covers or headings reflect '{marker}'.",
            })

    return findings


def _check_hygiene(policy_text):
    findings = []
    text = policy_text or ""

    if "error generating section" in text.lower():
        findings.append({
            "severity": "high",
            "category": "draft_hygiene",
            "issue": "The draft contains a section generation error message.",
            "requirement": "Regenerate or manually rewrite the affected section.",
        })

    if "requires manual review" in text.lower():
        findings.append({
            "severity": "medium",
            "category": "draft_hygiene",
            "issue": "The draft contains a manual review placeholder.",
            "requirement": "Replace placeholder content before finalizing the policy.",
        })

    if "## references" not in text.lower():
        findings.append({
            "severity": "low",
            "category": "draft_hygiene",
            "issue": "The draft does not contain a references section.",
            "requirement": "Append a references section with legal citations.",
        })

    return findings


def review_policy(policy_text, intent, grouped_rules):
    findings = []
    checked = 0

    if not grouped_rules.get("all"):
        findings.extend(_check_structure(policy_text, intent))
        findings.extend(_check_hygiene(policy_text))
        return {
            "status": "generic_review",
            "checked_rules": 0,
            "findings": findings[:5],
            "issues": findings[:5],
            "intent_subdomain": intent.get("subdomain"),
        }

    priority_buckets = [
        ("rights", "medium"),
        ("obligations", "high"),
        ("prohibitions", "high"),
        ("licensing_requirements", "high"),
        ("recordkeeping_requirements", "medium"),
        ("reporting_requirements", "medium"),
        ("procedures", "medium"),
    ]

    for bucket, severity in priority_buckets:
        rules = grouped_rules.get(bucket, [])[:5]

        for rule in rules:
            checked += 1
            if _rule_is_covered(policy_text, rule):
                continue

            findings.append({
                "severity": severity,
                "category": bucket,
                "citation": rule.get("citation") or f"{rule.get('law')} Section {rule.get('section')}",
                "issue": f"The draft may not sufficiently cover this {bucket[:-1].replace('_', ' ')}.",
                "requirement": rule.get("summary") or rule.get("text") or "Review the underlying legal rule and ensure it is addressed explicitly.",
                "rule_score": rule.get("match_score", 0),
                "coverage_score": _rule_coverage_score(policy_text, rule),
            })

    if checked >= 4:
        findings.extend(_check_structure(policy_text, intent))
    findings.extend(_check_hygiene(policy_text))

    findings = sorted(
        findings,
        key=lambda item: (
            item.get("severity") == "high",
            item.get("severity") == "medium",
        ),
        reverse=True,
    )

    status = "pass"
    if any(item["severity"] == "high" for item in findings):
        status = "needs_attention"
    elif findings:
        status = "review_recommended"

    return {
        "status": status,
        "checked_rules": checked,
        "findings": findings[:5],
        "issues": findings[:5],
        "intent_subdomain": intent.get("subdomain"),
    }


#prev working version
'''def _normalize(text):
    return " ".join((text or "").lower().split())


def _rule_covered(policy_text, rule):
    policy_lower = _normalize(policy_text)
    keywords = list(rule.get("keywords", []))
    if rule.get("topic"):
        keywords.append(rule["topic"])
    if rule.get("term"):
        keywords.append(rule["term"])

    hits = 0
    for keyword in keywords[:8]:
        keyword = _normalize(keyword)
        if keyword and keyword in policy_lower:
            hits += 1
    return hits >= 1


def review_policy(policy_text, intent, grouped_rules):
    priority_buckets = [
        ("rights", "medium"),
        ("obligations", "high"),
        ("prohibitions", "high"),
        ("licensing_requirements", "high"),
        ("recordkeeping_requirements", "medium"),
        ("reporting_requirements", "medium"),
        ("procedures", "medium"),
    ]

    findings = []
    checked = 0

    for bucket, severity in priority_buckets:
        for rule in grouped_rules.get(bucket, [])[:4]:
            checked += 1
            if _rule_covered(policy_text, rule):
                continue
            findings.append({
                "severity": severity,
                "category": bucket,
                "citation": rule.get("citation") or f"{rule.get('law')} Section {rule.get('section')}",
                "issue": f"The draft may not explicitly cover this {bucket[:-1].replace('_', ' ')}.",
                "requirement": rule.get("summary") or rule.get("text"),
            })

    status = "pass"
    if any(item["severity"] == "high" for item in findings):
        status = "needs_attention"
    elif findings:
        status = "review_recommended"

    return {
        "status": status,
        "checked_rules": checked,
        "findings": findings[:12],
        "intent_subdomain": intent.get("subdomain"),
    }
'''
