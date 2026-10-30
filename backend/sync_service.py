from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

import backend.config as app_config
from backend.config import (
    DATA_DIR,
    get_github_token,
    load_portfolio_config,
)
from backend.database import SessionLocal, get_db_dialect_name, init_db
from backend.github_service import GitHubClient, GitHubRateLimitError
from backend.ml.predictor import PyTorchReadmeAnalyzer, get_readme_analyzer
from backend.models import ActividadCommit, Repositorio, Usuario
from backend.repo_inspector import inspect_and_enrich_repository


def parse_github_datetime(iso_str: str) -> datetime:
    if iso_str.endswith("Z"):
        iso_str = iso_str[:-1] + "+00:00"
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def evaluate_repo_visibility(gh_repo: dict[str, Any], sync_cfg: dict[str, Any]) -> bool:
    if sync_cfg.get("exclude_forks", True) and gh_repo.get("fork", False):
        return False

    excluded_repos = {r.strip().lower() for r in (sync_cfg.get("excluded_repos") or []) if str(r).strip()}
    full_name = str(gh_repo.get("full_name") or "").strip().lower()
    if full_name in excluded_repos:
        return False

    excluded_topics = {t.strip().lower() for t in (sync_cfg.get("excluded_topics") or []) if str(t).strip()}
    topics = [str(t).strip().lower() for t in (gh_repo.get("topics") or []) if str(t).strip()]
    if any(t in excluded_topics for t in topics):
        return False

    return True


def get_active_user_and_repos(
    db: Session,
    config: dict[str, Any] | None = None,
) -> tuple[Usuario | None, list[Repositorio], list[ActividadCommit]]:
    """
    Obtiene el Usuario, sus Repositorios (propios + extra_repos configurados) y su
    historial de ActividadCommit correspondientes a la cuenta activa en config.json.
    Permite cambiar de usuario de GitHub sin mezclar ni borrar repositorios cacheados de otros perfiles.
    """
    cfg = config or load_portfolio_config()
    active_username = str(cfg.get("usuario", {}).get("github_username") or "").strip()
    sync_cfg = cfg.get("sincronizacion", {})
    extra_set = {
        str(x).strip().lower()
        for x in (sync_cfg.get("extra_repos") or [])
        if str(x).strip()
    }

    usuario: Usuario | None = None
    if active_username:
        usuario = db.scalar(
            select(Usuario).where(func.lower(Usuario.github_username) == active_username.lower())
        )
    else:
        usuario = db.scalar(select(Usuario).order_by(Usuario.id_usuario.asc()))

    all_repos = list(
        db.scalars(select(Repositorio).order_by(Repositorio.fecha_ultimo_commit.desc()))
    )
    if active_username:
        prefix = f"{active_username.lower()}/"
        repos = [
            r
            for r in all_repos
            if r.nombre_completo.lower().startswith(prefix)
            or r.nombre_completo.lower() in extra_set
        ]
    else:
        repos = all_repos

    repo_ids = {r.id_repositorio for r in repos}
    if repo_ids:
        commits = list(
            db.scalars(
                select(ActividadCommit)
                .where(ActividadCommit.id_repositorio.in_(repo_ids))
                .order_by(
                    ActividadCommit.fecha.asc(),
                    ActividadCommit.id_repositorio.asc(),
                )
            )
        )
    else:
        commits = []

    return usuario, repos, commits


