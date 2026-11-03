from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx

from backend.github_service import GitHubClient, GitHubRateLimitError
from backend.ml.predictor import PyTorchPrediction, PyTorchReadmeAnalyzer

IGNORED_PATH_PREFIXES = (
    "node_modules/",
    "vendor/",
    "__pycache__/",
    ".git/",
    ".github/",
    ".idea/",
    ".vscode/",
    "dist/",
    "build/",
    ".next/",
    ".expo/",
    "coverage/",
    "Library/",
    "Temp/",
    "Logs/",
    "obj/",
    "bin/",
    "bootstrap/cache/",
    "storage/",
)

NOISY_LANGUAGES = {"Rich Text Format", "TeX"}

SPANISH_STOPWORDS = {
    "el", "la", "los", "las", "de", "del", "en", "para", "con", "por", "una",
    "uno", "como", "sistema", "aplicación", "aplicacion", "mediante", "tiempo",
    "datos", "usuario", "usuarios", "permite", "evaluación", "evaluacion",
    "gestión", "gestion", "desarrollo", "usando", "desde", "hacia", "sobre",
}

ENGLISH_STOPWORDS = {
    "the", "and", "for", "with", "that", "from", "into", "using", "built",
    "system", "application", "platform", "real-time", "users", "user", "data",
    "allows", "provides", "designed", "through", "across", "production-ready",
    "interactive", "analysis", "pipeline", "backend", "frontend",
}

# Catálogo ordenado de detección de frameworks, motores y librerías técnicas
TECH_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("FastAPI", ("fastapi",)),
    ("Flask", ("flask",)),
    ("Django", ("django",)),
    ("ASP.NET Core", ("microsoft.aspnetcore", "webapplication.createbuilder", "microsoft.net.sdk.web")),
    (".NET MAUI", ("<usemaui>true", "mauiprogram.cs", "microsoft.maui")),
    ("NestJS", ("@nestjs/core", "nest-cli.json")),
    ("Express", ("dep:express",)),
    ("Laravel", ("laravel/framework", "artisan")),
    ("Streamlit", ("streamlit", ".streamlit/")),
    ("React Native", ("react-native",)),
    ("Expo", ("dep:expo", "expo-router")),
    ("React", ("dep:react", "react-dom")),
    ("Next.js", ("dep:next", "next.config")),
    ("Vue", ("dep:vue",)),
    ("Alpine.js", ("alpinejs", "alpine.js")),
    ("Tailwind CSS", ("tailwindcss",)),
    ("Bootstrap", ("dep:bootstrap", "bootstrap.min.css")),
    ("Three.js", ("dep:three", "three.min.js", "three.module.js", "import * as three")),
    ("WebXR / AR", ("aframe", "ar.js", "mindar", "vuforia", "xrinteraction", "arfoundation")),
    ("PyQt6", ("pyqt6", "pyqt5")),
    ("Pygame", ("pygame",)),
    ("Unity", ("projectversion.txt", "unityengine", "unity_project_detected")),
    ("PyTorch", ("dep:torch", "import torch", "from torch", "pytorch")),
    ("TensorFlow", ("tensorflow", "keras")),
    ("scikit-learn", ("scikit-learn", "sklearn")),
    ("XGBoost", ("xgboost",)),
    ("MediaPipe", ("mediapipe",)),
    ("YOLOv8", ("ultralytics", "yolov8")),
    ("OpenCV", ("opencv-python", "import cv2", "opencv")),
    ("sentence-transformers", ("sentence-transformers", "sentence_transformers")),
    ("OpenAI Whisper", ("openai-whisper", "import whisper", "faster-whisper")),
    ("Gemini API", ("google-generativeai", "google-genai", "gemini api")),
    ("Discord.py", ("discord.py", "py-cord", "nextcord")),
    ("yt-dlp", ("yt-dlp",)),
    ("Plotly", ("plotly",)),
    ("Matplotlib", ("matplotlib",)),
    ("ReportLab", ("reportlab",)),
    ("Pandas", ("pandas",)),
    ("PostgreSQL", ("psycopg", "dep:pg", "postgresql")),
    ("PostGIS", ("postgis", "st_dwithin", "st_simplify")),
    ("pgvector", ("pgvector",)),
    ("MySQL", ("mysql2", "pymysql", "provider:mysql")),
    ("SQLite", ("aiosqlite", "sqlite3", "provider:sqlite", "sqlite-net-pcl", "microsoft.entityframeworkcore.sqlite")),
    ("Supabase", ("@supabase/", "supabase")),
    ("Entity Framework", ("microsoft.entityframeworkcore", "dbcontext")),
    ("Prisma", ("@prisma/client", "schema.prisma")),
    ("SQLAlchemy", ("sqlalchemy",)),
    ("SQLModel", ("sqlmodel",)),
    ("Tortoise ORM", ("tortoise-orm",)),
    ("Alembic", ("alembic",)),
    ("JWT", ("pyjwt", "python-jose", "jsonwebtoken", "@nestjs/jwt", "jwtbearer")),
    ("Bcrypt", ("bcrypt", "bcryptjs", "passlib")),
    ("Helmet", ("dep:helmet", "helmet(")),
    ("Nodemailer", ("nodemailer",)),
    ("Docker", ("dockerfile", "docker-compose")),
    ("pytest", ("pytest",)),
]

GENERIC_APP_NAMES = {
    "app", "main", "backend", "back-end", "frontend", "front-end",
    "server", "client", "my-app", "vite-project", "vite + react", "vite + react + ts",
    "react app", "document", "home", "home page", "index", "untitled",
    "laravel", "laravel/laravel", "fastapi-full-stack-template", "starter", "project", "test",
}

