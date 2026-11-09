# Portafolio Dinámico Auto-actualizable

Aplicación web cliente-servidor que sincroniza automáticamente los repositorios públicos y colaborativos de GitHub hacia una base de datos relacional **PostgreSQL** (con soporte inmediato de base SQL local sin configuración extra), ejecuta una red neuronal propia en **PyTorch** (`Embedding` + `BiLSTM` bidireccional + `Self-Attention` + fusión estructural) para sintetizar descripciones claras a partir del `README`, y muestra la tendencia semanal de commits en el tiempo.

> **Nota:** Proyecto independiente para la materia de Gestión de Proyectos de Software (UABC Tijuana). Opera únicamente en modo lectura (`GET`) sobre la API de GitHub y no modifica ningún repositorio ni portafolio previo del autor.

## Estructura del Proyecto

```text
portafolioDinamico/
├── CONTEXTO.md                        # Fuente de verdad, alcance, requisitos y plan
├── config.json                        # Configuración de usuario, repos extra y filtros
├── .env.example                       # Plantilla segura para DATABASE_URL y GITHUB_TOKEN
├── requirements.txt                   # Dependencias Python (FastAPI, SQLAlchemy, Psycopg, PyTorch)
├── Dockerfile                         # Empaquetado para despliegue en la nube (Render / Railway / Fly)
├── run_local.ps1                      # Inicio rápido en un solo comando para Windows PowerShell
├── .github/workflows/
│   └── sync-portfolio.yml             # Job nocturno programado con GitHub Actions (RF8)
├── database/
│   └── schema.sql                     # DDL oficial para PostgreSQL (Supabase / Neon / local)
├── backend/
│   ├── main.py                        # Servidor FastAPI (API REST + configuración + estáticos)
│   ├── database.py                    # Motor SQLAlchemy 2.0 (PostgreSQL + fallback SQL local)
│   ├── models.py                      # Entidades Usuario, Repositorio, ActividadCommit
│   ├── github_service.py              # Cliente GitHub REST API (rate limits, HTTP 202, PushEvents y árboles)
│   ├── repo_inspector.py              # Inspector profundo de código, manifiestos, frameworks y modelos ORM
│   ├── sync_service.py                # Sincronización paralela hacia SQL + respaldo JSON (RNF4)
│   ├── analytics.py                   # Métricas semanales, desglose por repo y racha activa (RF7)
│   └── ml/
│       ├── network.py                 # Red neuronal PortfolioReadmeNet en PyTorch puro
│       ├── tokenizer.py               # Limpieza de Markdown/ruido y tensores/vocabulario PyTorch
│       ├── dataset_readmes.json       # Corpus etiquetado bilingüe (80 ejemplos ES/EN)
│       ├── train.py                   # Entrenamiento reproducible con Dataset, DataLoader y F1-score
│       ├── predictor.py               # Inferencia PyTorch sobre READMEs reales
│       └── artifacts/                 # Pesos entrenados (.pt), vocabulario y métricas (94.12% acc, 0.9333 F1)
├── index.html                         # Interfaz web responsiva Bilingüe ES/EN (Pantallas 1, 2, 3 y 4)
├── src/                               # Estilos CSS y módulos ES6 del cliente
├── data/                              # Base SQL local (opcional) y respaldo backup_portfolio.json
├── docs/
│   ├── MANUAL_DE_USUARIO.md           # Guía de instalación, token de GitHub, vista previa y 4 pantallas
│   ├── DOCUMENTACION_TECNICA.md       # Arquitectura, diagrama E-R, modelo PyTorch y API REST
│   └── INFORME_DE_PRUEBAS.md          # Matriz RF/RNF, 16 casos pytest y defectos corregidos
└── tests/
    └── test_sistema.py                # Suite de pruebas funcionales automatizadas con pytest
```

## Inicio Rápido en Local (Windows)

```powershell
.\run_local.ps1
```

O paso a paso:

```powershell
# 1. Crear archivo .env (si DATABASE_URL queda vacío usa automáticamente SQL local)
Copy-Item .env.example .env

# 2. (Opcional) Reentrenar el modelo neuronal en PyTorch
py -3.11 -m backend.ml.train

# 3. Sincronizar repositorios, READMEs y commits desde GitHub
py -3.11 -m backend.sync_service

# 4. Ejecutar las 16 pruebas automatizadas del sistema
py -3.11 -m pytest -v

# 5. Levantar el servidor web (FastAPI + Frontend)
py -3.11 -m uvicorn backend.main:app --reload --port 8000
```

Abre en el navegador: **http://localhost:8000** (o previsualiza cualquier cuenta pública con `http://localhost:8000/?user=NombreUsuario`).

## Modo de Operación y Despliegue (Actividad L)

- **Ejecución Local Autocontenida (Producción/Entrega oficial):** Para garantizar independencia de proveedores en la nube, costos nulos y máxima privacidad, el sistema opera de manera 100% autocontenida en la estación de trabajo local mediante `run_local.ps1` con base de datos relacional local SQLite (`data/portfolio_local.db`) en modo WAL. No requiere contratar ni configurar servicios de hosting externos (Render, Neon, Supabase).
- **Contenedor Docker (Opcional):** El archivo `Dockerfile` empaqueta Python 3.11, PyTorch CPU y FastAPI en el puerto `8000` para quienes prefieran correr el servicio en un contenedor local aislado sin dependencias en el sistema operativo anfitrión.
- **Sincronización Periódica Automatizada:** El script de sincronización `backend/sync_service.py` actualiza los repositorios de GitHub bajo demanda y guarda automáticamente un respaldo completo en `data/backup_portfolio.json`. El repositorio incluye además el flujo de GitHub Actions `.github/workflows/sync-portfolio.yml` preparado para ejecuciones programadas automáticas.

## Documentación Entregable (Actividad K)

- [Manual de Usuario](./docs/MANUAL_DE_USUARIO.md)
- [Documentación Técnica](./docs/DOCUMENTACION_TECNICA.md)
- [Informe de Pruebas](./docs/INFORME_DE_PRUEBAS.md)
