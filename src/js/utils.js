/**
 * Utilidades puras del Portafolio Dinámico Auto-actualizable.
 * Diseñadas sin dependencias del DOM para poderse probar unitariamente con node --test.
 */

const MS_POR_DIA = 1000 * 60 * 60 * 24;

/**
 * Formatea una fecha ISO en un indicador legible tipo "Actualizado hace X días" (RF5).
 * @param {string} isoDate Fecha ISO del último commit (pushed_at).
 * @param {Date} [now=new Date()] Fecha de referencia actual.
 * @returns {string}
 */
export function formatearTiempoRelativo(isoDate, now = new Date(), idioma = 'es') {
  const en = idioma === 'en';
  if (!isoDate) return en ? 'No update date' : 'Sin fecha de actualización';
  const fecha = new Date(isoDate);
  if (Number.isNaN(fecha.getTime())) return en ? 'Date unavailable' : 'Fecha no disponible';

  const diffMs = Math.max(0, now.getTime() - fecha.getTime());
  const dias = Math.floor(diffMs / MS_POR_DIA);

  if (dias === 0) return en ? 'Updated today' : 'Actualizado hoy';
  if (dias === 1) return en ? 'Updated 1 day ago' : 'Actualizado hace 1 día';
  if (dias < 7) return en ? `Updated ${dias} days ago` : `Actualizado hace ${dias} días`;

  const semanas = Math.floor(dias / 7);
  if (dias < 30) {
    if (en) return semanas === 1 ? 'Updated 1 week ago' : `Updated ${semanas} weeks ago`;
    return semanas === 1
      ? 'Actualizado hace 1 semana'
      : `Actualizado hace ${semanas} semanas`;
  }

  const meses = Math.floor(dias / 30);
  if (dias < 365) {
    if (en) return meses === 1 ? 'Updated 1 month ago' : `Updated ${meses} months ago`;
    return meses === 1
      ? 'Actualizado hace 1 mes'
      : `Actualizado hace ${meses} meses`;
  }

  const anios = Math.floor(dias / 365);
  if (en) return anios === 1 ? 'Updated 1 year ago' : `Updated ${anios} years ago`;
  return anios === 1
    ? 'Actualizado hace 1 año'
    : `Actualizado hace ${anios} años`;
}

/**
 * Formatea una fecha ISO a formato corto localizado (ej. "2 nov 2026" o "Nov 2, 2026").
 * @param {string} isoDate
 * @param {string} [idioma='es']
 * @returns {string}
 */
export function formatearFechaCorta(isoDate, idioma = 'es') {
  if (!isoDate) return idioma === 'en' ? 'N/A' : 'N/D';
  const fecha = new Date(isoDate);
  if (Number.isNaN(fecha.getTime())) return idioma === 'en' ? 'N/A' : 'N/D';
  return fecha.toLocaleDateString(idioma === 'en' ? 'en-US' : 'es-MX', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC'
  });
}

/**
 * Ordena repositorios del más reciente al más antiguo por fecha_ultimo_commit (RF6).
 * @param {Array<Object>} repositorios
 * @returns {Array<Object>} Copia ordenada.
 */
export function ordenarPorActividad(repositorios = []) {
  return [...repositorios].sort((a, b) => {
    const tA = new Date(a.fecha_ultimo_commit || 0).getTime();
    const tB = new Date(b.fecha_ultimo_commit || 0).getTime();
    return tB - tA;
  });
}

/**
 * Filtra repositorios visibles aplicando el campo visible y reglas adicionales de topics/exclusión (RF3).
 * @param {Array<Object>} repositorios
 * @param {Object} [sincronizacionConfig={}]
 * @returns {Array<Object>}
 */
export function filtrarRepositoriosVisibles(repositorios = [], sincronizacionConfig = {}) {
  const excludedTopics = new Set(
    (sincronizacionConfig.excluded_topics || []).map(t => String(t).trim().toLowerCase()).filter(Boolean)
  );
  const excludedRepos = new Set(
    (sincronizacionConfig.excluded_repos || []).map(r => String(r).trim().toLowerCase()).filter(Boolean)
  );

  return ordenarPorActividad(
    repositorios.filter(repo => {
      if (repo.visible === false) return false;
      if (sincronizacionConfig.exclude_forks && repo.es_fork) return false;
      if (repo.nombre_completo && excludedRepos.has(repo.nombre_completo.toLowerCase())) {
        return false;
      }
      const topics = Array.isArray(repo.topics) ? repo.topics : [];
      if (topics.some(t => excludedTopics.has(String(t).toLowerCase()))) {
        return false;
      }
      return true;
    })
  );
}

