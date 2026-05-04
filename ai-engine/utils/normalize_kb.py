import json
import os
import re
import shutil
from typing import Any, Dict, List, Optional


KB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "kb")
BACKUP_DIR = os.path.join(KB_DIR, "_backup_original")


LAW_CONFIGS: Dict[str, Dict[str, Any]] = {
    "THE CLINICAL ESTABLISHMENTS (REGISTRATION AND REGULATION) ACT, 2010": {
        "source_short_name": "Clinical Establishments Act 2010",
        "source_type": "act",
        "issuing_authority": "Parliament of India",
        "ministry": "Ministry of Health and Family Welfare",
        "domain": "healthcare",
        "subdomain": "clinical_establishments",
        "law_family": "core_healthcare",
        "year": 2010,
        "effective_from": "2012-03-01",
        "applies_to": ["hospital", "clinic", "diagnostic_lab"],
        "entity_tags": ["hospital", "clinic", "diagnostic_lab"],
        "authority_tags": ["Central Government", "State Government", "District Registering Authority"],
        "keywords": ["clinical establishment", "registration", "standards", "health facility"],
        "target_folder": "core_healthcare",
    },
    "THE EPIDEMIC DISEASES ACT, 1897": {
        "source_short_name": "Epidemic Diseases Act 1897",
        "source_type": "act",
        "issuing_authority": "Parliament of India",
        "ministry": "Cross-cutting",
        "domain": "healthcare",
        "subdomain": "public_health_emergency",
        "law_family": "cross_cutting",
        "year": 1897,
        "effective_from": None,
        "applies_to": ["government", "hospital", "clinic"],
        "entity_tags": ["public_health_authority", "hospital", "clinic"],
        "authority_tags": ["Central Government", "State Government"],
        "keywords": ["epidemic", "outbreak", "public health", "containment"],
        "target_folder": "cross_cutting",
    },
    "THE MENTAL HEALTHCARE ACT, 2017": {
        "source_short_name": "MHCA 2017",
        "source_type": "act",
        "issuing_authority": "Parliament of India",
        "ministry": "Ministry of Health and Family Welfare",
        "domain": "healthcare",
        "subdomain": "mental_health",
        "law_family": "core_healthcare",
        "year": 2017,
        "effective_from": "2018-05-29",
        "applies_to": ["mental_health_establishment", "hospital", "government"],
        "entity_tags": ["mental_health_establishment", "hospital", "care_provider"],
        "authority_tags": ["Central Government", "State Government", "Mental Health Review Board"],
        "keywords": ["mental health", "patient rights", "treatment", "admission"],
        "target_folder": "core_healthcare",
    },
    "THE NARCOTIC DRUGS AND PSYCHOTROPIC SUBSTANCES ACT, 1985": {
        "source_short_name": "NDPS Act 1985",
        "source_type": "act",
        "issuing_authority": "Parliament of India",
        "ministry": "Cross-cutting",
        "domain": "healthcare",
        "subdomain": "controlled_substances",
        "law_family": "cross_cutting",
        "year": 1985,
        "effective_from": None,
        "applies_to": ["hospital", "doctor", "pharmacy"],
        "entity_tags": ["hospital", "registered_medical_practitioner", "pharmacy"],
        "authority_tags": ["Central Government", "State Government"],
        "keywords": ["narcotic drugs", "psychotropic substances", "controlled medicines"],
        "target_folder": "cross_cutting",
    },
    "THE NATIONAL COMMISSION FOR ALLIED AND HEALTHCARE PROFESSIONS ACT, 2021": {
        "source_short_name": "NCAHP Act 2021",
        "source_type": "act",
        "issuing_authority": "Parliament of India",
        "ministry": "Ministry of Health and Family Welfare",
        "domain": "healthcare",
        "subdomain": "allied_health",
        "law_family": "core_healthcare",
        "year": 2021,
        "effective_from": None,
        "applies_to": ["allied_health_professional", "educational_institution"],
        "entity_tags": ["allied_health_professional", "training_institution"],
        "authority_tags": ["Central Government", "Commission", "State Council"],
        "keywords": ["allied health", "professional regulation", "education", "registration"],
        "target_folder": "core_healthcare",
    },
    "THE DRUGS AND COSMETICS ACT, 1940": {
        "source_short_name": "Drugs and Cosmetics Act 1940",
        "source_type": "act",
        "issuing_authority": "Parliament of India",
        "ministry": "Ministry of Health and Family Welfare",
        "domain": "healthcare",
        "subdomain": "drug_regulation",
        "law_family": "core_healthcare",
        "year": 1940,
        "effective_from": None,
        "applies_to": ["manufacturer", "hospital", "pharmacy"],
        "entity_tags": ["drug_manufacturer", "hospital", "pharmacy"],
        "authority_tags": ["Central Government", "State Government", "Inspector"],
        "keywords": ["drugs", "cosmetics", "quality", "licensing"],
        "target_folder": "core_healthcare",
    },
    "THE MEDICAL TERMINATION OF PREGNANCY ACT, 1971": {
        "source_short_name": "MTP Act 1971",
        "source_type": "act",
        "issuing_authority": "Parliament of India",
        "ministry": "Ministry of Health and Family Welfare",
        "domain": "healthcare",
        "subdomain": "reproductive_health",
        "law_family": "core_healthcare",
        "year": 1971,
        "effective_from": None,
        "applies_to": ["registered_medical_practitioner", "hospital", "clinic"],
        "entity_tags": ["registered_medical_practitioner", "hospital", "clinic"],
        "authority_tags": ["Central Government", "State Government"],
        "keywords": ["pregnancy termination", "reproductive health", "consent", "medical practitioner"],
        "target_folder": "core_healthcare",
    },
    "THE DIGITAL PERSONAL DATA PROTECTION ACT, 2023": {
        "source_short_name": "DPDP Act 2023",
        "source_type": "act",
        "issuing_authority": "Parliament of India",
        "ministry": "Cross-cutting",
        "domain": "healthcare",
        "subdomain": "digital_health_records",
        "law_family": "cross_cutting",
        "year": 2023,
        "effective_from": None,
        "applies_to": ["hospital", "clinic", "digital_health_platform"],
        "entity_tags": ["hospital", "clinic", "digital_health_platform"],
        "authority_tags": ["Central Government", "Data Protection Board"],
        "keywords": ["personal data", "health data", "privacy", "consent"],
        "target_folder": "cross_cutting",
    },
    "THE DISASTER MANAGEMENT ACT, 2005": {
        "source_short_name": "Disaster Management Act 2005",
        "source_type": "act",
        "issuing_authority": "Parliament of India",
        "ministry": "Cross-cutting",
        "domain": "healthcare",
        "subdomain": "public_health_emergency",
        "law_family": "cross_cutting",
        "year": 2005,
        "effective_from": None,
        "applies_to": ["government", "hospital", "district_authority"],
        "entity_tags": ["government", "hospital", "district_authority"],
        "authority_tags": ["National Authority", "State Authority", "District Authority"],
        "keywords": ["disaster management", "emergency response", "public health preparedness"],
        "target_folder": "cross_cutting",
    },
    "THE NATIONAL MEDICAL COMMISSION ACT, 2019": {
        "source_short_name": "NMC Act 2019",
        "source_type": "act",
        "issuing_authority": "Parliament of India",
        "ministry": "Ministry of Health and Family Welfare",
        "domain": "healthcare",
        "subdomain": "medical_education",
        "law_family": "core_healthcare",
        "year": 2019,
        "effective_from": "2020-09-24",
        "applies_to": ["medical_college", "registered_medical_practitioner"],
        "entity_tags": ["medical_college", "registered_medical_practitioner"],
        "authority_tags": ["Central Government", "National Medical Commission", "Autonomous Boards"],
        "keywords": ["medical education", "medical registration", "commission", "licence"],
        "target_folder": "core_healthcare",
    },
    "THE NATIONAL NURSING AND MIDWIFERY COMMISSION ACT, 2023": {
        "source_short_name": "NNMC Act 2023",
        "source_type": "act",
        "issuing_authority": "Parliament of India",
        "ministry": "Ministry of Health and Family Welfare",
        "domain": "healthcare",
        "subdomain": "nursing",
        "law_family": "core_healthcare",
        "year": 2023,
        "effective_from": None,
        "applies_to": ["nurse", "midwife", "educational_institution"],
        "entity_tags": ["nurse", "midwife", "training_institution"],
        "authority_tags": ["Central Government", "National Commission", "State Commission"],
        "keywords": ["nursing", "midwifery", "education", "registration"],
        "target_folder": "core_healthcare",
    },
    "THE TRANSPLANTATION OF HUMAN ORGANS AND TISSUES ACT, 1994": {
        "source_short_name": "THOTA 1994",
        "source_type": "act",
        "issuing_authority": "Parliament of India",
        "ministry": "Ministry of Health and Family Welfare",
        "domain": "healthcare",
        "subdomain": "organ_transplant",
        "law_family": "core_healthcare",
        "year": 1994,
        "effective_from": None,
        "applies_to": ["hospital", "transplant_center", "registered_medical_practitioner"],
        "entity_tags": ["hospital", "transplant_center", "registered_medical_practitioner"],
        "authority_tags": ["Central Government", "State Government", "Authorization Committee"],
        "keywords": ["organ transplant", "tissues", "donation", "authorization"],
        "target_folder": "core_healthcare",
    },
}


