# Informe de Pruebas — Portafolio Dinámico Auto-actualizable

## 1. Objetivo y alcance

Este documento registra los resultados de las **Actividades I (Pruebas funcionales)** y **J (Corrección de errores y repetición de pruebas)** del plan de trabajo. Cubre la validación integral del backend en **FastAPI**, la capa relacional **SQLAlchemy / PostgreSQL**, el modelo neuronal en **PyTorch (`PortfolioReadmeNet`)**, la integración de solo lectura con la **API de GitHub** y el comportamiento de las cuatro pantallas del cliente web.

- **Entorno de ejecución:** Windows 11 · Python `3.11.9` · PyTorch `2.6.0+cpu` · FastAPI `0.115.12` · SQLAlchemy `2.1.8` · Psycopg `3.3.7` · Pytest `9.0.3`.
- **Archivo de suite automatizada:** `tests/test_sistema.py`.
- **Comando de verificación:** `py -3.11 -m pytest -v`.

---

## 2. Matriz de trazabilidad de requisitos

| Requisito | Descripción resumida | Módulos verificados | Casos de prueba | Estado |
|---|---|---|---|---|
| **RF1** | Conectar cuenta de GitHub y sincronizar repositorios propios y colaborativos | `github_service.py`, `sync_service.py`, `main.py` | `CP-04`, `CP-05`, `CP-13`, `CP-15` | Cumplido |
| **RF2** | Leer `README` y generar descripción enriquecida con modelo de lenguaje PyTorch e inspector | `ml/network.py`, `ml/predictor.py`, `ml/tokenizer.py`, `repo_inspector.py` | `CP-02`, `CP-03`, `CP-10`, `CP-11`, `CP-14`, `CP-16` | Cumplido |
| **RF3** | Excluir repositorios mediante *topics* y listas configurables | `sync_service.py`, `main.py`, `src/js/utils.js` | `CP-05`, `CP-07` | Cumplido |
| **RF4** | Generar tarjetas con nombre, descripción, stack detectado y enlace al repo | `index.html`, `src/js/app.js`, `src/js/utils.js`, `models.py` | `CP-05`, `CP-06`, `CP-11`, `CP-12` | Cumplido |
| **RF5** | Mostrar última actualización relativa («Actualizado hace X días») | `src/js/utils.js`, `src/js/app.js` | `CP-06` | Cumplido |
| **RF6** | Ordenar proyectos automáticamente por actividad reciente (`pushed_at`) | `sync_service.py`, `main.py`, `src/js/utils.js` | `CP-05` | Cumplido |
| **RF7** | Mostrar gráfica semanal de tendencia de commits, desglose por repo, lenguaje y racha | `analytics.py`, `github_service.py`, `src/js/app.js` | `CP-05`, `CP-16` | Cumplido |
| **RF8** | Actualización automática (en visita con enfriamiento o job GitHub Actions) | `main.py`, `.github/workflows/sync-portfolio.yml` | `CP-06`, `CP-07` | Cumplido |
| **RNF1** | Carga del portafolio en menos de 3 segundos | `main.py`, `database.py` | `CP-06` | Cumplido (< 0.25 s local) |
| **RNF2** | Compatibilidad en navegadores estándar y diseño responsivo móvil (`<= 768px`) | `index.html`, `src/css/styles.css` | Verificación UI | Cumplido |
| **RNF3** | Manejo de *rate limits* y estados `HTTP 202` de la API de GitHub | `github_service.py`, `sync_service.py` | `CP-04`, `CP-09` | Cumplido |
| **RNF4** | Respaldo periódico de descripciones e historial (`data/backup_portfolio.json`) | `sync_service.py` | `CP-05`, `CP-09`, `CP-15` | Cumplido |
| **RNF5** | Acceso público al portafolio (y vista previa `?user=`) sin login; escritura protegida por `X-Admin-Key` | `main.py`, `index.html` | `CP-06`, `CP-08`, `CP-15` | Cumplido |
| **RNF6** | Disponibilidad >= 95% apoyada en SQL + respaldo JSON desconectado | `main.py`, `src/js/app.js` | `CP-06`, `CP-09` | Cumplido |

