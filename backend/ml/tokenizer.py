from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import torch

PAD_TOKEN = "<PAD>"
UNK_TOKEN = "<UNK>"

TECH_PURPOSE_TERMS = {
    "sistema", "plataforma", "aplicacion", "aplicación", "api", "rest", "backend",
    "frontend", "pipeline", "modelo", "red", "neuronal", "tiempo", "real", "realtime",
    "real-time", "automatiza", "detecta", "clasifica", "gestiona", "gestión", "monitoreo",
    "base", "datos", "database", "sincroniza", "visualiza", "visualización", "dashboard",
    "bot", "voz", "audio", "algoritmo", "arquitectura", "microservicios", "espacial",
    "autenticacion", "autenticación", "seguridad", "servidor", "cliente", "despliegue",
    "system", "platform", "application", "service", "engine", "detection", "classification",
    "management", "interactive", "automated", "analytics", "semantic", "machine", "learning",
    "computer", "vision", "full-stack", "fullstack", "production", "cloud", "game",
}

BOILERPLATE_PATTERNS = (
    "laravel is a web application framework",
    "expressive, elegant syntax",
    "expressive, intuitive database orm",
    "real-time event broadcasting",
    "database agnostic schema migrations",
    "robust background job processing",
    "welcome to your expo app",
    "when you're ready, run",
    "bootstrapped with create react app",
    "get started by editing",
    "this template provides a minimal setup",
    "cpu intel",
    "(recomendado)",
    "mit license",
    "apache license",
    "permission is hereby granted",
    "pull requests are welcome",
    "feel free to contribute",
    "how to install",
    "clone the repository",
    "clona este repositorio",
    "instalar dependencias",
    "all rights reserved",
    "table of contents",
    "tabla de contenido",
    "open http://127.0.0.1",
    "open http://localhost",
    "localhost:",
    "127.0.0.1:",
    "0.0.0.0:",
    "environment:",
    "abrirá en http",
    "disponible en http",
    "available at http",
    ".woff",
    ".ttf",
    ".otf",
    "font for headings",
    "system sans-serif fonts",
    "system monospace fonts",
    "pulsa stop",
    "selecciona la cámara",
    "circleci.com",
)

WORD_RE = re.compile(r"[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9+#.-]+")


def clean_readme_to_sentences(raw_markdown: str | None) -> list[str]:
    """
    Limpia un archivo README en Markdown/HTML eliminando bloques de código, imágenes,
    escudos (badges) y tablas decorativas, y devuelve sus oraciones candidatas en orden.
    """
    if not raw_markdown or not isinstance(raw_markdown, str):
        return []

    text = raw_markdown.replace("\x00", "").lstrip("\ufeff\ufffd").replace("\r\n", "\n")
    # Eliminar bloques de código y etiquetas decorativas
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"<table[\s\S]*?</table>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)

    # Eliminar badges e imágenes Markdown, conservando el texto de enlaces normales
    text = re.sub(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)

    # Verificar plantillas por defecto tras limpiar enlaces Markdown (Laravel, Expo, CRA, NestJS, Vite)
    lower_clean = text.lower()
    if any(
        tpl in lower_clean
        for tpl in (
            "laravel is a web application framework with expressive, elegant syntax",
            "welcome to your expo app",
            "this project was bootstrapped with create react app",
            "a progressive node.js framework for building efficient",
            "nest framework typescript starter repository",
            "this template provides a minimal setup to get react working in vite",
        )
    ):
        return []

    cleaned_blocks: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.replace("\x00", "").lstrip("\ufeff\ufffd").strip()
        if not line:
            continue
        # Ignorar encabezados Markdown, filas de tablas Markdown e introducciones con dos puntos finales
        if re.match(r"^#{1,6}\s+", line):
            continue
        if re.match(r"^[-=_*]{3,}$", line):
            continue
        if line.startswith("|") or line.count("|") >= 2:
            continue

        line = re.sub(r"^>\s*", "", line)
        line = re.sub(r"^[-*+]\s+", "", line)
        line = re.sub(r"^\d+\.\s+", "", line)
        line = re.sub(r"[*_`~]", "", line)
        line = re.sub(r"\s+", " ", line).strip()

        if not line or line.endswith(":"):
            continue
        if len(line) < 22:
            continue
        if re.match(r"^https?://\S+$", line, flags=re.IGNORECASE):
            continue
        if line.startswith("[") and "]:" in line:
            continue
        if re.match(r"^(npm |yarn |pnpm |pip |py |python |git clone |cd |docker |dotnet |composer |php artisan )", line, flags=re.IGNORECASE):
            continue
        if re.search(r"\.(?:woff2?|ttf|otf|eot)\b", line, flags=re.IGNORECASE):
            continue
        low_line = line.lower()
        if any(
            bp in low_line
            for bp in (
                "open http://127.0.0.1",
                "open http://localhost",
                "localhost:",
                "127.0.0.1:",
                "0.0.0.0:",
                "environment:",
                "abrirá en http",
                "disponible en http",
                "available at http",
                "font for headings",
                "system sans-serif fonts",
                "system monospace fonts",
                "consideraciones previas",
                "instalacion en windows",
                "instalación en windows",
                "pulsa stop",
                "selecciona la cámara",
            )
        ):
            continue

        cleaned_blocks.append(line)

    # Segmentar bloques en oraciones respetando abreviaturas comunes
    sentences: list[str] = []
    for block in cleaned_blocks:
        parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ])", block)
        for part in parts:
            sent = part.strip()
            if len(sent) < 22 or sent.endswith(":"):
                continue
            low_sent = sent.lower()
            if any(
                bad in low_sent
                for bad in ("localhost:", "127.0.0.1:", "environment:", ".woff", ".ttf", "font for headings")
            ):
                continue
            # Ignorar listas puras de identificadores largos sin verbos ni contexto (ej. nombres de índices SQL)
            words_only = re.findall(r"[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9_]+", sent)
            if words_only and sum(1 for w in words_only if len(w) >= 22) >= 2 and len(words_only) <= 6:
                continue
            if sent[-1] not in ".!?":
                sent = f"{sent}."
            sentences.append(sent)

    # Eliminar duplicados exactos conservando orden
    seen: set[str] = set()
    unique_sentences: list[str] = []
    for s in sentences:
        key = s.lower()
        if key not in seen:
            seen.add(key)
            unique_sentences.append(s)

    return unique_sentences[:45]


