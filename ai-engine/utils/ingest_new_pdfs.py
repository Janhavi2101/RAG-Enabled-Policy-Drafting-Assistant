import json
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
import pdfplumber


ROOT = Path(__file__).resolve().parents[1]
KB_DIR = ROOT / "kb"
NEW_PDFS_DIR = KB_DIR / "new_pdfs"


DOCS = [
    {
        "pdf_name": " Employees State Insurance Act, 1948 .pdf",
        "output_folder": "cross_cutting",
        "output_name": "employees_state_insurance_act_1948.json",
        "source_title": "The Employees' State Insurance Act, 1948",
        "source_short_name": "ESI Act 1948",
        "source_type": "act",
        "document_version": "act_1948_compilation",
        "unit_label": "Section",
        "issuing_authority": "Parliament of India",
        "ministry": "Ministry of Labour and Employment",
        "subdomain": "social_insurance",
        "law_family": "cross_cutting",
        "year": 1948,
        "effective_from": None,
        "applies_to": ["employer", "employee", "hospital"],
        "entity_tags": ["employer", "employee", "hospital"],
        "authority_tags": ["Central Government", "Employees' State Insurance Corporation", "State Government"],
        "keywords": ["employees state insurance", "employee benefits", "sickness benefit", "maternity benefit"],
        "related_law": None,
        "body_start": r"(?m)^1\.\s+Short title, extent, commencement and application\.",
        "ocr_mode": "auto",
    },
    {
        "pdf_name": "Employees State Insurance Central Rules, 1950 .pdf",
        "output_folder": "cross_cutting",
        "output_name": "employees_state_insurance_central_rules_1950.json",
        "source_title": "The Employees' State Insurance (Central) Rules, 1950",
        "source_short_name": "ESI Central Rules 1950",
        "source_type": "rules",
        "document_version": "rules_1950_compilation",
        "unit_label": "Rule",
        "issuing_authority": "Central Government",
        "ministry": "Ministry of Labour and Employment",
        "subdomain": "social_insurance",
        "law_family": "cross_cutting",
        "year": 1950,
        "effective_from": None,
        "applies_to": ["employer", "employee", "hospital"],
        "entity_tags": ["employer", "employee", "hospital"],
        "authority_tags": ["Central Government", "Employees' State Insurance Corporation"],
        "keywords": ["employees state insurance", "central rules", "social insurance", "employee benefits"],
        "related_law": "The Employees' State Insurance Act, 1948",
        "body_start": r"(?m)^1\.\s+Short title and extent\.",
        "ocr_mode": "auto",
    },
    {
        "pdf_name": "Employees State Insurance General Regulations, 1950 .pdf",
        "output_folder": "cross_cutting",
        "output_name": "employees_state_insurance_general_regulations_1950.json",
        "source_title": "The Employees' State Insurance (General) Regulations, 1950",
        "source_short_name": "ESI General Regulations 1950",
        "source_type": "regulation",
        "document_version": "regulations_1950_compilation",
        "unit_label": "Regulation",
        "issuing_authority": "Employees' State Insurance Corporation",
        "ministry": "Employees' State Insurance Corporation",
        "subdomain": "social_insurance",
        "law_family": "cross_cutting",
        "year": 1950,
        "effective_from": None,
        "applies_to": ["employer", "employee", "hospital"],
        "entity_tags": ["employer", "employee", "hospital"],
        "authority_tags": ["Employees' State Insurance Corporation", "Central Government"],
        "keywords": ["employees state insurance", "general regulations", "social insurance", "benefits administration"],
        "related_law": "The Employees' State Insurance Act, 1948",
        "body_start": r"(?m)^1\.\s+Short title, commencement and application\.",
        "ocr_mode": "auto",
    },
    {
        "pdf_name": "Ethics-Regulations-2002.pdf",
        "output_folder": "core_healthcare",
        "output_name": "indian_medical_council_professional_conduct_etiquette_and_ethics_regulations_2002.json",
        "source_title": "Indian Medical Council (Professional Conduct, Etiquette and Ethics) Regulations, 2002",
        "source_short_name": "Medical Ethics Regulations 2002",
        "source_type": "regulation",
        "document_version": "regulations_2002_amended_2016",
        "unit_label": "Clause",
        "issuing_authority": "Medical Council of India",
        "ministry": "Medical Council of India",
        "subdomain": "medical_ethics",
        "law_family": "core_healthcare",
        "year": 2002,
        "effective_from": None,
        "applies_to": ["registered_medical_practitioner", "hospital", "clinic"],
        "entity_tags": ["registered_medical_practitioner", "hospital", "clinic"],
        "authority_tags": ["Medical Council of India", "State Medical Council"],
        "keywords": ["medical ethics", "professional conduct", "etiquette", "medical practitioner"],
        "related_law": "Indian Medical Council Act, 1956",
        "body_start": r"Short\s+Title\s+and\s+Commencement:",
        "ocr_mode": "auto",
        "hierarchical": True,
    },
    {
        "pdf_name": "HIV and AIDS Act 2017- English.pdf",
        "output_folder": "core_healthcare",
        "output_name": "hiv_and_aids_prevention_and_control_act_2017.json",
        "source_title": "The Human Immunodeficiency Virus and Acquired Immune Deficiency Syndrome (Prevention and Control) Act, 2017",
        "source_short_name": "HIV and AIDS Act 2017",
        "source_type": "act",
        "document_version": "act_2017",
        "unit_label": "Section",
        "issuing_authority": "Parliament of India",
        "ministry": "Ministry of Health and Family Welfare",
        "subdomain": "hiv_aids",
        "law_family": "core_healthcare",
        "year": 2017,
        "effective_from": None,
        "applies_to": ["hospital", "clinic", "registered_medical_practitioner"],
        "entity_tags": ["hospital", "clinic", "registered_medical_practitioner"],
        "authority_tags": ["Central Government", "State Government", "ombudsman"],
        "keywords": ["hiv", "aids", "anti-discrimination", "consent", "confidentiality"],
        "related_law": None,
        "body_start": r"(?m)^CHAPTER I\s*$",
        "ocr_mode": "auto",
    },
    {
        "pdf_name": "Medical Termination of Pregnancy Amendment Act 2021.pdf",
        "output_folder": "core_healthcare",
        "output_name": "medical_termination_of_pregnancy_amendment_act_2021.json",
        "source_title": "The Medical Termination of Pregnancy (Amendment) Act, 2021",
        "source_short_name": "MTP Amendment Act 2021",
        "source_type": "amendment",
        "document_version": "amendment_act_2021",
        "unit_label": "Section",
        "issuing_authority": "Parliament of India",
        "ministry": "Ministry of Health and Family Welfare",
        "subdomain": "reproductive_health",
        "law_family": "core_healthcare",
        "year": 2021,
        "effective_from": None,
        "applies_to": ["registered_medical_practitioner", "hospital", "clinic"],
        "entity_tags": ["registered_medical_practitioner", "hospital", "clinic"],
        "authority_tags": ["Central Government", "State Government", "Medical Board"],
        "keywords": ["pregnancy termination", "amendment", "medical practitioner", "reproductive health"],
        "related_law": "The Medical Termination of Pregnancy Act, 1971",
        "body_start": r"(?m)^1\.\s+\(1\)\s+This Act may be called the Medical Termination of Pregnancy",
        "ocr_mode": "auto",
    },
    {
        "pdf_name": "Mental Healthcare (Central Mental Health Authority adn Mental Health Review Boards) Rules, 2018.pdf",
        "output_folder": "core_healthcare",
        "output_name": "mental_healthcare_central_mental_health_authority_and_mental_health_review_boards_rules_2018.json",
        "source_title": "Mental Healthcare (Central Mental Health Authority and Mental Health Review Boards) Rules, 2018",
        "source_short_name": "MHCA Central Authority Rules 2018",
        "source_type": "rules",
        "document_version": "rules_2018",
        "unit_label": "Rule",
        "issuing_authority": "Central Government",
        "ministry": "Ministry of Health and Family Welfare",
        "subdomain": "mental_health",
        "law_family": "core_healthcare",
        "year": 2018,
        "effective_from": "2018-05-29",
        "applies_to": ["mental_health_establishment", "hospital", "government"],
        "entity_tags": ["mental_health_establishment", "hospital", "care_provider"],
        "authority_tags": ["Central Government", "Central Mental Health Authority", "Mental Health Review Board"],
        "keywords": ["mental healthcare", "central authority", "review board", "mental health"],
        "related_law": "The Mental Healthcare Act, 2017",
        "body_start": r"Mental Healthcare \(Central Mental Health Authority\s+and Mental Health Review Boards\) Rules, 2018\.",
        "ocr_mode": "auto",
    },
    {
        "pdf_name": "Mental Healthcare (Rights of Persons with Mental Illness) Rules, 2018.pdf",
        "output_folder": "core_healthcare",
        "output_name": "mental_healthcare_rights_of_persons_with_mental_illness_rules_2018.json",
        "source_title": "Mental Healthcare (Rights of Persons with Mental Illness) Rules, 2018",
        "source_short_name": "MHCA Rights Rules 2018",
        "source_type": "rules",
        "document_version": "rules_2018",
        "unit_label": "Rule",
        "issuing_authority": "Central Government",
        "ministry": "Ministry of Health and Family Welfare",
        "subdomain": "mental_health",
        "law_family": "core_healthcare",
        "year": 2018,
        "effective_from": "2018-05-29",
        "applies_to": ["mental_health_establishment", "hospital", "government"],
        "entity_tags": ["mental_health_establishment", "hospital", "care_provider"],
        "authority_tags": ["Central Government", "State Government", "Mental Health Review Board"],
        "keywords": ["mental healthcare", "rights", "mental illness", "community rehabilitation"],
        "related_law": "The Mental Healthcare Act, 2017",
        "body_start": r"(?m)^CHAPTER\s+[–-]\s*I\s*$",
        "ocr_mode": "auto",
    },
    {
        "pdf_name": "Mental Healthcare (State Mental Health Authority) Rules, 2018.pdf",
        "output_folder": "core_healthcare",
        "output_name": "mental_healthcare_state_mental_health_authority_rules_2018.json",
        "source_title": "Mental Healthcare (State Mental Health Authority) Rules, 2018",
        "source_short_name": "MHCA State Authority Rules 2018",
        "source_type": "rules",
        "document_version": "rules_2018",
        "unit_label": "Rule",
        "issuing_authority": "Central Government",
        "ministry": "Ministry of Health and Family Welfare",
        "subdomain": "mental_health",
        "law_family": "core_healthcare",
        "year": 2018,
        "effective_from": "2018-05-29",
        "applies_to": ["mental_health_establishment", "hospital", "government"],
        "entity_tags": ["mental_health_establishment", "hospital", "care_provider"],
        "authority_tags": ["Central Government", "State Government", "State Mental Health Authority"],
        "keywords": ["mental healthcare", "state authority", "mental health", "governance"],
        "related_law": "The Mental Healthcare Act, 2017",
        "body_start": r"(?m)^CHAPTER\s+[–-]\s*I\s*$",
        "ocr_mode": "auto",
    },
    {
        "pdf_name": "Clinical Establishment (Central Government) Rules, 2012.pdf",
        "output_folder": "core_healthcare",
        "output_name": "clinical_establishments_central_government_rules_2012.json",
        "source_title": "Clinical Establishments (Central Government) Rules, 2012",
        "source_short_name": "Clinical Establishments Rules 2012",
        "source_type": "rules",
        "document_version": "rules_2012",
        "unit_label": "Rule",
        "issuing_authority": "Central Government",
        "ministry": "Ministry of Health and Family Welfare",
        "subdomain": "clinical_establishments",
        "law_family": "core_healthcare",
        "year": 2012,
        "effective_from": None,
        "applies_to": ["hospital", "clinic", "diagnostic_lab"],
        "entity_tags": ["hospital", "clinic", "diagnostic_lab"],
        "authority_tags": ["Central Government", "National Council", "District Registering Authority"],
        "keywords": ["clinical establishments", "registration", "rules", "diagnostic laboratory"],
        "related_law": "The Clinical Establishments (Registration and Regulation) Act, 2010",
        "body_start": r"1\.\s+Short title and commencement[—-]",
        "ocr_mode": "ocr",
    },
    {
        "pdf_name": "NEW DRUGS ANDctrS RULE, 2019.pdf",
        "output_folder": "core_healthcare",
        "output_name": "new_drugs_and_clinical_trials_rules_2019.json",
        "source_title": "The New Drugs and Clinical Trials Rules, 2019",
        "source_short_name": "NDCT Rules 2019",
        "source_type": "rules",
        "document_version": "rules_2019",
        "unit_label": "Rule",
        "issuing_authority": "Central Government",
        "ministry": "Ministry of Health and Family Welfare",
        "subdomain": "drug_regulation",
        "law_family": "core_healthcare",
        "year": 2019,
        "effective_from": None,
        "applies_to": ["drug_manufacturer", "hospital", "registered_medical_practitioner"],
        "entity_tags": ["drug_manufacturer", "hospital", "registered_medical_practitioner"],
        "authority_tags": ["Central Government", "Central Licensing Authority", "Ethics Committee"],
        "keywords": ["new drugs", "clinical trials", "drug regulation", "ethics committee"],
        "related_law": "The Drugs and Cosmetics Act, 1940",
        "body_start": r"(?m)^CHAPTER I\s*$",
        "ocr_mode": "auto",
    },
    {
        "pdf_name": "THE MATERNITY BENEFIT ACT, 1961.pdf",
        "output_folder": "cross_cutting",
        "output_name": "maternity_benefit_act_1961.json",
        "source_title": "The Maternity Benefit Act, 1961",
        "source_short_name": "Maternity Benefit Act 1961",
        "source_type": "act",
        "document_version": "act_1961_compilation",
        "unit_label": "Section",
        "issuing_authority": "Parliament of India",
        "ministry": "Ministry of Labour and Employment",
        "subdomain": "employee_benefits",
        "law_family": "cross_cutting",
        "year": 1961,
        "effective_from": None,
        "applies_to": ["employer", "employee", "hospital"],
        "entity_tags": ["employer", "employee", "hospital"],
        "authority_tags": ["Central Government", "State Government", "Inspector"],
        "keywords": ["maternity benefit", "employee benefits", "women employees", "leave"],
        "related_law": None,
        "body_start": r"(?m)^1\.\s+Short title, extent and commencement\.",
        "ocr_mode": "auto",
    },
    {
        "pdf_name": "THE SEXUAL HARASSMENT OF WOMEN AT WORKPLACE (PREVENTION, PROHIBITION AND REDRESSAL) ACT, 2013.pdf",
        "output_folder": "cross_cutting",
        "output_name": "sexual_harassment_of_women_at_workplace_act_2013.json",
        "source_title": "The Sexual Harassment of Women at Workplace (Prevention, Prohibition and Redressal) Act, 2013",
        "source_short_name": "POSH Act 2013",
        "source_type": "act",
        "document_version": "act_2013_compilation",
        "unit_label": "Section",
        "issuing_authority": "Parliament of India",
        "ministry": "Ministry of Women and Child Development",
        "subdomain": "workplace_harassment",
        "law_family": "cross_cutting",
        "year": 2013,
        "effective_from": None,
        "applies_to": ["employer", "employee", "hospital"],
        "entity_tags": ["employer", "employee", "hospital"],
        "authority_tags": ["Central Government", "District Officer", "Internal Committee"],
        "keywords": ["sexual harassment", "workplace", "internal committee", "employer duties"],
        "related_law": None,
        "body_start": r"ACT NO\.\s+14 OF 2013",
        "ocr_mode": "auto",
    },
    {
        "pdf_name": "THOA_2011 amendment and rules.pdf",
        "output_folder": "core_healthcare",
        "output_name": "transplantation_of_human_organs_and_tissues_rules_and_amendment_compilation.json",
        "source_title": "The Transplantation of Human Organs and Tissues Rules and Amendment Compilation",
        "source_short_name": "THOTA Rules Compilation",
        "source_type": "rules",
        "document_version": "rules_and_amendment_compilation",
        "unit_label": "Provision",
        "issuing_authority": "Central Government",
        "ministry": "Ministry of Health and Family Welfare",
        "subdomain": "organ_transplant",
        "law_family": "core_healthcare",
        "year": 2014,
        "effective_from": None,
        "applies_to": ["hospital", "transplant_center", "registered_medical_practitioner"],
        "entity_tags": ["hospital", "transplant_center", "registered_medical_practitioner"],
        "authority_tags": ["Central Government", "Appropriate Authority", "Authorization Committee"],
        "keywords": ["organ transplant", "tissues", "rules", "authorization committee"],
        "related_law": "The Transplantation of Human Organs and Tissues Act, 1994",
        "body_start": r"1\.\s+Short title, application and commencement",
        "ocr_mode": "ocr",
    },
    {
        "pdf_name": "The Occupational Safety, Health and Working Conditions Code, 2020  .pdf",
        "output_folder": "cross_cutting",
        "output_name": "occupational_safety_health_and_working_conditions_code_2020.json",
        "source_title": "The Occupational Safety, Health and Working Conditions Code, 2020",
        "source_short_name": "OSHWC Code 2020",
        "source_type": "code",
        "document_version": "code_2020",
        "unit_label": "Section",
        "issuing_authority": "Parliament of India",
        "ministry": "Ministry of Labour and Employment",
        "subdomain": "workplace_safety",
        "law_family": "cross_cutting",
        "year": 2020,
        "effective_from": None,
        "applies_to": ["employer", "employee", "hospital"],
        "entity_tags": ["employer", "employee", "hospital"],
        "authority_tags": ["Central Government", "State Government", "Inspector-cum-Facilitator"],
        "keywords": ["occupational safety", "working conditions", "employee welfare", "health and safety"],
        "related_law": None,
        "body_start": r"(?m)^CHAPTER I\s*$",
        "ocr_mode": "auto",
    },
    {
        "pdf_name": "the_rights_of_persons_with_disabilities_act,_2016.pdf",
        "output_folder": "cross_cutting",
        "output_name": "rights_of_persons_with_disabilities_act_2016.json",
        "source_title": "The Rights of Persons with Disabilities Act, 2016",
        "source_short_name": "RPwD Act 2016",
        "source_type": "act",
        "document_version": "act_2016",
        "unit_label": "Section",
        "issuing_authority": "Parliament of India",
        "ministry": "Ministry of Social Justice and Empowerment",
        "subdomain": "disability_rights",
        "law_family": "cross_cutting",
        "year": 2016,
        "effective_from": None,
        "applies_to": ["employer", "employee", "hospital"],
        "entity_tags": ["person_with_disability", "employer", "hospital"],
        "authority_tags": ["Central Government", "State Government", "Chief Commissioner"],
        "keywords": ["disability rights", "accessibility", "reasonable accommodation", "non-discrimination"],
        "related_law": None,
        "body_start": r"(?m)^CHAPTER I\s*$",
        "ocr_mode": "auto",
    },
]


