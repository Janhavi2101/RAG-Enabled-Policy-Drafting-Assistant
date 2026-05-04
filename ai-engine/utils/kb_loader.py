import os
import json


DEFAULT_RULE_FIELDS = {
    "law": "",
    "section": "",
    "sub_section": "",
    "citation": "",
    "domain": "",
    "subdomain": "",
    "jurisdiction": "",
    "type": "",
    "topic": "",
    "term": "",
    "summary": "",
    "text": "",
    "keywords": [],
    "applies_to": [],
    "entity_tags": [],
    "law_family": "",
    "retrieval_boost": 1.0,
}


def normalize_rule(rule, source_file=""):
    if not isinstance(rule, dict):
        return None

    normalized = dict(DEFAULT_RULE_FIELDS)
    normalized.update(rule)

    normalized["source_file"] = normalized.get("source_file") or source_file

    if not isinstance(normalized.get("keywords"), list):
        normalized["keywords"] = []

    if not isinstance(normalized.get("applies_to"), list):
        normalized["applies_to"] = []

    if not isinstance(normalized.get("entity_tags"), list):
        normalized["entity_tags"] = []

    return normalized


def load_legal_kb(path="kb"):
    all_rules = []

    if not os.path.exists(path):
        print(f"⚠️ Warning: KB folder '{path}' not found.")
        return []

    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith("_")]

        for file in files:
            if not file.endswith(".json"):
                continue

            file_path = os.path.join(root, file)

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    rules = json.load(f)

                if isinstance(rules, list):
                    for rule in rules:
                        normalized = normalize_rule(rule, source_file=file)
                        if normalized:
                            all_rules.append(normalized)

            except Exception as e:
                print(f"❌ Error loading file {file}: {e}")

    return all_rules





#prev working version

'''import os
import json

def load_legal_kb(path="kb"):
    all_rules = []

    # Safety check: Ensure the folder exists before trying to read
    if not os.path.exists(path):
        print(f"⚠️ Warning: KB folder '{path}' not found.")
        return []

    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        for file in files:
            if not file.endswith(".json"):
                continue

            file_path = os.path.join(root, file)

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    rules = json.load(f)

                    if isinstance(rules, list):
                        for rule in rules:
                            rule["source_file"] = rule.get("source_file", file)
                            all_rules.append(rule)
            except Exception as e:
                print(f"❌ Error loading file {file}: {e}")

    return all_rules
'''