LAW_NORMALIZATION = {
    "THE CLINICAL ESTABLISHMENTS (REGISTRATION AND REGULATION)ACT, 2010": "THE CLINICAL ESTABLISHMENTS (REGISTRATION AND REGULATION) ACT, 2010",
    "THE CLINICAL ESTABLISHMENTS (REGISTRATION AND REGULATION) ACT, 2010": "THE CLINICAL ESTABLISHMENTS (REGISTRATION AND REGULATION) ACT, 2010",
    "THE NARCOTIC DRUGS AND PSYCHOTROPIC SUBSTANCES, ACT, 1985": "THE NARCOTIC DRUGS AND PSYCHOTROPIC SUBSTANCES ACT, 1985",
    "THE_DRUGS_AND_COSMETICS_ACT_1940": "THE DRUGS AND COSMETICS ACT, 1940",
    "THE DRUGS AND COSMETICS ACT, 1940": "THE DRUGS AND COSMETICS ACT, 1940",
    "THE_MEDICAL_TERMINATION_OF_PREGNANCY_ACT_1971": "THE MEDICAL TERMINATION OF PREGNANCY ACT, 1971",
    "THE MEDICAL TERMINATION OF PREGNANCY ACT, 1971": "THE MEDICAL TERMINATION OF PREGNANCY ACT, 1971",
    "The Digital Personal Data Protection Act, 2023": "THE DIGITAL PERSONAL DATA PROTECTION ACT, 2023",
    "The Disaster Management Act, 2005": "THE DISASTER MANAGEMENT ACT, 2005",
}


