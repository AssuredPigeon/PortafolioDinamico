from __future__ import annotations

import torch
import torch.nn as nn

NUM_STRUCTURAL_FEATURES = 6


class SelfAttentionPooling(nn.Module):
    """
    Capa de Atención Propia (Self-Attention Pooling) en PyTorch puro.
    Calcula pesos de relevancia sobre cada palabra codificada por el BiLSTM,
    ignorando posiciones de relleno (<PAD> = 0), para obtener el vector semántico de la oración.
    """

    def __init__(self, hidden_dim: int) -> None:
        super().__init__()
        self.scorer = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.Tanh(),
            nn.Linear(hidden_dim // 2, 1),
        )

    def forward(self, sequence_output: torch.Tensor, mask: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        # sequence_output: [batch, seq_len, hidden_dim]
        # mask: [batch, seq_len] (True donde hay token real, False en <PAD>)
        scores = self.scorer(sequence_output).squeeze(-1)  # [batch, seq_len]
        scores = scores.masked_fill(~mask, -1e9)
        attn_weights = torch.softmax(scores, dim=-1)  # [batch, seq_len]
        context = torch.bmm(attn_weights.unsqueeze(1), sequence_output).squeeze(1)  # [batch, hidden_dim]
        return context, attn_weights


class PortfolioReadmeNet(nn.Module):
    """
    Red Neuronal Multitarea en PyTorch puro para el Portafolio Dinámico:
    1) Codificador léxico-secuencial: Embedding -> BiLSTM bidireccional -> Self-Attention Pooling.
    2) Rama estructural: Proyección densa con LayerNorm sobre metadatos de la oración y del repo.
    3) Cabeza 1 (salience_head): Puntuación de relevancia extractiva para generar la descripción (RF2).
    4) Cabeza 2 (project_head): Clasificación Proyecto de Portafolio vs Práctica/Plantilla (apoyo RF3).
    """

    def __init__(
        self,
        vocab_size: int,
        embed_dim: int = 32,
        lstm_hidden: int = 32,
        num_features: int = NUM_STRUCTURAL_FEATURES,
        dropout: float = 0.35,
    ) -> None:
        super().__init__()
        self.embedding = nn.Embedding(
            num_embeddings=vocab_size,
            embedding_dim=embed_dim,
            padding_idx=0,
        )
        self.embed_drop = nn.Dropout(dropout)
        self.bilstm = nn.LSTM(
            input_size=embed_dim,
            hidden_size=lstm_hidden,
            num_layers=1,
            batch_first=True,
            bidirectional=True,
        )
        encoded_dim = lstm_hidden * 2
        self.attention = SelfAttentionPooling(encoded_dim)

        self.feature_branch = nn.Sequential(
            nn.Linear(num_features, 24),
            nn.LayerNorm(24),
            nn.GELU(),
        )

        fused_dim = encoded_dim + 24
        self.shared_fusion = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(fused_dim, 32),
            nn.LayerNorm(32),
            nn.GELU(),
        )

        self.salience_head = nn.Linear(32, 1)
        self.project_head = nn.Linear(32, 1)

    def forward(
        self,
        token_ids: torch.Tensor,
        structural_features: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        mask = token_ids != 0
        # Evitar filas completamente vacías en la máscara de atención
        empty_rows = ~mask.any(dim=1)
        if empty_rows.any():
            mask = mask.clone()
            mask[empty_rows, 0] = True

        embedded = self.embed_drop(self.embedding(token_ids))
        lstm_out, _ = self.bilstm(embedded)
        text_vec, attn_weights = self.attention(lstm_out, mask)
        feat_vec = self.feature_branch(structural_features)

        fused = self.shared_fusion(torch.cat([text_vec, feat_vec], dim=-1))
        salience_logits = self.salience_head(fused).squeeze(-1)
        project_logits = self.project_head(fused).squeeze(-1)
        return salience_logits, project_logits, attn_weights

