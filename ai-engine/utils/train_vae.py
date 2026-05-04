import argparse
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from sentence_transformers import SentenceTransformer
from torch import nn
from torch.utils.data import DataLoader, TensorDataset, random_split

CURRENT_DIR = Path(__file__).resolve().parent
BASE_PACKAGE_DIR = CURRENT_DIR.parent
if str(BASE_PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_PACKAGE_DIR))

from models.vae_model import PolicyDraftVAE
from utils.kb_loader import load_legal_kb


DEFAULT_EMBEDDING_MODEL = os.environ.get("POLICY_VALIDATION_EMBEDDING_MODEL", "all-MiniLM-L6-v2")


def normalize(text):
    return " ".join((text or "").split())


def chunk_text(text, max_chars=1400, overlap=180):
    text = normalize(text)
    if not text:
        return []

    chunks = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = min(text_len, start + max_chars)
        chunk = text[start:end].strip()
        if len(chunk) >= 220:
            chunks.append(chunk)
        if end >= text_len:
            break
        start = max(0, end - overlap)
    return chunks


def build_corpus(kb_path):
    rules = load_legal_kb(str(kb_path))
    grouped = {}

    for rule in rules:
        key = rule.get("source_file") or rule.get("law") or "unknown_source"
        grouped.setdefault(key, []).append(rule)

    documents = []
    for source_file, items in grouped.items():
        law_name = items[0].get("law") or source_file
        sections = []
        for rule in items:
            parts = [
                str(rule.get("law") or "").strip(),
                str(rule.get("citation") or "").strip(),
                str(rule.get("topic") or "").strip(),
                str(rule.get("summary") or "").strip(),
                str(rule.get("text") or "").strip(),
            ]
            line = " | ".join(part for part in parts if part)
            if line:
                sections.append(line)

        combined = "\n".join(sections)
        for chunk in chunk_text(combined):
            documents.append({
                "source_file": source_file,
                "law": law_name,
                "text": chunk,
            })

    return documents


def encode_corpus(texts, model_name):
    model = SentenceTransformer(model_name, local_files_only=True)
    vectors = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=True)
    return np.asarray(vectors, dtype=np.float32)


def vae_loss(reconstruction, target, mu, logvar, beta=0.05):
    recon = F.mse_loss(reconstruction, target, reduction="mean")
    kld = -0.5 * torch.mean(1 + logvar - mu.pow(2) - logvar.exp())
    return recon + beta * kld, recon, kld


def evaluate_model(model, data_loader, device):
    model.eval()
    losses = []
    errors = []

    with torch.no_grad():
        for (batch,) in data_loader:
            batch = batch.to(device)
            reconstruction, mu, logvar = model(batch)
            loss, _, _ = vae_loss(reconstruction, batch, mu, logvar)
            losses.append(loss.item())
            batch_errors = torch.mean((reconstruction - batch) ** 2, dim=1)
            errors.extend(batch_errors.detach().cpu().tolist())

    return {
        "loss": float(np.mean(losses)) if losses else 0.0,
        "errors": [float(x) for x in errors],
    }


def train(args):
    base_dir = Path(args.base_dir).resolve()
    kb_path = base_dir / "kb"
    output_dir = base_dir / "saved_models"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "vae_model.pth"

    corpus = build_corpus(kb_path)
    if len(corpus) < 20:
        raise RuntimeError(f"Not enough training samples found in {kb_path}. Found {len(corpus)} chunks.")

    texts = [item["text"] for item in corpus]
    embeddings = encode_corpus(texts, args.embedding_model)

    tensor_data = torch.tensor(embeddings, dtype=torch.float32)
    dataset = TensorDataset(tensor_data)

    val_size = max(1, math.floor(len(dataset) * args.validation_split))
    train_size = len(dataset) - val_size
    train_set, val_set = random_split(
        dataset,
        [train_size, val_size],
        generator=torch.Generator().manual_seed(args.seed),
    )

    train_loader = DataLoader(train_set, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_set, batch_size=args.batch_size, shuffle=False)

    device = torch.device("cpu")
    model = PolicyDraftVAE(
        input_dim=tensor_data.shape[1],
        latent_dim=args.latent_dim,
        hidden_dim=args.hidden_dim,
    ).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate)

    best_val_loss = float("inf")
    best_state = None

    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_losses = []
        epoch_recon = []
        epoch_kld = []

        for (batch,) in train_loader:
            batch = batch.to(device)
            optimizer.zero_grad()
            reconstruction, mu, logvar = model(batch)
            loss, recon, kld = vae_loss(reconstruction, batch, mu, logvar, beta=args.beta)
            loss.backward()
            optimizer.step()

            epoch_losses.append(loss.item())
            epoch_recon.append(recon.item())
            epoch_kld.append(kld.item())

        eval_stats = evaluate_model(model, val_loader, device)
        train_loss = float(np.mean(epoch_losses)) if epoch_losses else 0.0
        val_loss = eval_stats["loss"]

        print(
            f"Epoch {epoch:03d} | train_loss={train_loss:.6f} "
            f"| train_recon={float(np.mean(epoch_recon)):.6f} "
            f"| train_kld={float(np.mean(epoch_kld)):.6f} "
            f"| val_loss={val_loss:.6f}"
        )

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.detach().cpu() for k, v in model.state_dict().items()}

    if best_state is None:
        raise RuntimeError("Training did not produce a checkpoint.")

    model.load_state_dict(best_state)
    train_eval = evaluate_model(model, train_loader, device)
    val_eval = evaluate_model(model, val_loader, device)
    calibration_errors = np.asarray(val_eval["errors"] or train_eval["errors"], dtype=np.float32)

    checkpoint = {
        "state_dict": model.state_dict(),
        "config": {
            "input_dim": int(tensor_data.shape[1]),
            "latent_dim": int(args.latent_dim),
            "hidden_dim": int(args.hidden_dim),
            "embedding_model": args.embedding_model,
            "sample_count": int(len(corpus)),
            "train_size": int(train_size),
            "validation_size": int(val_size),
        },
        "thresholds": {
            "mean_error": float(np.mean(calibration_errors)),
            "std_error": float(np.std(calibration_errors)),
            "p95_error": float(np.percentile(calibration_errors, 95)),
            "p99_error": float(np.percentile(calibration_errors, 99)),
        },
        "corpus_preview": {
            "sources": sorted({item["source_file"] for item in corpus})[:20],
        },
    }

    torch.save(checkpoint, output_path)

    summary_path = output_dir / "vae_training_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "checkpoint": str(output_path),
                "best_val_loss": best_val_loss,
                "thresholds": checkpoint["thresholds"],
                "config": checkpoint["config"],
            },
            f,
            indent=2,
        )

    print(f"Saved trained checkpoint to {output_path}")
    print(f"Saved training summary to {summary_path}")


def parse_args():
    parser = argparse.ArgumentParser(description="Train a VAE anomaly detector on the policy/legal KB corpus.")
    parser.add_argument("--base-dir", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--epochs", type=int, default=24)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--latent-dim", type=int, default=48)
    parser.add_argument("--hidden-dim", type=int, default=192)
    parser.add_argument("--beta", type=float, default=0.05)
    parser.add_argument("--validation-split", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


if __name__ == "__main__":
    train(parse_args())