BAD_TEXT_PATTERNS = (
    "not explicitly defined in the text",
    "sections as specified",
    "all the remaining provisions",
    "the text pertains to article 252",
)


TYPE_NORMALIZATION = {
    "scope": "scope",
    "definition": "definition",
    "obligation": "obligation",
    "prohibition": "prohibition",
    "condition": "condition",
    "exception": "exception",
    "penalty": "penalty",
}


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def canonicalize_law(raw_law: Optional[str], filename: str) -> str:
    if raw_law:
        cleaned = re.sub(r"\s+", " ", raw_law.strip())
        if cleaned in LAW_NORMALIZATION:
            return LAW_NORMALIZATION[cleaned]
        return cleaned

    stem = os.path.splitext(os.path.basename(filename))[0]
    stem = stem.replace(".pdf_chunks", "").replace("_chunks", "").replace(".pdf", "")
    stem = stem.replace("_", " ")
    cleaned = re.sub(r"\s+", " ", stem).strip()
    return LAW_NORMALIZATION.get(cleaned, cleaned)


def derive_keywords(text: str, topic: Optional[str], term: Optional[str], base_keywords: List[str]) -> List[str]:
    words = []
    for value in (topic, term):
        if value:
            words.extend(re.findall(r"[A-Za-z][A-Za-z\- ]+", value.lower()))
    if text:
        words.extend(re.findall(r"[A-Za-z][A-Za-z\-]{3,}", text.lower()))

    seen = set()
    result: List[str] = []
    for keyword in base_keywords + words:
        keyword = re.sub(r"\s+", " ", keyword.strip(" -"))
        if not keyword or len(keyword) < 4:
            continue
        if keyword in seen:
            continue
        seen.add(keyword)
        result.append(keyword)
        if len(result) >= 12:
            break
    return result


