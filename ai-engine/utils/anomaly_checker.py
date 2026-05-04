import os
import re
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from sentence_transformers import SentenceTransformer

from models.vae_model import PolicyDraftVAE
from modules.compliance_review import review_policy
from modules.intent_extractor import normalize_intent
from modules.law_matcher import group_rules, match_laws
from utils.pdf_utils import extract_text_from_pdf


LOW_THRESHOLD = float(os.environ.get("POLICY_VAE_LOW_THRESHOLD", "0.33"))
HIGH_THRESHOLD = float(os.environ.get("POLICY_VAE_HIGH_THRESHOLD", "0.66"))
EMBEDDING_MODEL_NAME = os.environ.get("POLICY_VALIDATION_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
USE_MOCK_SCORING = os.environ.get("POLICY_VAE_USE_MOCK", "").lower() in {"1", "true", "yes"}
REFERENCE_CORPUS_LIMIT = int(os.environ.get("POLICY_REFERENCE_CORPUS_LIMIT", "350"))
REFERENCE_POLICY_PDF_LIMIT = int(os.environ.get("POLICY_REFERENCE_POLICY_PDF_LIMIT", "18"))
ENABLE_SECTION_WISE_REVIEW = os.environ.get("POLICY_ENABLE_SECTION_WISE_REVIEW", "true").lower() in {"1", "true", "yes"}

SUBDOMAIN_ALIASES = {
    "employee_benefits": {"employee_benefits", "parental_leave", "employment_policy"},
    "parental_leave": {"employee_benefits", "parental_leave", "employment_policy"},
    "employment_policy": {"employee_benefits", "parental_leave", "employment_policy"},
}

POLICY_SECTION_MARKERS = {
    "purpose",
    "scope",
    "definitions",
    "applicability",
    "eligibility",
    "compliance",
    "governance",
    "responsibilities",
    "reporting",
    "records",
    "penalties",
    "review",
}

POLICY_SECTION_GROUPS = {
    "purpose_scope": {"purpose", "objectives", "scope", "applicability"},
    "definitions": {"definitions", "interpretation"},
    "eligibility": {"eligibility", "entitlement", "access"},
    "procedures": {"procedure", "procedures", "approval", "application", "process"},
    "operations": {"compliance", "governance", "responsibilities", "records", "documentation", "reporting"},
    "review": {"review", "amendments", "exceptions", "return to work"},
}

POLICY_TERMS = {
    "policy",
    "shall",
    "must",
    "compliance",
    "procedure",
    "applicable",
    "employee",
    "hospital",
    "records",
    "review",
    "documentation",
    "confidentiality",
    "responsibility",
}

NON_POLICY_RED_FLAGS = {
    "invoice",
    "receipt",
    "order id",
    "shipping",
    "cart",
    "product",
    "chapter",
    "abstract",
    "bibliography",
    "semester",
    "marks",
    "recipe",
}

FORMAL_POLICY_TERMS = {
    "shall",
    "must",
    "policy",
    "procedure",
    "documentation",
    "records",
    "compliance",
    "applicable",
    "authority",
    "patient",
    "hospital",
}

INFORMAL_DRAFT_TERMS = {
    "we",
    "our",
    "you",
    "your",
    "i",
    "us",
}

GENERIC_CONFLICT_TOKENS = {
    "obtained", "employed", "provided", "required", "person", "persons", "means",
    "include", "including", "applicable", "following", "thereof", "therein",
    "section", "rule", "clause", "provision", "another", "other", "during",
    "within", "under", "such", "where", "when",
}

HIGH_VALUE_POLICY_TOKENS = {
    "consent", "informed", "interpreter", "disclosure", "confidentiality", "privacy",
    "record", "records", "documentation", "patient", "guardian", "emergency",
    "eligibility", "entitlement", "benefit", "approval", "authorization",
    "reporting", "register", "medical", "clinical", "treatment", "language",
    "communication", "rights", "obligation", "prohibition", "security", "data",
}


def _normalize(text):
    return " ".join((text or "").lower().split())


def _tokenize(*values):
    tokens = set()
    for value in values:
        if not value:
            continue
        if isinstance(value, (list, tuple, set)):
            tokens.update(_tokenize(*value))
            continue
        tokens.update(re.findall(r"[a-z0-9_]{4,}", _normalize(value)))
    return tokens


def _heading_candidates(text):
    headings = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            headings.append(line.lstrip("#").strip())
            continue
        if len(line) > 80:
            continue
        if re.match(r"^(\d+(\.\d+)?|[ivx]+)[\).\s-]+", line.lower()):
            headings.append(line)
            continue
        title_like = line == line.upper() or sum(1 for c in line if c.isupper()) >= max(2, len(line) // 5)
        if title_like and len(line.split()) <= 8:
            headings.append(line)
    return headings


def _section_group_hits(headings):
    heading_text = " ".join(headings).lower()
    hits = set()

    for group, markers in POLICY_SECTION_GROUPS.items():
        if any(marker in heading_text for marker in markers):
            hits.add(group)

    return hits


def _severity_weight(level):
    return {"high": 1.0, "medium": 0.6, "low": 0.3}.get(str(level).lower(), 0.4)


def _split_sentences(text):
    candidates = re.split(r"(?<=[\.\?!;:])\s+|\n+", text or "")
    return [segment.strip() for segment in candidates if len(segment.strip()) >= 40]


def _sentences_for_token(sentences, token):
    token = str(token or "").lower()
    return [sentence for sentence in sentences if token in sentence.lower()]


def _modality(sentence):
    lower = sentence.lower()
    negative_markers = [
        "shall not", "must not", "not eligible", "ineligible", "prohibited",
        "forbidden", "no person shall", "not entitled", "cannot", "may not",
        "without", "unless",
    ]
    positive_markers = [
        "shall", "must", "eligible", "entitled", "allowed", "permitted",
        "required", "will", "is to be", "may be granted",
    ]

    if any(marker in lower for marker in negative_markers):
        return "negative"
    if any(marker in lower for marker in positive_markers):
        return "positive"
    return "neutral"


def _content_tokens(text):
    stopwords = {
        "policy", "draft", "section", "shall", "must", "with", "from", "that", "this", "under",
        "have", "has", "into", "during", "after", "before", "such", "their", "they", "them",
        "being", "where", "which", "there", "here", "through", "would", "could", "should",
        "employee", "employees", "hospital", "healthcare", "patient", "patients",
    }
    tokens = re.findall(r"[a-z][a-z_]{3,}", (text or "").lower())
    return {token for token in tokens if token not in stopwords}


def _candidate_conflict_tokens(draft_tokens, reference_tokens):
    shared = draft_tokens & reference_tokens
    return sorted(shared, key=lambda token: (-len(token), token))


def _meaningful_conflict_tokens(draft_text, reference_text):
    draft_tokens = _content_tokens(draft_text)
    reference_tokens = _content_tokens(reference_text)
    shared = draft_tokens & reference_tokens
    prioritized = [token for token in shared if token in HIGH_VALUE_POLICY_TOKENS]
    if prioritized:
        return sorted(prioritized, key=lambda token: (-len(token), token))
    filtered = [
        token for token in shared
        if token not in GENERIC_CONFLICT_TOKENS and len(token) >= 6
    ]
    return sorted(filtered, key=lambda token: (-len(token), token))


def _normative_rule_type(rule_type):
    return str(rule_type or "").lower() in {
        "right",
        "obligation",
        "prohibition",
        "procedure",
        "recordkeeping_requirement",
        "reporting_requirement",
        "licensing_requirement",
        "condition",
        "exception",
    }


def _infer_section_group(title, text=""):
    haystack = f"{title or ''} {text or ''}".lower()
    for group, markers in POLICY_SECTION_GROUPS.items():
        if any(marker in haystack for marker in markers):
            return group
    return "general"


def _split_into_sections(text):
    sections = []
    current = None

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                current["lines"].append("")
            continue

        is_heading = False
        heading_text = line

        if line.startswith("#"):
            is_heading = True
            heading_text = line.lstrip("#").strip()
        elif re.match(r"^\d+\.\s+[A-Z]", line):
            is_heading = True
        elif len(line) <= 80 and (
            line.isupper()
            or sum(1 for c in line if c.isupper()) >= max(2, len(line) // 5)
        ) and len(line.split()) <= 10:
            is_heading = True

        if is_heading:
            if current and current["text"].strip():
                sections.append(current)
            current = {
                "title": heading_text,
                "lines": [],
                "text": "",
                "group": _infer_section_group(heading_text),
            }
            continue

        if current is None:
            current = {
                "title": "Preamble",
                "lines": [],
                "text": "",
                "group": "purpose_scope",
            }

        current["lines"].append(line)

    if current:
        current["text"] = "\n".join(current["lines"]).strip()
        if current["text"]:
            sections.append(current)

    for section in sections:
        section["text"] = "\n".join(section["lines"]).strip()
        section["group"] = _infer_section_group(section["title"], section["text"])
        section["sentence_count"] = len(_split_sentences(section["text"]))

    return [section for section in sections if section["text"]]


class DraftAnomalyService:
    def __init__(self, base_dir, legal_kb=None):
        self.base_dir = Path(base_dir)
        self.device = torch.device("cpu")
        self.model_path = self.base_dir / "saved_models" / "vae_model.pth"
        self.embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME, local_files_only=True)
        self.model = None
        self.model_mode = "mock"
        self.thresholds = {}
        self.embedding_model_name = EMBEDDING_MODEL_NAME
        self.legal_kb = legal_kb or []
        self.reference_texts = self._build_reference_texts(self.legal_kb)
        self.reference_embeddings = self._encode_reference_texts(self.reference_texts)
        self.reference_policy_profiles = self._build_reference_policy_profiles()
        self._load_model()

    def _load_model(self):
        if USE_MOCK_SCORING or not self.model_path.exists():
            self.model = None
            self.model_mode = "mock"
            return

        checkpoint = torch.load(self.model_path, map_location=self.device)

        config = checkpoint.get("config", {}) if isinstance(checkpoint, dict) else {}
        self.thresholds = checkpoint.get("thresholds", {}) if isinstance(checkpoint, dict) else {}

        if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
            state_dict = checkpoint["state_dict"]
        else:
            state_dict = checkpoint

        input_dim = int(config.get("input_dim") or self._infer_input_dim(state_dict))
        latent_dim = int(config.get("latent_dim") or 64)
        hidden_dim = int(config.get("hidden_dim") or 256)
        model = PolicyDraftVAE(input_dim=input_dim, latent_dim=latent_dim, hidden_dim=hidden_dim)
        model.load_state_dict(state_dict)
        model.to(self.device)
        model.eval()

        self.model = model
        self.model_mode = "vae"
        self.embedding_model_name = config.get("embedding_model") or EMBEDDING_MODEL_NAME

    def _infer_input_dim(self, state_dict):
        weight = state_dict.get("encoder.0.weight")
        if weight is not None:
            return int(weight.shape[1])
        return 384

    def _build_reference_texts(self, legal_kb):
        if not legal_kb:
            return []

        texts = []
        seen = set()

        for rule in legal_kb:
            parts = [
                str(rule.get("law") or "").strip(),
                str(rule.get("topic") or "").strip(),
                str(rule.get("term") or "").strip(),
                str(rule.get("summary") or "").strip(),
                str(rule.get("text") or "").strip()[:320],
            ]
            combined = " | ".join(part for part in parts if part)
            normalized = _normalize(combined)
            if len(normalized) < 40 or normalized in seen:
                continue
            seen.add(normalized)
            texts.append(combined)
            if len(texts) >= REFERENCE_CORPUS_LIMIT:
                break

        return texts

    def _encode_reference_texts(self, texts):
        if not texts:
            return None
        vectors = self.embedding_model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return np.asarray(vectors, dtype=np.float32)

    def _build_reference_policy_profiles(self):
        pdf_dir = self.base_dir / "kb" / "new_pdfs"
        if not pdf_dir.exists():
            return []

        profiles = []
        for pdf_path in sorted(pdf_dir.glob("*.pdf"))[:REFERENCE_POLICY_PDF_LIMIT]:
            try:
                text = extract_text_from_pdf(pdf_path)
            except Exception:
                continue

            if len(text) < 1200:
                continue

            headings = _heading_candidates(text)
            section_groups = _section_group_hits(headings)
            sentences = _split_sentences(text)
            if not sentences:
                continue

            text_embedding = self.embedding_model.encode(
                text[:12000],
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            text_embedding = np.asarray(text_embedding, dtype=np.float32)

            profiles.append({
                "name": pdf_path.name,
                "text": text,
                "headings": headings[:20],
                "sections": _split_into_sections(text)[:24],
                "heading_count": len(headings),
                "section_group_count": len(section_groups),
                "section_groups": sorted(section_groups),
                "formal_term_count": len(_tokenize(text) & FORMAL_POLICY_TERMS),
                "informal_term_count": len(_tokenize(text) & INFORMAL_DRAFT_TERMS),
                "sentences": sentences[:240],
                "embedding": text_embedding,
            })

        return profiles

    def validate_text(self, text, filename="uploaded.pdf"):
        normalized_text = _normalize(text)
        embedding = self.embedding_model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        embedding = np.asarray(embedding, dtype=np.float32)

        reconstruction_error = self._reconstruction_error(embedding, len(text))
        similarity = self._reference_similarity(embedding)
        structure = self._structure_analysis(text, normalized_text)
        compliance = self._compliance_analysis(text)
        reference_policy = self._reference_policy_analysis(text, embedding, structure)
        similarity = self._adjust_similarity_assessment(similarity, reference_policy)
        section_review = self._section_wise_review(text, compliance, reference_policy) if ENABLE_SECTION_WISE_REVIEW else {
            "issues": [],
            "conflicts": [],
            "reviews": [],
            "recommendations": [],
            "risk_score": 0.0,
        }
        legal_conflicts = self._combine_conflicts(
            self._detect_rule_conflicts(text, compliance.get("matched_rule_objects") or []),
        )
        policy_conflicts = self._combine_conflicts(
            reference_policy["conflicts"],
            section_review["conflicts"],
        )
        compliance_gaps = self._combine_issues(
            self._collect_compliance_gaps(compliance["issues"], compliance["matched_rules"]),
        )
        conflicts = self._combine_conflicts(legal_conflicts, policy_conflicts)

        issues = self._combine_issues(
            structure["issues"],
            compliance["issues"],
            similarity["issues"],
            reference_policy["issues"],
            section_review["issues"],
        )
        recommendations = self._build_recommendations(
            issues,
            structure,
            compliance,
            similarity,
            reference_policy,
            section_review,
        )

        effective_similarity = max(
            float(similarity["max_similarity"]),
            float(reference_policy.get("top_similarity", 0.0)),
        )
        reconstruction_component = self._normalize_reconstruction_error(reconstruction_error)
        component_scores = {
            "reconstruction": reconstruction_component,
            "similarity_gap": 1.0 - effective_similarity,
            "structure": structure["risk_score"],
            "compliance": max(compliance["risk_score"], reference_policy["risk_score"], section_review["risk_score"]),
        }

        anomaly_score = (
            component_scores["reconstruction"] * 0.2
            + component_scores["similarity_gap"] * 0.3
            + component_scores["structure"] * 0.2
            + component_scores["compliance"] * 0.3
        )
        anomaly_score = round(float(min(max(anomaly_score, 0.0), 1.0)), 6)

        risk_level, message = map_risk(
            anomaly_score,
            effective_similarity,
            compliance["high_severity_count"],
            structure["heading_count"],
        )

        return {
            "filename": filename,
            "anomaly_score": anomaly_score,
            "risk_level": risk_level,
            "message": message,
            "recommendation": recommendations[0] if recommendations else "Manual review recommended.",
            "recommendations": recommendations[:5],
            "text_length": len(text),
            "validation_mode": self.model_mode,
            "reconstruction_error": round(float(reconstruction_error), 6),
            "reference_similarity": round(float(effective_similarity), 6),
            "matched_rules": compliance["matched_rules"][:5],
            "matched_rule_count": len(compliance["matched_rules"] or []),
            "conflicts": conflicts[:8],
            "conflict_count": len(conflicts),
            "issues": issues[:8],
            "legal_conflicts": legal_conflicts[:8],
            "legal_conflict_count": len(legal_conflicts),
            "policy_conflicts": policy_conflicts[:8],
            "policy_conflict_count": len(policy_conflicts),
            "compliance_gaps": compliance_gaps[:8],
            "compliance_gap_count": len(compliance_gaps),
            "compliance_status": compliance["status"],
            "embedding_model": self.embedding_model_name,
            "reference_policy_matches": reference_policy["matches"][:3],
            "section_reviews": section_review["reviews"][:8],
            "section_review_enabled": ENABLE_SECTION_WISE_REVIEW,
        }

    def _reconstruction_error(self, embedding, text_length):
        if self.model is None:
            return self._mock_score(embedding, text_length)

        tensor = torch.tensor(embedding, dtype=torch.float32, device=self.device).unsqueeze(0)
        with torch.no_grad():
            reconstruction, _, _ = self.model.reconstruct(tensor)
            return float(F.mse_loss(reconstruction, tensor).item())

    def _normalize_reconstruction_error(self, error):
        if not self.thresholds:
            return min(error / 0.04, 1.0)

        p95 = float(self.thresholds.get("p95_error", 0.02) or 0.02)
        p99 = float(self.thresholds.get("p99_error", p95 * 1.5) or (p95 * 1.5))

        if error <= p95:
            return min(error / max(p95, 1e-8), 0.65)

        if error <= p99:
            span = max(p99 - p95, 1e-8)
            return min(0.65 + ((error - p95) / span) * 0.25, 0.9)

        overflow = max(error - p99, 0.0)
        return min(0.9 + overflow / max(p99, 1e-8), 1.0)

    def _mock_score(self, embedding, text_length):
        spread = float(np.var(embedding))
        density = float(np.mean(np.abs(embedding)))
        length_factor = min(max(text_length, 250), 8000) / 8000.0
        score = 0.01 + (spread * 0.14) + (density * 0.03) + (1.0 - length_factor) * 0.015
        return min(max(score, 0.008), 0.08)

    def _reference_similarity(self, embedding):
        if self.reference_embeddings is None or not len(self.reference_embeddings):
            return {"max_similarity": 0.0, "mean_top_similarity": 0.0, "issues": []}

        similarities = np.matmul(self.reference_embeddings, embedding)
        top = np.sort(similarities)[-5:]
        max_similarity = float(np.max(similarities))
        mean_top_similarity = float(np.mean(top))
        issues = []

        if max_similarity < 0.28:
            issues.append({
                "severity": "high",
                "category": "document_fit",
                "issue": "This PDF is weakly aligned with the legal/policy corpus used by the assistant.",
                "requirement": "Confirm that the uploaded file is actually a drafted policy and not an unrelated document.",
            })
        elif max_similarity < 0.38:
            issues.append({
                "severity": "medium",
                "category": "document_fit",
                "issue": "The draft only partially resembles known policy and legal reference material.",
                "requirement": "Review document structure, scope, and legal grounding before accepting it.",
            })

        return {
            "max_similarity": max_similarity,
            "mean_top_similarity": mean_top_similarity,
            "issues": issues,
        }

    def _structure_analysis(self, text, normalized_text):
        headings = _heading_candidates(text)
        heading_text = " ".join(headings).lower()
        heading_hits = sum(1 for marker in POLICY_SECTION_MARKERS if marker in heading_text)
        section_groups = _section_group_hits(headings)
        policy_term_hits = len(_tokenize(normalized_text) & POLICY_TERMS)
        red_flag_hits = sum(1 for flag in NON_POLICY_RED_FLAGS if flag in normalized_text)
        issues = []

        if len(text) < 900:
            issues.append({
                "severity": "medium",
                "category": "structure",
                "issue": "The uploaded document is unusually short for a complete policy draft.",
                "requirement": "Ensure the draft includes scope, obligations, procedures, and review language.",
            })

        if len(headings) < 3:
            issues.append({
                "severity": "high" if len(headings) == 0 else "medium",
                "category": "structure",
                "issue": "The document lacks clear policy-style section headings.",
                "requirement": "Use explicit sections such as Purpose, Scope, Definitions, Compliance, and Review.",
            })

        if heading_hits < 2 and len(section_groups) < 3:
            issues.append({
                "severity": "medium",
                "category": "structure",
                "issue": "Expected policy sections such as scope, compliance, records, or review are not clearly visible.",
                "requirement": "Make the policy structure more auditable by adding clearer sections for scope, process, governance, and review.",
            })

        if policy_term_hits < 5:
            issues.append({
                "severity": "medium",
                "category": "document_fit",
                "issue": "The text does not use much policy-oriented language.",
                "requirement": "Check whether the uploaded file is a policy draft or another document type.",
            })

        if red_flag_hits >= 2:
            issues.append({
                "severity": "high",
                "category": "document_fit",
                "issue": "The PDF contains terms more typical of unrelated business, academic, or transactional documents.",
                "requirement": "Upload a policy draft PDF rather than an invoice, article, or generic report.",
            })

        risk_score = min(sum(_severity_weight(item["severity"]) for item in issues) / 3.0, 1.0)
        return {
            "issues": issues,
            "risk_score": risk_score,
            "heading_count": len(headings),
            "heading_hits": heading_hits,
            "section_group_count": len(section_groups),
            "headings": headings[:20],
            "section_groups": sorted(section_groups),
        }

    def _build_intent_from_text(self, text):
        preview = " ".join((text or "").split())[:12000]
        first_heading = ""
        for heading in _heading_candidates(text):
            first_heading = heading
            if heading:
                break

        lower_preview = preview.lower()
        inferred_subdomain = None
        entity_type = None

        if any(term in lower_preview for term in ["maternity", "pregnancy", "maternal", "prenatal", "postnatal", "child birth"]):
            inferred_subdomain = "employee_benefits"
            entity_type = "employer"
        elif any(term in lower_preview for term in ["paternity", "parental leave", "adoption leave", "caregiver leave"]):
            inferred_subdomain = "parental_leave"
            entity_type = "employer"
        elif any(term in lower_preview for term in ["employee benefit", "leave entitlement", "return to work", "hr policy"]):
            inferred_subdomain = "employment_policy"
            entity_type = "employer"

        seed_intent = {
            "policy_type": first_heading or "uploaded policy draft",
            "industry": "healthcare",
            "jurisdiction": "India",
            "entity_type": entity_type,
            "risk_level": "medium",
            "special_conditions": [],
            "domain": "healthcare",
            "subdomain": inferred_subdomain,
            "document_kind": "policy",
            "applies_to": [],
            "keywords": [],
        }
        return normalize_intent(seed_intent, preview)

    def _candidate_rules_for_intent(self, intent):
        if not self.legal_kb:
            return []

        subdomain = intent.get("subdomain")
        aliases = SUBDOMAIN_ALIASES.get(subdomain, {subdomain} if subdomain else set())
        keyword_text = " ".join(intent.get("keywords", []) + intent.get("applies_to", []))
        keyword_tokens = _tokenize(keyword_text)

        filtered = []
        for rule in self.legal_kb:
            rule_subdomain = str(rule.get("subdomain") or "").lower()
            rule_tokens = _tokenize(
                rule.get("law"),
                rule.get("topic"),
                rule.get("term"),
                rule.get("summary"),
                rule.get("keywords", []),
            )

            if aliases and rule_subdomain in aliases:
                filtered.append(rule)
                continue

            if aliases and aliases & {"employee_benefits", "parental_leave", "employment_policy"}:
                if keyword_tokens and len(keyword_tokens & rule_tokens) >= 2:
                    filtered.append(rule)
                continue

            if subdomain and rule_subdomain and rule_subdomain != subdomain:
                continue

            filtered.append(rule)

        return filtered or self.legal_kb

    def _compliance_analysis(self, text):
        if not self.legal_kb:
            return {
                "issues": [],
                "risk_score": 0.0,
                "matched_rules": [],
                "status": "unavailable",
                "high_severity_count": 0,
            }

        intent = self._build_intent_from_text(text)
        candidate_rules = self._candidate_rules_for_intent(intent)
        matched = match_laws(intent, candidate_rules, limit=24, per_law_cap=6)
        if matched:
            top_score = matched[0].get("match_score", 0) or 0
            min_score = max(6.0, top_score * 0.45)
            matched = [rule for rule in matched if (rule.get("match_score", 0) or 0) >= min_score]
        grouped = group_rules(matched)
        review = review_policy(text, intent, grouped)
        findings = review.get("findings") or []
        risk_score = min(sum(_severity_weight(item.get("severity")) for item in findings[:6]) / 4.0, 1.0)
        high_count = sum(1 for item in findings if item.get("severity") == "high")

        if not matched:
            findings = [{
                "severity": "high",
                "category": "document_fit",
                "issue": "No meaningful healthcare-policy rule matches were found for this document.",
                "requirement": "This usually indicates the PDF is not a policy draft in the assistant's target domain.",
            }]
            risk_score = max(risk_score, 0.8)
            high_count = max(high_count, 1)

        matched_rules = []
        for rule in matched[:5]:
            matched_rules.append({
                "law": rule.get("law"),
                "citation": rule.get("citation") or f"{rule.get('law')} Section {rule.get('section')}",
                "summary": (rule.get("summary") or rule.get("text") or "")[:180],
                "match_score": rule.get("match_score", 0),
                "type": rule.get("type"),
            })

        return {
            "issues": findings,
            "risk_score": risk_score,
            "matched_rules": matched_rules,
            "matched_rule_objects": matched[:12],
            "status": review.get("status", "review_recommended"),
            "high_severity_count": high_count,
        }

    def _reference_policy_analysis(self, text, embedding, structure):
        if not self.reference_policy_profiles:
            return {
                "issues": [],
                "risk_score": 0.0,
                "matches": [],
                "conflicts": [],
            }

        draft_tokens = _tokenize(text)
        draft_formal = len(draft_tokens & FORMAL_POLICY_TERMS)
        draft_informal = len(draft_tokens & INFORMAL_DRAFT_TERMS)
        draft_sentences = _split_sentences(text)
        matches = []

        for profile in self.reference_policy_profiles:
            similarity = float(np.dot(profile["embedding"], embedding))
            matches.append({
                "name": profile["name"],
                "similarity": round(similarity, 6),
                "heading_count": profile["heading_count"],
                "section_group_count": profile["section_group_count"],
                "section_groups": profile["section_groups"],
                "headings": profile["headings"][:8],
                "profile": profile,
            })

        matches.sort(key=lambda item: item["similarity"], reverse=True)
        top_matches = matches[:3]
        issues = []
        conflicts = []

        if top_matches and top_matches[0]["similarity"] < 0.34:
            issues.append({
                "severity": "medium",
                "category": "reference_policy_fit",
                "issue": "The draft does not closely resemble the structure and language of the reference policy PDFs.",
                "requirement": "Compare the draft against a similar reference policy and align its section flow and clause style more closely.",
            })

        avg_heading_count = sum(item["heading_count"] for item in top_matches) / max(len(top_matches), 1)
        avg_group_count = sum(item["section_group_count"] for item in top_matches) / max(len(top_matches), 1)

        if top_matches and structure["heading_count"] + 1 < avg_heading_count and structure["section_group_count"] < avg_group_count:
            example_sections = ", ".join(top_matches[0]["section_groups"][:4]) or "scope, procedures, and review"
            issues.append({
                "severity": "medium",
                "category": "reference_structure",
                "issue": "Compared with similar reference policies, the draft has a thinner section structure.",
                "requirement": f"Expand the draft so its section flow is closer to comparable policies, especially around {example_sections}.",
            })

        if draft_informal > 0 and draft_informal >= max(2, draft_formal):
            issues.append({
                "severity": "medium",
                "category": "reference_tone",
                "issue": "The draft uses conversational or first-person language more often than the reference policy corpus.",
                "requirement": "Use more formal policy language and avoid first-person phrasing such as 'we', 'our', or direct reader-facing wording.",
            })

        if top_matches:
            conflicts.extend(self._detect_reference_policy_conflicts(draft_sentences, top_matches))

        risk_score = min(
            sum(_severity_weight(item.get("severity")) for item in issues[:4]) / 3.0,
            1.0,
        )

        cleaned_matches = []
        for item in top_matches:
            cleaned_matches.append({
                "name": item["name"],
                "similarity": item["similarity"],
                "section_groups": item["section_groups"],
                "headings": item["headings"],
            })

        return {
            "issues": issues,
            "risk_score": risk_score,
            "matches": cleaned_matches,
            "conflicts": conflicts[:6],
            "top_similarity": top_matches[0]["similarity"] if top_matches else 0.0,
        }

    def _adjust_similarity_assessment(self, similarity, reference_policy):
        adjusted = dict(similarity)
        top_policy_similarity = float(reference_policy.get("top_similarity", 0.0))
        issues = []

        for item in similarity.get("issues", []):
            if item.get("category") != "document_fit":
                issues.append(item)
                continue

            if top_policy_similarity >= 0.52:
                issues.append({
                    "severity": "medium",
                    "category": "legal_grounding",
                    "issue": "The draft resembles existing policy documents, but its subject matter only partially overlaps the legal rule corpus used for automated review.",
                    "requirement": "Keep the draft's policy structure, but manually verify legal grounding and citations against the closest applicable law or guideline.",
                })
            else:
                issues.append(item)

        adjusted["issues"] = issues
        adjusted["max_similarity"] = max(float(similarity.get("max_similarity", 0.0)), top_policy_similarity)
        return adjusted

    def _section_wise_review(self, text, compliance, reference_policy):
        draft_sections = _split_into_sections(text)
        if not draft_sections:
            return {
                "issues": [],
                "conflicts": [],
                "reviews": [],
                "recommendations": [],
                "risk_score": 0.0,
            }

        reference_matches = reference_policy.get("matches") or []
        reference_lookup = {item["name"]: item for item in reference_matches}
        reference_profiles = []
        for profile in self.reference_policy_profiles:
            if profile["name"] in reference_lookup:
                reference_profiles.append(profile)

        reviews = []
        issues = []
        conflicts = []

        for draft_section in draft_sections[:10]:
            best_match = None
            best_score = -1.0
            draft_text = draft_section["text"]
            draft_embedding = self.embedding_model.encode(
                draft_text[:4000],
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            draft_embedding = np.asarray(draft_embedding, dtype=np.float32)

            for profile in reference_profiles:
                for ref_section in profile.get("sections", [])[:20]:
                    group_bonus = 0.15 if ref_section.get("group") == draft_section.get("group") else 0.0
                    lexical = len(_content_tokens(draft_text) & _content_tokens(ref_section.get("text", ""))) * 0.01
                    score = float(np.dot(
                        draft_embedding,
                        self.embedding_model.encode(
                            ref_section.get("text", "")[:4000],
                            convert_to_numpy=True,
                            normalize_embeddings=True,
                        )
                    )) + group_bonus + lexical
                    if score > best_score:
                        best_score = score
                        best_match = {
                            "policy_name": profile["name"],
                            "title": ref_section.get("title") or "Reference section",
                            "group": ref_section.get("group"),
                            "text": ref_section.get("text", ""),
                            "score": round(score, 6),
                        }

            tone_note = None
            severity = "low"
            if best_match and best_match["score"] < 0.32:
                severity = "medium"
                tone_note = "This section is materially different from the closest reference section and may need stronger alignment in structure or wording."
            elif best_match and draft_section["sentence_count"] + 2 < max(4, len(_split_sentences(best_match["text"]))):
                severity = "medium"
                tone_note = "This section is much thinner than the closest reference section and may be missing expected detail."
            else:
                tone_note = "This section is broadly aligned with the closest reference section."

            if severity == "medium":
                issues.append({
                    "severity": "medium",
                    "category": "section_review",
                    "issue": f"The section '{draft_section['title']}' could be aligned more closely with comparable policy language and structure.",
                    "requirement": f"Compare it with '{best_match['title']}' in {best_match['policy_name']} and strengthen missing detail or formal wording.",
                })

            if best_match:
                conflicts.extend(self._detect_reference_policy_conflicts(
                    _split_sentences(draft_text),
                    [{"profile": {"name": best_match["policy_name"], "text": best_match["text"], "sentences": _split_sentences(best_match["text"])}}],
                ))

            reviews.append({
                "title": draft_section["title"],
                "group": draft_section.get("group"),
                "status": "needs_attention" if severity == "medium" else "aligned",
                "summary": tone_note,
                "reference_policy": best_match["policy_name"] if best_match else None,
                "reference_section": best_match["title"] if best_match else None,
                "similarity": best_match["score"] if best_match else None,
            })

        if reviews and not any(item["status"] == "needs_attention" for item in reviews):
            reviews.append({
                "title": "Overall section flow",
                "group": "general",
                "status": "aligned",
                "summary": "Section-wise comparison did not find any major structural drift against the closest reference policies.",
                "reference_policy": None,
                "reference_section": None,
                "similarity": None,
            })

        recommendations = []
        for review in reviews:
            if review["status"] == "needs_attention" and review.get("reference_policy"):
                recommendations.append(
                    f"Revise '{review['title']}' using '{review['reference_section']}' in {review['reference_policy']} as the closest structural reference."
                )
            if len(recommendations) >= 3:
                break

        risk_score = min(sum(_severity_weight(item["severity"]) for item in issues[:4]) / 3.0, 1.0)
        return {
            "issues": issues,
            "conflicts": conflicts[:6],
            "reviews": reviews,
            "recommendations": recommendations,
            "risk_score": risk_score,
        }

    def _detect_rule_conflicts(self, draft_text, rules):
        draft_sentences = _split_sentences(draft_text)
        conflicts = []
        seen = set()

        for rule in rules or []:
            if not _normative_rule_type(rule.get("type")):
                continue

            reference_text = " ".join(
                part for part in [
                    str(rule.get("summary") or "").strip(),
                    str(rule.get("text") or "").strip(),
                    str(rule.get("topic") or "").strip(),
                ] if part
            )[:1600]
            if not reference_text:
                continue

            shared_tokens = _meaningful_conflict_tokens(draft_text, reference_text)
            if len(shared_tokens) < 1:
                continue

            reference_sentences = _split_sentences(reference_text)
            for token in shared_tokens[:10]:
                draft_matches = _sentences_for_token(draft_sentences, token)
                reference_matches = _sentences_for_token(reference_sentences, token)
                if not draft_matches or not reference_matches:
                    continue

                draft_modality = _modality(draft_matches[0])
                reference_modality = _modality(reference_matches[0])
                if "neutral" in {draft_modality, reference_modality}:
                    continue
                if draft_modality == reference_modality:
                    continue

                citation = rule.get("citation") or f"{rule.get('law')} Section {rule.get('section')}"
                key = (citation, token, draft_modality, reference_modality)
                if key in seen:
                    continue
                seen.add(key)

                conflicts.append({
                    "severity": "high" if token in {"consent", "eligibility", "record", "records", "confidentiality", "privacy"} else "medium",
                    "law": rule.get("law") or "Applicable legal rule",
                    "citation": citation,
                    "issue": f"If implemented as written, this draft may handle '{token}' in a way that conflicts with the applicable legal rule.",
                    "why_it_matters": "This is a possible implementation-level legal contradiction, not just a wording difference.",
                    "requirement": reference_matches[0][:280],
                })

        conflicts.sort(
            key=lambda item: (
                item.get("severity") == "high",
                item.get("severity") == "medium",
            ),
            reverse=True,
        )
        return conflicts

    def _detect_reference_policy_conflicts(self, draft_sentences, reference_matches):
        draft_text = " ".join(draft_sentences)
        conflicts = []
        seen = set()

        for match in reference_matches:
            profile = match["profile"]
            reference_text = profile.get("text") or ""
            shared_tokens = _meaningful_conflict_tokens(draft_text, reference_text)
            if len(shared_tokens) < 2:
                continue

            reference_sentences = profile.get("sentences") or _split_sentences(reference_text)

            for token in shared_tokens[:6]:
                draft_matches = _sentences_for_token(draft_sentences, token)
                reference_matches_for_token = _sentences_for_token(reference_sentences, token)
                if not draft_matches or not reference_matches_for_token:
                    continue

                draft_modality = _modality(draft_matches[0])
                reference_modality = _modality(reference_matches_for_token[0])
                if "neutral" in {draft_modality, reference_modality}:
                    continue
                if draft_modality == reference_modality:
                    continue

                key = (profile["name"], token, draft_modality, reference_modality)
                if key in seen:
                    continue
                seen.add(key)

                conflicts.append({
                    "severity": "medium",
                    "law": profile["name"],
                    "citation": None,
                    "issue": f"If implemented as written, the draft may create inconsistency with existing policy practice around '{token}'.",
                    "why_it_matters": "This is a possible policy inconsistency with an existing reference document, not necessarily a legal violation.",
                    "requirement": reference_matches_for_token[0][:260],
                })

        return conflicts

    def _collect_compliance_gaps(self, findings, matched_rules):
        citation_to_rule = {}
        for rule in matched_rules or []:
            citation = rule.get("citation")
            if citation:
                citation_to_rule[citation] = rule

        gaps = []
        seen = set()

        for item in findings or []:
            severity = str(item.get("severity") or "medium").lower()
            if severity not in {"high", "medium", "low"}:
                continue

            citation = item.get("citation")
            related_rule = citation_to_rule.get(citation, {})
            law_name = related_rule.get("law") or citation or "Applicable guideline"
            issue = item.get("issue") or "The draft may not fully address this legal or policy requirement."
            requirement = item.get("requirement") or related_rule.get("summary") or "Review the applicable rule carefully."
            key = (law_name, citation, issue)
            if key in seen:
                continue
            seen.add(key)

            gaps.append({
                "severity": severity,
                "category": "compliance_gap",
                "issue": issue,
                "requirement": requirement,
                "citation": citation,
                "law": law_name,
            })

        gaps.sort(
            key=lambda item: (
                item.get("severity") == "high",
                item.get("severity") == "medium",
            ),
            reverse=True,
        )
        return gaps

    def _combine_issues(self, *issue_groups):
        combined = []
        seen = set()
        for group in issue_groups:
            for item in group or []:
                key = (
                    item.get("category"),
                    item.get("issue"),
                    item.get("requirement"),
                )
                if key in seen:
                    continue
                seen.add(key)
                combined.append(item)

        combined.sort(
            key=lambda item: (
                item.get("severity") == "high",
                item.get("severity") == "medium",
            ),
            reverse=True,
        )
        return combined

    def _combine_conflicts(self, *conflict_groups):
        combined = []
        seen = set()

        for group in conflict_groups:
            for item in group or []:
                key = (
                    item.get("law"),
                    item.get("citation"),
                    item.get("issue"),
                )
                if key in seen:
                    continue
                seen.add(key)
                combined.append(item)

        combined.sort(
            key=lambda item: (
                item.get("severity") == "high",
                item.get("severity") == "medium",
            ),
            reverse=True,
        )
        return combined

    def _build_recommendations(self, issues, structure, compliance, similarity, reference_policy, section_review):
        recommendations = []

        if similarity["max_similarity"] < 0.28:
            recommendations.append("Confirm the uploaded PDF is actually a policy draft. The document is weakly aligned with known policy/legal material.")

        if structure["heading_count"] < 3:
            recommendations.append("Rework the draft into a formal policy structure with headings such as Purpose, Scope, Definitions, Compliance, and Review.")
        elif structure.get("section_group_count", 0) < 3:
            recommendations.append("Strengthen the policy structure by making the scope, process, governance, and review sections easier to identify.")

        if compliance["high_severity_count"] > 0:
            recommendations.append("Address the high-severity compliance findings before treating this draft as ready for approval.")

        if reference_policy.get("matches"):
            top_match = reference_policy["matches"][0]
            recommendations.append(
                f"Use {top_match['name']} as a style reference and align the draft's headings, clause density, and formal language more closely with it."
            )

        for item in section_review.get("recommendations", []):
            if item not in recommendations:
                recommendations.append(item)
            if len(recommendations) >= 5:
                break

        for issue in issues:
            requirement = issue.get("requirement")
            if requirement and requirement not in recommendations:
                recommendations.append(requirement)
            if len(recommendations) >= 5:
                break

        if not recommendations:
            recommendations.append("Safe for further compliance review, but keep a human legal review in the loop.")

        return recommendations


def map_risk(anomaly_score, max_similarity, high_findings, heading_count):
    if anomaly_score >= HIGH_THRESHOLD or high_findings >= 2 or max_similarity < 0.22:
        return (
            "High",
            "The uploaded PDF has major structural or legal-fit concerns and should be reviewed manually before use.",
        )

    if anomaly_score >= LOW_THRESHOLD or high_findings >= 1 or heading_count < 3 or max_similarity < 0.38:
        return (
            "Moderate",
            "The draft shows meaningful deviations from expected policy structure or legal coverage and needs review.",
        )

    return (
        "Low",
        "The draft looks structurally consistent with policy-style documents and can proceed to human compliance review.",
    )
