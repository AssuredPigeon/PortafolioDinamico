from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx
import pytest
import torch
from fastapi.testclient import TestClient

from backend.analytics import compute_activity_trend
from backend.config import normalize_database_url
from backend.database import build_engine, get_db, init_db
from backend.github_service import GitHubClient, GitHubRateLimitError
from backend.main import app, get_gh_client
from backend.ml.network import PortfolioReadmeNet
from backend.ml.predictor import PyTorchReadmeAnalyzer
from backend.ml.tokenizer import clean_readme_to_sentences
from backend.models import ActividadCommit, Repositorio, Usuario
from backend.repo_inspector import detect_text_language, inspect_and_enrich_repository
from backend.sync_service import sync_portfolio_to_db
from sqlalchemy.orm import sessionmaker


def test_normalize_postgresql_urls_for_supabase_and_neon():
    """Verifica que las URLs de PostgreSQL (Supabase/Neon/local) usen psycopg v3 automáticamente."""
    raw_pg = "postgres://user:pass@db.supabase.co:5432/postgres?sslmode=require"
    assert normalize_database_url(raw_pg).startswith("postgresql+psycopg://user:pass@db.supabase.co")

    raw_neon = "postgresql://neondb_owner:secret@ep-cool.us-east-2.aws.neon.tech/neondb"
    assert normalize_database_url(raw_neon).startswith("postgresql+psycopg://neondb_owner:secret@")


def test_pytorch_network_shapes_and_attention_mask():
    """Verifica tensores de salida y enmascaramiento de atención en la red PyTorch pura."""
    net = PortfolioReadmeNet(vocab_size=120, embed_dim=32, lstm_hidden=32)
    tokens = torch.tensor([[2, 5, 9, 0, 0], [0, 0, 0, 0, 0]], dtype=torch.long)
    feats = torch.rand((2, 6), dtype=torch.float32)

    sal_logits, proj_logits, attn = net(tokens, feats)
    assert sal_logits.shape == (2,)
    assert proj_logits.shape == (2,)
    assert attn.shape == (2, 5)
    # En la primera fila los últimos 2 tokens son <PAD>=0, por lo que su atención debe ser ~0
    assert float(attn[0, 3].item()) < 1e-5
    assert float(attn[0, 4].item()) < 1e-5


def test_pytorch_analyzer_extracts_real_sentences_and_rejects_laravel_boilerplate():
    """
    RF2 y Regla 6: El analizador en PyTorch debe extraer oraciones reales de arquitectura
    sin inventar palabras, y descartar plantillas genéricas por defecto (ej. Laravel README).
    """
    analyzer = PyTorchReadmeAnalyzer()

    # Caso A: README real descriptivo
    real_readme = """
    # DanceLabo
    [![Python](https://img.shields.io/badge/python-3.11-blue)](https://python.org)

    Sistema de evaluación de coreografías en tiempo real utilizando visión por computadora con MediaPipe y redes LSTM conectadas a Unity.

    ```bash
    pip install -r requirements.txt
    ```
    """
    pred_real = analyzer.analyze_readme(
        real_readme,
        {"nombre": "DanceLabo", "lenguajes": ["Python", "C#"], "topics": []},
    )
    assert pred_real.descripcion is not None
    assert "MediaPipe" in pred_real.descripcion
    assert "pip install" not in pred_real.descripcion
    assert pred_real.origen == "pytorch-bilstm"
    assert pred_real.puntaje_relevancia >= 0.48

    # Caso B: README por defecto de Laravel (ruido/plantilla)
    laravel_default = """
    # About Laravel
    Laravel is a web application framework with expressive, elegant syntax that attempts to take the pain out of development.
    We would like to extend our thanks to the following sponsors for funding Laravel development.
    """
    pred_boiler = analyzer.analyze_readme(
        laravel_default,
        {"nombre": "animeExplorer", "lenguajes": ["Blade", "PHP"], "topics": []},
    )
    assert pred_boiler.descripcion is None
    assert pred_boiler.origen == "metadatos"


