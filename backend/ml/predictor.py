from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

import torch

from backend.ml.network import PortfolioReadmeNet
from backend.ml.tokenizer import (
    ReadmeVocabulary,
    clean_readme_to_sentences,
    extract_sentence_features,
)
from backend.ml.train import MODEL_PATH, VOCAB_PATH, train_and_save_model


@dataclass
class PyTorchPrediction:
    descripcion: str | None
    origen: str
    puntaje_relevancia: float
    es_proyecto_portafolio: bool
    puntos_clave: list[str] = field(default_factory=list)


class PyTorchReadmeAnalyzer:
    """
    Motor de inferencia en PyTorch para generar descripciones enriquecidas a partir
    del README real del repositorio (RF2) sin inventar información (Regla 6).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        if not MODEL_PATH.exists() or not VOCAB_PATH.exists():
            train_and_save_model(verbose=False)

        self.vocab = ReadmeVocabulary.load(VOCAB_PATH)
        checkpoint = torch.load(MODEL_PATH, map_location="cpu", weights_only=True)
        self.model = PortfolioReadmeNet(vocab_size=int(checkpoint["vocab_size"]))
        self.model.load_state_dict(checkpoint["state_dict"])
        self.model.eval()

    def analyze_readme(
        self,
        raw_markdown: str | None,
        repo_meta: dict[str, Any],
        max_chars: int = 330,
        salience_threshold: float = 0.48,
    ) -> PyTorchPrediction:
        sentences = clean_readme_to_sentences(raw_markdown)
        if not sentences:
            desc_orig = (repo_meta.get("descripcion_original") or "").strip()
            if desc_orig:
                return PyTorchPrediction(
                    descripcion=None,
                    origen="original",
                    puntaje_relevancia=0.5,
                    es_proyecto_portafolio=True,
                )
            return PyTorchPrediction(
                descripcion=None,
                origen="metadatos",
                puntaje_relevancia=0.0,
                es_proyecto_portafolio=True,
            )

        token_batch = self.vocab.encode_batch(sentences)
        feats_list = [
            extract_sentence_features(sent, idx, len(sentences), repo_meta)
            for idx, sent in enumerate(sentences)
        ]
        feat_batch = torch.tensor(feats_list, dtype=torch.float32)

        with self._lock, torch.no_grad():
            sal_logits, proj_logits, _attn = self.model(token_batch, feat_batch)
            sal_probs = torch.sigmoid(sal_logits).tolist()
            proj_probs = torch.sigmoid(proj_logits).tolist()

        if isinstance(sal_probs, float):
            sal_probs = [sal_probs]
        if isinstance(proj_probs, float):
            proj_probs = [proj_probs]

        scored = list(enumerate(zip(sentences, sal_probs, proj_probs)))
        # Priorizar probabilidad neuronal dando peso natural al párrafo introductorio del README cuando supera el umbral
        ranked = sorted(
            scored,
            key=lambda item: (
                item[1][1]
                + (
                    0.09
                    if item[0] == 0 and item[1][1] >= salience_threshold
                    else (0.04 if item[0] == 1 and item[1][1] >= salience_threshold else 0.0)
                )
            ),
            reverse=True,
        )

        best_salience = float(ranked[0][1][1])
        avg_top_proj = sum(x[1][2] for x in ranked[: min(3, len(ranked))]) / min(3, len(ranked))

        # Filtrar oraciones que superen el umbral (descarta plantillas boilerplate como el README default de Laravel)
        selected_indices: list[int] = []
        current_len = 0
        for orig_idx, (sent, sal_p, _proj_p) in ranked:
            if sal_p < salience_threshold:
                continue
            projected_len = current_len + len(sent) + (1 if selected_indices else 0)
            if projected_len <= max_chars or not selected_indices:
                selected_indices.append(orig_idx)
                current_len = projected_len
            if len(selected_indices) >= 2 or current_len >= max_chars - 40:
                break

        if not selected_indices:
            return PyTorchPrediction(
                descripcion=None,
                origen="metadatos",
                puntaje_relevancia=round(best_salience, 4),
                es_proyecto_portafolio=bool(avg_top_proj >= 0.45),
            )

        # Reconstruir en el orden narrativo original del README para lectura natural
        summary_set = set(selected_indices)
        selected_indices.sort()
        summary = " ".join(sentences[i] for i in selected_indices).strip()
        if len(summary) > max_chars:
            cut = summary[:max_chars].rsplit(" ", 1)[0].rstrip(",;:-.")
            summary = f"{cut}..."

        # Extraer hasta 5 puntos clave técnicos adicionales puntuados por la red neuronal en PyTorch
        highlight_indices: list[int] = []
        for orig_idx, (sent, sal_p, _proj_p) in ranked:
            if orig_idx in summary_set:
                continue
            if sal_p < max(0.42, salience_threshold - 0.06):
                continue
            if len(sent) < 28:
                continue
            highlight_indices.append(orig_idx)
            if len(highlight_indices) >= 5:
                break

        highlight_indices.sort()
        puntos_clave: list[str] = []
        for idx in highlight_indices:
            bullet = sentences[idx].strip()
            if len(bullet) > 220:
                bullet = bullet[:217].rsplit(" ", 1)[0].rstrip(",;:-.") + "..."
            puntos_clave.append(bullet)

        return PyTorchPrediction(
            descripcion=summary,
            origen="pytorch-bilstm",
            puntaje_relevancia=round(best_salience, 4),
            es_proyecto_portafolio=bool(avg_top_proj >= 0.45),
            puntos_clave=puntos_clave,
        )


_singleton_analyzer: PyTorchReadmeAnalyzer | None = None


def get_readme_analyzer() -> PyTorchReadmeAnalyzer:
    global _singleton_analyzer
    if _singleton_analyzer is None:
        _singleton_analyzer = PyTorchReadmeAnalyzer()
    return _singleton_analyzer