def infer_applies_to(text: str, existing: List[str]) -> List[str]:
    mapping = {
        "hospital": "hospital",
        "clinic": "clinic",
        "medical practitioner": "registered_medical_practitioner",
        "doctor": "registered_medical_practitioner",
        "nurse": "nurse",
        "midwife": "midwife",
        "mental health establishment": "mental_health_establishment",
        "clinical establishment": "clinic",
        "medical college": "medical_college",
        "transplantation": "transplant_center",
        "transplant": "transplant_center",
        "laboratory": "diagnostic_lab",
        "diagnostic": "diagnostic_lab",
    }
    found = list(existing)
    lower = text.lower()
    for needle, tag in mapping.items():
        if needle in lower and tag not in found:
            found.append(tag)
    return found


def classify_type(rule: Dict[str, Any]) -> str:
    rule_type = str(rule.get("type") or "").strip().lower()
    text = str(rule.get("text") or "").lower()
    topic = str(rule.get("topic") or "").lower()

    if rule_type in TYPE_NORMALIZATION:
        normalized = TYPE_NORMALIZATION[rule_type]
    else:
        normalized = "scope"

    if "right" in topic or text.startswith("every person shall have a right"):
        return "right"
    if normalized == "obligation":
        if "maintain" in text or "record" in text or "register" in text:
            return "recordkeeping_requirement"
        if "report" in text or "inform" in text or "intimate" in text:
            return "reporting_requirement"
        if "license" in text or "licence" in text or "registration" in text:
            return "licensing_requirement"
    if normalized == "scope" and ("procedure" in topic or text.startswith("the manner")):
        return "procedure"
    return normalized


def build_summary(text: str, topic: Optional[str], rule_type: str) -> str:
    clean_text = re.sub(r"\s+", " ", text).strip()
    if not clean_text:
        return ""
    if len(clean_text) <= 180:
        return clean_text
    prefix = f"{topic}: " if topic else ""
    return prefix + clean_text[:177].rstrip() + "..."


def should_skip(rule: Dict[str, Any]) -> bool:
    text = rule.get("text")
    if text is None:
        return True
    if not isinstance(text, str):
        return True

    stripped = re.sub(r"\s+", " ", text).strip()
    if not stripped:
        return True

    lower = stripped.lower()
    if any(pattern in lower for pattern in BAD_TEXT_PATTERNS):
        return True
    if "vide notification no." in lower and "gazette of india" in lower:
        return True
    return False


