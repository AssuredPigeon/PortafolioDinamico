from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

from backend.ml.network import PortfolioReadmeNet
from backend.ml.tokenizer import ReadmeVocabulary, extract_sentence_features

ML_DIR = Path(__file__).resolve().parent
DATASET_PATH = ML_DIR / "dataset_readmes.json"
ARTIFACTS_DIR = ML_DIR / "artifacts"
MODEL_PATH = ARTIFACTS_DIR / "readme_model.pt"
VOCAB_PATH = ARTIFACTS_DIR / "vocab.json"
METRICS_PATH = ARTIFACTS_DIR / "training_metrics.json"


class ReadmeSentenceDataset(Dataset):
    """Dataset de PyTorch para entrenar el modelo multitarea de análisis de READMEs."""

    def __init__(self, records: list[dict[str, Any]], vocab: ReadmeVocabulary) -> None:
        self.token_tensors: list[torch.Tensor] = []
        self.feature_tensors: list[torch.Tensor] = []
        self.salience_labels: list[torch.Tensor] = []
        self.project_labels: list[torch.Tensor] = []

        for item in records:
            sentence = item["sentence"]
            pos_idx = int(item.get("pos_idx", 0))
            total_sents = int(item.get("total_sentences", 5))
            repo_meta = {
                "lenguajes": item.get("lenguajes", []),
                "topics": item.get("topics", []),
                "nombre": item.get("nombre", ""),
            }

            ids = vocab.encode(sentence)
            feats = extract_sentence_features(sentence, pos_idx, total_sents, repo_meta)

            self.token_tensors.append(torch.tensor(ids, dtype=torch.long))
            self.feature_tensors.append(torch.tensor(feats, dtype=torch.float32))
            self.salience_labels.append(torch.tensor(float(item["salient"]), dtype=torch.float32))
            self.project_labels.append(torch.tensor(float(item["portfolio_project"]), dtype=torch.float32))

    def __len__(self) -> int:
        return len(self.token_tensors)

    def __getitem__(
        self, idx: int
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        return (
            self.token_tensors[idx],
            self.feature_tensors[idx],
            self.salience_labels[idx],
            self.project_labels[idx],
        )


def set_reproducible_seed(seed: int = 42) -> None:
    random.seed(seed)
    torch.manual_seed(seed)


def train_and_save_model(
    epochs: int = 35,
    batch_size: int = 8,
    learning_rate: float = 2e-3,
    seed: int = 42,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Entrena desde cero la red neuronal PortfolioReadmeNet en PyTorch (CPU/GPU),
    evalúa la precisión en validación con partición estratificada y guarda el mejor modelo (.pt).
    """
    set_reproducible_seed(seed)
    records: list[dict[str, Any]] = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

    positives = [r for r in records if int(r["salient"]) == 1]
    negatives = [r for r in records if int(r["salient"]) == 0]
    random.shuffle(positives)
    random.shuffle(negatives)

    p_split = max(1, int(len(positives) * 0.8))
    n_split = max(1, int(len(negatives) * 0.8))
    train_records = positives[:p_split] + negatives[:n_split]
    val_records = positives[p_split:] + negatives[n_split:]
    random.shuffle(train_records)

    vocab = ReadmeVocabulary.build_from_texts([r["sentence"] for r in records])
    train_ds = ReadmeSentenceDataset(train_records, vocab)
    val_ds = ReadmeSentenceDataset(val_records, vocab)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

    device = torch.device("cpu")
    model = PortfolioReadmeNet(vocab_size=vocab.size).to(device)

    criterion = nn.BCEWithLogitsLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-2)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    history: list[dict[str, float]] = []
    best_val_loss = float("inf")
    best_metrics: dict[str, float] = {}
    best_state = None

    for epoch in range(1, epochs + 1):
        model.train()
        running_loss = 0.0
        total_train = 0
        correct_train = 0

        for tok_ids, feats, y_sal, y_proj in train_loader:
            tok_ids = tok_ids.to(device)
            feats = feats.to(device)
            y_sal = y_sal.to(device)
            y_proj = y_proj.to(device)

            optimizer.zero_grad()
            sal_logits, proj_logits, _ = model(tok_ids, feats)
            loss_sal = criterion(sal_logits, y_sal)
            loss_proj = criterion(proj_logits, y_proj)
            loss = loss_sal + 0.5 * loss_proj
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

            running_loss += float(loss.item()) * tok_ids.size(0)
            preds = (torch.sigmoid(sal_logits) >= 0.5).float()
            correct_train += int((preds == y_sal).sum().item())
            total_train += tok_ids.size(0)

        scheduler.step()

        model.eval()
        val_loss = 0.0
        val_correct_sal = 0
        val_correct_proj = 0
        val_total = 0
        tp = 0
        fp = 0
        fn = 0

        with torch.no_grad():
            for tok_ids, feats, y_sal, y_proj in val_loader:
                sal_logits, proj_logits, _ = model(tok_ids, feats)
                loss = criterion(sal_logits, y_sal) + 0.5 * criterion(proj_logits, y_proj)
                val_loss += float(loss.item()) * tok_ids.size(0)

                pred_sal = (torch.sigmoid(sal_logits) >= 0.5).float()
                pred_proj = (torch.sigmoid(proj_logits) >= 0.5).float()
                val_correct_sal += int((pred_sal == y_sal).sum().item())
                val_correct_proj += int((pred_proj == y_proj).sum().item())
                tp += int(((pred_sal == 1) & (y_sal == 1)).sum().item())
                fp += int(((pred_sal == 1) & (y_sal == 0)).sum().item())
                fn += int(((pred_sal == 0) & (y_sal == 1)).sum().item())
                val_total += tok_ids.size(0)

        train_acc = correct_train / max(total_train, 1)
        avg_val_loss = val_loss / max(val_total, 1)
        val_acc_sal = val_correct_sal / max(val_total, 1)
        val_acc_proj = val_correct_proj / max(val_total, 1)
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        epoch_stats = {
            "epoch": epoch,
            "train_loss": round(running_loss / max(total_train, 1), 4),
            "val_loss": round(avg_val_loss, 4),
            "train_acc": round(train_acc, 4),
            "val_salience_acc": round(val_acc_sal, 4),
            "val_salience_precision": round(precision, 4),
            "val_salience_recall": round(recall, 4),
            "val_salience_f1": round(f1, 4),
            "val_project_acc": round(val_acc_proj, 4),
        }
        history.append(epoch_stats)

        if avg_val_loss <= best_val_loss:
            best_val_loss = avg_val_loss
            best_metrics = epoch_stats
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

        if verbose and (epoch == 1 or epoch % 10 == 0 or epoch == epochs):
            print(
                f"[PyTorch Epoch {epoch:02d}/{epochs}] "
                f"train_loss={epoch_stats['train_loss']:.4f} | "
                f"val_loss={avg_val_loss:.4f} | "
                f"val_salience_acc={val_acc_sal * 100:.1f}% | "
                f"val_f1={f1:.3f} | "
                f"val_project_acc={val_acc_proj * 100:.1f}%"
            )

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    if best_state is not None:
        model.load_state_dict(best_state)

    vocab.save(VOCAB_PATH)
    torch.save(
        {
            "vocab_size": vocab.size,
            "state_dict": model.state_dict(),
            "architecture": "PortfolioReadmeNet(Embedding+BiLSTM+SelfAttention+MetadataFusion)",
        },
        MODEL_PATH,
    )

    summary = {
        "architecture": "PortfolioReadmeNet (PyTorch BiLSTM + Self-Attention)",
        "pytorch_version": torch.__version__,
        "vocab_size": vocab.size,
        "dataset_size": len(records),
        "epochs": epochs,
        "best_checkpoint_metrics": best_metrics,
        "final_metrics": history[-1],
    }
    METRICS_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    info = train_and_save_model(verbose=True)
    print("\nEntrenamiento en PyTorch completado:", json.dumps(info, ensure_ascii=False, indent=2))

