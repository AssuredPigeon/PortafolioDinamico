from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config.json"
DATA_DIR = ROOT_DIR / "data"
BACKUP_PATH = DATA_DIR / "backup_portfolio.json"

load_dotenv(ROOT_DIR / ".env")


def normalize_database_url(raw_url: str | None) -> str:
    """
    Normaliza la cadena DATABASE_URL para usar el driver moderno psycopg v3 en PostgreSQL
    (compatible directo con cadenas copiadas de Supabase, Neon o PostgreSQL local).
    Si aún no se ha definido DATABASE_URL en .env, utiliza una base SQL local de respaldo
    en data/portfolio_local.db con exactamente las mismas tablas relacionales.
    """
    url = (raw_url or "").strip()
    if not url:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        local_db = (DATA_DIR / "portfolio_local.db").as_posix()
        return f"sqlite:///{local_db}"

    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://") and "+psycopg" not in url:
        url = "postgresql+psycopg://" + url[len("postgresql://") :]

    return url


def get_database_url() -> str:
    return normalize_database_url(os.getenv("DATABASE_URL"))


def get_github_token() -> str | None:
    token = (os.getenv("GITHUB_TOKEN") or "").strip()
    return token or None


def load_portfolio_config(config_path: Path | None = None) -> dict[str, Any]:
    target = config_path if config_path is not None else CONFIG_PATH
    with target.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_portfolio_config(config_data: dict[str, Any], config_path: Path | None = None) -> None:
    target = config_path if config_path is not None else CONFIG_PATH
    with target.open("w", encoding="utf-8") as fh:
        json.dump(config_data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

