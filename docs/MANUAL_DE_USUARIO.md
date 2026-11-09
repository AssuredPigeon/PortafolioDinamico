# Manual de Usuario — Portafolio Dinámico Auto-actualizable

## 1. Propósito del sistema

El **Portafolio Dinámico Auto-actualizable** es una aplicación web que conecta tu cuenta de GitHub (y repositorios colaborativos adicionales), almacena tus proyectos en una base de datos relacional SQL, analiza el `README` de cada repositorio mediante una red neuronal propia en **PyTorch** para mostrar descripciones claras sin inventar información, y presenta tanto tus tarjetas de proyecto como tu gráfica de actividad reciente sin editar código HTML manualmente.

---

## 2. Requisitos previos

- **Sistema operativo:** Windows 10/11, macOS o Linux.
- **Python:** versión `3.11` o superior (en Windows se invoca con `py -3.11`).
- **Conexión a internet:** necesaria únicamente al momento de sincronizar con la API de GitHub (el sistema cuenta con respaldo local automático si no hay red).

Instala las dependencias desde la carpeta `portafolioDinamico` si es la primera vez en un equipo nuevo:

```powershell
py -3.11 -m pip install -r requirements.txt
```

---

## 3. Configuración inicial (`.env`)

1. Crea tu archivo `.env` local a partir de la plantilla incluida (el archivo `.env` está protegido en `.gitignore` para que nunca se suba a GitHub):
   ```powershell
   Copy-Item .env.example .env
   ```

### 3.1 Base de datos SQL (Modo Local Autocontenido)

- **Modo local autocontenido (modo oficial de entrega y uso):** deja `DATABASE_URL=` vacío en `.env`. El sistema crea y utiliza automáticamente `data/portfolio_local.db` con las tablas relacionales `usuario`, `repositorio` y `actividad_commit`. No requiere servicios de hosting externos ni servidores de base de datos en la nube.
- **Compatibilidad opcional con PostgreSQL:** si cuentas con una base de datos PostgreSQL local o remota, puedes definir `DATABASE_URL`. El backend detecta y normaliza automáticamente la conexión con `postgresql+psycopg://` y crea las tablas si no existen (también puedes ejecutar manualmente `database/schema.sql`).

### 3.2 Cómo obtener tu `GITHUB_TOKEN` (recomendado)

Sin token, GitHub limita las consultas públicas a **60 peticiones por hora**. Con un token gratuito de solo lectura el límite sube a **5,000 peticiones por hora**.

1. Inicia sesión en GitHub y abre la página de tokens personales de grano fino (*Fine-grained tokens*):  
   https://github.com/settings/personal-access-tokens/new
2. En **Token name**, escribe por ejemplo: `Portafolio-Dinamico-Lectura`.
3. En **Expiration**, elige `90 days` (o la vigencia de tu semestre).
4. En **Repository access**, deja marcada la opción **Public Repositories (read-only)**. No es necesario otorgar ningún permiso de escritura; así garantizas seguridad total sobre tus repositorios.
5. Haz clic en **Generate token** y copia el valor generado (`github_pat_...`).
6. Guárdalo en tu archivo `.env` ejecutando en PowerShell dentro de `portafolioDinamico` (lo que escribas permanecerá oculto en pantalla):
   ```powershell
   $sec = Read-Host "Ingresa tu GITHUB_TOKEN (escritura oculta)" -AsSecureString
   $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
   $val = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
   Add-Content -Path ".env" -Value "`nGITHUB_TOKEN=$val"
   Write-Host "GITHUB_TOKEN guardado en .env correctamente."
   ```

---

## 4. Cómo iniciar el portafolio

Opción A — **Script rápido en Windows PowerShell:**

```powershell
.\run_local.ps1
```

Opción B — **Comandos manuales:**

```powershell
# 1. Sincronizar proyectos desde GitHub hacia SQL (opcional si ya tienes datos locales)
py -3.11 -m backend.sync_service

# 2. Iniciar el servidor web FastAPI
py -3.11 -m uvicorn backend.main:app --reload --port 8000
```

Abre tu navegador en: **http://localhost:8000**

---

## 5. Guía de pantallas

### Pantalla 1: Portafolio Público y Selector Bilingüe (`ES | EN`)
- En la barra superior derecha dispones del conmutador instantáneo **`ES | EN`**, que cambia todos los textos de la interfaz, fechas relativas, gráficas, resúmenes y puntos clave entre español e inglés sin recargar la página.
- Presenta la **cuadrícula responsiva de tarjetas** ordenada automáticamente desde el proyecto con actividad más reciente hasta el más antiguo (`RF6`).
- Cada tarjeta incluye:
  - Nombre del proyecto, etiqueta de organización colaborativa (si aplica) e **indicador del idioma/fuente original del repositorio** (`Repo: ES`, `Repo: EN`, `Código` o `Vacío`).
  - Descripción enriquecida de hasta 3 líneas (extraída por PyTorch desde el `README` o sintetizada desde los manifiestos y módulos reales del código fuente).
  - **Stack detectado** combinando lenguajes de GitHub y principales *frameworks*/librerías verificadas (`RF4`).
  - Indicador relativo **«Actualizado hace X días»** (`RF5`) y botones **Ver detalle** / **Ver repo ↗**.
- En la barra superior derecha de la cuadrícula dispones de una **barra de búsqueda instantánea** (filtra sin distinguir acentos por nombre, descripción, módulos o modelos de datos), además de los selectores para **filtrar proyectos por lenguaje** y **filtrar por framework o herramienta** (por ejemplo `.NET MAUI`, `FastAPI`, `Unity`, `Laravel`).
- También puedes compartir o previsualizar temporalmente cualquier cuenta pública sin modificar la configuración del sitio agregando `?user=NombreUsuario` a la URL (por ejemplo: `http://localhost:8000/?user=AssuredPigeon`); la interfaz mostrará un banner de **Vista previa de solo lectura** con enlace para volver al portafolio principal.