ALLOWED_SUBPROJECT_README_DIRS = {
    "backend", "back-end", "frontend", "front-end",
    "server", "client", "api", "app", "mobile", "web", "docs",
}

ASSET_ONLY_DIRS = {
    "public", "assets", "static", "img", "images", "fonts", "icons",
    "css", "js", "styles", "scripts", "wwwroot", "resources", "media",
}

GENERIC_COMMIT_PATTERNS = (
    "initial commit",
    "first commit",
    "add files via upload",
    "update readme",
    "create readme",
    "merge pull request",
    "merge branch",
    "wip",
)


def detect_text_language(text: str | None) -> str:
    """Detecta de forma determinista si un texto técnico está en español ('es') o inglés ('en')."""
    if not text or not text.strip():
        return "es"

    sample = text.lower()
    words = re.findall(r"[a-záéíóúüñ]+", sample)
    es_score = sum(2 for ch in sample if ch in "áéíóúñ¿¡")
    en_score = 0

    for w in words:
        if w in SPANISH_STOPWORDS:
            es_score += 2
        if w in ENGLISH_STOPWORDS:
            en_score += 2

    return "es" if es_score >= en_score else "en"


def translate_texts_batch(
    texts: list[str],
    source_lang: str,
    target_lang: str,
    enabled: bool = True,
) -> list[str]:
    """
    Traduce una lista corta de oraciones técnicas entre 'es' y 'en' sin costo ($0)
    durante la sincronización para almacenar ambas versiones listas en la BD SQL.
    Si no hay red o está deshabilitado (ej. pruebas unitarias offline), conserva el original.
    """
    clean_inputs = [t.strip() for t in texts]
    if not enabled or source_lang == target_lang or not any(clean_inputs):
        return clean_inputs

    separator = "\n ||| \n"
    joined = separator.join(clean_inputs)
    try:
        resp = httpx.get(
            "https://translate.googleapis.com/translate_a/single",
            params={
                "client": "gtx",
                "sl": source_lang,
                "tl": target_lang,
                "dt": "t",
                "q": joined,
            },
            timeout=5.0,
        )
        if resp.status_code != 200:
            return clean_inputs
        data = resp.json()
        if not isinstance(data, list) or not data or not isinstance(data[0], list):
            return clean_inputs
        translated_full = "".join(str(part[0]) for part in data[0] if part and part[0])
        parts = [p.strip() for p in re.split(r"\s*\|\|\|\s*", translated_full)]
        if len(parts) == len(clean_inputs):
            return parts
        # Si el separador se alteró, traducir elemento por elemento de respaldo
        results: list[str] = []
        for item in clean_inputs:
            if not item:
                results.append("")
                continue
            r_one = httpx.get(
                "https://translate.googleapis.com/translate_a/single",
                params={"client": "gtx", "sl": source_lang, "tl": target_lang, "dt": "t", "q": item},
                timeout=4.0,
            )
            if r_one.status_code == 200:
                d_one = r_one.json()
                results.append("".join(str(seg[0]) for seg in d_one[0] if seg and seg[0]).strip())
            else:
                results.append(item)
        return results
    except Exception:
        return clean_inputs


def compute_language_breakdown(lang_bytes: dict[str, int]) -> tuple[list[str], list[dict[str, Any]]]:
    """Calcula porcentajes exactos por lenguaje filtrando formatos documentales ruidosos."""
    if not lang_bytes:
        return [], []

    real_langs = {k: v for k, v in lang_bytes.items() if k not in NOISY_LANGUAGES}
    working = real_langs if real_langs else lang_bytes

    total_bytes = sum(working.values())
    if total_bytes <= 0:
        return list(working.keys()), []

    breakdown: list[dict[str, Any]] = []
    for name, b_count in sorted(working.items(), key=lambda kv: kv[1], reverse=True):
        pct = round((b_count / total_bytes) * 100.0, 1)
        if pct <= 0.0 and len(breakdown) >= 4:
            continue
        breakdown.append(
            {
                "nombre": name,
                "bytes": int(b_count),
                "porcentaje": max(0.1, pct),
            }
        )

    return [item["nombre"] for item in breakdown], breakdown


def extract_demo_url(gh_repo: dict[str, Any], raw_readme: str | None) -> str | None:
    """Detecta enlaces reales de demo/despliegue en vivo desde homepage o el README."""
    homepage = str(gh_repo.get("homepage") or "").strip()
    if homepage.startswith(("http://", "https://")) and "github.com" not in homepage.lower():
        return homepage

    if not raw_readme:
        return None

    # Buscar enlaces explícitos etiquetados como Demo / Live / Play
    md_links = re.findall(r"\[([^\]]{2,45})\]\((https?://[^)\s]+)\)", raw_readme)
    html_links = re.findall(r'<a[^>]+href=["\'](https?://[^"\']+)["\'][^>]*>([^<]{2,45})</a>', raw_readme, flags=re.I)

    candidates: list[tuple[str, str]] = [(label, url) for label, url in md_links] + [
        (label, url) for url, label in html_links
    ]
    ignored_domains = ("github.com", "shields.io", "badge", "localhost", "127.0.0.1", "linkedin.com", "mailto:")
    for label, url in candidates:
        low_lbl = label.lower()
        low_url = url.lower()
        if any(bad in low_url for bad in ignored_domains):
            continue
        if any(kw in low_lbl for kw in ("live demo", "demo", "play on", "ver demo", "sitio web", "live")):
            return url.strip()

    return None


