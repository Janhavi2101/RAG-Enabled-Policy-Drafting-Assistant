def check_feasibility(intent, grouped_rules):
    if not grouped_rules.get("all"):
        return {
            "status": "insufficient_legal_match",
            "warnings": [],
        }

    warnings = []

    for rule in grouped_rules.get("obligations", [])[:1]:
        warnings.append(
            f"Mandatory: {(rule.get('summary') or rule['text'])[:180]} "
            f"({rule['law']} Section {rule['section']})"
        )

    for rule in grouped_rules.get("licensing_requirements", [])[:1]:
        warnings.append(
            f"Licensing/registration requirement: {(rule.get('summary') or rule['text'])[:180]} "
            f"({rule['law']} Section {rule['section']})"
        )

    for rule in grouped_rules.get("prohibitions", [])[:1]:
        warnings.append(
            f"Do not omit: {(rule.get('summary') or rule['text'])[:180]} "
            f"({rule['law']} Section {rule['section']})"
        )

    status = "allowed_with_conditions" if warnings else "allowed"

    return {
        "status": status,
        "warnings": warnings
    }