def test_github_client_handles_http_202_retry_and_404_readme():
    """Regla 7 y Sección 9: Manejo de respuestas HTTP 202 en /stats/commit_activity y 404 en /readme."""
    attempts = {"stats": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/readme"):
            return httpx.Response(404, headers={"x-ratelimit-remaining": "58", "x-ratelimit-limit": "60"})
        if request.url.path.endswith("/stats/commit_activity"):
            attempts["stats"] += 1
            if attempts["stats"] == 1:
                return httpx.Response(202, headers={"x-ratelimit-remaining": "57"})
            return httpx.Response(
                200,
                json=[{"week": 1762041600, "total": 4, "days": [1, 3, 0, 0, 0, 0, 0]}],
                headers={"x-ratelimit-remaining": "56"},
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as raw_http:
        gh = GitHubClient(http_client=raw_http)
        assert gh.fetch_repo_readme("owner/no-readme") is None

        weeks, status = gh.fetch_stats_commit_activity(
            "owner/active-repo", max_retries=2, retry_delay_sec=0.01
        )
        assert status == 200
        assert attempts["stats"] == 2
        assert weeks is not None and weeks[0]["total"] == 4


def test_full_sql_sync_and_activity_trend_with_mocked_github(tmp_path):
    """
    Prueba integral de las entidades SQL (Usuario, Repositorio, ActividadCommit),
    filtrado por topics (RF3), ordenamiento (RF6), PyTorch (RF2) y racha de commits (RF7).
    """
    db_file = tmp_path / "test_portfolio.db"
    test_engine = build_engine(f"sqlite:///{db_file.as_posix()}")
    init_db(test_engine)
    TestSession = sessionmaker(bind=test_engine, expire_on_commit=False)

    def mock_github_handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if p == "/users/AssuredPigeon/repos":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 200,
                        "name": "repo-practica",
                        "full_name": "AssuredPigeon/repo-practica",
                        "description": "Tarea escolar",
                        "language": "Python",
                        "topics": ["practica"],
                        "html_url": "https://github.com/AssuredPigeon/repo-practica",
                        "stargazers_count": 0,
                        "pushed_at": "2026-11-03T12:00:00Z",
                        "fork": False,
                    },
                    {
                        "id": 100,
                        "name": "api-semantica",
                        "full_name": "AssuredPigeon/api-semantica",
                        "description": "",
                        "language": "Python",
                        "topics": ["nlp"],
                        "html_url": "https://github.com/AssuredPigeon/api-semantica",
                        "stargazers_count": 3,
                        "pushed_at": "2026-11-02T15:00:00Z",
                        "fork": False,
                    },
                ],
                headers={"x-ratelimit-remaining": "55", "x-ratelimit-limit": "60"},
            )
        if p == "/repos/labtech/extra-app":
            return httpx.Response(
                200,
                json={
                    "id": 300,
                    "name": "extra-app",
                    "full_name": "labtech/extra-app",
                    "description": "Sistema colaborativo",
                    "language": "TypeScript",
                    "topics": [],
                    "html_url": "https://github.com/labtech/extra-app",
                    "stargazers_count": 5,
                    "pushed_at": "2026-11-03T18:00:00Z",
                    "fork": False,
                },
            )
        if p.endswith("/languages"):
            return httpx.Response(200, json={"TypeScript": 9000, "Python": 4000})
        if p.endswith("/readme"):
            return httpx.Response(
                200,
                text="# Proyecto\nPlataforma backend en Python y FastAPI para búsqueda semántica y gestión automatizada en tiempo real.",
            )
        if p.endswith("/stats/commit_activity"):
            return httpx.Response(202)
        if p.endswith("/commits"):
            return httpx.Response(
                200,
                json=[
                    {"commit": {"author": {"date": "2026-11-01T10:00:00Z"}}},
                    {"commit": {"author": {"date": "2026-11-02T11:00:00Z"}}},
                    {"commit": {"author": {"date": "2026-11-03T09:00:00Z"}}},
                ],
            )
        return httpx.Response(404)

    cfg = {
        "usuario": {
            "id_usuario": 1,
            "nombre": "Daniel Tornero Solano",
            "github_username": "AssuredPigeon",
            "correo": "danieltornero4@gmail.com",
        },
        "sincronizacion": {
            "extra_repos": ["labtech/extra-app"],
            "excluded_topics": ["practica"],
            "excluded_repos": [],
            "exclude_forks": True,
            "aliases_nombre": {},
        },
        "opciones": {
            "generar_descripciones_ia": True,
            "mostrar_grafica_actividad": True,
            "metodo_actualizacion": "github-actions",
        },
    }

    backup_file = tmp_path / "backup.json"
    transport = httpx.MockTransport(mock_github_handler)
    with httpx.Client(transport=transport) as raw_client, TestSession() as session:
        gh_client = GitHubClient(http_client=raw_client)
        snapshot = sync_portfolio_to_db(
            session,
            config=cfg,
            gh_client=gh_client,
            backup_path=backup_file,
        )

        assert backup_file.exists()
        assert snapshot["metadata"]["total_repositorios"] == 3
        assert snapshot["metadata"]["total_visibles"] == 2

        visibles = [r for r in snapshot["repositorios"] if r["visible"]]
        # Ordenado por actividad reciente: extra-app (03 nov) antes que api-semantica (02 nov)
        assert visibles[0]["nombre_completo"] == "labtech/extra-app"
        assert visibles[1]["nombre_completo"] == "AssuredPigeon/api-semantica"
        assert visibles[0]["origen_descripcion"] == "pytorch-bilstm"
        assert "FastAPI" in (visibles[0]["descripcion_generada"] or "")

        trend = compute_activity_trend(
            snapshot["actividad_commits"],
            snapshot["repositorios"],
            reference_now=datetime(2026, 11, 3, 20, 0, tzinfo=timezone.utc),
        )
        assert trend["rachaActualDias"] == 3
        assert trend["totalCommitsPeriodo"] == 6
        assert trend["lenguajePrincipalReciente"] == "TypeScript"

    test_engine.dispose()