function normalizarTextoBusqueda(texto) {
  return String(texto || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();
}

/**
 * Busca y filtra repositorios visibles por texto libre, lenguaje y framework (Pantalla 1).
 * @param {Array<Object>} reposVisibles
 * @param {{ busqueda?: string, lenguaje?: string, framework?: string }} [filtros={}]
 * @returns {Array<Object>}
 */
export function buscarYFiltrarProyectos(reposVisibles = [], filtros = {}) {
  const q = normalizarTextoBusqueda(filtros.busqueda);
  const langTarget = String(filtros.lenguaje || '').trim().toLowerCase();
  const fwTarget = String(filtros.framework || '').trim().toLowerCase();

  return reposVisibles.filter(repo => {
    const langs = Array.isArray(repo.lenguajes) ? repo.lenguajes : [];
    if (langTarget && !langs.some(l => String(l).trim().toLowerCase() === langTarget)) {
      return false;
    }

    const det = repo.detalle_tecnico || {};
    const frameworks = Array.isArray(det.frameworks) ? det.frameworks : [];
    if (fwTarget && !frameworks.some(fw => String(fw).trim().toLowerCase() === fwTarget)) {
      return false;
    }

    if (!q) return true;

    const campos = [
      repo.nombre,
      repo.nombre_completo,
      repo.descripcion_original,
      repo.descripcion_generada,
      det.resumen_es,
      det.resumen_en,
      det.arquitectura_es,
      det.arquitectura_en,
      ...langs,
      ...(Array.isArray(repo.topics) ? repo.topics : []),
      ...frameworks,
      ...(Array.isArray(det.modelos_datos) ? det.modelos_datos : []),
      ...(Array.isArray(det.modulos_detectados) ? det.modulos_detectados : []),
      ...(Array.isArray(det.rutas_detectadas) ? det.rutas_detectadas : []),
      ...(Array.isArray(det.puntos_clave_es) ? det.puntos_clave_es : []),
      ...(Array.isArray(det.puntos_clave_en) ? det.puntos_clave_en : [])
    ];
    return normalizarTextoBusqueda(campos.join(' ')).includes(q);
  });
}

export function obtenerEtiquetaIdiomaRepo(repo, idiomaUI = 'es') {
  const en = idiomaUI === 'en';
  const raw = repo?.detalle_tecnico?.idioma_original || '';

  if (raw === 'en') {
    return {
      badgeCorto: 'Repo: EN',
      etiquetaLarga: en ? 'Original repo language: English (EN)' : 'Idioma original del repo: Inglés (EN)',
      tooltip: en
        ? 'README originally written in English on GitHub'
        : 'README escrito originalmente en inglés en GitHub',
      clase: 'repo-lang-en'
    };
  }
  if (raw === 'es') {
    return {
      badgeCorto: 'Repo: ES',
      etiquetaLarga: en ? 'Original repo language: Spanish (ES)' : 'Idioma original del repo: Español (ES)',
      tooltip: en
        ? 'README originally written in Spanish on GitHub'
        : 'README escrito originalmente en español en GitHub',
      clase: 'repo-lang-es'
    };
  }
  if (raw === 'vacio') {
    return {
      badgeCorto: en ? 'Empty' : 'Vacío',
      etiquetaLarga: en ? 'No source files published yet' : 'Sin archivos publicados aún',
      tooltip: en
        ? 'Repository initialized without source files on its default branch'
        : 'Repositorio inicializado sin archivos en su rama principal',
      clase: 'repo-lang-code'
    };
  }
  return {
    badgeCorto: en ? 'Code' : 'Código',
    etiquetaLarga: en ? 'Analyzed from source code' : 'Analizado desde código fuente',
    tooltip: en
      ? 'No descriptive README; extracted from manifests, models, and code modules'
      : 'Sin README descriptivo; extraído de manifiestos, modelos y módulos del código',
    clase: 'repo-lang-code'
  };
}

/**
 * Devuelve la descripción y puntos clave bilingües respetando la Regla 6 (no inventar información).
 * @param {Object} repo Entidad Repositorio.
 * @param {boolean} [usarIA=true] Si está activa la opción de mostrar descripciones enriquecidas.
 * @param {string} [idiomaUI='es'] Idioma seleccionado en la interfaz ('es' | 'en').
 * @returns {{ texto: string, puntosClave: string[], etiquetaOrigen: string }}
 */
export function obtenerDescripcionRepositorio(repo, usarIA = true, idiomaUI = 'es') {
  const en = idiomaUI === 'en';
  const det = repo?.detalle_tecnico || {};
  const resumenBilingue = en
    ? (det.resumen_en || det.resumen_es || repo.descripcion_generada)
    : (det.resumen_es || repo.descripcion_generada || det.resumen_en);
  const puntosBilingues = en
    ? (Array.isArray(det.puntos_clave_en) && det.puntos_clave_en.length > 0 ? det.puntos_clave_en : (det.puntos_clave_es || []))
    : (Array.isArray(det.puntos_clave_es) && det.puntos_clave_es.length > 0 ? det.puntos_clave_es : (det.puntos_clave_en || []));

  if (usarIA && resumenBilingue && String(resumenBilingue).trim() !== '') {
    const pctNum = repo.puntaje_ia ? Math.round(repo.puntaje_ia * 100) : 0;
    let origen;
    if (repo.origen_descripcion === 'pytorch-bilstm') {
      const pctTxt = pctNum > 0 ? (en ? ` (${pctNum}% relevance)` : ` (${pctNum}% relevancia)`) : '';
      origen = en ? `PyTorch Model on README${pctTxt}` : `Modelo PyTorch sobre README${pctTxt}`;
    } else if (repo.origen_descripcion === 'codigo-fuente') {
      origen = en ? 'Deep source code inspector' : 'Inspector profundo de código';
    } else {
      origen = en ? 'Automated repo synthesis' : 'Síntesis automática del repo';
    }
    return {
      texto: String(resumenBilingue).trim(),
      puntosClave: puntosBilingues,
      etiquetaOrigen: origen
    };
  }

  if (repo.descripcion_original && repo.descripcion_original.trim() !== '') {
    return {
      texto: repo.descripcion_original.trim(),
      puntosClave: usarIA ? puntosBilingues : [],
      etiquetaOrigen: en ? 'GitHub description' : 'Descripción de GitHub'
    };
  }

  const stackList = Array.isArray(repo.lenguajes) && repo.lenguajes.length > 0
    ? repo.lenguajes.slice(0, 3).join(', ')
    : null;

  if (en) {
    const stackEn = stackList ? `built with ${stackList}` : 'hosted on GitHub';
    return {
      texto: `Repository ${stackEn}. No manual description registered on GitHub.`,
      puntosClave: [],
      etiquetaOrigen: 'Repository metadata'
    };
  }

  const stackEs = stackList ? `desarrollado con ${stackList}` : 'público en GitHub';
  return {
    texto: `Repositorio ${stackEs}. Sin descripción manual registrada en GitHub.`,
    puntosClave: [],
    etiquetaOrigen: 'Metadatos del repositorio'
  };
}

/**
 * Obtiene el inicio de la semana (lunes 00:00:00 UTC) para una fecha dada.
 * @param {Date} date
 * @returns {Date}
 */
function obtenerInicioSemanaUTC(date) {
  const d = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
  const day = d.getUTCDay(); // 0 domingo ... 6 sábado
  const diffToMonday = day === 0 ? -6 : 1 - day;
  d.setUTCDate(d.getUTCDate() + diffToMonday);
  return d;
}

/**
 * Convierte un objeto Date a cadena YYYY-MM-DD en UTC.
 * @param {Date} date
 * @returns {string}
 */
export function toISODateUTC(date) {
  return date.toISOString().slice(0, 10);
}

/**
 * Calcula las métricas de la Pantalla 3 (Tendencia de Actividad - RF7):
 * - Serie de commits por semana en los últimos 2 meses (~9 semanas)
 * - Lenguaje principal reciente
 * - Racha actual de días consecutivos con actividad (y racha máxima en la ventana)
 *
 * @param {Array<Object>} actividadCommits Registros de la entidad ActividadCommit.
 * @param {Array<Object>} repositorios Registros de la entidad Repositorio.
 * @param {Date} [now=new Date()] Fecha actual de referencia.
 * @param {number} [semanas=9] Cantidad de semanas a graficar (~2 meses).
 */
export function calcularTendenciaActividad(
  actividadCommits = [],
  repositorios = [],
  now = new Date(),
  semanas = 9
) {
  const inicioSemanaActual = obtenerInicioSemanaUTC(now);
  const buckets = [];
  const bucketMap = new Map();
  const bucketReposMap = new Map();

  for (let i = semanas - 1; i >= 0; i--) {
    const start = new Date(inicioSemanaActual.getTime() - i * 7 * MS_POR_DIA);
    const key = toISODateUTC(start);
    const etiqueta = start.toLocaleDateString('es-MX', {
      day: '2-digit',
      month: 'short',
      timeZone: 'UTC'
    });
    const bucket = { semanaInicio: key, etiqueta, commits: 0, desglose: [] };
    buckets.push(bucket);
    bucketMap.set(key, bucket);
    bucketReposMap.set(key, new Map());
  }

  const fechaMinima = buckets[0]?.semanaInicio || '1970-01-01';
  const conteoPorLenguaje = new Map();
  const commitsPorDia = new Map();
  let totalCommitsPeriodo = 0;

  // Mapa auxiliar de repos visibles para ignorar actividad de repos ocultos si existen
  const reposVisiblesIds = new Set(
    repositorios.filter(r => r.visible !== false).map(r => r.id_repositorio)
  );
  const nombresRepo = new Map(
    repositorios.map(r => [r.id_repositorio, r.nombre || r.nombre_completo || `Repo #${r.id_repositorio}`])
  );

  for (const reg of actividadCommits) {
    if (reposVisiblesIds.size > 0 && !reposVisiblesIds.has(reg.id_repositorio)) {
      continue;
    }
    const cant = Number(reg.cantidad_commits) || 0;
    if (cant <= 0 || !reg.fecha) continue;

    const fechaObj = new Date(`${reg.fecha.slice(0, 10)}T00:00:00Z`);
    if (Number.isNaN(fechaObj.getTime())) continue;

    const diaKey = toISODateUTC(fechaObj);
    commitsPorDia.set(diaKey, (commitsPorDia.get(diaKey) || 0) + cant);

    const semanaKey = toISODateUTC(obtenerInicioSemanaUTC(fechaObj));
    if (semanaKey >= fechaMinima && bucketMap.has(semanaKey)) {
      bucketMap.get(semanaKey).commits += cant;
      const repoNombre = nombresRepo.get(reg.id_repositorio) || `Repo #${reg.id_repositorio}`;
      const repoMapSem = bucketReposMap.get(semanaKey);
      repoMapSem.set(repoNombre, (repoMapSem.get(repoNombre) || 0) + cant);
      totalCommitsPeriodo += cant;

      const lang = reg.lenguaje_principal && reg.lenguaje_principal !== 'N/A'
        ? reg.lenguaje_principal
        : null;
      if (lang) {
        conteoPorLenguaje.set(lang, (conteoPorLenguaje.get(lang) || 0) + cant);
      }
    }
  }

  for (const [semanaKey, bucket] of bucketMap.entries()) {
    const repoMapSem = bucketReposMap.get(semanaKey);
    bucket.desglose = Array.from(repoMapSem.entries())
      .sort((a, b) => (b[1] - a[1]) || a[0].localeCompare(b[0]))
      .map(([nombre, commits]) => ({ nombre, commits }));
  }

  // Determinar lenguaje principal reciente (por commits recientes; fallback al repo visible más reciente)
  let lenguajePrincipalReciente = 'Sin detectar';
  if (conteoPorLenguaje.size > 0) {
    lenguajePrincipalReciente = Array.from(conteoPorLenguaje.entries())
      .sort((a, b) => b[1] - a[1])[0][0];
  } else {
    const visiblesOrdenados = ordenarPorActividad(repositorios.filter(r => r.visible !== false));
    const conLenguaje = visiblesOrdenados.find(r => Array.isArray(r.lenguajes) && r.lenguajes.length > 0);
    if (conLenguaje) {
      lenguajePrincipalReciente = conLenguaje.lenguajes[0];
    }
  }

  // Calcular racha actual de días consecutivos con actividad (admite hoy o desde ayer si hoy aún no se hace commit)
  const hoyUTC = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const ayerUTC = new Date(hoyUTC.getTime() - MS_POR_DIA);

  let cursor = null;
  if (commitsPorDia.has(toISODateUTC(hoyUTC))) {
    cursor = hoyUTC;
  } else if (commitsPorDia.has(toISODateUTC(ayerUTC))) {
    cursor = ayerUTC;
  }

  let rachaActualDias = 0;
  while (cursor && commitsPorDia.has(toISODateUTC(cursor))) {
    rachaActualDias++;
    cursor = new Date(cursor.getTime() - MS_POR_DIA);
  }

  // Calcular también la mejor racha dentro de los últimos 2 meses como dato complementario útil
  const diasOrdenados = Array.from(commitsPorDia.keys())
    .filter(d => d >= fechaMinima)
    .sort();

  let mejorRachaReciente = 0;
  let rachaTemp = 0;
  let prevDateMs = null;

  for (const diaStr of diasOrdenados) {
    const ms = new Date(`${diaStr}T00:00:00Z`).getTime();
    if (prevDateMs !== null && Math.round((ms - prevDateMs) / MS_POR_DIA) === 1) {
      rachaTemp++;
    } else {
      rachaTemp = 1;
    }
    if (rachaTemp > mejorRachaReciente) {
      mejorRachaReciente = rachaTemp;
    }
    prevDateMs = ms;
  }

  return {
    semanas: buckets,
    totalCommitsPeriodo,
    lenguajePrincipalReciente,
    rachaActualDias,
    mejorRachaReciente,
    diasActivosPeriodo: diasOrdenados.length
  };
}