---

## 3. Catálogo de casos de prueba automatizados (`pytest`)

| ID | Función de prueba en `tests/test_sistema.py` | Escenario validado | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| **CP-01** | `test_normalize_postgresql_urls_for_supabase_and_neon` | Cadenas `postgres://` y `postgresql://` de proveedores en la nube | Conversión automática a `postgresql+psycopg://` | **PASSED** |
| **CP-02** | `test_pytorch_network_shapes_and_attention_mask` | Inferencia de tensores en `PortfolioReadmeNet` con tokens `<PAD>` | Dimensiones exactas y peso de atención `< 1e-5` en `<PAD>` | **PASSED** |
| **CP-03** | `test_pytorch_analyzer_extracts_real_sentences_and_rejects_laravel_boilerplate` | `README` técnico real vs plantilla por defecto de Laravel | Extrae oración real sin comandos CLI y descarta plantilla genérica | **PASSED** |
| **CP-04** | `test_github_client_handles_http_202_retry_and_404_readme` | GitHub responde `202` calculando estadísticas y `404` sin `README` | Reintenta hasta obtener `200` y devuelve `None` limpio ante `404` | **PASSED** |
| **CP-05** | `test_full_sql_sync_and_activity_trend_with_mocked_github` | Sincronización completa en tablas SQL, exclusión por topic y tendencia | 3 repos guardados (2 visibles ordenados), racha de 3 días y respaldo creado | **PASSED** |
| **CP-06** | `test_fastapi_endpoints_and_load_under_3_seconds` | Peticiones públicas `GET /`, `GET /api/portfolio` y `GET /api/projects/999` | Respuesta `HTTP 200` sin login y tiempo total `< 3.0 s` | **PASSED** |
| **CP-07** | `test_config_panel_endpoints_and_visibility_recalculation` | `GET /api/config` y `PUT /api/config` desde Pantalla 4 + validación de formato | Recálculo inmediato en SQL al excluir topic `tutorial` y `HTTP 422` ante slug inválido | **PASSED** |
| **CP-08** | `test_admin_key_protection_when_configured` | Protección opcional `PORTFOLIO_ADMIN_KEY` en `PUT /api/config` | Devuelve `HTTP 403` sin cabecera y `HTTP 200` con `X-Admin-Key` válida | **PASSED** |
| **CP-09** | `test_rate_limit_resilience_preserves_existing_sql_and_backup` | Simulación de agotamiento de cuota GitHub (`HTTP 403`, `remaining=0`) | Conserva datos previos en SQL, exporta aviso no destructivo y no cae | **PASSED** |
| **CP-10** | `test_tokenizer_handles_utf8_bom_markdown_tables_and_expo_boilerplate` | Marca BOM `\ufeff`, tablas Markdown con `\|` y plantilla Expo `create-expo-app` | Ignora BOM y filas de tabla; descarta plantilla genérica de Expo | **PASSED** |
| **CP-11** | `test_deep_repo_inspector_extracts_code_entities_when_readme_missing_or_boilerplate` | Repositorio con plantilla NestJS por defecto, `package.json`, `schema.prisma`, controladores y rutas | Descarta plantilla base y extrae frameworks, modelos Prisma, rutas, módulos y perfil bilingüe ES/EN | **PASSED** |
| **CP-12** | `test_detect_text_language_and_empty_repo_handling` | Detección de idioma original (`es` vs `en`) y repositorio vacío sin archivos (`MLAD`) | Clasifica correctamente ES/EN y etiqueta el repo vacío como `vacio` sin inventar tecnologías | **PASSED** |
| **CP-13** | `test_switch_github_user_in_config_and_restore_previous_profile` | Cambio de usuario de GitHub desde Pantalla 4 (`404` inexistente, cuenta nueva y retorno a `AssuredPigeon`) | Aísla repositorios por cuenta, detecta nombre público y restaura caché/ajustes de `AssuredPigeon` | **PASSED** |
| **CP-14** | `test_font_asset_readmes_and_localhost_noise_are_ignored_in_favor_of_real_code` | Repositorios con `public/fonts/README.md` (`BlockchainFont.woff2`), proyectos `.NET MAUI` (`.csproj`) y líneas `localhost`/`ENVIRONMENT:` | Ignora READMEs de recursos estáticos, filtra ruido de entorno local y sintetiza arquitectura real desde `.csproj`, modelos y vistas | **PASSED** |
| **CP-15** | `test_readonly_url_preview_mode_and_admin_key_flag` | Vista previa pública `?user=VisitantePublico` en `GET /api/portfolio` y bandera `admin_key_requerida` en `GET /api/config` | Previsualiza cuenta externa sin alterar `config.json` ni `backup_portfolio.json`, cachea en SQL y devuelve `404`/`422` según el caso | **PASSED** |
| **CP-16** | `test_weekly_repo_breakdown_and_pytorch_f1_metrics` | Desglose semanal de commits por repositorio (`compute_activity_trend`) y evaluación PyTorch (`training_metrics.json`) | Devuelve lista ordenada `desglose` por semana y verifica corpus `>= 80` con `val_salience_precision`, `val_salience_recall` y `val_salience_f1 >= 0.85` | **PASSED** |