def test_fastapi_endpoints_and_load_under_3_seconds(tmp_path, monkeypatch):
    """RNF1 y RNF5: El servidor FastAPI sirve el portafolio público sin login en menos de 3 segundos."""
    import json
    import backend.config as app_config

    temp_cfg_file = tmp_path / "config_api_test.json"
    temp_cfg_file.write_text(
        json.dumps(
            {
                "usuario": {"id_usuario": 1, "nombre": "Daniel Tornero", "github_username": "AssuredPigeon", "correo": "test@uabc.edu.mx"},
                "sincronizacion": {"extra_repos": ["labtechmovilfcitec-hash/DanceLabo"], "excluded_topics": [], "excluded_repos": [], "exclude_forks": True},
                "opciones": {"generar_descripciones_ia": True, "mostrar_grafica_actividad": True, "metodo_actualizacion": "github-actions"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(app_config, "CONFIG_PATH", temp_cfg_file)

    db_file = tmp_path / "api_test.db"
    test_engine = build_engine(f"sqlite:///{db_file.as_posix()}")
    init_db(test_engine)
    TestSession = sessionmaker(bind=test_engine, expire_on_commit=False)

    with TestSession() as s:
        u = Usuario(nombre="Daniel Tornero", github_username="AssuredPigeon", correo="test@uabc.edu.mx")
        s.add(u)
        s.flush()
        s.add(
            Repositorio(
                id_repositorio=999,
                id_usuario=u.id_usuario,
                nombre="DanceLabo",
                nombre_completo="labtechmovilfcitec-hash/DanceLabo",
                descripcion_original="",
                descripcion_generada="Sistema de evaluación en tiempo real con MediaPipe y Unity.",
                origen_descripcion="pytorch-bilstm",
                puntaje_ia=0.92,
                lenguajes=["C#", "Python"],
                topics=[],
                visible=True,
                url="https://github.com/labtechmovilfcitec-hash/DanceLabo",
                estrellas=1,
                fecha_ultimo_commit=datetime(2026, 11, 2, 11, 43, tzinfo=timezone.utc),
                es_fork=False,
                readme_consultado=True,
            )
        )
        s.commit()

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            t0 = time.perf_counter()
            r_html = client.get("/")
            r_api = client.get("/api/portfolio")
            r_detail = client.get("/api/projects/999")
            elapsed = time.perf_counter() - t0

            assert r_html.status_code == 200
            assert "Portafolio Dinámico Auto-actualizable" in r_html.text
            assert r_api.status_code == 200
            assert r_detail.status_code == 200
            assert elapsed < 3.0

            payload = r_api.json()
            assert payload["repositorios"][0]["nombre"] == "DanceLabo"
            assert payload["repositorios"][0]["origen_descripcion"] == "pytorch-bilstm"
    finally:
        app.dependency_overrides.clear()
        test_engine.dispose()


def test_config_panel_endpoints_and_visibility_recalculation(tmp_path, monkeypatch):
    """
    Actividad H (Pantalla 4) y RF3: Verifica GET /api/config y PUT /api/config, el recálculo
    inmediato de visibilidad en SQL por topics excluidos y el rechazo (422) de formatos inválidos.
    """
    import json
    import backend.config as app_config

    temp_cfg_file = tmp_path / "config_isolated.json"
    temp_bkp_file = tmp_path / "backup_isolated.json"
    initial_cfg = {
        "usuario": {
            "id_usuario": 1,
            "nombre": "Daniel Tornero Solano",
            "github_username": "AssuredPigeon",
            "correo": "danieltornero4@gmail.com",
        },
        "sincronizacion": {
            "extra_repos": ["labtechmovilfcitec-hash/DanceLabo"],
            "excluded_topics": [],
            "excluded_repos": [],
            "exclude_forks": True,
            "aliases_nombre": {},
        },
        "opciones": {
            "generar_descripciones_ia": True,
            "mostrar_grafica_actividad": True,
            "metodo_actualizacion": "github-actions",
        },
    }
    temp_cfg_file.write_text(json.dumps(initial_cfg, indent=2), encoding="utf-8")

    monkeypatch.setattr(app_config, "CONFIG_PATH", temp_cfg_file)
    monkeypatch.setattr(app_config, "BACKUP_PATH", temp_bkp_file)
    monkeypatch.delenv("PORTFOLIO_ADMIN_KEY", raising=False)

    db_file = tmp_path / "config_panel.db"
    test_engine = build_engine(f"sqlite:///{db_file.as_posix()}")
    init_db(test_engine)
    TestSession = sessionmaker(bind=test_engine, expire_on_commit=False)

    with TestSession() as s:
        u = Usuario(nombre="Daniel Tornero Solano", github_username="AssuredPigeon", correo="danieltornero4@gmail.com")
        s.add(u)
        s.flush()
        s.add_all(
            [
                Repositorio(
                    id_repositorio=10,
                    id_usuario=u.id_usuario,
                    nombre="proyecto-real",
                    nombre_completo="AssuredPigeon/proyecto-real",
                    descripcion_original="App principal",
                    descripcion_generada="Sistema backend principal.",
                    origen_descripcion="pytorch-bilstm",
                    puntaje_ia=0.88,
                    lenguajes=["Python"],
                    topics=["portafolio"],
                    visible=True,
                    url="https://github.com/AssuredPigeon/proyecto-real",
                    estrellas=2,
                    fecha_ultimo_commit=datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc),
                    es_fork=False,
                    readme_consultado=True,
                ),
                Repositorio(
                    id_repositorio=11,
                    id_usuario=u.id_usuario,
                    nombre="curso-basico",
                    nombre_completo="AssuredPigeon/curso-basico",
                    descripcion_original="Ejercicio guiado",
                    descripcion_generada=None,
                    origen_descripcion="original",
                    puntaje_ia=0.0,
                    lenguajes=["JavaScript"],
                    topics=["tutorial"],
                    visible=True,
                    url="https://github.com/AssuredPigeon/curso-basico",
                    estrellas=0,
                    fecha_ultimo_commit=datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc),
                    es_fork=False,
                    readme_consultado=True,
                ),
            ]
        )
        s.commit()

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            r_get = client.get("/api/config")
            assert r_get.status_code == 200
            assert r_get.json()["opciones"]["metodo_actualizacion"] == "github-actions"

            # Excluir el topic "tutorial" y cambiar opciones
            r_put = client.put(
                "/api/config",
                json={
                    "excluded_topics": ["tutorial", "Practica"],
                    "extra_repos": ["labtechmovilfcitec-hash/DanceLabo"],
                    "excluded_repos": [],
                    "exclude_forks": True,
                    "generar_descripciones_ia": True,
                    "mostrar_grafica_actividad": False,
                    "metodo_actualizacion": "client-side",
                },
            )
            assert r_put.status_code == 200
            body = r_put.json()
            assert body["metadata"]["total_repositorios"] == 2
            assert body["metadata"]["total_visibles"] == 1
            assert body["config"]["opciones"]["mostrar_grafica_actividad"] is False
            assert body["config"]["sincronizacion"]["excluded_topics"] == ["tutorial", "practica"]
            assert temp_bkp_file.exists()

            # Validar rechazo 422 si se envía un repositorio sin formato dueño/repo
            r_bad = client.put(
                "/api/config",
                json={
                    "excluded_topics": [],
                    "extra_repos": ["formato_invalido_sin_slash"],
                    "excluded_repos": [],
                    "exclude_forks": True,
                    "generar_descripciones_ia": True,
                    "mostrar_grafica_actividad": True,
                    "metodo_actualizacion": "github-actions",
                },
            )
            assert r_bad.status_code == 422
    finally:
        app.dependency_overrides.clear()
        test_engine.dispose()


def test_admin_key_protection_when_configured(tmp_path, monkeypatch):
    """Verifica que si PORTFOLIO_ADMIN_KEY está definido, PUT /api/config exija X-Admin-Key."""
    import json
    import backend.config as app_config

    temp_cfg_file = tmp_path / "cfg_auth.json"
    temp_bkp_file = tmp_path / "bkp_auth.json"
    temp_cfg_file.write_text(
        json.dumps(
            {
                "usuario": {"id_usuario": 1, "nombre": "Daniel", "github_username": "AssuredPigeon", "correo": "a@b.com"},
                "sincronizacion": {"extra_repos": [], "excluded_topics": [], "excluded_repos": [], "exclude_forks": True},
                "opciones": {"generar_descripciones_ia": True, "mostrar_grafica_actividad": True, "metodo_actualizacion": "github-actions"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(app_config, "CONFIG_PATH", temp_cfg_file)
    monkeypatch.setattr(app_config, "BACKUP_PATH", temp_bkp_file)
    monkeypatch.setenv("PORTFOLIO_ADMIN_KEY", "clave-prueba-segura")

    db_file = tmp_path / "auth_test.db"
    test_engine = build_engine(f"sqlite:///{db_file.as_posix()}")
    init_db(test_engine)
    TestSession = sessionmaker(bind=test_engine, expire_on_commit=False)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            payload = {
                "excluded_topics": ["oculto"],
                "extra_repos": [],
                "excluded_repos": [],
                "exclude_forks": True,
                "generar_descripciones_ia": True,
                "mostrar_grafica_actividad": True,
                "metodo_actualizacion": "github-actions",
            }
            assert client.put("/api/config", json=payload).status_code == 403
            assert (
                client.put("/api/config", json=payload, headers={"X-Admin-Key": "clave-prueba-segura"}).status_code
                == 200
            )
    finally:
        app.dependency_overrides.clear()
        test_engine.dispose()


def test_rate_limit_resilience_preserves_existing_sql_and_backup(tmp_path):
    """
    RNF3, RNF4 y Regla 7: Si la API de GitHub agota su rate limit (HTTP 403 con remaining=0),
    el sistema conserva los proyectos previamente sincronizados en SQL y genera respaldo sin caer.
    """
    db_file = tmp_path / "ratelimit.db"
    test_engine = build_engine(f"sqlite:///{db_file.as_posix()}")
    init_db(test_engine)
    TestSession = sessionmaker(bind=test_engine, expire_on_commit=False)

    with TestSession() as s:
        u = Usuario(nombre="Daniel Tornero", github_username="AssuredPigeon", correo="danieltornero4@gmail.com")
        s.add(u)
        s.flush()
        s.add(
            Repositorio(
                id_repositorio=777,
                id_usuario=u.id_usuario,
                nombre="musicbot",
                nombre_completo="AssuredPigeon/musicbot",
                descripcion_original="Bot musical",
                descripcion_generada="Bot de música en Python para servidores de Discord.",
                origen_descripcion="pytorch-bilstm",
                puntaje_ia=0.81,
                lenguajes=["Python"],
                topics=[],
                visible=True,
                url="https://github.com/AssuredPigeon/musicbot",
                estrellas=1,
                fecha_ultimo_commit=datetime(2026, 8, 17, 4, 12, tzinfo=timezone.utc),
                es_fork=False,
                readme_consultado=True,
            )
        )
        s.commit()

    def rate_limited_handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            headers={
                "x-ratelimit-remaining": "0",
                "x-ratelimit-limit": "60",
                "x-ratelimit-reset": "1793750000",
            },
            json={"message": "API rate limit exceeded"},
        )

    cfg = {
        "usuario": {"id_usuario": 1, "nombre": "Daniel Tornero", "github_username": "AssuredPigeon", "correo": "danieltornero4@gmail.com"},
        "sincronizacion": {"extra_repos": [], "excluded_topics": [], "excluded_repos": [], "exclude_forks": True},
        "opciones": {"generar_descripciones_ia": True, "mostrar_grafica_actividad": True, "metodo_actualizacion": "github-actions"},
    }
    bkp_file = tmp_path / "bkp_ratelimit.json"

    transport = httpx.MockTransport(rate_limited_handler)
    with httpx.Client(transport=transport) as raw_http, TestSession() as session:
        gh_client = GitHubClient(http_client=raw_http)
        snapshot = sync_portfolio_to_db(session, config=cfg, gh_client=gh_client, backup_path=bkp_file)
        assert snapshot["metadata"]["total_repositorios"] == 1
        assert "aviso_rate_limit" in snapshot["metadata"]
        assert snapshot["repositorios"][0]["nombre"] == "musicbot"
        assert bkp_file.exists()

    test_engine.dispose()


def test_tokenizer_handles_utf8_bom_markdown_tables_and_expo_boilerplate():
    """
    Casos reales detectados durante validación con repositorios de AssuredPigeon:
    1) BOM UTF-8 (\\ufeff) al inicio del README + tablas Markdown con tuberías (|).
    2) Plantilla por defecto de Expo (create-expo-app) descartada para no inventar descripción.
    """
    bom_and_table_md = (
        "\ufeff# SDGKU Subject System\n\n"
        "| Comando | Función |\n"
        "| --- | --- |\n"
        "| !play | Reproduce audio |\n\n"
        "Aplicación web académica para administrar materias, horarios y asignaciones estudiantiles.\n"
    )
    cleaned = clean_readme_to_sentences(bom_and_table_md)
    assert len(cleaned) == 1
    assert "Aplicación web académica" in cleaned[0]
    assert "| Comando |" not in cleaned[0]

    expo_default_md = (
        "# Welcome to your Expo app\n\n"
        "This is an Expo project created with `create-expo-app`.\n"
        "In the output, you'll find options to open the app in a development build.\n"
    )
    assert clean_readme_to_sentences(expo_default_md) == []


def test_deep_repo_inspector_extracts_code_entities_when_readme_missing_or_boilerplate():
    """
    Verifica que cuando un repositorio carece de README descriptivo (o contiene la plantilla
    por defecto de NestJS), el inspector profundo analiza el árbol Git, package.json,
    schema.prisma y controladores para construir el resumen y puntos clave bilingües (ES/EN).
    """
    import json

    nestjs_starter_md = (
        "## Description\n\n"
        "[Nest](https://github.com/nestjs/nest) framework TypeScript starter repository.\n"
        "A progressive [Node.js](http://nodejs.org) framework for building server-side applications.\n"
    )
    pkg_json = json.dumps(
        {
            "name": "academic-portal",
            "dependencies": {
                "@nestjs/core": "^10.0.0",
                "@prisma/client": "^5.0.0",
                "react": "^18.2.0",
            },
        }
    )
    prisma_schema = (
        "datasource db { provider = \"postgresql\" }\n"
        "model Student {\n  id Int @id\n}\n"
        "model Course {\n  id Int @id\n}\n"
    )
    main_ts = "app.get('/api/courses', handler);\n"

    def mock_inspector_handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if "/git/trees/" in p:
            return httpx.Response(
                200,
                json={
                    "tree": [
                        {"path": "Back-end/README.md", "type": "blob"},
                        {"path": "package.json", "type": "blob"},
                        {"path": "prisma/schema.prisma", "type": "blob"},
                        {"path": "src/controllers/CourseController.ts", "type": "blob"},
                        {"path": "src/services/EnrollmentService.ts", "type": "blob"},
                        {"path": "src/main.ts", "type": "blob"},
                    ]
                },
            )
        if p.endswith("/contributors"):
            return httpx.Response(200, json=[{"login": "dev1"}, {"login": "dev2"}, {"login": "dev3"}])
        if p.endswith("/contents/Back-end/README.md"):
            return httpx.Response(200, text=nestjs_starter_md)
        if p.endswith("/contents/package.json"):
            return httpx.Response(200, text=pkg_json)
        if p.endswith("/contents/prisma/schema.prisma"):
            return httpx.Response(200, text=prisma_schema)
        if p.endswith("/contents/src/main.ts"):
            return httpx.Response(200, text=main_ts)
        if p.endswith("/commits"):
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    analyzer = PyTorchReadmeAnalyzer()
    gh_repo = {
        "full_name": "org/academic-system",
        "default_branch": "main",
        "created_at": "2026-09-01T00:00:00Z",
        "description": "",
        "language": "TypeScript",
        "topics": [],
        "homepage": "",
    }
    lang_bytes = {"TypeScript": 14000, "HTML": 6000}

    with httpx.Client(transport=httpx.MockTransport(mock_inspector_handler)) as raw_http:
        gh_client = GitHubClient(http_client=raw_http)
        pred, clean_langs, detalle = inspect_and_enrich_repository(
            gh_client=gh_client,
            gh_repo=gh_repo,
            lang_bytes=lang_bytes,
            raw_readme=None,
            analyzer=analyzer,
            repo_display_name="Academic System",
            enable_translation=False,
        )

    assert pred.origen == "codigo-fuente"
    assert clean_langs == ["TypeScript", "HTML"]
    assert detalle["idioma_original"] == "codigo"
    assert detalle["colaboradores"] == 3
    assert "NestJS" in detalle["frameworks"]
    assert "Prisma" in detalle["frameworks"]
    assert "PostgreSQL" in detalle["frameworks"]
    assert "Student" in detalle["modelos_datos"]
    assert "Course" in detalle["modelos_datos"]
    assert "/api/courses" in detalle["rutas_detectadas"]
    assert "CourseController" in detalle["modulos_detectados"]
    assert len(detalle["resumen_es"]) > 30
    assert len(detalle["resumen_en"]) > 30
    assert len(detalle["puntos_clave_es"]) >= 3
    assert len(detalle["puntos_clave_en"]) >= 3


def test_detect_text_language_and_empty_repo_handling():
    """
    Verifica la detección de idioma original (ES vs EN) y el manejo honesto (Regla 6)
    de repositorios recién creados sin archivos publicados ('vacio').
    """
    assert (
        detect_text_language(
            "Sistema de evaluación de movimiento en tiempo real para usuarios mediante cámara."
        )
        == "es"
    )
    assert (
        detect_text_language(
            "Production-ready platform built with Python for interactive semantic analysis."
        )
        == "en"
    )

    def empty_repo_handler(request: httpx.Request) -> httpx.Response:
        if "/git/trees/" in request.url.path:
            return httpx.Response(200, json={"tree": []})
        if request.url.path.endswith("/contributors"):
            return httpx.Response(200, json=[{"login": "AssuredPigeon"}])
        return httpx.Response(404)

    gh_repo = {
        "full_name": "AssuredPigeon/MLAD",
        "default_branch": "main",
        "created_at": "2026-10-01T00:00:00Z",
        "description": "",
        "language": None,
        "topics": [],
    }
    with httpx.Client(transport=httpx.MockTransport(empty_repo_handler)) as raw_http:
        gh_client = GitHubClient(http_client=raw_http)
        pred, clean_langs, detalle = inspect_and_enrich_repository(
            gh_client=gh_client,
            gh_repo=gh_repo,
            lang_bytes={},
            raw_readme=None,
            analyzer=PyTorchReadmeAnalyzer(),
            repo_display_name="MLAD",
            enable_translation=False,
        )

    assert clean_langs == []
    assert detalle["idioma_original"] == "vacio"
    assert detalle["frameworks"] == []
    assert detalle["puntos_clave_es"] == []
    assert pred.es_proyecto_portafolio is False


def test_switch_github_user_in_config_and_restore_previous_profile(tmp_path, monkeypatch):
    """
    Verifica el cambio dinámico de cuenta de GitHub desde PUT /api/config:
    1) Devuelve HTTP 404 si el usuario de GitHub no existe.
    2) Al cambiar a otra cuenta pública ('CompaneroUABC'), sincroniza sus repositorios sin mezclarlos
       con los de 'AssuredPigeon' y detecta su nombre público desde GitHub.
    3) Al volver a 'AssuredPigeon', restaura su nombre, correo, extra_repos y caché SQL al instante.
    """
    import json
    import backend.config as app_config

    temp_cfg_file = tmp_path / "cfg_multiuser.json"
    temp_bkp_file = tmp_path / "bkp_multiuser.json"
    initial_cfg = {
        "usuario": {
            "id_usuario": 1,
            "nombre": "Daniel Tornero Solano",
            "github_username": "AssuredPigeon",
            "correo": "danieltornero4@gmail.com",
        },
        "sincronizacion": {
            "extra_repos": ["labtechmovilfcitec-hash/DanceLabo"],
            "excluded_topics": ["practica"],
            "excluded_repos": ["AssuredPigeon/AssuredPigeon"],
            "exclude_forks": True,
            "aliases_nombre": {"labtechmovilfcitec-hash/DanceLabo": "DanceLabo"},
        },
        "opciones": {
            "generar_descripciones_ia": True,
            "mostrar_grafica_actividad": False,
            "metodo_actualizacion": "github-actions",
        },
    }
    temp_cfg_file.write_text(json.dumps(initial_cfg, indent=2), encoding="utf-8")
    monkeypatch.setattr(app_config, "CONFIG_PATH", temp_cfg_file)
    monkeypatch.setattr(app_config, "BACKUP_PATH", temp_bkp_file)
    monkeypatch.delenv("PORTFOLIO_ADMIN_KEY", raising=False)

    db_file = tmp_path / "multiuser.db"
    test_engine = build_engine(f"sqlite:///{db_file.as_posix()}")
    init_db(test_engine)
    TestSession = sessionmaker(bind=test_engine, expire_on_commit=False)

    with TestSession() as s:
        u1 = Usuario(nombre="Daniel Tornero Solano", github_username="AssuredPigeon", correo="danieltornero4@gmail.com")
        s.add(u1)
        s.flush()
        s.add_all(
            [
                Repositorio(
                    id_repositorio=501,
                    id_usuario=u1.id_usuario,
                    nombre="musicbot",
                    nombre_completo="AssuredPigeon/musicbot",
                    descripcion_original="Bot de música",
                    descripcion_generada="Bot musical en Python.",
                    origen_descripcion="pytorch-bilstm",
                    puntaje_ia=0.85,
                    lenguajes=["Python"],
                    topics=[],
                    detalle_tecnico={"idioma_original": "es", "resumen_es": "Bot musical en Python."},
                    visible=True,
                    url="https://github.com/AssuredPigeon/musicbot",
                    estrellas=1,
                    fecha_ultimo_commit=datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc),
                    es_fork=False,
                    readme_consultado=True,
                ),
                Repositorio(
                    id_repositorio=502,
                    id_usuario=u1.id_usuario,
                    nombre="DanceLabo",
                    nombre_completo="labtechmovilfcitec-hash/DanceLabo",
                    descripcion_original="",
                    descripcion_generada="Evaluación con MediaPipe y Unity.",
                    origen_descripcion="pytorch-bilstm",
                    puntaje_ia=0.91,
                    lenguajes=["C#", "Python"],
                    topics=[],
                    detalle_tecnico={"idioma_original": "es", "resumen_es": "Evaluación con MediaPipe y Unity."},
                    visible=True,
                    url="https://github.com/labtechmovilfcitec-hash/DanceLabo",
                    estrellas=2,
                    fecha_ultimo_commit=datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc),
                    es_fork=False,
                    readme_consultado=True,
                ),
            ]
        )
        s.commit()

    def mock_gh_switch(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if p == "/users/usuario-inexistente-404":
            return httpx.Response(404, json={"message": "Not Found"})
        if p == "/users/companerouabc":
            return httpx.Response(
                200,
                json={"login": "CompaneroUABC", "name": "Carlos Méndez", "email": None},
            )
        if p == "/users/CompaneroUABC/repos":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 901,
                        "name": "sistema-inventario",
                        "full_name": "CompaneroUABC/sistema-inventario",
                        "description": "Sistema web de inventario con FastAPI y PostgreSQL.",
                        "language": "Python",
                        "topics": [],
                        "html_url": "https://github.com/CompaneroUABC/sistema-inventario",
                        "stargazers_count": 4,
                        "pushed_at": "2026-11-04T12:00:00Z",
                        "fork": False,
                        "default_branch": "main",
                        "created_at": "2026-10-01T00:00:00Z",
                    }
                ],
            )
        if "/repos/CompaneroUABC/sistema-inventario/languages" in p:
            return httpx.Response(200, json={"Python": 12000})
        if "/repos/CompaneroUABC/sistema-inventario/git/trees/" in p:
            return httpx.Response(200, json={"tree": [{"path": "app/main.py", "type": "blob"}]})
        if p.endswith("/contributors"):
            return httpx.Response(200, json=[{"login": "CompaneroUABC"}])
        return httpx.Response(404)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    raw_mock_http = httpx.Client(transport=httpx.MockTransport(mock_gh_switch))
    mock_gh_client = GitHubClient(http_client=raw_mock_http)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_gh_client] = lambda: mock_gh_client
    try:
        with TestClient(app) as client:
            # 1) Intentar cambiar a un usuario inexistente debe responder 404 sin alterar AssuredPigeon
            r_404 = client.put(
                "/api/config",
                json={
                    "github_username": "usuario-inexistente-404",
                    "excluded_topics": ["practica"],
                    "extra_repos": [],
                    "excluded_repos": [],
                    "exclude_forks": True,
                    "generar_descripciones_ia": True,
                    "mostrar_grafica_actividad": False,
                    "metodo_actualizacion": "github-actions",
                },
            )
            assert r_404.status_code == 404

            # 2) Cambiar a CompaneroUABC
            r_switch = client.put(
                "/api/config",
                json={
                    "github_username": "@companerouabc",
                    "nombre": "",
                    "correo": "",
                    "excluded_topics": ["practica"],
                    "extra_repos": [],
                    "excluded_repos": [],
                    "exclude_forks": True,
                    "generar_descripciones_ia": True,
                    "mostrar_grafica_actividad": False,
                    "metodo_actualizacion": "github-actions",
                },
            )
            assert r_switch.status_code == 200
            data_switch = r_switch.json()
            assert data_switch["usuario"]["github_username"] == "CompaneroUABC"
            assert data_switch["usuario"]["nombre"] == "Carlos Méndez"
            assert data_switch["usuario"]["correo"] == ""
            assert len(data_switch["repositorios"]) == 1
            assert data_switch["repositorios"][0]["nombre_completo"] == "CompaneroUABC/sistema-inventario"

            # 3) Regresar a AssuredPigeon: debe restaurar sus 2 repos (incluyendo DanceLabo) desde caché SQL
            r_back = client.put(
                "/api/config",
                json={
                    "github_username": "AssuredPigeon",
                    "nombre": "",
                    "correo": "",
                    "excluded_topics": ["practica"],
                    "extra_repos": [],
                    "excluded_repos": [],
                    "exclude_forks": True,
                    "generar_descripciones_ia": True,
                    "mostrar_grafica_actividad": False,
                    "metodo_actualizacion": "github-actions",
                },
            )
            assert r_back.status_code == 200
            data_back = r_back.json()
            assert data_back["origen"] == "perfil-sql-cache"
            assert data_back["usuario"]["nombre"] == "Daniel Tornero Solano"
            assert data_back["usuario"]["correo"] == "danieltornero4@gmail.com"
            assert len(data_back["repositorios"]) == 2
            nombres = {r["nombre_completo"] for r in data_back["repositorios"]}
            assert "AssuredPigeon/musicbot" in nombres
            assert "labtechmovilfcitec-hash/DanceLabo" in nombres
    finally:
        app.dependency_overrides.clear()
        raw_mock_http.close()
        test_engine.dispose()


