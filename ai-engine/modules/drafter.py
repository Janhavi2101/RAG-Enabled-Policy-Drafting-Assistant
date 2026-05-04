import json
import re
from difflib import SequenceMatcher


TEMPLATE_LIBRARY = {
    "default": [
        "Purpose and Objectives",
        "Scope and Applicability",
        "Definitions",
        "Governance and Responsibilities",
        "Operational Requirements",
        "Compliance and Review",
    ],
    "clinical_establishments": [
        "Purpose and Objectives",
        "Scope and Applicability",
        "Definitions",
        "Registration and Licensing",
        "Clinical Operations and Standards",
        "Medical Records and Documentation",
        "Compliance and Reporting",
        "Enforcement and Penalties",
        "Review and Amendments",
    ],
    "mental_health": [
        "Purpose and Objectives",
        "Scope and Applicability",
        "Definitions",
        "Eligibility and Access",
        "Consent and Patient Rights",
        "Clinical Operations and Standards",
        "Medical Records and Documentation",
        "Grievance Redressal",
        "Review and Amendments",
    ],
    "reproductive_health": [
        "Purpose and Objectives",
        "Scope and Applicability",
        "Eligibility and Access",
        "Clinical Operations and Standards",
        "Medical Records and Documentation",
        "Compliance and Reporting",
        "Review and Amendments",
    ],
    "organ_transplant": [
        "Purpose and Objectives",
        "Scope and Applicability",
        "Definitions",
        "Eligibility and Access",
        "Registration and Licensing",
        "Clinical Operations and Standards",
        "Medical Records and Documentation",
        "Compliance and Reporting",
        "Enforcement and Penalties",
        "Review and Amendments",
    ],
    "parental_leave": [
        "Purpose and Objectives",
        "Scope and Applicability",
        "Eligibility",
        "Leave Entitlement",
        "Application and Approval Process",
        "Benefits and Protections",
        "Return to Work and Recordkeeping",
        "Review and Exceptions",
    ],
    "employment_policy": [
        "Purpose and Objectives",
        "Scope and Applicability",
        "Eligibility",
        "Employee Entitlements",
        "Application and Approval Process",
        "Manager and HR Responsibilities",
        "Confidentiality and Records",
        "Review and Amendments",
    ],
}


SECTION_TYPE_HINTS = {
    "Purpose and Objectives": ["scope", "rights", "obligations"],
    "Scope and Applicability": ["scope", "definitions"],
    "Definitions": ["definitions"],
    "Eligibility": ["rights", "conditions", "exceptions"],
    "Eligibility and Access": ["rights", "conditions", "exceptions"],
    "Registration and Licensing": ["licensing_requirements", "procedures", "authority_powers"],
    "Clinical Operations and Standards": ["obligations", "prohibitions", "procedures"],
    "Medical Records and Documentation": ["recordkeeping_requirements", "reporting_requirements", "obligations"],
    "Compliance and Reporting": ["reporting_requirements", "obligations", "penalties"],
    "Enforcement and Penalties": ["penalties", "prohibitions", "authority_powers"],
    "Benefits and Protections": ["rights", "obligations", "exceptions"],
    "Application and Approval Process": ["procedures", "conditions", "recordkeeping_requirements"],
    "Return to Work and Recordkeeping": ["recordkeeping_requirements", "procedures", "rights"],
    "Review and Exceptions": ["exceptions", "conditions", "procedures"],
    "Manager and HR Responsibilities": ["obligations", "procedures"],
    "Confidentiality and Records": ["recordkeeping_requirements", "rights", "obligations"],
    "Operational Requirements": ["obligations", "procedures", "conditions"],
    "Compliance and Review": ["obligations", "procedures", "penalties"],
    "Review and Amendments": ["procedures", "authority_powers"],
    "Grievance Redressal": ["rights", "procedures"],
}


def extract_json_array(text: str):
    if not text:
        raise ValueError("LLM returned empty output")

    text = text.replace("```json", "").replace("```", "").strip()
    match = re.search(r"\[[\s\S]*?\]", text)

    if not match:
        raise ValueError(f"No JSON array found in LLM output:\n{text}")

    parsed = json.loads(match.group())
    return [str(item).strip() for item in parsed if str(item).strip()]