def _is_clean_source_path(path_str: str) -> bool:
    norm = path_str.replace("\\", "/")
    if any(norm.startswith(pref) or f"/{pref}" in norm for pref in IGNORED_PATH_PREFIXES):
        return False
    base = norm.rsplit("/", 1)[-1]
    if base in {".DS_Store", ".gitignore", ".gitattributes", ".editorconfig", "package-lock.json", "composer.lock", "yarn.lock", "pnpm-lock.yaml"}:
        return False
    if base.endswith((".pyc", ".pyo", ".lock", ".iml", ".meta", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".pdf", ".xlsx", ".rtf")):
        return False
    return True


def _parse_manifest_evidence(file_path: str, content: str) -> dict[str, Any]:
    """Extrae dependencias, nombre comercial y descripción interna desde archivos de manifiesto."""
    low_path = file_path.lower()
    deps_blob: list[str] = [low_path]
    app_title: str | None = None
    manifest_desc: str | None = None
    prisma_models: list[str] = []

    if low_path.endswith("package.json"):
        try:
            pkg = json.loads(content)
            raw_name = str(pkg.get("name") or "").strip()
            if raw_name and raw_name.lower() not in GENERIC_APP_NAMES and not raw_name.startswith("@"):
                app_title = raw_name
            raw_desc = str(pkg.get("description") or "").strip()
            if len(raw_desc) >= 18:
                manifest_desc = raw_desc
            for section in ("dependencies", "devDependencies"):
                sec_obj = pkg.get(section)
                if isinstance(sec_obj, dict):
                    for k in sec_obj.keys():
                        kl = k.lower()
                        deps_blob.append(kl)
                        deps_blob.append(f"dep:{kl}")
        except Exception:
            deps_blob.append(content.lower())

    elif low_path.endswith("app.json"):
        try:
            cfg = json.loads(content)
            expo_obj = cfg.get("expo") if isinstance(cfg.get("expo"), dict) else cfg
            raw_name = str(expo_obj.get("name") or "").strip()
            if raw_name and raw_name.lower() not in GENERIC_APP_NAMES:
                app_title = raw_name
            deps_blob.append("dep:expo")
        except Exception:
            pass

    elif low_path.endswith("composer.json"):
        try:
            comp = json.loads(content)
            raw_desc = str(comp.get("description") or "").strip()
            if len(raw_desc) >= 18 and "skeleton application" not in raw_desc.lower() and "laravel framework" not in raw_desc.lower():
                manifest_desc = raw_desc
            for section in ("require", "require-dev"):
                sec_obj = comp.get(section)
                if isinstance(sec_obj, dict):
                    deps_blob.extend(k.lower() for k in sec_obj.keys())
        except Exception:
            deps_blob.append(content.lower())

    elif low_path.endswith("schema.prisma"):
        deps_blob.append("schema.prisma")
        prov_match = re.search(r'provider\s*=\s*"([a-zA-Z0-9_-]+)"', content)
        if prov_match:
            prov_name = prov_match.group(1).lower()
            deps_blob.append(prov_name)
            deps_blob.append(f"provider:{prov_name}")
        prisma_models = re.findall(r"^\s*model\s+([A-Za-z0-9_]+)\s*\{", content, flags=re.MULTILINE)

    elif low_path.endswith(".csproj"):
        deps_blob.append(content.lower())
        title_m = re.search(r"<(?:ApplicationTitle|AssemblyTitle|Product)>([^<]{3,60})</", content)
        if title_m:
            cand_t = title_m.group(1).strip()
            if cand_t and cand_t.lower() not in GENERIC_APP_NAMES and not cand_t.startswith("$("):
                app_title = cand_t
        desc_m = re.search(r"<Description>([^<]{18,240})</Description>", content)
        if desc_m:
            manifest_desc = desc_m.group(1).strip()

    else:
        # requirements.txt, pyproject.toml, Dockerfile, etc.
        deps_blob.append(content.lower())
        for pkg_tok in re.findall(r"^\s*([a-zA-Z0-9_.-]+)", content, flags=re.MULTILINE):
            deps_blob.append(f"dep:{pkg_tok.lower()}")

    return {
        "deps_text": " ".join(deps_blob),
        "app_title": app_title,
        "manifest_desc": manifest_desc,
        "prisma_models": prisma_models,
    }


def _extract_entrypoint_signals(content: str, file_path: str = "") -> dict[str, Any]:
    """Extrae docstrings iniciales, títulos de aplicación (<title>, FastAPI, Streamlit) y rutas HTTP."""
    docstring: str | None = None
    app_title: str | None = None
    low_path = file_path.lower()

    if low_path.endswith((".html", ".htm")):
        t_match = re.search(r"<title[^>]*>([^<]{3,80})</title>", content, flags=re.IGNORECASE)
        if t_match:
            cand_title = re.sub(r"\s+", " ", t_match.group(1)).strip()
            if cand_title and cand_title.lower() not in GENERIC_APP_NAMES:
                app_title = cand_title
        meta_desc = re.search(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']{22,260})["\']',
            content,
            flags=re.IGNORECASE,
        )
        if meta_desc:
            docstring = re.sub(r"\s+", " ", meta_desc.group(1)).strip()
        return {"docstring": docstring, "app_title": app_title, "routes": []}

    doc_match = re.match(r'^\s*(?:#[^\n]*\n)*\s*(?:"""|\'\'\')([\s\S]{20,350}?)(?:"""|\'\'\')', content)
    if doc_match:
        cleaned_doc = " ".join(line.strip() for line in doc_match.group(1).splitlines() if line.strip())
        if len(cleaned_doc) >= 22:
            docstring = cleaned_doc

    for pat in (
        r'page_title\s*=\s*["\']([^"\']{3,70})["\']',
        r'FastAPI\([^)]*title\s*=\s*["\']([^"\']{3,70})["\']',
        r'setWindowTitle\(\s*["\']([^"\']{3,70})["\']\s*\)',
    ):
        m = re.search(pat, content)
        if m:
            cand = m.group(1).strip()
            if cand.lower() not in GENERIC_APP_NAMES:
                app_title = cand
            break

    routes = re.findall(
        r'@?(?:app|router|api)\.(?:get|post|put|delete|patch|route|use)\(\s*["\'](/[a-zA-Z0-9_./:-]{2,45})["\']',
        content,
    )
    # Rutas ASP.NET Core [HttpGet("...")] / app.MapGet("/...", ...)
    routes.extend(
        re.findall(
            r'Map(?:Get|Post|Put|Delete|Patch)\(\s*["\'](/[a-zA-Z0-9_./{}:-]{2,45})["\']',
            content,
        )
    )
    unique_routes: list[str] = []
    for r in routes:
        if r not in unique_routes and r != "/":
            unique_routes.append(r)

    return {
        "docstring": docstring,
        "app_title": app_title,
        "routes": unique_routes[:6],
    }