---

## 4. Defectos detectados y corregidos durante pruebas reales (Actividad J)

Durante las pruebas de integración con los **14 repositorios reales** asociados a `AssuredPigeon` (12 propios + 2 colaborativos), se identificaron y corrigieron los siguientes casos borde:

1. **Marca BOM UTF-8 (`\ufeff`) al inicio de archivo:**  
   - *Hallazgo:* El `README` de `Garethsito/SDKGU-Subject-Sistem` iniciaba con `\ufeff# SDGKU...`, impidiendo que la expresión regular `^#{1,6}\s+` descartara el encabezado principal.  
   - *Corrección:* Se añadió `.lstrip("\ufeff")` por línea en `backend/ml/tokenizer.py` y se cubrió en `CP-10`.
2. **Tablas Markdown interpretadas como texto corrido:**  
   - *Hallazgo:* En `AssuredPigeon/musicbot`, las tablas de comandos (`| Comando | Descripción |`) producían secuencias artificiales de símbolos `|`.  
   - *Corrección:* Se filtraron líneas que inician con `|` o contienen dos o más separadores de columna en `clean_readme_to_sentences()`.
3. **Plantillas autogeneradas por frameworks (Laravel y Expo):**  
   - *Hallazgo:* `AssuredPigeon/animeExplorerContSol` y `AssuredPigeon/ASPHALT` conservaban el `README` por defecto de Laravel y `create-expo-app`. Mostrar ese texto violaría la Regla 6 de veracidad del portafolio.  
   - *Corrección:* Se incorporó detección documental de plantillas base (`STARTER_TEMPLATE_MARKERS`), haciendo que el sistema recurra limpiamente a los metadatos verificados de GitHub (`origen_descripcion = "metadatos"`).
4. **Sobreajuste inicial (*overfitting*) en `PortfolioReadmeNet`:**  
   - *Hallazgo:* En la primera corrida con dimensión oculta `64`, la pérdida de validación subía tras pocas épocas.  
   - *Corrección:* Se ajustó `embed_dim=32`, `lstm_hidden=32`, `Dropout(0.35)`, regularización `weight_decay=1e-2` y selección del mejor *checkpoint* sobre partición estratificada, alcanzando **88.89%** de exactitud en validación (`val_loss = 0.6015`).
5. **Commits colaborativos en ramas secundarias y commits de bots:**  
   - *Hallazgo:* `/stats/commit_activity` solo contabiliza la rama por defecto (`main`), omitiendo trabajo reciente en ramas de equipo (`DanceLabo`, `SDKGU-Subject-Sistem`), mientras que `dependabot` generaba pushes automáticos en `semantic-review-insights`.  
   - *Corrección:* Se integró `fetch_repo_push_events()` en `backend/github_service.py` excluyendo explícitamente cuentas `[bot]` y `dependabot`, elevando los registros verificados de `ActividadCommit` sin contaminar métricas con bots.
