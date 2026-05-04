import os
import datetime
import traceback
import json

from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from pymongo import MongoClient

# --- AI & RAG IMPORTS ---
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_ollama import ChatOllama

# --- PIPELINE IMPORTS ---
from pipeline import run_pipeline
from utils.kb_loader import load_legal_kb
from utils.pdf_utils import extract_text_from_pdf
from utils.anomaly_checker import DraftAnomalyService


app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CORS(
    app,
    resources={r"/*": {"origins": [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]}},
    supports_credentials=True
)

# --- CONFIGURATION ---
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
VECTOR_STORE_PATH = os.path.join(BASE_DIR, "faiss_index")
KB_PATH = os.path.join(BASE_DIR, "kb")

MONGO_URI = os.environ.get(
    "MONGODB_URI",
    "mongodb://127.0.0.1:27017/policy_db"
)

CHAT_MODEL_NAME = "gemma:2b"
DRAFT_MODEL_NAME = "mistral:latest"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- LOAD EMBEDDINGS ---
print("Loading Embeddings...")
try:
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    embeddings_error = None
except Exception as e:
    print("Embeddings Error:", e)
    embeddings = None
    embeddings_error = str(e)

# --- LOAD LEGAL KB ---
print("Loading Legal Knowledge Base...")
legal_kb_data = load_legal_kb(KB_PATH)
print(f"Loaded {len(legal_kb_data)} legal rules.")

# --- LOAD MODELS ---
print("Loading Chat Model...")
try:
    llm_chat = ChatOllama(model=CHAT_MODEL_NAME, temperature=0.3)
except Exception as e:
    print("Chat Model Error:", e)
    llm_chat = None

print("Loading Draft Model...")
try:
    llm_draft = ChatOllama(model=DRAFT_MODEL_NAME, temperature=0.1)
except Exception as e:
    print("Draft Model Error:", e)
    llm_draft = None

print("AI Engines Ready 🚀")
print("Loading Draft Validation Service...")
try:
    anomaly_service = DraftAnomalyService(BASE_DIR, legal_kb=legal_kb_data)
except Exception as e:
    print("Draft Validation Service Error:", e)
    anomaly_service = None

# --- WRAPPER FOR PIPELINE ---
def draft_wrapper(prompt_text):
    if not llm_draft:
        return "Draft model unavailable"
    return llm_draft.invoke(prompt_text).content


def sanitize_current_content(text):
    if not text:
        return ""

    cleaned_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        if lower in {
            "# new policy document",
            "new policy document",
            "generated content will appear here...",
        }:
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


def retrieve_precedents(query, limit=3):
    if not embeddings or vector_store is None:
        return []

    try:
        docs = vector_store.similarity_search(query, k=limit)
        items = []
        for doc in docs:
            text = getattr(doc, "page_content", "").strip()
            if not text or text.strip().lower() == "system placeholder":
                continue
            metadata = getattr(doc, "metadata", {}) or {}
            items.append({
                "title": metadata.get("title") or metadata.get("source") or metadata.get("filename") or "Policy precedent",
                "text": text,
                "metadata": metadata,
            })
        return items
    except Exception as e:
        print("Precedent retrieval error:", e)
        return []


TOPIC_STOPWORDS = {
    "policy", "draft", "section", "shall", "must", "will", "with", "from", "that", "this", "under",
    "have", "has", "into", "during", "after", "before", "such", "their", "they", "them", "been",
    "being", "where", "which", "there", "here", "through", "would", "could", "should", "review",
    "compliance", "organization", "employee", "employees", "hospital", "healthcare", "leave",
}