def _detect_frameworks(combined_evidence: str, lang_names: list[str]) -> list[str]:
    low = combined_evidence.lower()
    lang_lower = {l.lower() for l in lang_names}
    found: list[str] = []
    for label, markers in TECH_RULES:
        if label.lower() in lang_lower:
            continue
        for mk in markers:
            # Coincidencia segura por palabra o subcadena específica
            if len(mk) <= 3:
                if re.search(rf"\b{re.escape(mk)}\b", low):
                    found.append(label)
                    break
            elif mk in low:
                found.append(label)
                break
    return found[:12]


def _extract_meaningful_modules_and_models(clean_paths: list[str], prisma_models: list[str]) -> tuple[list[str], list[str]]:
    modules: list[str] = []
    models: list[str] = list(dict.fromkeys(prisma_models))
    fallback_code_files: list[str] = []

    generic_stems = {
        "index", "main", "app", "layout", "_layout", "controller", "service",
        "utils", "helpers", "config", "constants", "types", "global", "init",
        "__init__", "test", "tests", "setup", "styles", "style", "script", "scripts",
        "routes", "web", "console", "channels", "api", "program", "mauiprogram",
        "appdelegate", "mainactivity", "mainapplication", "assemblyinfo",
        "requirements", "package", "composer", "dockerfile", "readme",
    }

    for p in clean_paths:
        norm = p.replace("\\", "/")
        low = norm.lower()
        if low.endswith((
            ".txt", ".json", ".md", ".yml", ".yaml", ".toml", ".csproj", ".sln",
            ".spec.ts", ".test.ts", ".test.js", ".fbx", ".prefab", ".mat", ".asset",
            ".woff", ".woff2", ".ttf", ".otf", ".css",
        )):
            continue
        stem = Path(norm).stem
        if stem.endswith(".xaml"):
            stem = stem[:-5]
        low_stem = stem.lower()
        if low_stem.endswith(("test", "tests", "spec")) or low_stem in generic_stems:
            continue

        # Detectar modelos ORM en carpetas Models / entities (excluyendo pruebas unitarias)
        if any(seg in low for seg in ("/models/", "app/models/", "/entities/", "models/")):
            if stem not in models and len(stem) >= 3:
                models.append(stem)
            continue

        # Controladores, servicios, ViewModels, páginas XAML/móviles, algoritmos y rutas
        is_interesting = (
            stem.endswith(("Controller", "Service", "Middleware", "Screen", "Navigator", "Guard", "Pipeline", "ViewModel", "Page", "Repository"))
            or low.endswith((".controller.ts", ".service.ts", ".module.ts"))
            or any(seg in low for seg in ("/routes/", "/routers/", "/controllers/", "/services/", "/screens/", "/views/", "/pages/", "/viewmodels/", "src/"))
            or "visualization" in low_stem
            or stem in {"dashboard", "Badges", "EditProfile", "BenchmarkApi"}
        )
        if is_interesting:
            clean_stem = stem.replace(".controller", "Controller").replace(".service", "Service").replace(".module", "Module")
            if clean_stem.lower() not in generic_stems and clean_stem not in modules and len(clean_stem) >= 3:
                modules.append(clean_stem)
        elif low.endswith((".py", ".js", ".ts", ".tsx", ".jsx", ".cs", ".php", ".java", ".cpp", ".html")) and len(stem) >= 4:
            if stem not in fallback_code_files:
                fallback_code_files.append(stem)

    if len(modules) < 3 and fallback_code_files:
        for cand in fallback_code_files:
            if cand not in modules:
                modules.append(cand)
            if len(modules) >= 5:
                break

    return modules[:10], models[:10]