def tokenize_text(text: str) -> list[str]:
    return [tok.lower().strip(".-") for tok in WORD_RE.findall(text) if tok.strip(".-")]


class ReadmeVocabulary:
    """Vocabulario propio para convertir oraciones de README en tensores de PyTorch."""

    def __init__(self, token_to_idx: dict[str, int] | None = None, max_seq_len: int = 36) -> None:
        self.max_seq_len = max_seq_len
        self.token_to_idx = token_to_idx or {PAD_TOKEN: 0, UNK_TOKEN: 1}

    @property
    def size(self) -> int:
        return len(self.token_to_idx)

    @classmethod
    def build_from_texts(cls, texts: list[str], max_vocab: int = 2500, max_seq_len: int = 36) -> "ReadmeVocabulary":
        counter: Counter[str] = Counter()
        for t in texts:
            counter.update(tokenize_text(t))

        # Incluir siempre los términos técnicos clave aunque aparezcan pocas veces
        token_to_idx: dict[str, int] = {PAD_TOKEN: 0, UNK_TOKEN: 1}
        for term in sorted(TECH_PURPOSE_TERMS):
            for sub in tokenize_text(term):
                if sub not in token_to_idx:
                    token_to_idx[sub] = len(token_to_idx)

        for token, _freq in counter.most_common(max_vocab):
            if token not in token_to_idx and len(token_to_idx) < max_vocab:
                token_to_idx[token] = len(token_to_idx)

        return cls(token_to_idx=token_to_idx, max_seq_len=max_seq_len)

    def encode(self, sentence: str) -> list[int]:
        tokens = tokenize_text(sentence)[: self.max_seq_len]
        unk_id = self.token_to_idx[UNK_TOKEN]
        pad_id = self.token_to_idx[PAD_TOKEN]
        ids = [self.token_to_idx.get(tok, unk_id) for tok in tokens]
        if len(ids) < self.max_seq_len:
            ids.extend([pad_id] * (self.max_seq_len - len(ids)))
        return ids

    def encode_batch(self, sentences: list[str]) -> torch.Tensor:
        return torch.tensor([self.encode(s) for s in sentences], dtype=torch.long)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"max_seq_len": self.max_seq_len, "token_to_idx": self.token_to_idx}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "ReadmeVocabulary":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            token_to_idx=payload["token_to_idx"],
            max_seq_len=int(payload.get("max_seq_len", 36)),
        )


def extract_sentence_features(
    sentence: str,
    pos_idx: int,
    total_sentences: int,
    repo_meta: dict[str, Any] | None = None,
) -> list[float]:
    """
    Extrae 6 características numéricas normalizadas en [0, 1] que alimentan la rama
    estructural de la red neuronal en PyTorch junto con los embeddings del texto.
    """
    repo_meta = repo_meta or {}
    lower = sentence.lower()
    tokens = tokenize_text(sentence)
    n_words = len(tokens)

    # 1. Posición relativa inversa (inicio del README = 1.0, final = cercano a 0.0)
    pos_rel = 1.0 - (min(pos_idx, max(total_sentences - 1, 1)) / max(total_sentences, 1))

    # 2. Longitud óptima para resumen (ideal entre 8 y 34 palabras)
    if 8 <= n_words <= 34:
        len_score = 1.0
    elif n_words < 8:
        len_score = max(0.0, n_words / 8.0)
    else:
        len_score = max(0.1, 1.0 - ((n_words - 34) / 40.0))

    # 3. Coincidencia con lenguajes, topics o nombre real del repositorio
    stack_terms = [
        str(x).lower()
        for x in (
            list(repo_meta.get("lenguajes") or [])
            + list(repo_meta.get("topics") or [])
            + [repo_meta.get("nombre", "")]
        )
        if x
    ]
    if stack_terms:
        hits = sum(1 for term in stack_terms if term and term in lower)
        stack_overlap = min(1.0, hits / min(len(stack_terms), 3))
    else:
        stack_overlap = 0.0

    # 4. Densidad de vocabulario técnico / arquitectura de software
    tech_hits = sum(1 for tok in tokens if tok in TECH_PURPOSE_TERMS)
    tech_density = min(1.0, tech_hits / 4.0)

    # 5. Señal de plantilla boilerplate o ruido administrativo
    is_boilerplate = 1.0 if any(pat in lower for pat in BOILERPLATE_PATTERNS) else 0.0

    # 6. Proporción de caracteres alfabéticos (penaliza líneas llenas de rutas o símbolos)
    alpha_chars = sum(1 for ch in sentence if ch.isalpha() or ch.isspace())
    alpha_ratio = alpha_chars / max(len(sentence), 1)

    return [
        float(pos_rel),
        float(len_score),
        float(stack_overlap),
        float(tech_density),
        float(is_boilerplate),
        float(alpha_ratio),
    ]