HEADER_PATTERNS = [
    r"THE GAZETTE OF INDIA.*",
    r"REGISTERED NO\..*",
    r"REGD\. NO\..*",
    r"PUBLISHED BY AUTHORITY.*",
    r"EXTRAORDINARY.*",
    r"PART II.*",
    r"MINISTRY OF LAW AND JUSTICE.*",
    r"New Delhi,.*",
    r"^\[\d+\]$",
    r"^\d+\s*$",
    r"^\(\d+\)\s*$",
]


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def clean_line(line: str) -> str:
    line = line.replace("\x0c", " ")
    line = re.sub(r"\s+", " ", line).strip()
    line = re.sub(r"\.{3,}", " ", line)
    return line


def is_englishish(line: str) -> bool:
    if not line:
        return False
    if re.search(r"[\u0900-\u097F]", line):
        letters = sum(ch.isalpha() for ch in line)
        ascii_letters = sum(("a" <= ch.lower() <= "z") for ch in line)
        return ascii_letters >= max(6, letters // 2)
    return True


def strip_noise(text: str) -> str:
    cleaned_lines = []
    for raw_line in text.splitlines():
        line = clean_line(raw_line)
        if not line:
            cleaned_lines.append("")
            continue
        if not is_englishish(line):
            continue
        if any(re.match(pattern, line, flags=re.IGNORECASE) for pattern in HEADER_PATTERNS):
            continue
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text_pages(path: Path, ocr_mode: str) -> tuple[list[str], str]:
    pages = []
    used_ocr = False
    doc = fitz.open(str(path))
    with TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        plumber_texts = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                plumber_texts.append(page.extract_text(x_tolerance=2, y_tolerance=2) or "")

        total_pages = max(len(plumber_texts), doc.page_count)
        for index in range(total_pages):
            extracted = ""
            if index < len(plumber_texts):
                extracted = plumber_texts[index]
            else:
                extracted = doc[index].get_text("text") or ""

            compact = re.sub(r"\s+", "", extracted)
            needs_ocr = ocr_mode == "ocr" or len(compact) < 80
            if needs_ocr:
                used_ocr = True
                pix = doc[index].get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
                image_path = tmp_dir / f"page_{index + 1}.png"
                pix.save(str(image_path))
                result = subprocess.run(
                    ["tesseract", str(image_path), "stdout", "-l", "eng", "--psm", "6"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                page_text = result.stdout or extracted
            else:
                page_text = extracted
            pages.append(strip_noise(page_text))
    return pages, ("ocr_extracted" if used_ocr else "text_extracted")


def select_body(text: str, start_pattern: str) -> str:
    matches = list(re.finditer(start_pattern, text, flags=re.IGNORECASE))
    if matches:
        return text[matches[-1].start():].strip()
    return text


def split_into_chunks(text: str, hierarchical: bool = False) -> list[tuple[str, str, str]]:
    pattern = (
        r"(?m)^[\"'‘\[]?(?P<num>\d+(?:\.\d+){1,3})\s+(?P<title>[^\n]{3,200})$"
        if hierarchical
        else r"(?m)^[\"'‘\[]?(?P<num>\d+[A-Z]?)\.\s+(?P<title>[^\n]{3,200})$"
    )
    matches = list(re.finditer(pattern, text))
    chunks = []
    for idx, match in enumerate(matches):
        number = match.group("num").strip()
        title = clean_line(match.group("title"))
        if not title or "contents" in title.lower():
            continue
        if re.search(r"\b\d{1,3}$", title) and "—" not in title and "-" not in title:
            continue
        if len(title) > 180:
            title = re.split(r"\s+[—-]\s+", title, maxsplit=1)[0]
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = clean_line(text[start:end])
        if len(body) < 25:
            continue
        chunks.append((number, title, body))
    return chunks


def infer_type(title: str, text: str) -> str:
    lower = f"{title} {text[:600]}".lower()
    if "definition" in lower or re.search(r"\bmeans\b", lower):
        return "definition"
    if "penalt" in lower or "punish" in lower or "fine" in lower:
        return "penalty"
    if "right" in lower:
        return "right"
    if "prohibit" in lower or "shall not" in lower or lower.startswith("no "):
        return "prohibition"
    if "procedure" in lower or "application for" in lower:
        return "procedure"
    if "duty" in lower or "shall" in lower or "must" in lower:
        return "obligation"
    return "scope"


def derive_keywords(text: str, title: str, base_keywords: list[str]) -> list[str]:
    words = list(base_keywords)
    for value in [title, text[:500]]:
        words.extend(re.findall(r"[A-Za-z][A-Za-z\-]{3,}", value.lower()))
    seen = set()
    result = []
    for word in words:
        word = re.sub(r"\s+", " ", word.strip(" -"))
        if not word or word in seen or len(word) < 4:
            continue
        seen.add(word)
        result.append(word)
        if len(result) >= 14:
            break
    return result


def infer_applies_to(text: str, seed: list[str]) -> list[str]:
    mapping = {
        "hospital": "hospital",
        "clinic": "clinic",
        "employee": "employee",
        "employer": "employer",
        "medical practitioner": "registered_medical_practitioner",
        "doctor": "registered_medical_practitioner",
        "diagnostic": "diagnostic_lab",
        "laboratory": "diagnostic_lab",
        "transplant": "transplant_center",
        "mental health establishment": "mental_health_establishment",
    }
    found = list(seed)
    lower = text.lower()
    for needle, tag in mapping.items():
        if needle in lower and tag not in found:
            found.append(tag)
    return found


def build_summary(text: str) -> str:
    text = clean_line(text)
    if len(text) <= 220:
        return text
    return text[:217].rstrip() + "..."


def make_chunk(config: dict, number: str, title: str, text: str, index: int, status: str) -> dict:
    if "." in number and not number.endswith("."):
        section = number.split(".")[0]
        sub_section = number
    else:
        section = number
        sub_section = None

    chunk_type = infer_type(title, text)
    citation_bits = [config["source_title"], f'{config["unit_label"]} {number}']
    cross_refs = [config["related_law"]] if config["related_law"] else []

    return {
        "id": f'{slugify(config["source_short_name"])}_{slugify(number)}_{index:04d}',
        "source_type": config["source_type"],
        "source_title": config["source_title"],
        "source_short_name": config["source_short_name"],
        "source_file": config["pdf_name"],
        "issuing_authority": config["issuing_authority"],
        "ministry": config["ministry"],
        "jurisdiction": "India",
        "domain": "healthcare",
        "subdomain": config["subdomain"],
        "law_family": config["law_family"],
        "language": "en",
        "year": config["year"],
        "effective_from": config["effective_from"],
        "document_version": config["document_version"],
        "citation": ", ".join(citation_bits),
        "law": config["source_title"],
        "section": section,
        "sub_section": sub_section,
        "clause": None,
        "schedule": "Schedule" if "schedule" in title.lower() else None,
        "topic": title,
        "term": title if chunk_type == "definition" else None,
        "type": chunk_type,
        "applies_to": infer_applies_to(text, config["applies_to"]),
        "entity_tags": config["entity_tags"],
        "authority_tags": config["authority_tags"],
        "keywords": derive_keywords(text, title, config["keywords"]),
        "text": text,
        "summary": build_summary(text),
        "condition_text": text if chunk_type == "condition" else None,
        "exception_text": text if chunk_type == "exception" else None,
        "penalty_text": text if chunk_type == "penalty" else None,
        "cross_references": cross_refs,
        "retrieval_boost": 1.0 if config["law_family"] == "core_healthcare" else 0.85,
        "is_repealed": False,
        "is_draft": False,
        "validation_status": status,
    }


def process_document(config: dict) -> None:
    pdf_path = NEW_PDFS_DIR / config["pdf_name"]
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    pages, status = extract_text_pages(pdf_path, config["ocr_mode"])
    text = "\n\n".join(page for page in pages if page)
    text = select_body(text, config["body_start"])
    text = re.sub(r"\n{3,}", "\n\n", text)
    chunks = split_into_chunks(text, hierarchical=config.get("hierarchical", False))
    if not chunks:
        raise RuntimeError(f"No chunks parsed for {config['pdf_name']}")

    records = [make_chunk(config, number, title, body, idx + 1, status) for idx, (number, title, body) in enumerate(chunks)]
    output_dir = KB_DIR / config["output_folder"]
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / config["output_name"]
    output_path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(records)} chunks to {output_path}")


def main() -> None:
    for config in DOCS:
        process_document(config)


if __name__ == "__main__":
    main()
