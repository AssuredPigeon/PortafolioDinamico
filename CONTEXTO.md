# Contexto del proyecto: Portafolio Dinámico Auto-actualizable

> Este archivo es la fuente de verdad del proyecto. Léelo completo antes de escribir código y vuelve a consultarlo antes de agregar o cambiar funciones.

## 1. Qué es

Un sistema web cliente-servidor de portafolio que se mantiene actualizado solo. Su backend en **Python (FastAPI)** se conecta a la API de GitHub, almacena la información en una base de datos relacional **PostgreSQL**, ejecuta un modelo neuronal propio entrenado en **PyTorch** para generar descripciones claras a partir del `README` y clasificar la relevancia de oraciones/proyectos, y expone todo a un frontend web responsivo sin tener que editar HTML manualmente.

- **Autor:** Daniel Tornero Solano (Sewell), estudiante de Software Engineering and Emerging Technologies en UABC Tijuana.
- **Usuario de GitHub:** `AssuredPigeon`.
- **Contexto:** proyecto de la materia de gestión de proyectos de software. Se entrega como un sistema funcional en un **repositorio independiente** (`portafolioDinamico`), sin modificar ni reemplazar el portafolio personal actual del autor (`assuredpigeon.github.io` ni `AssuredPigeon/AssuredPigeon`).
- **Responsable único:** una sola persona desarrolla todo el proyecto.

## 2. Problema que resuelve

Quien mantiene un portafolio a mano lo actualiza poco, los repos destacados (pinned) no siempre son los mejores proyectos, las descripciones son escuetas y no se ve qué tan activo ha estado programando. El sistema automatiza todo eso.

## 3. Fechas y restricciones

- Inicio planeado del proyecto: lunes 28 de septiembre de 2026.
- **Fecha límite de entrega: viernes 27 de noviembre de 2026.**
- Esfuerzo estimado del plan completo: 308 horas (41 días laborables a 8 h/día).
- Estrategia de ejecución: validar primero el núcleo **MVP** (BD SQL + sincronización GitHub + tarjetas responsivas) y enseguida las actividades del cronograma vigentes hasta hoy (**F: Modelo en PyTorch** y **G: Tendencia de actividad**).
- Presupuesto: sin presupuesto asignado (`$0`). Uso de PyTorch local en CPU y PostgreSQL local o gratuito (Supabase / Neon).

## 4. Alcance

### Incluido en el proyecto completo
1. Sincronización automática con la API de GitHub (nombre, descripción, lenguajes, estrellas, fecha del último commit).
2. Lectura del README de cada repo para generar una descripción más clara mediante un modelo propio entrenado en **PyTorch**.
3. Filtro para ocultar repos de práctica o tutoriales, mediante topics/tags de GitHub y lista configurable.
4. Tarjetas de proyecto con stack detectado, enlace al repo e indicador "actualizado hace X días".
5. Ordenamiento automático por actividad reciente.
6. Gráfica de tendencia de actividad (commits en el tiempo).
7. Panel de configuración (topics a excluir, método de actualización).
8. Actualización automática: al visitar cuando el caché expira o mediante job programado con GitHub Actions.

### Fuera del alcance (NO implementar)
- Análisis de compatibilidad con vacantes de empleo (match score).
- Detección de brechas de habilidades (skill gap).
- Aplicación móvil nativa.
- Integración con otras plataformas de portafolio.
- Animaciones y temas de color extra.

Si algo no está en la lista de "Incluido", pregunta antes de agregarlo.

## 5. Requisitos

### Funcionales
- **RF1:** conectar una cuenta de GitHub y sincronizar los repositorios del usuario.
- **RF2:** leer el README de cada repo y generar una descripción enriquecida con un modelo en PyTorch.
- **RF3:** excluir repos del portafolio mediante topics/tags configurables.
- **RF4:** generar tarjetas de proyecto con nombre, descripción, stack detectado y enlace al repo.
- **RF5:** mostrar la última actualización de cada proyecto ("hace X días").
- **RF6:** ordenar los proyectos por actividad reciente.
- **RF7:** mostrar una gráfica de tendencia de actividad basada en el historial de commits.
- **RF8:** actualizarse automáticamente (al cargar si expiró ventana o job programado).