GENERIC_POLICY_CONFLICT_TOKENS = {
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


def _topic_tokens(text):
    import re

    raw_tokens = re.findall(r"[a-z][a-z_]{3,}", (text or "").lower())
    return {
        token for token in raw_tokens
        if token not in TOPIC_STOPWORDS
    }


def _filter_relevant_precedents(draft_text, precedents, limit=2):
    draft_tokens = _topic_tokens(draft_text)
    if not draft_tokens:
        return precedents[:limit]

    ranked = []
    for item in precedents or []:
        title = item.get("title") or ""
        snippet = " ".join(str(item.get("text", "")).split())[:1800]
        precedent_tokens = _topic_tokens(f"{title} {snippet}")
        overlap = draft_tokens & precedent_tokens
        score = len(overlap)

        if score < 1:
            continue

        ranked.append((score, item))

    ranked.sort(key=lambda row: row[0], reverse=True)
    return [item for _, item in ranked[:limit]]


def _precedent_topic_map(precedents):
    topic_map = {}
    for item in precedents or []:
        title = item.get("title") or "Existing policy"
        snippet = " ".join(str(item.get("text", "")).split())[:1800]
        topic_map[title] = _topic_tokens(f"{title} {snippet}")
    return topic_map


def _split_sentences(text):
    import re

    candidates = re.split(r"(?<=[\.\?!;])\s+|\n+", text or "")
    return [segment.strip() for segment in candidates if len(segment.strip()) >= 40]


def _sentences_for_token(sentences, token):
    token = str(token or "").lower()
    return [sentence for sentence in sentences if token in sentence.lower()]


def _modality(sentence):
    lower = sentence.lower()
    negative_markers = [
        "shall not", "must not", "not eligible", "ineligible", "prohibited",
        "forbidden", "no employee", "not entitled", "cannot", "may not",
    ]
    positive_markers = [
        "shall", "must", "eligible", "entitled", "allowed", "permitted",
        "required", "will be granted", "is granted",
    ]

    if any(marker in lower for marker in negative_markers):
        return "negative"
    if any(marker in lower for marker in positive_markers):
        return "positive"
    return "neutral"


def _candidate_conflict_tokens(draft_tokens, precedent_tokens):
    noisy = {
        "policy", "draft", "employee", "employees", "hospital", "healthcare",
        "shall", "must", "review", "compliance", "organization",
    }
    shared = (draft_tokens & precedent_tokens) - noisy
    return sorted(shared, key=lambda token: (-len(token), token))


def _meaningful_policy_conflict_tokens(draft_text, precedent_text):
    draft_tokens = _topic_tokens(draft_text)
    precedent_tokens = _topic_tokens(precedent_text)
    shared = draft_tokens & precedent_tokens
    prioritized = [token for token in shared if token in HIGH_VALUE_POLICY_TOKENS]
    if prioritized:
        return sorted(prioritized, key=lambda token: (-len(token), token))
    filtered = [
        token for token in shared
        if token not in GENERIC_POLICY_CONFLICT_TOKENS and len(token) >= 6
    ]
    return sorted(filtered, key=lambda token: (-len(token), token))


def detect_existing_policy_conflicts(draft_text, precedents):
    precedents = _filter_relevant_precedents(draft_text, precedents or [], limit=2)
    if not precedents:
        return {
            "status": "no_precedents",
            "conflicts": [],
        }

    draft_topic_tokens = _topic_tokens(draft_text)
    precedent_topics = _precedent_topic_map(precedents)
    draft_sentences = _split_sentences(draft_text)
    conflicts = []
    seen = set()

    for item in precedents[:2]:
        title = item.get("title") or "Existing policy"
        snippet = " ".join(str(item.get("text", "")).split())[:1800]
        if not snippet:
            continue

        precedent_tokens = precedent_topics.get(title, set())
        shared_tokens = _meaningful_policy_conflict_tokens(draft_text, snippet)

        # Be strict: if topic overlap is weak, do not even attempt a conflict call.
        if len(shared_tokens) < 1:
            continue

        precedent_sentences = _split_sentences(snippet)

        for token in shared_tokens[:10]:
            draft_matches = _sentences_for_token(draft_sentences, token)
            precedent_matches = _sentences_for_token(precedent_sentences, token)
            if not draft_matches or not precedent_matches:
                continue

            draft_modality = _modality(draft_matches[0])
            precedent_modality = _modality(precedent_matches[0])
            if draft_modality == "neutral" or precedent_modality == "neutral":
                continue
            if draft_modality == precedent_modality:
                continue

            key = (title, token, draft_modality, precedent_modality)
            if key in seen:
                continue
            seen.add(key)

            conflicts.append({
                "severity": "medium" if token not in {"eligibility", "entitlement", "benefit", "notice"} else "high",
                "policy_title": title,
                "issue": f"If implemented as written, the draft may handle '{token}' differently from an existing policy excerpt.",
                "why_it_matters": "This is a possible inconsistency with an existing internal or reference policy position on the same topic.",
                "recommendation": "Review the relevant clauses side by side and align the draft with the established internal policy rule where appropriate.",
            })

    return {
        "status": "reviewed",
        "conflicts": conflicts[:3],
    }


# --- DATABASE SYNC ---
def fetch_documents_from_mongo():
    try:
        client = MongoClient(MONGO_URI)
        db = client.get_database()
        collection = db['documents']

        docs = []
        cursor = collection.find({"content": {"$exists": True, "$ne": ""}})

        for record in cursor:
            docs.append(record['content'])

        print(f"Loaded {len(docs)} docs from MongoDB")
        return docs

    except Exception as e:
        print("Mongo error:", e)
        return []


def rebuild_index():
    print("Rebuilding Vector Store...")
    global vector_store

    if not embeddings:
        print("Vector store unavailable because embeddings could not be loaded.")
        vector_store = None
        return

    texts = fetch_documents_from_mongo()

    if texts:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50
        )

        docs = splitter.create_documents(texts)

        vector_store = FAISS.from_documents(docs, embeddings)

        vector_store.save_local(VECTOR_STORE_PATH)

        print("Vector store rebuilt")

    else:
        vector_store = FAISS.from_texts(
            ["System placeholder"],
            embeddings
        )