def test_font_asset_readmes_and_localhost_noise_are_ignored_in_favor_of_real_code():
    """
    Evita que archivos README de carpetas de fuentes/recursos (ej. public/fonts/README.md con
    BlockchainFont.woff2) o líneas de configuración local (localhost:5173, ENVIRONMENT: production,
    subtítulos en negrita terminados en dos puntos) contaminen las descripciones del portafolio.
    """
    analyzer = PyTorchReadmeAnalyzer()

    # Caso 1: README con párrafo ejecutivo real + ruido de localhost y subtítulos con dos puntos
    toros_readme = (
        "# Dashboard Comercial\n\n"
        "Plataforma integral de analítica comercial, control de boletaje y asistencia inteligente en tiempo real.\n\n"
        "La aplicación web abrirá en http://localhost:5173. ENVIRONMENT: production.\n"
        "La documentación interactiva estará disponible en http://localhost:8000/docs.\n"
        "**Pantalla negra en Android:**\n"
        "idxventaszonacovering, idxventascanalcovering y idxventastimelinecovering.\n"
    )
    pred_toros = analyzer.analyze_readme(
        toros_readme,
        {"nombre": "Dashboard_Toros", "lenguajes": ["Python", "JavaScript"], "topics": []},
    )
    assert pred_toros.descripcion is not None
    assert "Plataforma integral de analítica comercial" in pred_toros.descripcion
    assert "localhost" not in pred_toros.descripcion.lower()
    assert "environment" not in pred_toros.descripcion.lower()
    assert "pantalla negra" not in pred_toros.descripcion.lower()

    # Caso 2: Proyecto .NET MAUI sin README raíz pero con public/fonts/README.md (fuentes .woff2)
    def mock_maui_handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if p.endswith("/git/trees/main"):
            return httpx.Response(
                200,
                json={
                    "tree": [
                        {"path": "MauiComplete.csproj", "type": "blob"},
                        {"path": "MauiProgram.cs", "type": "blob"},
                        {"path": "Models/Alumno.cs", "type": "blob"},
                        {"path": "Models/AlumnoTests.cs", "type": "blob"},
                        {"path": "Views/LoginPage.xaml.cs", "type": "blob"},
                        {"path": "public/fonts/README.md", "type": "blob"},
                    ]
                },
            )
        if p.endswith("/contributors"):
            return httpx.Response(200, json=[{"login": "George170205"}])
        if "public/fonts/README.md" in p:
            return httpx.Response(
                200,
                text="BlockchainFont-Regular.woff2 and BlockchainFont-Regular.woff. Bold weight font for headings.",
            )
        if "MauiComplete.csproj" in p:
            return httpx.Response(
                200,
                text="<Project><PropertyGroup><UseMaui>true</UseMaui><ApplicationTitle>Control Escolar MAUI</ApplicationTitle></PropertyGroup></Project>",
            )
        if p.endswith("/commits"):
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    gh_repo = {
        "id": 999,
        "name": "Maui-Complete",
        "full_name": "George170205/Maui-Complete",
        "description": "",
        "language": "C#",
        "topics": [],
        "default_branch": "main",
        "created_at": "2026-10-15T00:00:00Z",
    }
    with httpx.Client(transport=httpx.MockTransport(mock_maui_handler)) as raw_http:
        gh_client = GitHubClient(http_client=raw_http)
        pred, clean_langs, det = inspect_and_enrich_repository(
            gh_client=gh_client,
            gh_repo=gh_repo,
            lang_bytes={"C#": 25000, "HTML": 1200},
            raw_readme="\ufeff# Maui-Complete\r\n",
            analyzer=analyzer,
            repo_display_name="Maui-Complete",
            enable_translation=False,
        )

    assert "BlockchainFont" not in (pred.descripcion or "")
    assert "woff" not in (pred.descripcion or "")
    assert ".NET MAUI" in det["frameworks"]
    assert "Alumno" in det["modelos_datos"]
    assert "AlumnoTests" not in det["modelos_datos"]
    assert "LoginPage" in det["modulos_detectados"]
    assert det["idioma_original"] == "codigo"


