from __future__ import annotations

import json
import os
import re
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import backend.config as app_config
from backend.analytics import compute_activity_trend
from backend.config import (
    ROOT_DIR,
    get_github_token,
    load_portfolio_config,
    save_portfolio_config,
)
from backend.database import SessionLocal, get_db, get_db_dialect_name, init_db
from backend.github_service import (
    GitHubClient,
    GitHubRateLimitError,
    GitHubUserNotFoundError,
)
from backend.ml.predictor import get_readme_analyzer
from backend.ml.train import METRICS_PATH
from backend.models import ActividadCommit, Repositorio, Usuario
from backend.sync_service import (
    get_active_user_and_repos,
    recalculate_db_visibility,
    restore_from_backup_if_empty,
    sync_portfolio_to_db,
)

_last_auto_sync_ts: datetime | None = None
_sync_lock = threading.Lock()
CLIENT_SIDE_COOLDOWN = timedelta(minutes=15)
REPO_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
GITHUB_USER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")


class ConfigUpdatePayload(BaseModel):
    """Esquema validado para guardar cambios desde la Pantalla 4 (Panel de Configuración)."""

    github_username: str | None = None
    nombre: str | None = None
    correo: str | None = None
    excluded_topics: list[str] = Field(default_factory=list)
    extra_repos: list[str] = Field(default_factory=list)
    excluded_repos: list[str] = Field(default_factory=list)
    exclude_forks: bool = True
    generar_descripciones_ia: bool = True
    mostrar_grafica_actividad: bool = True
    metodo_actualizacion: Literal["client-side", "github-actions"] = "github-actions"

    @field_validator("github_username")
    @classmethod
    def _validate_github_username(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lstrip("@").strip()
        if not cleaned:
            return None
        if not GITHUB_USER_RE.match(cleaned):
            raise ValueError(
                f"Usuario de GitHub inválido '{cleaned}'. Usa solo letras, números o guiones."
            )
        return cleaned

    @field_validator("excluded_topics")
    @classmethod
    def _clean_topics(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for v in values:
            item = v.strip().lower()
            if item and item not in seen:
                seen.add(item)
                cleaned.append(item)
        return cleaned

    @field_validator("extra_repos", "excluded_repos")
    @classmethod
    def _validate_repo_slugs(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for v in values:
            item = v.strip()
            if not item:
                continue
            if not REPO_SLUG_RE.match(item):
                raise ValueError(f"Formato inválido '{item}'. Usa el formato dueño/repositorio.")
            low = item.lower()
            if low not in seen:
                seen.add(low)
                cleaned.append(item)
        return cleaned


def _snapshot_current_profile(cfg: dict[str, Any]) -> None:
    """Guarda en perfiles_usuario la configuración particular del usuario actual antes de cambiar."""
    user_cfg = cfg.get("usuario") or {}
    curr_login = str(user_cfg.get("github_username") or "").strip()
    if not curr_login:
        return
    sync_cfg = cfg.get("sincronizacion") or {}
    perfiles = cfg.setdefault("perfiles_usuario", {})
    perfiles[curr_login.lower()] = {
        "github_username": curr_login,
        "nombre": str(user_cfg.get("nombre") or curr_login),
        "correo": str(user_cfg.get("correo") or ""),
        "extra_repos": list(sync_cfg.get("extra_repos") or []),
        "excluded_repos": list(sync_cfg.get("excluded_repos") or []),
        "aliases_nombre": dict(sync_cfg.get("aliases_nombre") or {}),
    }


def _build_portfolio_response(
    db: Session,
    cfg: dict[str, Any],
    origen_carga: str,
    aviso: str | None = None,
    modo_vista_previa: bool = False,
    sync_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    usuario, repo_rows, commit_rows = get_active_user_and_repos(db, cfg)
    repos = [r.to_dict() for r in repo_rows]
    commits = [c.to_dict() for c in commit_rows]

    active_username = str((cfg.get("usuario") or {}).get("github_username") or "").strip().lower()
    backup_meta: dict[str, Any] = {}
    if app_config.BACKUP_PATH.exists():
        try:
            raw_bkp = json.loads(app_config.BACKUP_PATH.read_text(encoding="utf-8"))
            bkp_user = str((raw_bkp.get("usuario") or {}).get("github_username") or "").strip().lower()
            if not active_username or bkp_user == active_username:
                backup_meta = raw_bkp.get("metadata") or {}
        except Exception:
            backup_meta = {}

    if sync_meta:
        backup_meta = {**backup_meta, **sync_meta}

    tendencia = compute_activity_trend(commits, repos)

    return {
        "config": {
            **cfg,
            "admin_key_requerida": bool((os.getenv("PORTFOLIO_ADMIN_KEY") or "").strip()),
        },
        "origen": origen_carga,
        "aviso": aviso,
        "modo_vista_previa": modo_vista_previa,
        "metadata": {
            "ultima_sincronizacion": backup_meta.get("ultima_sincronizacion"),
            "motor_bd": get_db_dialect_name(db.get_bind()),
            "modelo_ia": "PyTorch PortfolioReadmeNet (BiLSTM + Self-Attention)",
            "total_repositorios": len(repos),
            "total_visibles": sum(1 for r in repos if r["visible"]),
            "rate_limit_restante": backup_meta.get("rate_limit_restante"),
        },
        "usuario": usuario.to_dict() if usuario else cfg.get("usuario"),
        "repositorios": repos,
        "actividad_commits": commits,
        "tendencia": tendencia,
    }


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    get_readme_analyzer()
    with SessionLocal() as db:
        restore_from_backup_if_empty(db)
    yield


app = FastAPI(
    title="Portafolio Dinámico Auto-actualizable API",
    description="Backend FastAPI + PostgreSQL + PyTorch para el Portafolio Dinámico Auto-actualizable.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def disable_stale_browser_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith(("/src/", "/api/")):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/src", StaticFiles(directory=str(ROOT_DIR / "src")), name="src")


@app.get("/", include_in_schema=False)
def serve_index() -> FileResponse:
    return FileResponse(ROOT_DIR / "index.html")


@app.get("/data/backup_portfolio.json", include_in_schema=False)
def serve_backup_json() -> FileResponse:
    if not app_config.BACKUP_PATH.exists():
        raise HTTPException(status_code=404, detail="Respaldo local aún no generado.")
    return FileResponse(app_config.BACKUP_PATH)


@app.get("/api/health")
def health_check(db: Session = Depends(get_db)) -> dict[str, Any]:
    ml_metrics = {}
    if METRICS_PATH.exists():
        ml_metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))

    repo_count = db.query(Repositorio).count()
    return {
        "status": "ok",
        "database_engine": get_db_dialect_name(db.get_bind()),
        "repositories_in_db": repo_count,
        "pytorch_model": ml_metrics,
    }


def get_gh_client():
    """Dependencia inyectable de cliente GitHub de solo lectura."""
    with GitHubClient(token=get_github_token()) as client:
        yield client


def _build_preview_config(
    base_cfg: dict[str, Any],
    raw_user: str,
    db: Session,
    gh_client: GitHubClient,
) -> dict[str, Any]:
    """
    Construye una configuración efímera en memoria para previsualizar cualquier cuenta pública
    de GitHub vía ?user=NombreUsuario sin modificar config.json ni data/backup_portfolio.json.
    """
    key_lower = raw_user.lower()
    perfiles = base_cfg.get("perfiles_usuario") or {}
    base_sync = base_cfg.get("sincronizacion") or {}
    base_opts = dict(base_cfg.get("opciones") or {})

    if key_lower in perfiles:
        saved = perfiles[key_lower]
        canonical_login = str(saved.get("github_username") or raw_user)
        user_block = {
            "id_usuario": 0,
            "github_username": canonical_login,
            "nombre": str(saved.get("nombre") or canonical_login),
            "correo": str(saved.get("correo") or ""),
        }
        sync_block = {
            "excluded_topics": list(base_sync.get("excluded_topics") or []),
            "exclude_forks": bool(base_sync.get("exclude_forks", True)),
            "extra_repos": list(saved.get("extra_repos") or []),
            "excluded_repos": list(saved.get("excluded_repos") or []),
            "aliases_nombre": dict(saved.get("aliases_nombre") or {}),
        }
    else:
        existing_user = db.scalar(
            select(Usuario).where(func.lower(Usuario.github_username) == key_lower)
        )
        if existing_user is not None:
            canonical_login = existing_user.github_username
            resolved_name = existing_user.nombre or canonical_login
            resolved_email = existing_user.correo or ""
        else:
            gh_profile = gh_client.fetch_user_profile(raw_user)
            canonical_login = str(gh_profile.get("login") or raw_user)
            resolved_name = str(gh_profile.get("name") or canonical_login)
            resolved_email = str(gh_profile.get("email") or "")

        user_block = {
            "id_usuario": 0,
            "github_username": canonical_login,
            "nombre": resolved_name,
            "correo": resolved_email,
        }
        sync_block = {
            "excluded_topics": list(base_sync.get("excluded_topics") or []),
            "exclude_forks": bool(base_sync.get("exclude_forks", True)),
            "extra_repos": [],
            "excluded_repos": [
                f"{canonical_login}/{canonical_login}",
                f"{canonical_login}/{canonical_login.lower()}.github.io",
            ],
            "aliases_nombre": {},
        }

    return {
        "usuario": user_block,
        "sincronizacion": sync_block,
        "opciones": base_opts,
    }


@app.get("/api/portfolio")
def get_portfolio(
    user: str | None = Query(
        default=None,
        description="Previsualizar el portafolio público de otro usuario de GitHub en modo solo lectura",
    ),
    db: Session = Depends(get_db),
    gh_client: GitHubClient = Depends(get_gh_client),
) -> dict[str, Any]:
    global _last_auto_sync_ts
    cfg = load_portfolio_config()
    aviso: str | None = None
    origen_carga = f"sql-{get_db_dialect_name(db.get_bind())}"

    requested_user = (user or "").strip().lstrip("@").strip()
    active_username = str((cfg.get("usuario") or {}).get("github_username") or "").strip()

    if requested_user and requested_user.lower() != active_username.lower():
        if not GITHUB_USER_RE.match(requested_user):
            raise HTTPException(
                status_code=422,
                detail=f"Usuario de GitHub inválido '{requested_user}'. Usa solo letras, números o guiones.",
            )
        try:
            preview_cfg = _build_preview_config(cfg, requested_user, db, gh_client)
        except GitHubUserNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except GitHubRateLimitError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc

        _, cached_preview_repos, _ = get_active_user_and_repos(db, preview_cfg)
        sync_meta: dict[str, Any] | None = None
        if len(cached_preview_repos) > 0:
            origen_carga = "vista-previa-sql-cache"
        else:
            try:
                with _sync_lock:
                    snapshot = sync_portfolio_to_db(
                        db,
                        config=preview_cfg,
                        gh_client=gh_client,
                        write_backup=False,
                    )
                sync_meta = snapshot.get("metadata") or {}
                aviso = sync_meta.get("aviso_rate_limit")
                origen_carga = "vista-previa-github"
            except GitHubUserNotFoundError as exc:
                db.rollback()
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except GitHubRateLimitError as exc:
                db.rollback()
                raise HTTPException(status_code=429, detail=str(exc)) from exc

        return _build_portfolio_response(
            db,
            preview_cfg,
            origen_carga=origen_carga,
            aviso=aviso,
            modo_vista_previa=True,
            sync_meta=sync_meta,
        )

    metodo = cfg.get("opciones", {}).get("metodo_actualizacion", "github-actions")
    _, active_repos, _ = get_active_user_and_repos(db, cfg)
    repo_count = len(active_repos)
    now_utc = datetime.now(timezone.utc)

    should_sync_now = repo_count == 0 or (
        metodo == "client-side"
        and (_last_auto_sync_ts is None or (now_utc - _last_auto_sync_ts) >= CLIENT_SIDE_COOLDOWN)
    )

    if should_sync_now:
        if _sync_lock.acquire(blocking=False):
            try:
                sync_portfolio_to_db(db, config=cfg, gh_client=gh_client)
                _last_auto_sync_ts = now_utc
                origen_carga = "sincronizado-en-visita"
            except Exception as exc:
                db.rollback()
                aviso = f"Mostrando datos almacenados en SQL (no se pudo refrescar GitHub en vivo: {exc})."
            finally:
                _sync_lock.release()
        else:
            aviso = "Sincronización en curso en segundo plano; mostrando datos actuales en caché SQL."

    return _build_portfolio_response(db, cfg, origen_carga, aviso)


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    cfg = load_portfolio_config()
    _snapshot_current_profile(cfg)
    return {
        **cfg,
        "admin_key_requerida": bool((os.getenv("PORTFOLIO_ADMIN_KEY") or "").strip()),
    }


@app.put("/api/config")
def update_config(
    payload: ConfigUpdatePayload,
    x_admin_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
    gh_client: GitHubClient = Depends(get_gh_client),
) -> dict[str, Any]:
    global _last_auto_sync_ts
    required_key = (os.getenv("PORTFOLIO_ADMIN_KEY") or "").strip()
    if required_key and x_admin_key != required_key:
        raise HTTPException(status_code=403, detail="Clave de administración inválida.")

    cfg = load_portfolio_config()
    cfg.setdefault("usuario", {"id_usuario": 1, "nombre": "", "github_username": "", "correo": ""})
    cfg.setdefault("sincronizacion", {})
    cfg.setdefault("opciones", {})

    # Guardar instantánea del usuario activo antes de cualquier cambio
    _snapshot_current_profile(cfg)
    prev_username = str(cfg["usuario"].get("github_username") or "").strip()
    prev_name = str(cfg["usuario"].get("nombre") or "").strip()
    perfiles = cfg.setdefault("perfiles_usuario", {})

    target_username = payload.github_username
    user_changed = bool(target_username and target_username.lower() != prev_username.lower())

    cfg["sincronizacion"]["excluded_topics"] = payload.excluded_topics
    cfg["sincronizacion"]["exclude_forks"] = payload.exclude_forks
    cfg["opciones"]["generar_descripciones_ia"] = payload.generar_descripciones_ia
    cfg["opciones"]["mostrar_grafica_actividad"] = payload.mostrar_grafica_actividad
    cfg["opciones"]["metodo_actualizacion"] = payload.metodo_actualizacion

    aviso: str | None = None
    origen_carga = f"sql-{get_db_dialect_name(db.get_bind())}"

    if user_changed and target_username:
        target_key = target_username.lower()
        custom_name = (payload.nombre or "").strip()
        # Si por accidente llegó el mismo nombre del usuario anterior, ignorarlo para usar el del nuevo perfil
        if custom_name and custom_name.lower() == prev_name.lower():
            custom_name = ""
        custom_email = (payload.correo or "").strip() if payload.correo is not None else ""

        if target_key in perfiles:
            saved = perfiles[target_key]
            canonical_login = str(saved.get("github_username") or target_username)
            cfg["usuario"]["github_username"] = canonical_login
            cfg["usuario"]["nombre"] = custom_name or str(saved.get("nombre") or canonical_login)
            cfg["usuario"]["correo"] = custom_email if custom_email else str(saved.get("correo") or "")
            cfg["sincronizacion"]["extra_repos"] = (
                payload.extra_repos if payload.extra_repos else list(saved.get("extra_repos") or [])
            )
            cfg["sincronizacion"]["excluded_repos"] = (
                payload.excluded_repos if payload.excluded_repos else list(saved.get("excluded_repos") or [])
            )
            cfg["sincronizacion"]["aliases_nombre"] = dict(saved.get("aliases_nombre") or {})
        else:
            try:
                gh_profile = gh_client.fetch_user_profile(target_username)
            except GitHubUserNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except GitHubRateLimitError as exc:
                raise HTTPException(status_code=429, detail=str(exc)) from exc

            canonical_login = str(gh_profile.get("login") or target_username)
            resolved_name = custom_name or str(gh_profile.get("name") or canonical_login)
            resolved_email = custom_email or str(gh_profile.get("email") or "")

            default_exclusions = [
                f"{canonical_login}/{canonical_login}",
                f"{canonical_login}/{canonical_login.lower()}.github.io",
            ]
            merged_exclusions = list(dict.fromkeys([*default_exclusions, *payload.excluded_repos]))

            cfg["usuario"]["github_username"] = canonical_login
            cfg["usuario"]["nombre"] = resolved_name
            cfg["usuario"]["correo"] = resolved_email
            cfg["sincronizacion"]["extra_repos"] = payload.extra_repos
            cfg["sincronizacion"]["excluded_repos"] = merged_exclusions
            cfg["sincronizacion"]["aliases_nombre"] = {}

        _snapshot_current_profile(cfg)

        _, cached_repos, _ = get_active_user_and_repos(db, cfg)
        if len(cached_repos) > 0:
            save_portfolio_config(cfg)
            recalculate_db_visibility(db, cfg)
            origen_carga = "perfil-sql-cache"
        else:
            try:
                with _sync_lock:
                    snapshot = sync_portfolio_to_db(db, config=cfg, gh_client=gh_client)
                save_portfolio_config(cfg)
                _last_auto_sync_ts = datetime.now(timezone.utc)
                aviso = snapshot.get("metadata", {}).get("aviso_rate_limit")
                origen_carga = "sincronizado-cambio-usuario"
            except GitHubUserNotFoundError as exc:
                db.rollback()
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except GitHubRateLimitError as exc:
                db.rollback()
                raise HTTPException(status_code=429, detail=str(exc)) from exc
    else:
        if payload.nombre is not None and payload.nombre.strip():
            cfg["usuario"]["nombre"] = payload.nombre.strip()
        if payload.correo is not None:
            cfg["usuario"]["correo"] = payload.correo.strip()

        cfg["sincronizacion"]["extra_repos"] = payload.extra_repos
        cfg["sincronizacion"]["excluded_repos"] = payload.excluded_repos

        _snapshot_current_profile(cfg)
        save_portfolio_config(cfg)
        recalculate_db_visibility(db, cfg)

    return _build_portfolio_response(
        db,
        cfg,
        origen_carga=origen_carga,
        aviso=aviso,
    )


@app.get("/api/projects/{id_repositorio}")
def get_project_detail(id_repositorio: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    repo = db.get(Repositorio, id_repositorio)
    if not repo:
        raise HTTPException(status_code=404, detail="Repositorio no encontrado en la base de datos.")
    return repo.to_dict()


@app.post("/api/sync")
def trigger_sync(
    force: bool = Query(default=False, description="Forzar relectura completa ignorando caché por commit"),
    db: Session = Depends(get_db),
    gh_client: GitHubClient = Depends(get_gh_client),
) -> dict[str, Any]:
    global _last_auto_sync_ts
    cfg = load_portfolio_config()
    try:
        with _sync_lock:
            snapshot = sync_portfolio_to_db(db, config=cfg, gh_client=gh_client, force_refresh=force)
        _last_auto_sync_ts = datetime.now(timezone.utc)
        aviso = snapshot.get("metadata", {}).get("aviso_rate_limit")
        return _build_portfolio_response(
            db,
            cfg,
            origen_carga="sincronizado-manual",
            aviso=aviso,
        )
    except GitHubUserNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GitHubRateLimitError as exc:
        db.rollback()
        raise HTTPException(status_code=429, detail=str(exc)) from exc