# --- LOAD VECTOR STORE ---
print("Loading Vector Store...")
vector_store = None

if embeddings and os.path.exists(VECTOR_STORE_PATH):

    try:
        vector_store = FAISS.load_local(
            VECTOR_STORE_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
        print("Vector Store Loaded")

    except:
        rebuild_index()

elif embeddings:
    rebuild_index()
else:
    print("Skipping vector store initialization because embeddings are unavailable.")


# =========================
# API ROUTES
# =========================

@app.route("/")
def root():
    return "Server running"


# --- SYNC VECTOR DB ---
@app.route("/sync", methods=["POST"])
def sync():
    if not embeddings:
        return jsonify({"error": f"Embeddings unavailable: {embeddings_error}"}), 503

    rebuild_index()
    return jsonify({"message": "Memory synced"})


# --- FILE INGEST ---
@app.route("/ingest", methods=["POST"])
def ingest():
    if not embeddings or vector_store is None:
        return jsonify({"error": f"Vector store unavailable: {embeddings_error}"}), 503

    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400

    file = request.files["file"]
    filename = secure_filename(file.filename)

    save_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(save_path)

    try:

        loader = PyPDFLoader(save_path)
        docs = loader.load()

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50
        )

        chunks = splitter.split_documents(docs)

        vector_store.add_documents(chunks)
        vector_store.save_local(VECTOR_STORE_PATH)

        return jsonify({
            "message": "Ingested",
            "chunks": len(chunks)
        })

    except Exception as e:
        return jsonify({"error": str(e)})


# --- CHAT ---
@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(silent=True) or {}

    query = data.get("query", "")

    if not llm_chat:
        return jsonify({"response": "Chat model unavailable"}), 503

    if not embeddings or vector_store is None:
        return jsonify({"response": f"Vector search unavailable: {embeddings_error}"}), 503

    try:

        docs = vector_store.similarity_search(query, k=3)

        context = "\n".join([d.page_content for d in docs])

        prompt = f"""
You are a policy assistant.

Context:
{context}

Question:
{query}
"""

        response = llm_chat.invoke(prompt).content

        return jsonify({"response": response})

    except Exception as e:

        print("CHAT ERROR:", e)

        return jsonify({"response": "Chat error"})