### No funcionales
- **RNF1:** cargar el portafolio en menos de 3 segundos en una conexión estándar.
- **RNF2:** funcionar en navegadores estándar (Chrome, Edge, Firefox) y verse bien en celular.
- **RNF3:** manejar los límites de peticiones (rate limits) de la API de GitHub.
- **RNF4:** respaldar periódicamente la información generada (`data/backup_portfolio.json` además de la BD SQL).
- **RNF5:** el portafolio es público; el visitante no inicia sesión.
- **RNF6:** disponibilidad de al menos 95%.

## 6. Pantallas

1. **Portafolio público:** cuadrícula de tarjetas (nombre, stack, "actualizado hace X días", botón "Ver detalle" y botón "Ver repo").
2. **Detalle de proyecto:** nombre, stack detectado, última actualización, descripción generada por el modelo PyTorch, botón "Ver en GitHub".
3. **Tendencia de actividad:** gráfica de barras de commits por semana (últimos 2 meses), lenguaje principal reciente y racha actual.
4. **Configuración:** topic a excluir, activar descripciones con IA (PyTorch), mostrar gráfica de actividad, método de actualización.

## 7. Modelo de datos (PostgreSQL)

- **Tabla `usuario`:** `id_usuario` (PK), `nombre`, `github_username`, `correo`.
- **Tabla `repositorio`:** `id_repositorio` (PK), `id_usuario` (FK -> `usuario`), `nombre`, `nombre_completo`, `descripcion_original`, `descripcion_generada`, `origen_descripcion`, `puntaje_ia`, `lenguajes` (JSONB), `topics` (JSONB), `visible`, `url`, `estrellas`, `fecha_ultimo_commit`, `es_fork`, `readme_consultado`.
- **Tabla `actividad_commit`:** `id_actividad` (PK), `id_repositorio` (FK -> `repositorio`), `fecha`, `cantidad_commits`, `lenguaje_principal`.

**Relaciones:** un `Usuario` posee muchos `Repositorio` (`1:N`); un `Repositorio` registra muchos `ActividadCommit` (`1:N`).

## 9. Notas técnicas sobre GitHub y repositorios confirmados

- Cuenta principal: `GET /users/AssuredPigeon/repos` (**solo lectura**).
- Repositorios colaborativos externos confirmados (públicos, solo lectura):
  - **DanceLabo:** `labtechmovilfcitec-hash/DanceLabo`
  - **SDGKU:** `Garethsito/SDKGU-Subject-Sistem`
  - *(Vialix es `AssuredPigeon/ASPHALT` y `musicbot` es `AssuredPigeon/musicbot`, ya dentro de `AssuredPigeon`).*
- Lenguajes: `GET /repos/{dueño}/{repo}/languages`.
- README: `GET /repos/{dueño}/{repo}/readme`.
- Commits por semana: `GET /repos/{dueño}/{repo}/stats/commit_activity` (manejar HTTP `202` con reintento y respaldo a `/commits?since=...`).
- **Restricción clave del autor:** NO modificar ningún repositorio existente del autor.

## 11. Decisiones tecnológicas definitivas

- [x] **Frontend:** HTML5 + CSS3 + JavaScript moderno (ES Modules) + Chart.js.
- [x] **Backend:** Python 3.11 + **FastAPI** + Uvicorn + HTTPX + SQLAlchemy 2.0.
- [x] **Base de datos SQL:** **PostgreSQL** (local o gratuito en Supabase / Neon mediante `DATABASE_URL` con `psycopg` v3; script DDL en `database/schema.sql` y fallback SQLite local automático si aún no se define `DATABASE_URL` en desarrollo).
- [x] **Modelo de Lenguaje / IA (Actividad F):** **Full PyTorch (`torch.nn`)** — red neuronal propia (`Embedding` + `BiLSTM` bidireccional + `Self-Attention` + fusión de metadatos + cabeza multitarea de saliencia de oraciones y clasificación de proyecto) entrenada desde cero con `Dataset` y `DataLoader` sobre corpus bilingüe de READMEs, garantizando 0% de invención de datos (Regla 6).
- [x] **Automatización:** Job programado con GitHub Actions (`sync-portfolio.yml`) + endpoint de sincronización controlada.