def recalculate_db_visibility(
    db: Session,
    config: dict[str, Any],
    backup_path: Path | None = None,
) -> dict[str, Any]:
    """
    Recalcula al instante la visibilidad y alias de los repositorios ya guardados en SQL
    cuando el usuario modifica el Panel de Configuración (Actividad H), sin consumir
    llamadas adicionales a la API de GitHub.
    """
    sync_cfg = config.get("sincronizacion", {})
    aliases = sync_cfg.get("aliases_nombre") or {}
    user_cfg = config.get("usuario", {})
    active_username = str(user_cfg.get("github_username") or "").strip()

    if active_username:
        u_row = db.scalar(
            select(Usuario).where(func.lower(Usuario.github_username) == active_username.lower())
        )
        if u_row:
            if user_cfg.get("nombre"):
                u_row.nombre = str(user_cfg["nombre"])
            if "correo" in user_cfg:
                u_row.correo = str(user_cfg.get("correo") or "")

    _, active_repos, _ = get_active_user_and_repos(db, config)
    for r in active_repos:
        short_default = r.nombre_completo.split("/")[-1] if "/" in r.nombre_completo else r.nombre
        r.nombre = aliases.get(r.nombre_completo, short_default)
        r.visible = evaluate_repo_visibility(
            {
                "full_name": r.nombre_completo,
                "topics": r.topics or [],
                "fork": r.es_fork,
            },
            sync_cfg,
        )

    db.commit()
    return export_database_backup(db, config=config, backup_path=backup_path)


def export_database_backup(
    db: Session,
    metadata_extra: dict[str, Any] | None = None,
    backup_path: Path | None = None,
    config: dict[str, Any] | None = None,
    write_file: bool = True,
) -> dict[str, Any]:
    """
    Exporta una instantánea completa de las tablas SQL activas a data/backup_portfolio.json
    para cumplir con RNF4 (respaldo periódico de descripciones e historial).
    """
    cfg = config or load_portfolio_config()
    target_backup = backup_path if backup_path is not None else app_config.BACKUP_PATH
    usuario, repos, commits = get_active_user_and_repos(db, cfg)

    payload = {
        "metadata": {
            "ultima_sincronizacion": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "motor_bd": get_db_dialect_name(db.get_bind()),
            "modelo_ia": "PyTorch PortfolioReadmeNet (BiLSTM + Self-Attention)",
            "total_repositorios": len(repos),
            "total_visibles": sum(1 for r in repos if r.visible),
            "total_registros_actividad": len(commits),
            **(metadata_extra or {}),
        },
        "usuario": usuario.to_dict() if usuario else cfg.get("usuario"),
        "repositorios": [r.to_dict() for r in repos],
        "actividad_commits": [c.to_dict() for c in commits],
    }

    if write_file:
        target_backup.parent.mkdir(parents=True, exist_ok=True)
        target_backup.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def restore_from_backup_if_empty(db: Session, backup_path: Path | None = None) -> bool:
    """Si la BD SQL inicia vacía y existe un respaldo previo, restaura sus registros iniciales."""
    target_backup = backup_path if backup_path is not None else app_config.BACKUP_PATH
    existing_count = db.query(Repositorio).count()
    if existing_count > 0 or not target_backup.exists():
        return False

    raw = json.loads(target_backup.read_text(encoding="utf-8"))
    u_data = raw.get("usuario")
    if not u_data:
        return False

    user = Usuario(
        id_usuario=int(u_data.get("id_usuario", 1)),
        nombre=u_data["nombre"],
        github_username=u_data["github_username"],
        correo=u_data["correo"],
    )
    db.merge(user)
    db.flush()

    for r_data in raw.get("repositorios") or []:
        repo = Repositorio(
            id_repositorio=int(r_data["id_repositorio"]),
            id_usuario=int(r_data.get("id_usuario", user.id_usuario)),
            nombre=r_data["nombre"],
            nombre_completo=r_data["nombre_completo"],
            descripcion_original=r_data.get("descripcion_original") or "",
            descripcion_generada=r_data.get("descripcion_generada"),
            origen_descripcion=r_data.get("origen_descripcion") or "metadatos",
            puntaje_ia=float(r_data.get("puntaje_ia") or 0.0),
            lenguajes=list(r_data.get("lenguajes") or []),
            topics=list(r_data.get("topics") or []),
            detalle_tecnico=dict(r_data.get("detalle_tecnico") or {}),
            visible=bool(r_data.get("visible", True)),
            url=r_data["url"],
            estrellas=int(r_data.get("estrellas") or 0),
            fecha_ultimo_commit=parse_github_datetime(r_data["fecha_ultimo_commit"]),
            es_fork=bool(r_data.get("es_fork", False)),
            readme_consultado=bool(r_data.get("readme_consultado", False)),
        )
        db.merge(repo)

    db.flush()

    for c_data in raw.get("actividad_commits") or []:
        act = ActividadCommit(
            id_repositorio=int(c_data["id_repositorio"]),
            fecha=date.fromisoformat(str(c_data["fecha"])[:10]),
            cantidad_commits=int(c_data["cantidad_commits"]),
            lenguaje_principal=c_data.get("lenguaje_principal") or "Sin detectar",
        )
        db.add(act)

    db.commit()
    return True