def test_readonly_url_preview_mode_and_admin_key_flag(tmp_path, monkeypatch):
    """
    CP-15: Verifica el modo de vista previa de solo lectura (?user=OtroUsuario) en GET /api/portfolio
    sin alterar config.json ni backup_portfolio.json, así como la bandera admin_key_requerida en GET /api/config.
    """
    import json
    import backend.config as app_config

    temp_cfg_file = tmp_path / "cfg_preview.json"
    temp_bkp_file = tmp_path / "bkp_preview.json"
    initial_cfg = {
        "usuario": {
            "id_usuario": 1,
            "nombre": "Daniel Tornero Solano",
            "github_username": "AssuredPigeon",
            "correo": "danieltornero4@gmail.com",
        },
        "sincronizacion": {
            "extra_repos": [],
            "excluded_topics": ["practica"],
            "excluded_repos": [],
            "exclude_forks": True,
        },
        "opciones": {
            "generar_descripciones_ia": True,
            "mostrar_grafica_actividad": False,
            "metodo_actualizacion": "github-actions",
        },
    }
    temp_cfg_file.write_text(json.dumps(initial_cfg, indent=2), encoding="utf-8")
    monkeypatch.setattr(app_config, "CONFIG_PATH", temp_cfg_file)
    monkeypatch.setattr(app_config, "BACKUP_PATH", temp_bkp_file)
    monkeypatch.delenv("PORTFOLIO_ADMIN_KEY", raising=False)

    db_file = tmp_path / "preview_mode.db"
    test_engine = build_engine(f"sqlite:///{db_file.as_posix()}")
    init_db(test_engine)
    TestSession = sessionmaker(bind=test_engine, expire_on_commit=False)

    with TestSession() as s:
        u1 = Usuario(nombre="Daniel Tornero Solano", github_username="AssuredPigeon", correo="danieltornero4@gmail.com")
        s.add(u1)
        s.flush()
        s.add(
            Repositorio(
                id_repositorio=701,
                id_usuario=u1.id_usuario,
                nombre="musicbot",
                nombre_completo="AssuredPigeon/musicbot",
                descripcion_original="Bot de música",
                descripcion_generada="Bot musical en Python.",
                origen_descripcion="pytorch-bilstm",
                puntaje_ia=0.86,
                lenguajes=["Python"],
                topics=[],
                visible=True,
                url="https://github.com/AssuredPigeon/musicbot",
                estrellas=1,
                fecha_ultimo_commit=datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc),
                es_fork=False,
                readme_consultado=True,
            )
        )
        s.commit()

    def mock_preview_gh(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if p == "/users/usuario-no-existe":
            return httpx.Response(404, json={"message": "Not Found"})
        if p == "/users/visitantepublico":
            return httpx.Response(200, json={"login": "VisitantePublico", "name": "Ana López", "email": None})
        if p == "/users/VisitantePublico/repos":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 950,
                        "name": "app-movil-uabc",
                        "full_name": "VisitantePublico/app-movil-uabc",
                        "description": "Aplicación móvil académica construida con React Native.",
                        "language": "TypeScript",
                        "topics": [],
                        "html_url": "https://github.com/VisitantePublico/app-movil-uabc",
                        "stargazers_count": 3,
                        "pushed_at": "2026-11-05T12:00:00Z",
                        "fork": False,
                        "default_branch": "main",
                        "created_at": "2026-10-10T00:00:00Z",
                    }
                ],
            )
        if p.endswith("/languages"):
            return httpx.Response(200, json={"TypeScript": 15000})
        if "/git/trees/" in p:
            return httpx.Response(200, json={"tree": [{"path": "src/App.tsx", "type": "blob"}]})
        if p.endswith("/contributors"):
            return httpx.Response(200, json=[{"login": "VisitantePublico"}])
        return httpx.Response(404)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    raw_http = httpx.Client(transport=httpx.MockTransport(mock_preview_gh))
    mock_gh_client = GitHubClient(http_client=raw_http)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_gh_client] = lambda: mock_gh_client
    try:
        with TestClient(app) as client:
            assert client.get("/api/config").json()["admin_key_requerida"] is False
            monkeypatch.setenv("PORTFOLIO_ADMIN_KEY", "secreta-123")
            assert client.get("/api/config").json()["admin_key_requerida"] is True

            # Vista previa válida por URL (?user=visitantepublico)
            r_prev = client.get("/api/portfolio?user=visitantepublico")
            assert r_prev.status_code == 200
            prev_json = r_prev.json()
            assert prev_json["modo_vista_previa"] is True
            assert prev_json["origen"] == "vista-previa-github"
            assert prev_json["usuario"]["github_username"] == "VisitantePublico"
            assert prev_json["usuario"]["nombre"] == "Ana López"
            assert len(prev_json["repositorios"]) == 1
            assert prev_json["repositorios"][0]["nombre"] == "app-movil-uabc"
            assert not temp_bkp_file.exists()

            # Segunda llamada usa caché SQL de vista previa
            r_prev_cached = client.get("/api/portfolio?user=VisitantePublico")
            assert r_prev_cached.status_code == 200
            assert r_prev_cached.json()["origen"] == "vista-previa-sql-cache"

            # El portafolio principal (AssuredPigeon) permanece intacto en config.json y en /api/portfolio
            saved_disk_cfg = json.loads(temp_cfg_file.read_text(encoding="utf-8"))
            assert saved_disk_cfg["usuario"]["github_username"] == "AssuredPigeon"
            r_main = client.get("/api/portfolio")
            assert r_main.status_code == 200
            assert r_main.json()["modo_vista_previa"] is False
            assert r_main.json()["usuario"]["github_username"] == "AssuredPigeon"

            # Errores esperados ante usuario inexistente o formato inválido
            assert client.get("/api/portfolio?user=usuario-no-existe").status_code == 404
            assert client.get("/api/portfolio?user=invalido/con/slash").status_code == 422
    finally:
        app.dependency_overrides.clear()
        raw_http.close()
        test_engine.dispose()