def choose_template(intent):
    subdomain = (intent.get("subdomain") or "").strip().lower()
    return TEMPLATE_LIBRARY.get(subdomain) or TEMPLATE_LIBRARY["default"]


def limit_rules(grouped_rules, per_group_limit=2, total_limit=10):
    limited = []
    for group_name, rules in grouped_rules.items():
        if group_name == "all":
            continue
        limited.extend(rules[:per_group_limit])
    return limited[:total_limit]


def relevant_rules_for_section(section, grouped_rules, limit=6):
    desired_groups = SECTION_TYPE_HINTS.get(section, ["obligations", "procedures", "rights"])
    ranked = []
    seen = set()

    for group_name in desired_groups:
        for rule in grouped_rules.get(group_name, []):
            key = rule.get("id") or f"{rule.get('law')}:{rule.get('section')}:{rule.get('sub_section')}"
            if key in seen:
                continue
            seen.add(key)
            ranked.append((rule.get("match_score", 0), rule))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [rule for _, rule in ranked[:limit]]


def _normalize_precedents(precedents, limit=2):
    normalized = []
    for idx, item in enumerate((precedents or [])[:limit], start=1):
        if isinstance(item, dict):
            text = item.get("snippet") or item.get("text") or item.get("content") or ""
            title = item.get("title") or f"Policy precedent {idx}"
        else:
            text = str(item)
            title = f"Policy precedent {idx}"

        snippet = " ".join(text.split())[:320].strip()
        if snippet:
            normalized.append({
                "title": title,
                "snippet": snippet,
            })
    return normalized


def _strip_placeholder_lines(text):
    cleaned_lines = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        if not stripped:
            cleaned_lines.append(line)
            continue
        if lower in {
            "# new policy document",
            "new policy document",
            "generated content will appear here...",
        }:
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def _summarize_existing_context(text, limit=700):
    text = _strip_placeholder_lines(text)
    if not text:
        return ""
    paragraphs = [" ".join(p.split()) for p in text.split("\n\n")]
    keep = []
    total = 0
    for paragraph in paragraphs:
        if not paragraph:
            continue
        if paragraph.startswith("#"):
            continue
        if total + len(paragraph) > limit:
            break
        keep.append(paragraph)
        total += len(paragraph)
    return "\n\n".join(keep).strip()


def _clean_section_output(section, text):
    text = _strip_placeholder_lines(text)
    if not text:
        return text

    cleaned_lines = []
    section_tokens = set(re.findall(r"[a-z0-9]{4,}", section.lower()))

    for line in text.splitlines():
        stripped = line.strip()
        lower = stripped.lower().lstrip("#").strip()

        if not stripped:
            cleaned_lines.append("")
            continue

        if stripped.startswith("#"):
            heading_tokens = set(re.findall(r"[a-z0-9]{4,}", lower))
            if heading_tokens and (
                heading_tokens == section_tokens
                or len(heading_tokens & section_tokens) >= max(1, len(section_tokens) - 1)
            ):
                continue
            if lower in {
                "new policy document",
                "purpose and objectives",
                "scope and applicability",
                "eligibility",
                "application and approval process",
                "benefits and protections",
                "return to work and recordkeeping",
                "review and exceptions",
            }:
                continue

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


def _dedupe_paragraphs(section_text, prior_sections):
    paragraphs = [p.strip() for p in section_text.split("\n\n") if p.strip()]
    if not paragraphs:
        return section_text

    prior_paragraphs = []
    for value in prior_sections.values():
        prior_paragraphs.extend([p.strip() for p in value.split("\n\n") if p.strip()])

    kept = []
    for paragraph in paragraphs:
        normalized = " ".join(paragraph.lower().split())
        duplicate = False
        for prior in prior_paragraphs:
            prior_norm = " ".join(prior.lower().split())
            if normalized == prior_norm:
                duplicate = True
                break
            if len(normalized) > 80 and SequenceMatcher(None, normalized, prior_norm).ratio() > 0.82:
                duplicate = True
                break
        if not duplicate:
            kept.append(paragraph)

    return "\n\n".join(kept).strip() or section_text.strip()