def _classify_architecture(
    clean_paths: list[str],
    frameworks: list[str],
    lang_names: list[str],
) -> tuple[str, str]:
    low_paths = [p.lower() for p in clean_paths]
    fw_set = set(frameworks)

    has_backend_dir = any(p.startswith(("backend/", "back-end/", "server/", "api/")) for p in low_paths)
    has_frontend_dir = any(p.startswith(("frontend/", "front-end/", "client/", "src/components/", "app/")) for p in low_paths)
    has_mobile = bool({"React Native", "Expo"} & fw_set)
    has_maui = ".NET MAUI" in fw_set
    has_unity = "Unity" in fw_set or ("C#" in lang_names and not has_maui and "ASP.NET Core" not in fw_set and any(p.endswith(".unity") or "assets/" in p for p in low_paths))
    has_ml = bool({"PyTorch", "TensorFlow", "scikit-learn", "XGBoost", "MediaPipe", "YOLOv8", "sentence-transformers", "OpenAI Whisper"} & fw_set)

    if has_unity and has_ml:
        return ("Sistema Interactivo 3D + Visión/IA", "3D Interactive + Vision/AI System")
    if has_unity:
        return ("Proyecto Interactivo 3D (Unity)", "3D Interactive Project (Unity)")
    if has_maui:
        return ("Aplicación Multiplataforma (.NET MAUI)", "Cross-Platform App (.NET MAUI)")
    if has_mobile and has_backend_dir:
        return ("Plataforma Móvil Full-Stack + API", "Full-Stack Mobile + API Platform")
    if has_mobile:
        return ("Aplicación Móvil Multiplataforma", "Cross-Platform Mobile Application")
    if "WebXR / AR" in fw_set or "Three.js" in fw_set:
        return ("Aplicación Interactiva 3D / Realidad Aumentada", "3D / Augmented Reality Interactive App")
    if "Streamlit" in fw_set and has_ml:
        return ("Plataforma y Dashboard de Machine Learning", "Machine Learning Platform & Dashboard")
    if "Discord.py" in fw_set:
        return ("Bot en Tiempo Real y Procesamiento de Audio", "Real-Time Bot & Audio Pipeline")
    if "Laravel" in fw_set:
        return ("Aplicación Web MVC", "MVC Web Application")
    if has_backend_dir and has_frontend_dir:
        return ("Sistema Web Full-Stack (Cliente-Servidor)", "Full-Stack Web System (Client-Server)")
    if {"FastAPI", "NestJS", "Express", "Flask", "Django", "ASP.NET Core"} & fw_set and has_ml:
        return ("API Backend e Inteligencia Artificial", "Backend API & Artificial Intelligence")
    if {"FastAPI", "NestJS", "Express", "Flask", "Django", "ASP.NET Core"} & fw_set:
        return ("Servicio Backend / API REST", "Backend Service / REST API")
    if "Pygame" in fw_set:
        return ("Videojuego de Escritorio en Python", "Python Desktop Game")
    if has_ml:
        return ("Proyecto de Ciencia de Datos / IA", "Data Science / AI Project")
    if any("3d" in p or "visualization" in p for p in low_paths):
        return ("Aplicación de Visualización Interactiva", "Interactive Visualization Application")
    if "HTML" in lang_names and ("CSS" in lang_names or "JavaScript" in lang_names or "TypeScript" in lang_names):
        return ("Aplicación Web Frontend", "Frontend Web Application")
    return ("Proyecto de Ingeniería de Software", "Software Engineering Project")