def test_weekly_repo_breakdown_and_pytorch_f1_metrics():
    """
    CP-16: Verifica que compute_activity_trend calcule el desglose semanal de commits por repositorio
    (para el tooltip de Chart.js en Pantalla 3) y que los artefactos PyTorch incluyan F1-score sobre corpus >= 80.
    """
    import json
    from backend.ml.train import METRICS_PATH

    repos = [
        {"id_repositorio": 1, "nombre": "DanceLabo", "visible": True, "lenguajes": ["C#", "Python"]},
        {"id_repositorio": 2, "nombre": "musicbot", "visible": True, "lenguajes": ["Python"]},
    ]
    commits = [
        {"id_repositorio": 1, "fecha": "2026-11-02", "cantidad_commits": 3, "lenguaje_principal": "C#"},
        {"id_repositorio": 1, "fecha": "2026-11-04", "cantidad_commits": 2, "lenguaje_principal": "C#"},
        {"id_repositorio": 2, "fecha": "2026-11-03", "cantidad_commits": 2, "lenguaje_principal": "Python"},
    ]
    trend = compute_activity_trend(
        commits,
        repos,
        reference_now=datetime(2026, 11, 5, 18, 0, tzinfo=timezone.utc),
    )
    last_week = trend["semanas"][-1]
    assert last_week["commits"] == 7
    assert last_week["desglose"] == [
        {"nombre": "DanceLabo", "commits": 5},
        {"nombre": "musicbot", "commits": 2},
    ]

    metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    assert metrics["dataset_size"] >= 80
    best = metrics["best_checkpoint_metrics"]
    assert "val_salience_precision" in best
    assert "val_salience_recall" in best
    assert best["val_salience_f1"] >= 0.85