# --- POLICY DRAFT ---
@app.route("/draft", methods=["POST", "OPTIONS"])
def draft():
    if request.method == "OPTIONS":
        return ("", 204)

    print("Starting pipeline...")
    data = request.get_json(silent=True) or {}

    user_request = data.get("query")
    current_content = data.get("current_content", "")

    if not user_request:
        return jsonify({"response": "Drafting failed: missing query"}), 400

    try:
        current_content = sanitize_current_content(current_content)
        effective_query = user_request
        if current_content and "Generated content will appear here" not in current_content:
            effective_query = (
                f"{user_request}\n\n"
                f"Existing draft context:\n{current_content[:1500]}"
            )

        precedents = retrieve_precedents(user_request, limit=3)

        result = run_pipeline(
            effective_query,
            draft_wrapper,
            legal_kb_data,
            precedents=precedents,
            current_content=current_content,
        )

        print("Pipeline finished")

        intent = result.get("intent", {})
        feasibility = result.get("feasibility", {})
        review = result.get("review", {})

        final_doc = f"# Draft Policy: {intent.get('policy_type', 'Custom Policy')}\n\n"
        final_doc += (
            f"Jurisdiction: {intent.get('jurisdiction')} | "
            f"Risk Level: {intent.get('risk_level')} | "
            f"Subdomain: {intent.get('subdomain') or 'general_healthcare'}\n\n"
        )

        final_doc += result.get("policy", "")

        review_status = str(review.get("status") or "").lower()
        checked_rules = int(review.get("checked_rules", 0) or 0)

        if review and not (review_status == "generic_review" and checked_rules == 0):
            final_doc += "\n\n## Compliance Review\n\n"
            final_doc += (
                f"Status: {review.get('status')} | "
                f"Checked Rules: {checked_rules}\n\n"
            )
            findings = review.get("findings", [])
            if findings:
                for finding in findings:
                    final_doc += (
                        f"- [{finding.get('severity', 'medium').upper()}] "
                        f"{finding.get('issue')} "
                        f"Requirement: {finding.get('requirement')} "
                        f"[{finding.get('citation')}]\n"
                    )
            else:
                final_doc += "- No major coverage gaps detected against the highest-priority retrieved rules.\n"

        precedent_items = result.get("precedents") or []
        if precedent_items:
            final_doc += "\n\n## Existing Policy Inputs\n\n"
            for idx, item in enumerate(precedent_items[:2], start=1):
                if isinstance(item, dict):
                    title = item.get("title") or f"Precedent {idx}"
                    snippet = " ".join(str(item.get("text", "")).split())[:240]
                    final_doc += f"- {title}: {snippet}\n"
                else:
                    snippet = " ".join(str(item).split())[:240]
                    final_doc += f"- Precedent {idx}: {snippet}\n"

        warnings = feasibility.get("warnings") or []
        if warnings:
            final_doc += "\n\n## Legal Notes\n\n"
            for warning in warnings[:3]:
                final_doc += f"- {warning}\n"
        elif feasibility.get("status") == "insufficient_legal_match":
            final_doc += (
                "\n\n## Legal Notes\n\n"
                "- No directly relevant rule match was found in the current healthcare-law KB, so this draft was generated primarily from the request context rather than from specific statutory clauses.\n"
            )

        return jsonify({"response": final_doc})

    except Exception as e:
        print("PIPELINE ERROR:", e)
        traceback.print_exc()

        return jsonify({
            "response": f"Drafting failed: {str(e)}"
        })

# --- SAVE DRAFT ---
@app.route("/save-draft", methods=["POST"])
@app.route("/api/save-draft", methods=["POST"])
def save_draft():
    data = request.get_json(silent=True) or {}

    try:

        client = MongoClient(MONGO_URI)
        db = client.get_database()

        db.saved_drafts.insert_one({
            "content": data.get("content"),
            "timestamp": datetime.datetime.utcnow()
        })

        return jsonify({"message": "Saved"})

    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/validate-policy-pdf", methods=["POST"])
def validate_policy_pdf():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded."}), 400

    if anomaly_service is None:
        return jsonify({"error": "Draft validation service is unavailable."}), 503

    uploaded_file = request.files["file"]
    filename = secure_filename(uploaded_file.filename or "")

    if not filename:
        return jsonify({"error": "Uploaded file is missing a filename."}), 400

    if not filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are supported."}), 400

    save_path = os.path.join(UPLOAD_FOLDER, filename)
    uploaded_file.save(save_path)

    try:
        if os.path.getsize(save_path) == 0:
            return jsonify({"error": "Uploaded PDF is empty."}), 400

        extracted_text = extract_text_from_pdf(save_path)

        if not extracted_text:
            return jsonify({"error": "Could not extract text from PDF."}), 422

        result = anomaly_service.validate_text(extracted_text, filename=filename)
        precedent_inputs = retrieve_precedents(extracted_text[:1800], limit=3)
        policy_conflicts = detect_existing_policy_conflicts(extracted_text, precedent_inputs)
        result["existing_policy_conflicts"] = policy_conflicts.get("conflicts", [])
        result["existing_policy_status"] = policy_conflicts.get("status", "analysis_unavailable")
        result["existing_policy_precedent_count"] = len(precedent_inputs)
        return jsonify(result)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        print("VALIDATE POLICY PDF ERROR:", e)
        traceback.print_exc()
        return jsonify({"error": "Failed to validate the uploaded PDF."}), 500
    finally:
        if os.path.exists(save_path):
            os.remove(save_path)


if __name__ == "__main__":
    app.run(port=5001, debug=True)