def _build_code_based_bilingual_profile(
    repo_name: str,
    detected_app_name: str | None,
    arch_es: str,
    arch_en: str,
    lang_names: list[str],
    lang_breakdown: list[dict[str, Any]],
    frameworks: list[str],
    modules: list[str],
    models: list[str],
    routes: list[str],
    entrypoint_doc: str | None,
    top_dirs: list[str],
    clean_file_count: int,
    contributors: int,
    meaningful_commits: list[str],
) -> tuple[str, str, list[str], list[str]]:
    """
    Construye un resumen técnico preciso y viñetas verificables en Español e Inglés
    exclusivamente a partir de la evidencia real encontrada en el código del repositorio.
    """
    title_hint_es = f" ({detected_app_name})" if detected_app_name and detected_app_name.lower() not in repo_name.lower() else ""
    title_hint_en = title_hint_es

    # Evitar repetir el nombre del framework si ya viene implícito en la etiqueta de arquitectura
    filtered_fw = [fw for fw in frameworks if fw.lower() not in arch_es.lower() and fw.lower() not in arch_en.lower()]
    tech_main = (filtered_fw[:5] if filtered_fw else lang_names[:4]) or frameworks[:4]
    tech_str_es = ", ".join(tech_main) if tech_main else "código fuente propio"
    tech_str_en = ", ".join(tech_main) if tech_main else "custom source code"

    is_fem = arch_es.startswith(("Plataforma", "Aplicación"))
    participle_build = "construida" if is_fem else "construido"
    participle_struct = "estructurada" if is_fem else "estructurado"
    meaningful_dirs = [d for d in top_dirs if d.lower() not in ASSET_ONLY_DIRS]

    # Resumen principal ES / EN
    if entrypoint_doc:
        doc_lang = detect_text_language(entrypoint_doc)
        if doc_lang == "es":
            resumen_es = entrypoint_doc
            resumen_en = f"{arch_en}{title_hint_en} built with {tech_str_en}."
        else:
            resumen_en = entrypoint_doc
            resumen_es = f"{arch_es}{title_hint_es} {participle_build} con {tech_str_es}."
    else:
        mod_clause_es = ""
        mod_clause_en = ""
        if modules:
            sample_mods = ", ".join(modules[:4])
            mod_clause_es = f", integrando módulos clave como {sample_mods}"
            mod_clause_en = f", integrating core modules such as {sample_mods}"
        elif models:
            sample_mdls = ", ".join(models[:4])
            mod_clause_es = f", modelando entidades como {sample_mdls}"
            mod_clause_en = f", modeling entities such as {sample_mdls}"
        elif meaningful_dirs:
            sample_dirs = ", ".join(meaningful_dirs[:4])
            mod_clause_es = f", {participle_struct} en los módulos {sample_dirs}"
            mod_clause_en = f", structured across {sample_dirs} modules"

        resumen_es = f"{arch_es}{title_hint_es} {participle_build} con {tech_str_es}{mod_clause_es}."
        resumen_en = f"{arch_en}{title_hint_en} built with {tech_str_en}{mod_clause_en}."

    bullets_es: list[str] = []
    bullets_en: list[str] = []

    # Viñeta 1: Stack de frameworks y herramientas detectadas
    if frameworks:
        fw_list = ", ".join(frameworks[:8])
        bullets_es.append(f"Tecnologías y librerías verificadas en manifiestos del proyecto: {fw_list}.")
        bullets_en.append(f"Technologies and libraries verified in project manifests: {fw_list}.")

    # Viñeta 2: Módulos, controladores, pantallas o algoritmos detectados en el árbol
    if modules:
        mod_list = ", ".join(modules[:7])
        bullets_es.append(f"Componentes y módulos implementados en el código fuente: {mod_list}.")
        bullets_en.append(f"Components and modules implemented in source code: {mod_list}.")

    # Viñeta 3: Modelos de datos / esquema relacional
    if models:
        mdl_list = ", ".join(models[:7])
        bullets_es.append(f"Modelo de datos con {len(models)} entidades detectadas ({mdl_list}).")
        bullets_en.append(f"Data model featuring {len(models)} detected entities ({mdl_list}).")

    # Viñeta 4: Rutas / Endpoints HTTP detectados
    if routes:
        rt_list = ", ".join(routes[:5])
        bullets_es.append(f"Rutas y endpoints expuestos por la aplicación: {rt_list}.")
        bullets_en.append(f"Application routes and exposed endpoints: {rt_list}.")

    # Viñeta 5: Estructura de carpetas y composición del repositorio
    if lang_breakdown:
        dist = " · ".join(f"{item['nombre']} ({item['porcentaje']}%)" for item in lang_breakdown[:3])
        team_es = f"en equipo ({contributors} colaboradores)" if contributors > 1 else "de forma individual"
        team_en = f"in a team ({contributors} contributors)" if contributors > 1 else "individually"
        bullets_es.append(
            f"Base de código de {clean_file_count} archivos desarrollada {team_es} ({dist})."
        )
        bullets_en.append(
            f"Codebase of {clean_file_count} source files developed {team_en} ({dist})."
        )

    # Viñeta opcional de hito de commit si describe funcionalidad técnica real y faltan viñetas
    if len(bullets_es) < 4 and meaningful_commits:
        best_commit = meaningful_commits[0]
        c_lang = detect_text_language(best_commit)
        if c_lang == "es":
            bullets_es.append(f"Registro de implementación en historial Git: «{best_commit}».")
        else:
            bullets_en.append(f"Implementation milestone in Git history: \"{best_commit}\".")

    return resumen_es, resumen_en, bullets_es[:5], bullets_en[:5]


