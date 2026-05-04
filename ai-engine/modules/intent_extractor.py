import json
import re


KEYWORD_HINTS = {
    "parental": "parental_leave",
    "maternity": "parental_leave",
    "paternity": "parental_leave",
    "adoption": "parental_leave",
    "caregiver": "parental_leave",
    "single parent": "parental_leave",
    "leave": "employment_policy",
    "employee": "employment_policy",
    "staff": "employment_policy",
    "mental": "mental_health",
    "clinical establishment": "clinical_establishments",
    "clinic": "clinical_establishments",
    "hospital registration": "clinical_establishments",
    "transplant": "organ_transplant",
    "organ": "organ_transplant",
    "pregnan": "reproductive_health",
    "abortion": "reproductive_health",
    "mtp": "reproductive_health",
    "medical college": "medical_education",
    "doctor": "medical_education",
    "nmc": "medical_education",
    "nurs": "nursing",
    "midwi": "nursing",
}


FOCUSED_TERMS = {
    "parental", "leave", "single", "parents", "employee", "staff", "adoption",
    "caregiver", "maternity", "paternity", "eligibility", "benefits", "approval",
    "return", "work", "entitlement", "hospital", "clinic", "doctor", "nurse",
    "records", "grievance", "confidentiality", "consent", "rights", "registration",
    "licensing", "compliance", "reporting",
}


def extract_json(text: str):
    text = text.replace("```json", "").replace("```", "").strip()

    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON object start found in LLM output:\n{text}")

    candidate = text[start:].strip()

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    last_brace = candidate.rfind("}")
    if last_brace != -1:
        trimmed = candidate[: last_brace + 1]
        try:
            return json.loads(trimmed)
        except json.JSONDecodeError:
            pass

    repaired = candidate
    open_braces = repaired.count("{")
    close_braces = repaired.count("}")
    if open_braces > close_braces:
        repaired += "}" * (open_braces - close_braces)

    try:
        return json.loads(repaired)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON from LLM output:\n{text}\n\nParse error: {e}")


def _normalize_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip().lower() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip().lower()]
    return []


def _extract_keywords_from_text(text):
    tokens = set(re.findall(r"[a-z0-9]{4,}", text.lower()))
    return sorted(tokens & FOCUSED_TERMS)


def _infer_subdomain(text):
    lowered = text.lower()
    for needle, subdomain in KEYWORD_HINTS.items():
        if needle in lowered:
            return subdomain
    return None


def normalize_intent(intent, user_input):
    text = user_input.lower()
    inferred_subdomain = _infer_subdomain(user_input)

    normalized = {
        "policy_type": intent.get("policy_type"),
        "industry": intent.get("industry") or "healthcare",
        "jurisdiction": intent.get("jurisdiction") or "India",
        "entity_type": intent.get("entity_type"),
        "risk_level": intent.get("risk_level") or "medium",
        "special_conditions": _normalize_list(intent.get("special_conditions")),
        "domain": intent.get("domain") or "healthcare",
        "subdomain": intent.get("subdomain") or inferred_subdomain,
        "document_kind": intent.get("document_kind") or "policy",
        "applies_to": _normalize_list(intent.get("applies_to")),
        "keywords": _normalize_list(intent.get("keywords")),
        "query_text": user_input.strip(),
    }

    if not normalized["entity_type"]:
        if any(word in text for word in ["employee", "staff", "manager", "hr", "single parent", "parental"]):
            normalized["entity_type"] = "employer"
        elif "hospital" in text or "clinic" in text:
            normalized["entity_type"] = "hospital"
        elif "doctor" in text:
            normalized["entity_type"] = "doctor"
        elif "lab" in text or "diagnostic" in text:
            normalized["entity_type"] = "diagnostic_center"

    if not normalized["applies_to"] and normalized["entity_type"]:
        if normalized["subdomain"] in {"parental_leave", "employment_policy"}:
            normalized["applies_to"] = ["employee", "manager", "hr"]
        else:
            normalized["applies_to"] = [normalized["entity_type"]]

    fallback_keywords = _extract_keywords_from_text(user_input)
    normalized["keywords"] = sorted(set(normalized["keywords"] + fallback_keywords))

    if normalized["subdomain"] in {"parental_leave", "employment_policy"}:
        normalized["keywords"] = sorted(set(normalized["keywords"] + [
            "leave", "eligibility", "entitlement", "approval", "return", "employee"
        ]))

    if not normalized["keywords"]:
        normalized["keywords"] = ["policy"]

    return normalized


def extract_intent(user_input, llm):
    prompt = f"""
You are a legal intent extraction system.

STRICT RULES:
- Output ONLY valid JSON
- No explanations
- No markdown
- No backticks
- Fill fields only from the user request
- Do not force compliance, licensing, registration, penalties, or healthcare-regulation keywords unless the request is actually about them
- If the request is about staff leave, parental leave, maternity/paternity, adoption leave, or single-parent benefits, prefer subdomain values like "parental_leave" or "employment_policy"

Schema:
{{
  "policy_type": string | null,
  "industry": string | null,
  "jurisdiction": string | null,
  "entity_type": string | null,
  "risk_level": "low" | "medium" | "high" | null,
  "special_conditions": string[],
  "domain": string | null,
  "subdomain": string | null,
  "document_kind": string | null,
  "applies_to": string[],
  "keywords": string[]
}}

User input:
{user_input}
"""

    raw = llm(prompt).strip()

    if not raw:
        raise ValueError("LLM returned empty response")

    return normalize_intent(extract_json(raw), user_input)