def normalize_rule(rule: Dict[str, Any], law_name: str, config: Dict[str, Any], filename: str, index: int) -> Dict[str, Any]:
    text = re.sub(r"\s+", " ", str(rule.get("text") or "")).strip()
    topic = re.sub(r"\s+", " ", str(rule.get("topic") or "")).strip() or None
    term = re.sub(r"\s+", " ", str(rule.get("term") or "")).strip() or None
    section = str(rule.get("section") or "").strip() or None
    sub_section = str(rule.get("sub_section") or "").strip() or None
    normalized_type = classify_type(rule)
    applies_to = infer_applies_to(text, list(config["applies_to"]))
    source_title = law_name.title()

    citation_bits = [source_title]
    if section:
        citation_bits.append(f"Section {section}")
    if sub_section:
        citation_bits.append(sub_section)

    normalized: Dict[str, Any] = {
        "id": f"{slugify(config['source_short_name'])}_s{slugify(section or 'na')}_{index:04d}",
        "source_type": config["source_type"],
        "source_title": source_title,
        "source_short_name": config["source_short_name"],
        "source_file": filename,
        "issuing_authority": config["issuing_authority"],
        "ministry": config["ministry"],
        "jurisdiction": "India",
        "domain": config["domain"],
        "subdomain": config["subdomain"],
        "law_family": config["law_family"],
        "language": "en",
        "year": config["year"],
        "effective_from": config["effective_from"],
        "document_version": "original_act",
        "citation": ", ".join(citation_bits),
        "law": source_title,
        "section": section,
        "sub_section": sub_section,
        "clause": None,
        "schedule": None,
        "topic": topic,
        "term": term,
        "type": normalized_type,
        "applies_to": applies_to,
        "entity_tags": config["entity_tags"],
        "authority_tags": config["authority_tags"],
        "keywords": derive_keywords(text, topic, term, config["keywords"]),
        "text": text,
        "summary": build_summary(text, topic, normalized_type),
        "condition_text": text if normalized_type == "condition" else None,
        "exception_text": text if normalized_type == "exception" else None,
        "penalty_text": text if normalized_type == "penalty" else None,
        "cross_references": [],
        "retrieval_boost": 1.0 if config["law_family"] == "core_healthcare" else 0.85,
        "is_repealed": False,
        "is_draft": False,
        "validation_status": "verified",
    }
    return normalized


def backup_file(path: str) -> None:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    shutil.copy2(path, os.path.join(BACKUP_DIR, os.path.basename(path)))


def destination_path(config: Dict[str, Any], law_name: str) -> str:
    folder = os.path.join(KB_DIR, config["target_folder"])
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"{slugify(law_name)}.json")


def normalize_file(path: str) -> Optional[str]:
    filename = os.path.basename(path)
    with open(path, "r", encoding="utf-8") as handle:
        rules = json.load(handle)

    if not isinstance(rules, list) or not rules:
        return None

    first_law = None
    for rule in rules:
        if isinstance(rule, dict) and rule.get("law"):
            first_law = rule.get("law")
            break

    law_name = canonicalize_law(first_law, filename)
    config = LAW_CONFIGS.get(law_name)
    if not config:
        return None

    normalized_rules: List[Dict[str, Any]] = []
    seen = set()

    for index, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict) or should_skip(rule):
            continue
        normalized = normalize_rule(rule, law_name, config, filename, index)
        dedupe_key = (
            normalized["section"],
            normalized["sub_section"],
            normalized["term"],
            normalized["text"],
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized_rules.append(normalized)

    dest = destination_path(config, law_name)
    with open(dest, "w", encoding="utf-8") as handle:
        json.dump(normalized_rules, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return dest


def clean_top_level_jsons() -> None:
    for name in os.listdir(KB_DIR):
        path = os.path.join(KB_DIR, name)
        if os.path.isfile(path) and name.endswith(".json"):
            os.remove(path)


def main() -> None:
    original_paths = [
        os.path.join(KB_DIR, name)
        for name in os.listdir(KB_DIR)
        if name.endswith(".json")
    ]

    for path in original_paths:
        backup_file(path)

    written_paths = []
    for path in original_paths:
        written = normalize_file(path)
        if written:
            written_paths.append(written)

    clean_top_level_jsons()
    print(f"Normalized {len(written_paths)} KB files.")


if __name__ == "__main__":
    main()
