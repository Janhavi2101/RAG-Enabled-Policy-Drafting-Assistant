# Project Setup

replace the models in ai-engine/app.py as per ram specifications
current models:
CHAT_MODEL_NAME = "gemma:2b"
DRAFT_MODEL_NAME = "mistral:latest"


## Backend
cd ai-engine
pip install -r requirements.txt
python app.py

## Server
cd server
node index.js

## Frontend
npm run dev

## Notes
- FAISS index will be generated on first run
- Add PDFs to /kb folder before running


# Knowledge Base Layout

The KB is organized into subfolders so retrieval can stay healthcare-first:

- `core_healthcare/`: primary healthcare statutes and rules
- `cross_cutting/`: broader laws that may apply to healthcare operations
- `_backup_original/`: untouched copies of the legacy JSON exports

Each JSON file contains an array of normalized chunk objects with richer metadata for filtering and citation.