def inspect_and_enrich_repository(
    gh_client: GitHubClient,
    gh_repo: dict[str, Any],
    lang_bytes: dict[str, int],
    raw_readme: str | None,
    analyzer: PyTorchReadmeAnalyzer | None,
    repo_display_name: str,
    enable_translation: bool = True,
) -> tuple[PyTorchPrediction, list[str], dict[str, Any]]:
    """
    Ejecuta el análisis profundo de un repositorio combinando:
    1) Red neuronal PyTorch (PortfolioReadmeNet) sobre el README principal o secundario.
    2) Inspección profunda del árbol de archivos, manifiestos, esquemas Prisma/ORM y puntos de entrada.
    3) Síntesis bilingüe (ES / EN) + detección del idioma original del repositorio.
    """
    full_name = str(gh_repo["full_name"])
    default_branch = str(gh_repo.get("default_branch") or "main")
    created_at = str(gh_repo.get("created_at") or "")
    gh_description = str(gh_repo.get("description") or "").strip()

    clean_langs, lang_breakdown = compute_language_breakdown(lang_bytes)
    if not clean_langs and gh_repo.get("language"):
        clean_langs = [str(gh_repo["language"])]
        lang_breakdown = [{"nombre": clean_langs[0], "bytes": 1, "porcentaje": 100.0}]

    # 1. Consultar árbol de archivos y colaboradores del repositorio
    raw_tree: list[dict[str, Any]] = []
    contributors = 1
    try:
        raw_tree = gh_client.fetch_repo_tree(full_name, branch=default_branch)
    except GitHubRateLimitError:
        raw_tree = []

    try:
        contributors = gh_client.fetch_repo_contributors_count(full_name)
    except GitHubRateLimitError:
        contributors = 1

    blob_paths = [str(item.get("path") or "") for item in raw_tree if item.get("type") == "blob" and item.get("path")]
    clean_paths = [p for p in blob_paths if _is_clean_source_path(p)]
    top_dirs = sorted(
        {
            p.split("/")[0]
            for p in clean_paths
            if "/" in p and not p.split("/")[0].startswith(".")
        }
    )[:8]

    # Detectar presencia de Unity desde rutas antes del filtrado de ProjectSettings/Assets
    unity_signal = "unity_project_detected " if any(
        p.endswith(".unity") or "ProjectSettings/ProjectVersion.txt" in p for p in blob_paths
    ) else ""

    # 2. Si el README raíz no produjo texto, revisar si existe un README secundario limpio en subcarpeta
    effective_readme = raw_readme
    repo_meta_base = {
        "nombre": repo_display_name,
        "lenguajes": clean_langs,
        "topics": list(gh_repo.get("topics") or []),
        "descripcion_original": gh_description,
    }

    pytorch_pred = (
        analyzer.analyze_readme(effective_readme, repo_meta_base)
        if analyzer is not None
        else PyTorchPrediction(None, "metadatos", 0.0, True, [])
    )

    if pytorch_pred.descripcion is None and analyzer is not None:
        # Solo aceptar README secundarios de subproyectos reales (nunca carpetas de recursos/fuentes como public/fonts/README.md)
        secondary_readmes = [
            p for p in clean_paths
            if p.lower().endswith("readme.md")
            and p.count("/") == 1
            and p.split("/")[0].lower() in ALLOWED_SUBPROJECT_README_DIRS
        ]
        for sec_md_path in secondary_readmes[:2]:
            try:
                sec_text = gh_client.fetch_repo_file_text(full_name, sec_md_path)
                if sec_text:
                    cand_pred = analyzer.analyze_readme(sec_text, repo_meta_base)
                    if cand_pred.descripcion:
                        effective_readme = sec_text
                        pytorch_pred = cand_pred
                        break
            except GitHubRateLimitError:
                break

    # 3. Inspeccionar manifiestos clave (package.json, app.json, requirements.txt, composer.json, .csproj, schema.prisma)
    manifest_candidates = [
        p for p in clean_paths
        if p.count("/") <= 3
        and (
            p.lower().endswith((
                "package.json", "app.json", "requirements.txt", "pyproject.toml",
                "composer.json", "schema.prisma", "dockerfile", "docker-compose.yml", ".csproj",
            ))
            and not p.lower().endswith(("test.csproj", "tests.csproj"))
        )
    ]
    # Priorizar manifiestos más informativos primero
    manifest_candidates.sort(
        key=lambda p: (
            0 if any(k in p.lower() for k in ("schema.prisma", "app.json", ".csproj")) else 1,
            p.count("/"),
        )
    )

    validated_readme_text = effective_readme if pytorch_pred.descripcion else ""
    deps_chunks: list[str] = [unity_signal, " ".join(clean_paths), validated_readme_text or "", gh_description]
    detected_app_name: str | None = None
    manifest_desc: str | None = None
    prisma_models: list[str] = []

    for mf_path in manifest_candidates[:4]:
        try:
            mf_content = gh_client.fetch_repo_file_text(full_name, mf_path, max_chars=18000)
            if not mf_content:
                continue
            parsed = _parse_manifest_evidence(mf_path, mf_content)
            deps_chunks.append(parsed["deps_text"])
            if parsed["app_title"] and not detected_app_name:
                detected_app_name = parsed["app_title"]
            if parsed["manifest_desc"] and not manifest_desc:
                manifest_desc = parsed["manifest_desc"]
            if parsed["prisma_models"]:
                prisma_models.extend(parsed["prisma_models"])
        except GitHubRateLimitError:
            break

    # 4. Inspeccionar hasta 2 archivos de entrada (entrypoints) si hace falta mayor precisión
    entrypoint_doc: str | None = manifest_desc
    detected_routes: list[str] = []
    entrypoint_candidates = [
        p for p in clean_paths
        if p.count("/") <= 2
        and Path(p).name.lower() in {
            "app.py", "main.py", "dashboard.py", "server.py",
            "server.js", "index.js", "main.ts", "app.ts",
            "program.cs", "mauiprogram.cs", "index.html",
        }
    ]
    entrypoint_candidates.sort(key=lambda p: (1 if p.lower().endswith("index.html") else 0, p.count("/")))
    for ep_path in entrypoint_candidates[:2]:
        try:
            ep_text = gh_client.fetch_repo_file_text(full_name, ep_path, max_chars=8000)
            if not ep_text:
                continue
            deps_chunks.append(ep_text[:3000])
            ep_info = _extract_entrypoint_signals(ep_text, ep_path)
            if ep_info["docstring"] and not entrypoint_doc:
                entrypoint_doc = ep_info["docstring"]
            if ep_info["app_title"] and not detected_app_name:
                detected_app_name = ep_info["app_title"]
            for rt in ep_info["routes"]:
                if rt not in detected_routes:
                    detected_routes.append(rt)
        except GitHubRateLimitError:
            break

    frameworks = _detect_frameworks(" ".join(deps_chunks), clean_langs)
    modules, models = _extract_meaningful_modules_and_models(clean_paths, prisma_models)
    arch_es, arch_en = _classify_architecture(clean_paths, frameworks, clean_langs)
    demo_url = extract_demo_url(gh_repo, effective_readme)

    # 5. Determinar idioma original y construir resumen + puntos clave bilingües (ES / EN)
    is_empty_repo = len(clean_paths) == 0 and not clean_langs and not (effective_readme or "").strip()

    if is_empty_repo:
        idioma_original = "vacio"
        resumen_es = "Repositorio inicializado en GitHub sin archivos de código publicados aún en su rama principal."
        resumen_en = "Repository initialized on GitHub with no source files published on its default branch yet."
        puntos_es = []
        puntos_en = []
        final_pred = PyTorchPrediction(
            descripcion=resumen_es,
            origen="codigo-fuente",
            puntaje_relevancia=0.0,
            es_proyecto_portafolio=False,
            puntos_clave=[],
        )
    elif pytorch_pred.descripcion:
        # El repositorio cuenta con README rico analizado por nuestra red neuronal en PyTorch
        idioma_original = detect_text_language(pytorch_pred.descripcion)
        raw_summary = pytorch_pred.descripcion
        raw_bullets = list(pytorch_pred.puntos_clave)

        # Si el README era breve y dejó pocas viñetas, complementar con datos verificados del código
        if len(raw_bullets) < 2 and frameworks:
            fw_txt = ", ".join(frameworks[:6])
            if idioma_original == "es":
                raw_bullets.append(f"Stack técnico verificado en el repositorio: {fw_txt}.")
            else:
                raw_bullets.append(f"Verified technical stack in repository: {fw_txt}.")

        other_lang = "en" if idioma_original == "es" else "es"
        batch_to_translate = [raw_summary] + raw_bullets
        translated_batch = translate_texts_batch(
            batch_to_translate,
            source_lang=idioma_original,
            target_lang=other_lang,
            enabled=enable_translation,
        )
        tr_summary = translated_batch[0] if translated_batch else raw_summary
        tr_bullets = translated_batch[1:] if len(translated_batch) > 1 else raw_bullets

        if idioma_original == "es":
            resumen_es, resumen_en = raw_summary, tr_summary
            puntos_es, puntos_en = raw_bullets, tr_bullets
        else:
            resumen_en, resumen_es = raw_summary, tr_summary
            puntos_en, puntos_es = raw_bullets, tr_bullets

        final_pred = pytorch_pred
    elif gh_description:
        # Tiene descripción manual en GitHub pero no README largo
        idioma_original = detect_text_language(gh_description)
        other_lang = "en" if idioma_original == "es" else "es"
        tr_desc = translate_texts_batch([gh_description], idioma_original, other_lang, enabled=enable_translation)[0]
        _, _, code_b_es, code_b_en = _build_code_based_bilingual_profile(
            repo_name=repo_display_name,
            detected_app_name=detected_app_name,
            arch_es=arch_es,
            arch_en=arch_en,
            lang_names=clean_langs,
            lang_breakdown=lang_breakdown,
            frameworks=frameworks,
            modules=modules,
            models=models,
            routes=detected_routes,
            entrypoint_doc=None,
            top_dirs=top_dirs,
            clean_file_count=len(clean_paths),
            contributors=contributors,
            meaningful_commits=[],
        )
        if idioma_original == "es":
            resumen_es, resumen_en = gh_description, tr_desc
        else:
            resumen_en, resumen_es = gh_description, tr_desc
        puntos_es, puntos_en = code_b_es, code_b_en
        final_pred = PyTorchPrediction(
            descripcion=gh_description,
            origen="original",
            puntaje_relevancia=0.65,
            es_proyecto_portafolio=True,
            puntos_clave=puntos_es,
        )
    else:
        # Sin README útil ni descripción manual: activar síntesis profunda desde el código fuente real
        idioma_original = "codigo"
        meaningful_commits: list[str] = []
        try:
            raw_commits = gh_client.fetch_recent_commit_messages(full_name, limit=10)
            for msg in raw_commits:
                clean_msg = re.sub(r"^usar npm install y actualizar el \.env\s*", "", msg, flags=re.I).strip()
                low_m = clean_msg.lower()
                if len(clean_msg) >= 32 and not any(pat in low_m for pat in GENERIC_COMMIT_PATTERNS):
                    if len(clean_msg) > 200:
                        clean_msg = clean_msg[:197].rsplit(" ", 1)[0].rstrip(",;:-.") + "..."
                    meaningful_commits.append(clean_msg)
                    break
        except GitHubRateLimitError:
            meaningful_commits = []

        resumen_es, resumen_en, puntos_es, puntos_en = _build_code_based_bilingual_profile(
            repo_name=repo_display_name,
            detected_app_name=detected_app_name,
            arch_es=arch_es,
            arch_en=arch_en,
            lang_names=clean_langs,
            lang_breakdown=lang_breakdown,
            frameworks=frameworks,
            modules=modules,
            models=models,
            routes=detected_routes,
            entrypoint_doc=entrypoint_doc,
            top_dirs=top_dirs,
            clean_file_count=len(clean_paths),
            contributors=contributors,
            meaningful_commits=meaningful_commits,
        )
        # Si alguna viñeta de commit quedó en un solo idioma, sincronizar pares
        if len(puntos_es) > len(puntos_en):
            extra_tr = translate_texts_batch(puntos_es[len(puntos_en):], "es", "en", enabled=enable_translation)
            puntos_en.extend(extra_tr)
        elif len(puntos_en) > len(puntos_es):
            extra_tr = translate_texts_batch(puntos_en[len(puntos_es):], "en", "es", enabled=enable_translation)
            puntos_es.extend(extra_tr)

        final_pred = PyTorchPrediction(
            descripcion=resumen_es,
            origen="codigo-fuente",
            puntaje_relevancia=0.72 if (frameworks or modules or models) else 0.35,
            es_proyecto_portafolio=True,
            puntos_clave=puntos_es,
        )

    detalle_tecnico: dict[str, Any] = {
        "idioma_original": idioma_original,
        "resumen_es": resumen_es,
        "resumen_en": resumen_en,
        "puntos_clave_es": puntos_es,
        "puntos_clave_en": puntos_en,
        "frameworks": frameworks,
        "lenguajes_detalle": lang_breakdown,
        "arquitectura_es": arch_es,
        "arquitectura_en": arch_en,
        "modulos_detectados": modules,
        "modelos_datos": models,
        "rutas_detectadas": detected_routes,
        "carpetas_principales": top_dirs,
        "colaboradores": contributors,
        "archivos_codigo": len(clean_paths),
        "rama_principal": default_branch,
        "fecha_creacion": created_at,
        "demo_url": demo_url,
        "nombre_app_detectado": detected_app_name,
    }

    return final_pred, clean_langs, detalle_tecnico