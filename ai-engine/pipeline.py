import time

from modules.intent_extractor import extract_intent
from modules.law_matcher import match_laws, group_rules
from modules.feasibility_checker import check_feasibility
from modules.drafter import draft_policy
from modules.citations import (
    extract_citations,
    extract_inline_references,
    format_references,
    merge_citations,
)
from modules.compliance_review import review_policy
from modules.retriever import HybridRetriever


KB_SUPPORTED_SUBDOMAINS = {
    "clinical_establishments",
    "mental_health",
    "organ_transplant",
    "reproductive_health",
    "medical_education",
    "nursing",
    "allied_health",
    "drug_regulation",
    "digital_health_records",
    "public_health_emergency",
}


def run_pipeline(user_input, llm, legal_kb, precedents=None, current_content=""):
    total_start = time.time()
    print("\n--- PIPELINE START ---")

    # 1. Intent Extraction
    step_start = time.time()
    intent = extract_intent(user_input, llm)
    print(f"[TIME] Intent Extraction: {time.time() - step_start:.2f}s")

    # enrich intent with sections
    step_start = time.time()
    intent["sections_required"] = detect_sections(intent)
    print(f"[TIME] Detect Sections: {time.time() - step_start:.2f}s")

    # 2. Retrieval Layer
    step_start = time.time()
    retriever = HybridRetriever(legal_kb)
    print(f"[TIME] Retriever Init: {time.time() - step_start:.2f}s")

    kb_supported = intent.get("subdomain") in KB_SUPPORTED_SUBDOMAINS

    step_start = time.time()
    retrieved_docs = []
    if kb_supported:
        retrieved_docs = retriever.retrieve(
            query=user_input,
            metadata_filter={
                "domain": intent.get("domain"),
                "subdomain": intent.get("subdomain"),
            },
            k=8,
        )
    print(f"[TIME] Main Retrieval: {time.time() - step_start:.2f}s")

    step_start = time.time()
    matched = match_laws(intent, retrieved_docs) if retrieved_docs else []
    grouped = group_rules(matched)
    print(f"[TIME] Match + Group Rules: {time.time() - step_start:.2f}s")

    intent["kb_supported_subdomain"] = kb_supported
    intent["kb_match_count"] = len(matched)
    intent["draft_mode"] = "law_grounded" if matched else "generic_policy"

    # 3. Feasibility Check
    step_start = time.time()
    feasibility = check_feasibility(intent, grouped)
    print(f"[TIME] Feasibility Check: {time.time() - step_start:.2f}s")

    # 4. Section-Aware Drafting
    step_start = time.time()
    section_contexts = {}

    for section in intent["sections_required"][:2]:
        section_fetch_start = time.time()
        section_docs = []
        if kb_supported and retrieved_docs:
            section_docs = retriever.retrieve(
                query=f"{intent.get('subdomain', '')} {section}",
                metadata_filter={"subdomain": intent.get("subdomain")},
                k=2,
            )
        section_contexts[section] = section_docs
        print(f"[TIME] Section Retrieval ({section}): {time.time() - section_fetch_start:.2f}s")

    print(f"[TIME] Total Section Retrieval: {time.time() - step_start:.2f}s")

    step_start = time.time()
    policy = draft_policy(
        intent,
        grouped,
        llm,
        precedents=precedents,
        current_content=current_content,
        section_contexts=section_contexts,
    )
    print(f"[TIME] Draft Policy: {time.time() - step_start:.2f}s")

    # 5. Citations
    step_start = time.time()
    kb_citations = extract_citations(grouped)
    inline_citations = extract_inline_references(policy)
    citations = merge_citations(kb_citations, inline_citations)
    references = format_references(citations)
    final_policy = policy
    if references.strip():
        final_policy += "\n\n## References\n\n" + references
    print(f"[TIME] Citations + References: {time.time() - step_start:.2f}s")

    # 6. Compliance Review
    step_start = time.time()
    review = review_policy(final_policy, intent, grouped)
    print(f"[TIME] Compliance Review: {time.time() - step_start:.2f}s")

    print(f"[TIME] TOTAL PIPELINE: {time.time() - total_start:.2f}s")
    print("--- PIPELINE END ---\n")

    return {
        "intent": intent,
        "feasibility": feasibility,
        "policy": final_policy,
        "citations": citations,
        "review": review,
        "matched_rules": matched[:15],
        "precedents": precedents or [],
    }


def detect_sections(intent):
    subdomain = intent.get("subdomain", "")

    if "clinical" in subdomain:
        return ["scope", "registration", "compliance", "records", "penalties"]

    if "data" in subdomain:
        return ["definitions", "data_collection", "processing", "security", "breach"]

    if "employment" in subdomain:
        return ["scope", "eligibility", "conduct", "discipline", "termination"]

    if "parental" in subdomain or "leave" in subdomain:
        return ["purpose", "eligibility", "leave_entitlement", "approval_process", "return_to_work"]

    # fallback
    return ["scope", "definitions", "compliance", "penalties"]



#-------------------------------------------------------------------------
#-------------------------------------------------------------------------
#-------------------------------------------------------------------------

#prev working version without section-aware drafting and hybrid retrieval:

'''from modules.intent_extractor import extract_intent
from modules.law_matcher import match_laws, group_rules
from modules.feasibility_checker import check_feasibility
from modules.drafter import draft_policy
from modules.citations import extract_citations, format_references
from modules.compliance_review import review_policy


def run_pipeline(user_input, llm, legal_kb, precedents=None, current_content=""):
    intent = extract_intent(user_input, llm)
    matched = match_laws(intent, legal_kb)
    grouped = group_rules(matched)
    feasibility = check_feasibility(intent, grouped)

    policy = draft_policy(
        intent,
        grouped,
        llm,
        precedents=precedents,
        current_content=current_content,
    )

    citations = extract_citations(grouped)
    references = format_references(citations)
    final_policy = policy + "\n\n## References\n\n" + references
    review = review_policy(final_policy, intent, grouped)

    return {
        "intent": intent,
        "feasibility": feasibility,
        "policy": final_policy,
        "citations": citations,
        "review": review,
        "matched_rules": matched[:15],
        "precedents": precedents or [],
    }
'''