6. **Atributo HTML `hidden` sobreescrito por contenedores `display: flex` / `display: grid` en CSS:**  
   - *Hallazgo:* Durante la validación manual en navegador, al desactivar *«Mostrar gráfica de tendencia de actividad»* la sección `#activity-section` (`.panel-section { display: flex }`) permanecía visible, el contenedor de respaldo `.chart-fallback` añadía un espacio vacío debajo del `<canvas>` y la etiqueta `TOPICS EN GITHUB` seguía mostrándose vacía en proyectos sin topics.  
   - *Corrección:* Se añadió `[hidden] { display: none !important; }` y ajuste de altura de `.chart-wrapper` en `src/css/styles.css`, además de liberar la instancia activa de Chart.js al ocultar la sección en `src/js/app.js`.
7. **Doble barra de desplazamiento modal y bloqueo de SQLite en sincronizaciones secuenciales largas:**  
   - *Hallazgo:* Al probar el cambio a una cuenta nueva con 24 repositorios (`George170205`), el sincronizado secuencial tardaba ~40 s causando `sqlite3.OperationalError: database is locked` ante recargas rápidas del navegador, mientras el `<dialog>` mostraba dos barras verticales (una blanca del navegador y otra oscura del cuerpo interno).  
   - *Corrección:* Se fijó `overflow: hidden` en `.project-modal` con un único contenedor desplazable oscuro (`.modal-body-scroll { min-height: 0; color-scheme: dark; }`), se habilitó `PRAGMA journal_mode=WAL` con `busy_timeout=20000` en `backend/database.py`, y se refactorizó `sync_portfolio_to_db` para ejecutar consultas HTTP e inspecciones en paralelo (`ThreadPoolExecutor`) antes de una única transacción rápida en SQL (~9 s para 24 repositorios).
8. **Contaminación por `README` de fuentes estáticas, líneas `localhost:` y codificación `UTF-16`:**  
   - *Hallazgo:* Repositorios de `.NET MAUI` y aplicaciones web sin `README` raíz heredaban el `README` auxiliar `public/fonts/README.md` (`BlockchainFont-Regular.woff2`) o mostraban instrucciones locales (`http://localhost:5173`, `ENVIRONMENT: production`), mientras que archivos en `UTF-16 BOM` (`Class-7`, `Api-_.Net`) llegaban con caracteres nulos sin decodificar.  
   - *Corrección:* Se ignoraron rutas de fuentes/recursos estáticos en `repo_inspector.py` y `github_service.py`, se añadieron reglas de decodificación `UTF-16` e inspección de `.csproj`/`<title>`/`Three.js`, y se filtraron líneas de entorno local en `tokenizer.py` y `predictor.py` (`CP-14`).
9. **Ampliación del corpus PyTorch y métricas completas de clasificación:**  
   - *Hallazgo:* El corpus inicial contaba con 44 ejemplos y reportaba únicamente pérdida y exactitud global en validación.  
   - *Corrección:* Se expandió `backend/ml/dataset_readmes.json` a **80 ejemplos bilingües** y se incorporó el cálculo de **Precision (`100.0%`)**, **Recall (`87.50%`)** y **F1-score (`0.9333`)** en `backend/ml/train.py`, elevando `val_salience_acc` a **94.12%** con `val_loss = 0.4196` (`CP-16`).

---

## 5. Verificación final

- **Suite automatizada:** `16 passed` (`0 failed`).
- **Validación cliente ES6:** `node --check` sobre `src/js/app.js` y `src/js/utils.js`, verificación cruzada de los `111` IDs del DOM en `index.html` y pruebas unitarias funcionales de búsqueda/filtros y desglose semanal sin fallos.
- **Sincronización real y multiusuario verificada:** Perfiles `AssuredPigeon` (`11` visibles) y `George170205` (`24` visibles, `39` repositorios totales en `SQLite WAL`), con respaldo exportado en `data/backup_portfolio.json` y previsualización pública por URL `?user=` operativa.