### Pantalla 2: Detalle Profundo de Proyecto
- Se abre al hacer clic en **Ver detalle** sobre cualquier tarjeta.
- Presenta una ficha técnica completa con:
  - Clasificación de arquitectura, ruta `dueño/repositorio`, fecha relativa y exacta del último push, **idioma original del repositorio**, número de colaboradores (proyecto individual vs en equipo), conteo limpio de archivos fuente y estrellas.
  - **Descripción completa** con etiqueta de origen (`Modelo PyTorch sobre README`, `Inspector profundo de código` o `Descripción de GitHub`).
  - Lista de **Puntos clave y arquitectura** (3 a 5 viñetas técnicas extraídas del `README` o de la estructura verificada del repositorio).
  - **Barra proporcional de lenguajes** con porcentajes exactos por bytes de código.
  - **Frameworks, librerías y herramientas** verificadas en manifiestos (`package.json`, `requirements.txt`, `composer.json`, `schema.prisma`, etc.).
  - **Módulos, rutas HTTP y modelos de datos** detectados en el árbol de código, *topics* de GitHub y enlace a **Demo en vivo ↗** (cuando el repositorio la declara) además de **Ver en GitHub ↗**.

### Pantalla 3: Tendencia de Actividad
- Ubicada encima de la cuadrícula cuando la opción correspondiente está activa (`RF7`).
- Presenta tres indicadores resumen de los últimos 2 meses:
  1. **Lenguaje principal reciente** (ponderado por volumen de commits recientes).
  2. **Racha actual** de días consecutivos con actividad (y mejor racha reciente).
  3. **Total de commits y días activos** en el periodo.
- Debajo renderiza una **gráfica de barras semanal** con Chart.js (y cuenta con modo gráfico HTML de respaldo en caso de abrirse sin conexión al CDN). Al pasar el cursor sobre cualquier barra semanal, el *tooltip* muestra el **desglose exacto de commits por repositorio** de esa semana.

### Pantalla 4: Panel de Configuración y Cambio Dinámico de Usuario
- Se abre desde el botón **Configuración** en el encabezado superior.
- Permite ajustar sin tocar archivos de código:
  - **Cuenta de GitHub activa:** permite escribir cualquier usuario u organización pública de GitHub (`@username`) para generar su portafolio en vivo. El sistema guarda automáticamente cada perfil usado (con botones de **Cambio rápido**, por ejemplo `@AssuredPigeon`) para alternar entre cuentas al instante conservando sus repositorios cacheados en SQL.
  - **Topics excluidos (`RF3`):** por ejemplo `practica, tutorial, oculto`. Cualquier repositorio en GitHub con alguno de esos topics se oculta de inmediato.
  - **Repositorios colaborativos extra:** lista `dueño/repositorio` de proyectos en equipo donde participas como colaborador.
  - **Repositorios excluidos por nombre:** lista `dueño/repositorio` para ocultar repositorios específicos (como el `README` de perfil).
  - **Módulos activos:** activar/desactivar descripciones con IA PyTorch, mostrar/ocultar la gráfica de tendencia de actividad y ocultar forks automáticamente.
  - **Método de actualización automática (`RF8`):** elegir entre actualización al visitar la página (con enfriamiento de 15 minutos) o actualización nocturna mediante **GitHub Actions**.
  - **Clave de administración (`PORTFOLIO_ADMIN_KEY`, opcional):** cuando el portafolio se despliega en línea con la variable de entorno `PORTFOLIO_ADMIN_KEY` configurada, el formulario muestra automáticamente el campo de contraseña **Clave de administración (`X-Admin-Key`)** para que solo el propietario pueda guardar cambios permanentes.
- Incluye el botón **Sincronizar con GitHub** (fuerza una consulta en vivo a GitHub desde el navegador para la cuenta activa) y **Guardar cambios** para persistir la configuración o cambiar de perfil.

---

## 6. Solución de problemas frecuentes

| Situación | Causa probable | Solución |
|---|---|---|
| Aparece aviso de límite de peticiones (*rate limit*) | Se alcanzó el tope de 60 req/h sin autenticar en GitHub | Configura `GITHUB_TOKEN` en `.env` (sección 3.2). Mientras tanto, el portafolio sigue funcionando con los datos respaldados en SQL. |
| Agregué un repositorio colaborativo nuevo en Configuración y aún no aparece | Guardar configuración recalcula los repos ya almacenados sin gastar cuota de red | Haz clic en el botón **Sincronizar con GitHub** dentro del mismo modal de Configuración. |
| El puerto `8000` está ocupado | Otra instancia de Uvicorn u otro servicio local usa ese puerto | Ejecuta `py -3.11 -m uvicorn backend.main:app --port 8080` y abre `http://localhost:8080`. |