def generate_outline(intent, grouped_rules, llm):
    template = choose_template(intent)
    rules = limit_rules(grouped_rules, per_group_limit=1, total_limit=5)

    prompt = f"""
You are a legal policy drafting assistant.

Generate a structured outline for a professional policy document.

STRICT RULES:
- Output ONLY a JSON array
- No explanations
- No markdown
- Keep section names formal and practical
- Prefer the baseline template unless there is a strong reason to adapt it
- Return between 6 and 8 sections

Policy intent:
{json.dumps(intent, indent=2)}

Baseline template:
{json.dumps(template, indent=2)}

Relevant legal rules:
{json.dumps(rules, indent=2)}
"""

    raw = llm(prompt)

    if not raw:
        return template

    try:
        sections = extract_json_array(raw.strip())
        return sections[:8] if sections else template
    except Exception:
        return template


def draft_section(
    section,
    intent,
    rules,
    llm,
    precedents=None,
    current_content="",
    section_context=None,
):
    precedent_context = _normalize_precedents(precedents, limit=2)
    existing_context = _summarize_existing_context(current_content, limit=700)
    retrieved_context = _normalize_precedents(section_context, limit=2)

    prompt = f"""
Draft the section titled "{section}" for a policy document.

STRICT REQUIREMENTS:
- Use formal, clear, organization-ready policy language
- Stay tightly aligned to the user intent
- Do not switch topics
- If the request is about parental leave, staff benefits, or HR policy, do not drift into healthcare facility licensing, inspections, medical education, or hospital compliance law
- Use short numbered clauses where appropriate
- Be specific, practical, and implementable
- If relevant legal rules are provided, cite them in square brackets using the provided citation strings
- If no relevant legal rules are provided, do not invent citations
- Use precedent excerpts only to improve practical structure and wording, not as legal authority
- Do not include a references section
- Write ONLY the body content for this section
- Do not output H1/H2/H3 headings
- Do not repeat the section title
- Do not restate previously drafted sections such as purpose, scope, or eligibility unless strictly necessary for one short cross-reference

Policy intent:
{json.dumps(intent, indent=2)}

Relevant legal rules:
{json.dumps(rules, indent=2)}

Relevant policy precedent excerpts:
{json.dumps(precedent_context, indent=2)}

Retrieved section context:
{json.dumps(retrieved_context, indent=2)}

Existing drafted content:
{existing_context or "None"}
"""

    response = llm(prompt)

    if not response or not response.strip():
        raise ValueError(f"LLM returned empty response for section {section}")

    return _clean_section_output(section, response.strip())


def assemble_policy(sections_dict):
    document = ""
    for i, (title, content) in enumerate(sections_dict.items(), start=1):
        document += f"\n## {i}. {title}\n\n{content}\n"
    return document.strip()


def draft_policy(
    intent,
    grouped_rules,
    llm,
    precedents=None,
    current_content="",
    section_contexts=None,
):
    sections = generate_outline(intent, grouped_rules, llm)
    policy_sections = {}
    rolling_context = (current_content or "").strip()
    section_contexts = section_contexts or {}

    for section in sections:
        section_rules = relevant_rules_for_section(section, grouped_rules, limit=6)
        section_docs = section_contexts.get(section, [])
        try:
            section_text = draft_section(
                section,
                intent,
                section_rules,
                llm,
                precedents=precedents,
                current_content=rolling_context,
                section_context=section_docs,
            )
            section_text = _dedupe_paragraphs(section_text, policy_sections)
            policy_sections[section] = section_text
            rolling_context = (
                rolling_context
                + "\n\n"
                + f"Section completed: {section}\n"
                + " ".join(section_text.split())[:500]
            ).strip()
        except Exception as e:
            policy_sections[section] = (
                f"This section could not be generated automatically and requires manual review. "
                f"[Generation error: {str(e)}]"
            )

    return assemble_policy(policy_sections)