def sync_portfolio_to_db(
    db: Session,
    config: dict[str, Any] | None = None,
    gh_client: GitHubClient | None = None,
    analyzer: PyTorchReadmeAnalyzer | None = None,
    force_refresh: bool = False,
    backup_path: Path | None = None,
    window_days: int = 70,
    enable_translation: bool | None = None,
    max_deep_inspect: int = 40,
    max_workers: int = 8,
    write_backup: bool = True,
) -> dict[str, Any]:
    """
    Sincroniza los repositorios desde GitHub hacia la base de datos SQL (Usuario, Repositorio,
    ActividadCommit), ejecuta el modelo neuronal en PyTorch + inspección profunda del código
    en paralelo y realiza la escritura SQL en una sola transacción rápida al final.
    """
    cfg = config or load_portfolio_config()
    user_cfg = cfg["usuario"]
    sync_cfg = cfg.get("sincronizacion", {})
    opts_cfg = cfg.get("opciones", {})

    enable_pytorch_desc = bool(opts_cfg.get("generar_descripciones_ia", True))
    enable_commits = bool(opts_cfg.get("mostrar_grafica_actividad", True))

    owns_client = gh_client is None
    use_translation = owns_client if enable_translation is None else enable_translation
    client = gh_client or GitHubClient(token=get_github_token())

    try:
        # 1. Lectura previa sin abrir transacción de escritura en SQLite (evita bloqueos durante llamadas HTTP)
        prev_repos: dict[int, Repositorio] = {
            r.id_repositorio: r
            for r in db.scalars(select(Repositorio))
        }
        repos_with_commits: set[int] = set(
            db.scalars(select(ActividadCommit.id_repositorio).distinct())
        )
        prev_push_iso: dict[int, str] = {}
        for r_id, r_obj in prev_repos.items():
            prev_dt = r_obj.fecha_ultimo_commit
            if prev_dt.tzinfo is None:
                prev_dt = prev_dt.replace(tzinfo=timezone.utc)
            prev_push_iso[r_id] = prev_dt.astimezone(timezone.utc).isoformat()

        # 2. Consultar repositorios de la cuenta principal y repos colaborativos extra
        raw_map: dict[str, dict[str, Any]] = {}
        for repo in client.fetch_user_repos(user_cfg["github_username"]):
            raw_map[repo["full_name"].lower()] = repo

        for extra_full in sync_cfg.get("extra_repos") or []:
            key = extra_full.lower()
            if key in raw_map:
                continue
            extra_data = client.fetch_single_repo(extra_full)
            if extra_data:
                raw_map[key] = extra_data

        sorted_gh = sorted(
            raw_map.values(),
            key=lambda item: parse_github_datetime(item["pushed_at"]),
            reverse=True,
        )

        aliases = sync_cfg.get("aliases_nombre") or {}
        pytorch_engine = (analyzer or get_readme_analyzer()) if enable_pytorch_desc else None

        # 3. Planificar qué repositorios requieren enriquecimiento de red + PyTorch + código fuente
        enrichment_targets: list[tuple[dict[str, Any], str]] = []
        repo_plan: dict[int, dict[str, Any]] = {}
        deep_budget_used = 0

        for gh in sorted_gh:
            repo_id = int(gh["id"])
            pushed_dt = parse_github_datetime(gh["pushed_at"])
            pushed_iso = pushed_dt.isoformat()
            existing = prev_repos.get(repo_id)
            same_commit = bool(
                existing is not None
                and prev_push_iso.get(repo_id) == pushed_iso
                and not force_refresh
            )
            visible = evaluate_repo_visibility(gh, sync_cfg)
            has_deep_cache = bool(existing is not None and existing.detalle_tecnico)
            display_name = aliases.get(gh["full_name"], gh["name"])

            needs_enrichment = (
                visible
                and deep_budget_used < max_deep_inspect
                and (
                    not same_commit
                    or existing is None
                    or not existing.readme_consultado
                    or not has_deep_cache
                )
            )
            if needs_enrichment:
                deep_budget_used += 1
                enrichment_targets.append((gh, display_name))

            repo_plan[repo_id] = {
                "pushed_dt": pushed_dt,
                "same_commit": same_commit,
                "visible": visible,
                "has_deep_cache": has_deep_cache,
                "display_name": display_name,
            }

        def _enrich_worker(item: tuple[dict[str, Any], str]) -> tuple[int, dict[str, Any]]:
            gh_item, disp_name = item
            r_id = int(gh_item["id"])
            lang_bytes: dict[str, int] = {}
            queried_lang = False
            try:
                lang_bytes = client.fetch_repo_language_bytes(gh_item["full_name"])
                queried_lang = True
            except GitHubRateLimitError:
                lang_bytes = {}

            langs = (
                list(lang_bytes.keys())
                if lang_bytes
                else ([gh_item["language"]] if gh_item.get("language") else [])
            )
            try:
                raw_readme = client.fetch_repo_readme(gh_item["full_name"]) if enable_pytorch_desc else None
                pred, clean_langs, detalle_tecnico = inspect_and_enrich_repository(
                    gh_client=client,
                    gh_repo=gh_item,
                    lang_bytes=lang_bytes,
                    raw_readme=raw_readme,
                    analyzer=pytorch_engine,
                    repo_display_name=disp_name,
                    enable_translation=use_translation,
                )
                return (
                    r_id,
                    {
                        "ok": True,
                        "queried_lang": queried_lang,
                        "lenguajes": clean_langs if clean_langs else langs,
                        "pred": pred,
                        "detalle_tecnico": detalle_tecnico,
                    },
                )
            except GitHubRateLimitError:
                return (
                    r_id,
                    {
                        "ok": False,
                        "queried_lang": queried_lang,
                        "lenguajes": langs,
                    },
                )

        enriched_results: dict[int, dict[str, Any]] = {}
        if enrichment_targets:
            workers = min(max_workers, len(enrichment_targets))
            if workers <= 1:
                for target in enrichment_targets:
                    rid, res = _enrich_worker(target)
                    enriched_results[rid] = res
            else:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    for rid, res in pool.map(_enrich_worker, enrichment_targets):
                        enriched_results[rid] = res

        # 4. Consultar ActividadCommit en paralelo antes de abrir transacción de escritura SQL
        commits_fetched_by_repo: dict[int, tuple[str, dict[str, int]]] = {}
        cutoff_date: date | None = None
        if enable_commits:
            now_utc = datetime.now(timezone.utc)
            cutoff_dt = now_utc - timedelta(days=window_days)
            cutoff_date = cutoff_dt.date()
            cutoff_iso = cutoff_date.isoformat()
            since_iso = cutoff_dt.isoformat().replace("+00:00", "Z")

            push_events_by_repo: dict[str, dict[str, int]] = {}
            try:
                push_events_by_repo = client.fetch_user_push_events(
                    user_cfg["github_username"],
                    cutoff_date_iso=cutoff_iso,
                )
            except GitHubRateLimitError:
                push_events_by_repo = {}

            visible_gh_candidates = [
                gh for gh in sorted_gh if repo_plan[int(gh["id"])]["visible"]
            ][:15]

            commit_targets: list[tuple[int, str, str, dict[str, int]]] = []
            for gh in visible_gh_candidates:
                r_id = int(gh["id"])
                plan = repo_plan[r_id]
                pushed_dt = plan["pushed_dt"]
                repo_event_days = push_events_by_repo.get(gh["full_name"].lower(), {})
                if pushed_dt < cutoff_dt and not repo_event_days:
                    continue
                if plan["same_commit"] and (r_id in repos_with_commits) and not force_refresh:
                    continue

                # Determinar lenguaje principal resuelto
                enr = enriched_results.get(r_id)
                if enr and enr.get("lenguajes"):
                    p_lang = enr["lenguajes"][0]
                elif prev_repos.get(r_id) and prev_repos[r_id].lenguajes:
                    p_lang = prev_repos[r_id].lenguajes[0]
                else:
                    p_lang = gh.get("language") or "Sin detectar"

                commit_targets.append((r_id, gh["full_name"], p_lang, repo_event_days))

            def _commit_worker(
                c_item: tuple[int, str, str, dict[str, int]],
            ) -> tuple[int, str, dict[str, int] | None]:
                r_id, full_name, p_lang, ev_days = c_item
                try:
                    daily_map = client.fetch_daily_commits_window(
                        full_name,
                        cutoff_date_iso=cutoff_iso,
                        since_iso=since_iso,
                    )
                    for ev_day, ev_count in ev_days.items():
                        if ev_day >= cutoff_iso:
                            daily_map[ev_day] = max(daily_map.get(ev_day, 0), ev_count)
                    return (r_id, p_lang, daily_map)
                except GitHubRateLimitError:
                    return (r_id, p_lang, None)

            if commit_targets:
                c_workers = min(max_workers, len(commit_targets))
                if c_workers <= 1:
                    for ct in commit_targets:
                        rid, plang, dmap = _commit_worker(ct)
                        if dmap is not None:
                            commits_fetched_by_repo[rid] = (plang, dmap)
                else:
                    with ThreadPoolExecutor(max_workers=c_workers) as pool:
                        for rid, plang, dmap in pool.map(_commit_worker, commit_targets):
                            if dmap is not None:
                                commits_fetched_by_repo[rid] = (plang, dmap)

        # 5. Transacción atómica ultrarrápida en SQL (< 50 ms) con todos los datos ya descargados
        usuario = db.scalar(
            select(Usuario).where(
                func.lower(Usuario.github_username) == str(user_cfg["github_username"]).lower()
            )
        )
        if not usuario:
            usuario = Usuario(
                nombre=user_cfg["nombre"],
                github_username=user_cfg["github_username"],
                correo=user_cfg.get("correo") or "",
            )
            db.add(usuario)
            db.flush()
        else:
            usuario.github_username = user_cfg["github_username"]
            usuario.nombre = user_cfg["nombre"]
            usuario.correo = user_cfg.get("correo") or ""

        languages_queried = 0
        readmes_processed = 0
        user_prefix = f"{str(user_cfg['github_username']).lower()}/"

        for gh in sorted_gh:
            repo_id = int(gh["id"])
            plan = repo_plan[repo_id]
            existing = prev_repos.get(repo_id)
            enr = enriched_results.get(repo_id)

            if enr is not None:
                if enr.get("queried_lang"):
                    languages_queried += 1
                lenguajes = enr["lenguajes"]
            elif plan["same_commit"] and existing is not None and plan["has_deep_cache"]:
                lenguajes = list(existing.lenguajes or [])
            else:
                lenguajes = [gh["language"]] if gh.get("language") else []

            if existing is None:
                repo_row = Repositorio(
                    id_repositorio=repo_id,
                    id_usuario=usuario.id_usuario,
                    nombre=plan["display_name"],
                    nombre_completo=gh["full_name"],
                    descripcion_original=gh.get("description") or "",
                    descripcion_generada=None,
                    origen_descripcion="metadatos",
                    puntaje_ia=0.0,
                    lenguajes=lenguajes,
                    topics=list(gh.get("topics") or []),
                    detalle_tecnico={},
                    visible=plan["visible"],
                    url=gh["html_url"],
                    estrellas=int(gh.get("stargazers_count") or 0),
                    fecha_ultimo_commit=plan["pushed_dt"],
                    es_fork=bool(gh.get("fork", False)),
                    readme_consultado=False,
                )
                db.add(repo_row)
            else:
                repo_row = existing
                if gh["full_name"].lower().startswith(user_prefix):
                    repo_row.id_usuario = usuario.id_usuario
                repo_row.nombre = plan["display_name"]
                repo_row.nombre_completo = gh["full_name"]
                repo_row.descripcion_original = gh.get("description") or ""
                repo_row.lenguajes = lenguajes
                repo_row.topics = list(gh.get("topics") or [])
                repo_row.visible = plan["visible"]
                repo_row.url = gh["html_url"]
                repo_row.estrellas = int(gh.get("stargazers_count") or 0)
                repo_row.fecha_ultimo_commit = plan["pushed_dt"]
                repo_row.es_fork = bool(gh.get("fork", False))

            if enr is not None and enr.get("ok"):
                pred = enr["pred"]
                repo_row.descripcion_generada = pred.descripcion
                repo_row.origen_descripcion = pred.origen
                repo_row.puntaje_ia = pred.puntaje_relevancia
                repo_row.detalle_tecnico = enr["detalle_tecnico"]
                repo_row.readme_consultado = True
                readmes_processed += 1

        db.flush()

        commits_repos_queried = len(commits_fetched_by_repo)
        if enable_commits and cutoff_date is not None:
            db.execute(delete(ActividadCommit).where(ActividadCommit.fecha < cutoff_date))
            for r_id, (primary_lang, daily_map) in commits_fetched_by_repo.items():
                db.execute(
                    delete(ActividadCommit).where(ActividadCommit.id_repositorio == r_id)
                )
                for day_str, count in sorted(daily_map.items()):
                    db.add(
                        ActividadCommit(
                            id_repositorio=r_id,
                            fecha=date.fromisoformat(day_str),
                            cantidad_commits=count,
                            lenguaje_principal=primary_lang,
                        )
                    )

        db.commit()

        snapshot = export_database_backup(
            db,
            metadata_extra={
                "modo_autenticacion": "token" if client.token else "publico",
                "lenguajes_consultados": languages_queried,
                "readmes_procesados_pytorch": readmes_processed,
                "repos_commits_consultados": commits_repos_queried,
                "rate_limit_restante": client.rate_remaining,
                "rate_limit_maximo": client.rate_limit,
            },
            backup_path=backup_path,
            config=cfg,
            write_file=write_backup,
        )
        return snapshot

    except GitHubRateLimitError as exc:
        db.rollback()
        _, existing_active, _ = get_active_user_and_repos(db, cfg)
        if len(existing_active) > 0:
            return export_database_backup(
                db,
                metadata_extra={"aviso_rate_limit": str(exc)},
                backup_path=backup_path,
                config=cfg,
                write_file=write_backup,
            )
        raise
    finally:
        if owns_client:
            client.close()


if __name__ == "__main__":
    import sys

    force = "--force" in sys.argv
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    with SessionLocal() as session:
        result = sync_portfolio_to_db(session, force_refresh=force)
        meta = result["metadata"]
        print("=== Sincronización SQL + PyTorch completada ===")
        print(f"- Motor SQL activo         : {meta['motor_bd']}")
        print(f"- Modelo de lenguaje       : {meta['modelo_ia']}")
        print(f"- Repositorios totales     : {meta['total_repositorios']} ({meta['total_visibles']} visibles)")
        print(f"- READMEs analizados (IA)  : {meta.get('readmes_procesados_pytorch', 0)}")
        print(f"- Registros ActividadCommit: {meta['total_registros_actividad']}")
        print(f"- Rate limit restante      : {meta.get('rate_limit_restante')}/{meta.get('rate_limit_maximo')}")

