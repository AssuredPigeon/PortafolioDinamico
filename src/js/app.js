import {
  formatearTiempoRelativo,
  formatearFechaCorta,
  filtrarRepositoriosVisibles,
  buscarYFiltrarProyectos,
  obtenerDescripcionRepositorio,
  obtenerEtiquetaIdiomaRepo,
  calcularTendenciaActividad
} from './utils.js?v=7';

const COLORES_LENGUAJE = {
  Python: '#3572A5',
  TypeScript: '#3178c6',
  JavaScript: '#f1e05a',
  'C#': '#178600',
  HTML: '#e34c26',
  CSS: '#563d7c',
  PHP: '#4F5D95',
  Blade: '#f7523f',
  Shell: '#89e051',
  Dockerfile: '#384d54',
  Java: '#b07219',
  C: '#555555',
  'C++': '#f34b7d',
  ShaderLab: '#222c37',
  HLSL: '#aace60',
  Kotlin: '#A97BFF',
  Swift: '#F05138',
  Go: '#00ADD8',
  Rust: '#dea584',
  Vue: '#41b883',
  Dart: '#00B4AB',
  'Jupyter Notebook': '#DA5B0B'
};

const TEXTOS_UI = {
  es: {
    eyebrow: 'Portafolio Dinámico Auto-actualizable',
    configBtn: 'Configuración',
    loadingSync: 'Cargando repositorios...',
    syncSubDefault: 'Sincronización con GitHub',
    syncedProjectsCount: n => `${n} proyectos sincronizados`,
    pytorchActive: 'PyTorch + Inspector activos',
    activityTitle: 'Tendencia de actividad',
    activitySubtitle: 'Commits por semana (últimos 2 meses)',
    topLanguageLabel: 'Lenguaje principal reciente',
    streakLabel: 'Racha actual',
    totalCommitsLabel: 'Commits (últimos 2 meses)',
    undetectedLang: 'Sin detectar',
    streakOneDay: '1 día consecutivo con actividad',
    streakManyDays: n => `${n} días consecutivos con actividad`,
    streakZeroWithBest: best => `0 hoy (mejor reciente: ${best} d)`,
    activeDaysSuffix: (total, dias) => `${total} (${dias} días activos)`,
    weekPrefix: 'Sem',
    chartDatasetLabel: 'Commits en la semana',
    tooltipByRepoHeader: 'Por repositorio:',
    tooltipMoreRepos: n => `+${n} repositorios más`,
    projectsTitle: 'Proyectos sincronizados',
    projectsSubtitle: 'Ordenados automáticamente por actividad reciente en GitHub',
    searchProjectsLabel: 'Buscar proyectos por nombre, descripción o tecnología',
    searchProjectsPlaceholder: 'Buscar proyecto, tecnología o módulo...',
    filterByLangLabel: 'Filtrar por lenguaje',
    allLanguagesOption: 'Todos los lenguajes',
    filterByFrameworkLabel: 'Filtrar por framework o herramienta',
    allFrameworksOption: 'Todos los frameworks',
    emptyState: 'No se encontraron proyectos visibles con el filtro seleccionado.',
    noLanguageDetected: 'Sin lenguaje detectado',
    collabTooltip: owner => `Repositorio colaborativo en ${owner}`,
    viewDetailBtn: 'Ver detalle',
    viewRepoBtn: 'Ver repo ↗',
    modalCloseAria: 'Cerrar detalle',
    modalDescHeading: 'Descripción del proyecto',
    modalHighlightsHeading: 'Puntos clave y arquitectura',
    modalLanguagesHeading: 'Distribución de lenguajes',
    modalFrameworksHeading: 'Frameworks, librerías y herramientas',
    modalEntitiesHeading: 'Módulos, rutas y entidades detectadas en código',
    modalTopicsHeading: 'Topics en GitHub',
    modalCloseBtn: 'Cerrar',
    modalLiveDemoBtn: 'Demo en vivo ↗',
    modalGithubBtn: 'Ver en GitHub ↗',
    noGithubLanguages: 'No se detectaron lenguajes de programación en este repositorio.',
    teamBadge: n => `En equipo · ${n} colaboradores`,
    soloBadge: 'Proyecto individual',
    sourceFilesBadge: n => `${n} archivos fuente`,
    starsBadge: n => `★ ${n} ${n === 1 ? 'estrella' : 'estrellas'}`,
    entityModelPrefix: 'Modelo',
    entityRoutePrefix: 'Ruta',
    cfgEyebrow: 'Preferencias de sincronización y vista',
    cfgTitle: 'Configuración del portafolio',
    cfgAccountLegend: 'Cuenta de GitHub activa',
    cfgUsernameLabel: 'Usuario u organización en GitHub:',
    cfgUsernameHint: 'Cambia este usuario para generar automáticamente el portafolio de cualquier cuenta pública de GitHub.',
    cfgDisplayNameLabel: 'Nombre a mostrar (opcional):',
    cfgDisplayNamePlaceholder: 'Automático desde GitHub',
    cfgEmailLabel: 'Correo de contacto (opcional):',
    cfgEmailPlaceholder: 'Opcional',
    cfgSavedProfilesLabel: 'Cambio rápido:',
    cfgTopicsLabel: 'Excluir repos con el topic (separados por coma):',
    cfgTopicsHint: 'Los repositorios en GitHub que tengan cualquiera de estos topics se ocultarán del portafolio.',
    cfgExtraLabel: 'Repositorios colaborativos extra (dueño/repo):',
    cfgExcludedLabel: 'Excluir repositorios por nombre (dueño/repo):',
    cfgModulesLegend: 'Módulos activos',
    cfgUseAiLabel: 'Generar descripciones enriquecidas (PyTorch + Inspector de código)',
    cfgShowChartLabel: 'Mostrar gráfica de tendencia de actividad',
    cfgExcludeForksLabel: 'Ocultar repositorios fork automáticamente',
    cfgMethodLegend: 'Método de actualización automática (RF8)',
    cfgMethodClientLabel: 'Actualizar al visitar la página (consulta automática con enfriamiento)',
    cfgMethodActionsLabel: 'Actualizar cada noche con job programado (GitHub Actions)',
    cfgAdminKeyLabel: 'Clave de administración (X-Admin-Key):',
    cfgAdminKeyPlaceholder: 'Ingresa PORTFOLIO_ADMIN_KEY para guardar cambios',
    cfgAdminKeyHint: 'Requerida cuando el servidor público protege la configuración.',
    cfgSyncNowBtn: 'Sincronizar con GitHub',
    cfgSyncingBtn: 'Sincronizando...',
    cfgSwitchingUserBtn: 'Sincronizando usuario...',
    cfgSwitchingUserProgress: user => `Analizando repositorios públicos de @${user} en paralelo (aprox. 5–10 s la primera vez)...`,
    cfgCancelBtn: 'Cancelar',
    cfgSaveBtn: 'Guardar cambios',
    cfgSavedOk: n => `Configuración guardada (${n} repositorios visibles).`,
    cfgSwitchedUserOk: (user, n) => `Portafolio cargado para @${user} (${n} repositorios visibles).`,
    cfgSavedFallback: 'Vista actualizada temporalmente (inicia el servidor FastAPI para guardar cambios permanentes).',
    cfgSyncedOk: (n, cuotaTxt) => `Sincronización con GitHub completada (${n} visibles${cuotaTxt}).`,
    cfgQuotaRemaining: q => ` · Cuota API restante: ${q}`,
    cfgSyncConnError: 'No fue posible conectar con el servidor FastAPI para sincronizar en vivo.',
    previewBannerNotice: user => `Vista previa de solo lectura para @${user}. La configuración principal del portafolio no se ha modificado.`,
    previewBannerError: user => `No se pudo abrir la vista previa para @${user}.`,
    previewExitBtn: '← Volver al portafolio principal',
    staticFallbackNotice: 'Servidor FastAPI desconectado; mostrando último respaldo sincronizado.',
    loadErrorPrefix: 'Error al cargar el portafolio',
    loadErrorShort: 'Error de carga',
    footerText: 'Portafolio Dinámico Auto-actualizable · FastAPI + PostgreSQL + PyTorch + GitHub REST API'
  },
  en: {
    eyebrow: 'Self-Updating Dynamic Portfolio',
    configBtn: 'Settings',
    loadingSync: 'Loading repositories...',
    syncSubDefault: 'GitHub Synchronization',
    syncedProjectsCount: n => `${n} synced projects`,
    pytorchActive: 'PyTorch + Code Inspector',
    activityTitle: 'Activity trend',
    activitySubtitle: 'Weekly commits (last 2 months)',
    topLanguageLabel: 'Recent top language',
    streakLabel: 'Current streak',
    totalCommitsLabel: 'Commits (last 2 months)',
    undetectedLang: 'Undetected',
    streakOneDay: '1 consecutive active day',
    streakManyDays: n => `${n} consecutive active days`,
    streakZeroWithBest: best => `0 today (recent best: ${best} d)`,
    activeDaysSuffix: (total, dias) => `${total} (${dias} active days)`,
    weekPrefix: 'Wk',
    chartDatasetLabel: 'Weekly commits',
    tooltipByRepoHeader: 'By repository:',
    tooltipMoreRepos: n => `+${n} more repositories`,
    projectsTitle: 'Synced projects',
    projectsSubtitle: 'Automatically sorted by recent activity on GitHub',
    searchProjectsLabel: 'Search projects by name, description, or technology',
    searchProjectsPlaceholder: 'Search project, stack, or module...',
    filterByLangLabel: 'Filter by language',
    allLanguagesOption: 'All languages',
    filterByFrameworkLabel: 'Filter by framework or tool',
    allFrameworksOption: 'All frameworks',
    emptyState: 'No visible projects match the selected filter.',
    noLanguageDetected: 'No language detected',
    collabTooltip: owner => `Collaborative repository under ${owner}`,
    viewDetailBtn: 'View details',
    viewRepoBtn: 'View repo ↗',
    modalCloseAria: 'Close details',
    modalDescHeading: 'Project overview',
    modalHighlightsHeading: 'Key highlights & architecture',
    modalLanguagesHeading: 'Language breakdown',
    modalFrameworksHeading: 'Frameworks, libraries & tools',
    modalEntitiesHeading: 'Modules, routes & entities detected in code',
    modalTopicsHeading: 'GitHub topics',
    modalCloseBtn: 'Close',
    modalLiveDemoBtn: 'Live demo ↗',
    modalGithubBtn: 'View on GitHub ↗',
    noGithubLanguages: 'No programming languages detected in this repository.',
    teamBadge: n => `Team · ${n} contributors`,
    soloBadge: 'Solo project',
    sourceFilesBadge: n => `${n} source files`,
    starsBadge: n => `★ ${n} ${n === 1 ? 'star' : 'stars'}`,
    entityModelPrefix: 'Model',
    entityRoutePrefix: 'Route',
    cfgEyebrow: 'Sync & display preferences',
    cfgTitle: 'Portfolio settings',
    cfgAccountLegend: 'Active GitHub account',
    cfgUsernameLabel: 'GitHub user or organization:',
    cfgUsernameHint: 'Change this username to automatically build the portfolio for any public GitHub account.',
    cfgDisplayNameLabel: 'Display name (optional):',
    cfgDisplayNamePlaceholder: 'Auto-detected from GitHub',
    cfgEmailLabel: 'Contact email (optional):',
    cfgEmailPlaceholder: 'Optional',
    cfgSavedProfilesLabel: 'Quick switch:',
    cfgTopicsLabel: 'Exclude repos with topic (comma-separated):',
    cfgTopicsHint: 'GitHub repositories tagged with any of these topics will be hidden from the portfolio.',
    cfgExtraLabel: 'Extra collaborative repositories (owner/repo):',
    cfgExcludedLabel: 'Exclude repositories by full name (owner/repo):',
    cfgModulesLegend: 'Active modules',
    cfgUseAiLabel: 'Generate enriched descriptions (PyTorch + Deep Code Inspector)',
    cfgShowChartLabel: 'Show activity trend chart',
    cfgExcludeForksLabel: 'Automatically hide forked repositories',
    cfgMethodLegend: 'Automatic update method (RF8)',
    cfgMethodClientLabel: 'Update on page visit (automatic fetch with cooldown)',
    cfgMethodActionsLabel: 'Nightly scheduled job (GitHub Actions)',
    cfgAdminKeyLabel: 'Admin key (X-Admin-Key):',
    cfgAdminKeyPlaceholder: 'Enter PORTFOLIO_ADMIN_KEY to save changes',
    cfgAdminKeyHint: 'Required when the public server protects portfolio settings.',
    cfgSyncNowBtn: 'Sync with GitHub',
    cfgSyncingBtn: 'Syncing...',
    cfgSwitchingUserBtn: 'Syncing user...',
    cfgSwitchingUserProgress: user => `Analyzing public repositories for @${user} in parallel (approx. 5–10 s the first time)...`,
    cfgCancelBtn: 'Cancel',
    cfgSaveBtn: 'Save changes',
    cfgSavedOk: n => `Settings saved (${n} visible repositories).`,
    cfgSwitchedUserOk: (user, n) => `Portfolio loaded for @${user} (${n} visible repositories).`,
    cfgSavedFallback: 'View updated temporarily (start the FastAPI server to persist changes).',
    cfgSyncedOk: (n, cuotaTxt) => `GitHub sync completed (${n} visible${cuotaTxt}).`,
    cfgQuotaRemaining: q => ` · Remaining API quota: ${q}`,
    cfgSyncConnError: 'Could not reach the FastAPI server for live synchronization.',
    previewBannerNotice: user => `Read-only preview for @${user}. Main portfolio settings remain unchanged.`,
    previewBannerError: user => `Could not open preview for @${user}.`,
    previewExitBtn: '← Back to main portfolio',
    staticFallbackNotice: 'FastAPI server offline; displaying latest synced backup.',
    loadErrorPrefix: 'Failed to load portfolio',
    loadErrorShort: 'Load error',
    footerText: 'Self-Updating Dynamic Portfolio · FastAPI + PostgreSQL + PyTorch + GitHub REST API'
  }
};

function leerIdiomaInicial() {
  try {
    return localStorage.getItem('portafolio_idioma_ui') === 'en' ? 'en' : 'es';
  } catch {
    return 'es';
  }
}

let estadoGlobal = {
  idiomaUI: leerIdiomaInicial(),
  config: null,
  datos: null,
  tendencia: null,
  reposVisibles: [],
  filtroBusqueda: '',
  filtroLenguaje: '',
  filtroFramework: '',
  modoVistaPrevia: false,
  repoDetalleAbierto: null,
  chartInstance: null
};

function t() {
  return TEXTOS_UI[estadoGlobal.idiomaUI] || TEXTOS_UI.es;
}

function colorLenguaje(lang) {
  return COLORES_LENGUAJE[lang] || '#8b949e';
}

function crearBadgeLenguaje(textoMostrar, claveColor = textoMostrar) {
  const span = document.createElement('span');
  span.className = 'lang-badge';

  const dot = document.createElement('span');
  dot.className = 'lang-dot';
  dot.style.backgroundColor = colorLenguaje(claveColor);

  span.appendChild(dot);
  span.appendChild(document.createTextNode(textoMostrar));
  return span;
}

function crearBadgeFramework(fw) {
  const span = document.createElement('span');
  span.className = 'fw-badge';
  span.textContent = fw;
  return span;
}

function aplicarTextosInterfaz() {
  const txt = t();
  const esEn = estadoGlobal.idiomaUI === 'en';
  document.documentElement.lang = esEn ? 'en' : 'es';

  const btnEs = document.getElementById('lang-es-btn');
  const btnEn = document.getElementById('lang-en-btn');
  btnEs.classList.toggle('active', !esEn);
  btnEs.setAttribute('aria-pressed', String(!esEn));
  btnEn.classList.toggle('active', esEn);
  btnEn.setAttribute('aria-pressed', String(esEn));

  document.getElementById('ui-eyebrow').textContent = txt.eyebrow;
  document.getElementById('open-config-btn').textContent = txt.configBtn;

  document.getElementById('activity-title').textContent = txt.activityTitle;
  document.getElementById('activity-subtitle').textContent = txt.activitySubtitle;
  document.getElementById('label-top-language').textContent = txt.topLanguageLabel;
  document.getElementById('label-streak').textContent = txt.streakLabel;
  document.getElementById('label-total-commits').textContent = txt.totalCommitsLabel;

  document.getElementById('projects-title').textContent = txt.projectsTitle;
  document.getElementById('projects-subtitle').textContent = txt.projectsSubtitle;
  document.getElementById('label-project-search').textContent = txt.searchProjectsLabel;
  const searchInput = document.getElementById('project-search');
  searchInput.setAttribute('placeholder', txt.searchProjectsPlaceholder);
  searchInput.setAttribute('aria-label', txt.searchProjectsLabel);
  document.getElementById('label-language-filter').textContent = txt.filterByLangLabel;
  document.getElementById('language-filter').setAttribute('aria-label', txt.filterByLangLabel);
  document.getElementById('label-framework-filter').textContent = txt.filterByFrameworkLabel;
  document.getElementById('framework-filter').setAttribute('aria-label', txt.filterByFrameworkLabel);
  document.getElementById('empty-state-text').textContent = txt.emptyState;
  document.getElementById('preview-exit-link').textContent = txt.previewExitBtn;

  document.getElementById('modal-close-btn').setAttribute('aria-label', txt.modalCloseAria);
  document.getElementById('modal-label-desc').textContent = txt.modalDescHeading;
  document.getElementById('modal-label-highlights').textContent = txt.modalHighlightsHeading;
  document.getElementById('modal-label-languages').textContent = txt.modalLanguagesHeading;
  document.getElementById('modal-label-frameworks').textContent = txt.modalFrameworksHeading;
  document.getElementById('modal-label-entities').textContent = txt.modalEntitiesHeading;
  document.getElementById('modal-label-topics').textContent = txt.modalTopicsHeading;
  document.getElementById('modal-secondary-close').textContent = txt.modalCloseBtn;
  document.getElementById('modal-demo-btn').textContent = txt.modalLiveDemoBtn;
  document.getElementById('modal-github-btn').textContent = txt.modalGithubBtn;

  document.getElementById('cfg-eyebrow').textContent = txt.cfgEyebrow;
  document.getElementById('config-modal-title').textContent = txt.cfgTitle;
  document.getElementById('lbl-cfg-account').textContent = txt.cfgAccountLegend;
  document.getElementById('lbl-cfg-username').textContent = txt.cfgUsernameLabel;
  document.getElementById('hint-cfg-username').textContent = txt.cfgUsernameHint;
  document.getElementById('lbl-cfg-display-name').textContent = txt.cfgDisplayNameLabel;
  document.getElementById('cfg-user-name').setAttribute('placeholder', txt.cfgDisplayNamePlaceholder);
  document.getElementById('lbl-cfg-email').textContent = txt.cfgEmailLabel;
  document.getElementById('cfg-user-email').setAttribute('placeholder', txt.cfgEmailPlaceholder);
  document.getElementById('lbl-cfg-topics').textContent = txt.cfgTopicsLabel;
  document.getElementById('hint-cfg-topics').textContent = txt.cfgTopicsHint;
  document.getElementById('lbl-cfg-extra').textContent = txt.cfgExtraLabel;
  document.getElementById('lbl-cfg-excluded').textContent = txt.cfgExcludedLabel;
  document.getElementById('lbl-cfg-modules').textContent = txt.cfgModulesLegend;
  document.getElementById('lbl-cfg-ai').textContent = txt.cfgUseAiLabel;
  document.getElementById('lbl-cfg-chart').textContent = txt.cfgShowChartLabel;
  document.getElementById('lbl-cfg-forks').textContent = txt.cfgExcludeForksLabel;
  document.getElementById('lbl-cfg-method').textContent = txt.cfgMethodLegend;
  document.getElementById('lbl-cfg-client').textContent = txt.cfgMethodClientLabel;
  document.getElementById('lbl-cfg-actions').textContent = txt.cfgMethodActionsLabel;
  document.getElementById('lbl-cfg-admin-key').textContent = txt.cfgAdminKeyLabel;
  document.getElementById('cfg-admin-key').setAttribute('placeholder', txt.cfgAdminKeyPlaceholder);
  document.getElementById('hint-cfg-admin-key').textContent = txt.cfgAdminKeyHint;
  document.getElementById('cfg-sync-now-btn').textContent = txt.cfgSyncNowBtn;
  document.getElementById('config-cancel-btn').textContent = txt.cfgCancelBtn;
  document.getElementById('config-save-btn').textContent = txt.cfgSaveBtn;

  document.getElementById('footer-text').textContent = txt.footerText;
}

function renderizarEncabezado(usuario, metadata, origenCarga, totalVisibles) {
  const txt = t();
  if (usuario) {
    const displayName = usuario.nombre || usuario.github_username;
    document.getElementById('user-name').textContent = displayName;
    document.getElementById('user-github').textContent = usuario.github_username;
    document.getElementById('user-github-link').href = `https://github.com/${encodeURIComponent(usuario.github_username)}`;
    document.title = estadoGlobal.idiomaUI === 'en'
      ? `Dynamic Portfolio · ${displayName}`
      : `Portafolio Dinámico · ${displayName}`;

    const emailSep = document.getElementById('user-email-sep');
    const emailLink = document.getElementById('user-email-link');
    const emailSpan = document.getElementById('user-email');
    if (usuario.correo && String(usuario.correo).trim() !== '') {
      emailSpan.textContent = usuario.correo;
      emailLink.href = `mailto:${usuario.correo}`;
      emailLink.hidden = false;
      emailSep.hidden = false;
    } else {
      emailSpan.textContent = '';
      emailLink.hidden = true;
      emailSep.hidden = true;
    }
  }

  const syncText = document.getElementById('sync-status-text');
  const syncSub = document.getElementById('sync-timestamp-text');
  syncText.textContent = txt.syncedProjectsCount(totalVisibles);

  const prefijoBd = estadoGlobal.idiomaUI === 'en' ? 'DB' : 'BD';
  const motor = metadata?.motor_bd ? `${prefijoBd} ${metadata.motor_bd.toUpperCase()}` : (origenCarga || 'SQL');
  if (metadata?.ultima_sincronizacion) {
    syncSub.textContent = `${motor} · PyTorch · ${formatearFechaCorta(metadata.ultima_sincronizacion, estadoGlobal.idiomaUI)}`;
  } else {
    syncSub.textContent = `${motor} · ${txt.pytorchActive}`;
  }
}

function poblarSelectorLenguajes(reposVisibles) {
  const select = document.getElementById('language-filter');
  const txt = t();
  const conteo = new Map();

  for (const repo of reposVisibles) {
    for (const lang of repo.lenguajes || []) {
      conteo.set(lang, (conteo.get(lang) || 0) + 1);
    }
  }

  const ordenados = Array.from(conteo.entries()).sort((a, b) => b[1] - a[1]);
  select.innerHTML = '';

  const defaultOpt = document.createElement('option');
  defaultOpt.value = '';
  defaultOpt.textContent = txt.allLanguagesOption;
  select.appendChild(defaultOpt);

  for (const [lang, count] of ordenados) {
    const opt = document.createElement('option');
    opt.value = lang;
    opt.textContent = `${lang} (${count})`;
    select.appendChild(opt);
  }

  if (estadoGlobal.filtroLenguaje && conteo.has(estadoGlobal.filtroLenguaje)) {
    select.value = estadoGlobal.filtroLenguaje;
  } else {
    estadoGlobal.filtroLenguaje = '';
    select.value = '';
  }
}

function poblarSelectorFrameworks(reposVisibles) {
  const select = document.getElementById('framework-filter');
  const txt = t();
  const conteo = new Map();

  for (const repo of reposVisibles) {
    const frameworks = repo.detalle_tecnico?.frameworks || [];
    for (const fw of frameworks) {
      conteo.set(fw, (conteo.get(fw) || 0) + 1);
    }
  }

  const ordenados = Array.from(conteo.entries()).sort((a, b) => (b[1] - a[1]) || a[0].localeCompare(b[0]));
  select.innerHTML = '';

  const defaultOpt = document.createElement('option');
  defaultOpt.value = '';
  defaultOpt.textContent = txt.allFrameworksOption;
  select.appendChild(defaultOpt);

  for (const [fw, count] of ordenados) {
    const opt = document.createElement('option');
    opt.value = fw;
    opt.textContent = `${fw} (${count})`;
    select.appendChild(opt);
  }

  if (estadoGlobal.filtroFramework && conteo.has(estadoGlobal.filtroFramework)) {
    select.value = estadoGlobal.filtroFramework;
  } else {
    estadoGlobal.filtroFramework = '';
    select.value = '';
  }
}

function renderizarTarjetas() {
  const grid = document.getElementById('projects-grid');
  const emptyState = document.getElementById('empty-state');
  const usarIA = Boolean(estadoGlobal.config?.opciones?.generar_descripciones_ia);
  const idioma = estadoGlobal.idiomaUI;
  const txt = t();
  const mainUser = (estadoGlobal.datos?.usuario?.github_username || '').toLowerCase();

  const lista = buscarYFiltrarProyectos(estadoGlobal.reposVisibles, {
    busqueda: estadoGlobal.filtroBusqueda,
    lenguaje: estadoGlobal.filtroLenguaje,
    framework: estadoGlobal.filtroFramework
  });

  grid.innerHTML = '';

  if (lista.length === 0) {
    emptyState.hidden = false;
    return;
  }
  emptyState.hidden = true;

  for (const repo of lista) {
    const card = document.createElement('article');
    card.className = 'project-card';

    const top = document.createElement('div');
    top.className = 'card-top';

    const titleRow = document.createElement('div');
    titleRow.className = 'card-title-row';

    const h3 = document.createElement('h3');
    h3.className = 'card-title';
    h3.textContent = repo.nombre;
    titleRow.appendChild(h3);

    const badgesGroup = document.createElement('div');
    badgesGroup.className = 'card-badges-group';

    const owner = (repo.nombre_completo || '').split('/')[0];
    if (owner && owner.toLowerCase() !== mainUser) {
      const ownerBadge = document.createElement('span');
      ownerBadge.className = 'owner-badge';
      ownerBadge.title = txt.collabTooltip(owner);
      ownerBadge.textContent = owner;
      badgesGroup.appendChild(ownerBadge);
    }

    const infoIdioma = obtenerEtiquetaIdiomaRepo(repo, idioma);
    const langOriginBadge = document.createElement('span');
    langOriginBadge.className = `repo-lang-badge ${infoIdioma.clase}`;
    langOriginBadge.title = infoIdioma.tooltip;
    langOriginBadge.textContent = infoIdioma.badgeCorto;
    badgesGroup.appendChild(langOriginBadge);

    titleRow.appendChild(badgesGroup);
    top.appendChild(titleRow);

    const { texto: descTexto } = obtenerDescripcionRepositorio(repo, usarIA, idioma);
    const descP = document.createElement('p');
    descP.className = 'card-description';
    descP.textContent = descTexto;
    top.appendChild(descP);

    // Lenguajes principales + principales frameworks detectados (Opción A limpia)
    const stackDiv = document.createElement('div');
    stackDiv.className = 'stack-list';
    const todosLenguajes = Array.isArray(repo.lenguajes) ? repo.lenguajes : [];
    const lenguajesMostrar = todosLenguajes.slice(0, 3);
    const lowerMostrados = new Set(lenguajesMostrar.map(l => l.toLowerCase()));

    const todosFrameworks = Array.isArray(repo.detalle_tecnico?.frameworks)
      ? repo.detalle_tecnico.frameworks.filter(fw => !lowerMostrados.has(String(fw).toLowerCase()))
      : [];
    const frameworksMostrar = todosFrameworks.slice(0, 3);

    if (lenguajesMostrar.length > 0 || frameworksMostrar.length > 0) {
      for (const lang of lenguajesMostrar) {
        stackDiv.appendChild(crearBadgeLenguaje(lang));
      }
      for (const fw of frameworksMostrar) {
        stackDiv.appendChild(crearBadgeFramework(fw));
      }
      const ocultosCount = (todosLenguajes.length - lenguajesMostrar.length) +
        (todosFrameworks.length - frameworksMostrar.length);
      if (ocultosCount > 0) {
        const extra = document.createElement('span');
        extra.className = 'fw-badge';
        extra.textContent = `+${ocultosCount}`;
        stackDiv.appendChild(extra);
      }
    } else {
      const emptyLang = document.createElement('span');
      emptyLang.className = 'lang-badge';
      emptyLang.textContent = txt.noLanguageDetected;
      stackDiv.appendChild(emptyLang);
    }
    top.appendChild(stackDiv);

    const footer = document.createElement('div');
    footer.className = 'card-footer';

    const updatedSpan = document.createElement('span');
    updatedSpan.className = 'updated-text';
    const textoRelativo = formatearTiempoRelativo(repo.fecha_ultimo_commit, new Date(), idioma);
    updatedSpan.textContent = repo.estrellas > 0
      ? `${textoRelativo} · ★ ${repo.estrellas}`
      : textoRelativo;

    const actions = document.createElement('div');
    actions.className = 'card-actions';

    const detailBtn = document.createElement('button');
    detailBtn.type = 'button';
    detailBtn.className = 'btn btn-secondary';
    detailBtn.textContent = txt.viewDetailBtn;
    detailBtn.addEventListener('click', () => abrirDetalleProyecto(repo));

    const repoLink = document.createElement('a');
    repoLink.href = repo.url;
    repoLink.target = '_blank';
    repoLink.rel = 'noopener noreferrer';
    repoLink.className = 'btn btn-primary';
    repoLink.textContent = txt.viewRepoBtn;

    actions.appendChild(detailBtn);
    actions.appendChild(repoLink);

    footer.appendChild(updatedSpan);
    footer.appendChild(actions);

    card.appendChild(top);
    card.appendChild(footer);
    grid.appendChild(card);
  }
}

function poblarContenidoModalDetalle(repo) {
  const usarIA = Boolean(estadoGlobal.config?.opciones?.generar_descripciones_ia);
  const idioma = estadoGlobal.idiomaUI;
  const esEn = idioma === 'en';
  const txt = t();
  const det = repo.detalle_tecnico || {};

  document.getElementById('modal-repo-path').textContent = repo.nombre_completo;
  document.getElementById('modal-title').textContent = repo.nombre;

  const archPill = document.getElementById('modal-arch-pill');
  const archTexto = esEn ? (det.arquitectura_en || det.arquitectura_es) : (det.arquitectura_es || det.arquitectura_en);
  if (archTexto) {
    archPill.textContent = archTexto;
    archPill.hidden = false;
  } else {
    archPill.textContent = '';
    archPill.hidden = true;
  }

  // Fila de píldoras de metadatos verificados
  const rel = formatearTiempoRelativo(repo.fecha_ultimo_commit, new Date(), idioma);
  const exacta = formatearFechaCorta(repo.fecha_ultimo_commit, idioma);
  document.getElementById('modal-updated').textContent = `${rel} (${exacta})`;

  const infoIdioma = obtenerEtiquetaIdiomaRepo(repo, idioma);
  const modalRepoLang = document.getElementById('modal-repo-lang');
  modalRepoLang.textContent = infoIdioma.etiquetaLarga;
  modalRepoLang.title = infoIdioma.tooltip;

  const teamEl = document.getElementById('modal-team');
  const colabs = Number(det.colaboradores) || 0;
  const archivos = Number(det.archivos_codigo) || 0;
  if (colabs > 1) {
    teamEl.textContent = txt.teamBadge(colabs);
    teamEl.hidden = false;
  } else if (colabs === 1 && archivos > 0) {
    teamEl.textContent = txt.soloBadge;
    teamEl.hidden = false;
  } else {
    teamEl.hidden = true;
  }

  const filesEl = document.getElementById('modal-files');
  if (archivos > 0) {
    filesEl.textContent = txt.sourceFilesBadge(archivos);
    filesEl.hidden = false;
  } else {
    filesEl.hidden = true;
  }

  const starsEl = document.getElementById('modal-stars');
  if (repo.estrellas > 0) {
    starsEl.textContent = txt.starsBadge(repo.estrellas);
    starsEl.hidden = false;
  } else {
    starsEl.hidden = true;
  }

  // Descripción enriquecida y puntos clave bilingües
  const { texto, puntosClave, etiquetaOrigen } = obtenerDescripcionRepositorio(repo, usarIA, idioma);
  document.getElementById('modal-description').textContent = texto;
  document.getElementById('modal-desc-origin').textContent = etiquetaOrigen;

  const highlightsBlock = document.getElementById('modal-highlights-block');
  const highlightsList = document.getElementById('modal-highlights-list');
  highlightsList.innerHTML = '';
  if (Array.isArray(puntosClave) && puntosClave.length > 0) {
    for (const punto of puntosClave) {
      const li = document.createElement('li');
      li.textContent = punto;
      highlightsList.appendChild(li);
    }
    highlightsBlock.hidden = false;
  } else {
    highlightsBlock.hidden = true;
  }

  // Barra proporcional de lenguajes + etiquetas con porcentaje
  const langBar = document.getElementById('modal-lang-bar');
  const modalStack = document.getElementById('modal-stack');
  langBar.innerHTML = '';
  modalStack.innerHTML = '';

  const detalleLengs = Array.isArray(det.lenguajes_detalle) ? det.lenguajes_detalle : [];
  if (detalleLengs.length > 0) {
    langBar.hidden = false;
    for (const item of detalleLengs) {
      const seg = document.createElement('div');
      seg.className = 'lang-bar-segment';
      seg.style.width = `${Math.max(1.5, Number(item.porcentaje) || 0)}%`;
      seg.style.backgroundColor = colorLenguaje(item.nombre);
      seg.title = `${item.nombre}: ${item.porcentaje}%`;
      langBar.appendChild(seg);

      modalStack.appendChild(crearBadgeLenguaje(`${item.nombre} ${item.porcentaje}%`, item.nombre));
    }
  } else if (Array.isArray(repo.lenguajes) && repo.lenguajes.length > 0) {
    langBar.hidden = true;
    for (const lang of repo.lenguajes) {
      modalStack.appendChild(crearBadgeLenguaje(lang));
    }
  } else {
    langBar.hidden = true;
    modalStack.textContent = txt.noGithubLanguages;
  }

  // Frameworks, librerías y motores verificados
  const fwBlock = document.getElementById('modal-frameworks-block');
  const fwContainer = document.getElementById('modal-frameworks');
  fwContainer.innerHTML = '';
  const frameworks = Array.isArray(det.frameworks) ? det.frameworks : [];
  if (frameworks.length > 0) {
    for (const fw of frameworks) {
      fwContainer.appendChild(crearBadgeFramework(fw));
    }
    fwBlock.hidden = false;
  } else {
    fwBlock.hidden = true;
  }

  // Entidades de código: modelos ORM/Prisma, rutas HTTP y módulos/controladores/pantallas
  const entitiesBlock = document.getElementById('modal-code-entities-block');
  const entitiesContainer = document.getElementById('modal-code-entities');
  entitiesContainer.innerHTML = '';

  const etiquetasCodigo = [];
  for (const mdl of det.modelos_datos || []) {
    etiquetasCodigo.push(`${txt.entityModelPrefix}: ${mdl}`);
  }
  for (const ruta of det.rutas_detectadas || []) {
    etiquetasCodigo.push(`${txt.entityRoutePrefix}: ${ruta}`);
  }
  for (const mod of det.modulos_detectados || []) {
    etiquetasCodigo.push(mod);
  }

  if (etiquetasCodigo.length > 0) {
    for (const item of etiquetasCodigo.slice(0, 14)) {
      const chip = document.createElement('span');
      chip.className = 'entity-badge';
      chip.textContent = item;
      entitiesContainer.appendChild(chip);
    }
    entitiesBlock.hidden = false;
  } else {
    entitiesBlock.hidden = true;
  }

  // Topics configurados en GitHub
  const topicsBlock = document.getElementById('modal-topics-block');
  const topicsContainer = document.getElementById('modal-topics');
  topicsContainer.innerHTML = '';
  if (Array.isArray(repo.topics) && repo.topics.length > 0) {
    topicsBlock.hidden = false;
    for (const topic of repo.topics) {
      const span = document.createElement('span');
      span.className = 'topic-badge';
      span.textContent = topic;
      topicsContainer.appendChild(span);
    }
  } else {
    topicsBlock.hidden = true;
  }

  // Enlace a demo en vivo (si existe) y repositorio en GitHub
  const demoBtn = document.getElementById('modal-demo-btn');
  if (det.demo_url) {
    demoBtn.href = det.demo_url;
    demoBtn.hidden = false;
  } else {
    demoBtn.href = '#';
    demoBtn.hidden = true;
  }

  document.getElementById('modal-github-btn').href = repo.url;
}

function abrirDetalleProyecto(repo) {
  estadoGlobal.repoDetalleAbierto = repo;
  poblarContenidoModalDetalle(repo);

  const modal = document.getElementById('project-modal');
  if (typeof modal.showModal === 'function') {
    if (!modal.open) modal.showModal();
  } else {
    modal.setAttribute('open', '');
  }
}

function formatearEtiquetaSemana(sem) {
  if (sem.semanaInicio) {
    const fecha = new Date(`${sem.semanaInicio}T00:00:00Z`);
    if (!Number.isNaN(fecha.getTime())) {
      return fecha.toLocaleDateString(estadoGlobal.idiomaUI === 'en' ? 'en-US' : 'es-MX', {
        day: '2-digit',
        month: 'short',
        timeZone: 'UTC'
      });
    }
  }
  return sem.etiqueta;
}

function renderizarGraficaRespaldo(semanas) {
  const canvas = document.getElementById('commits-chart');
  const fallback = document.getElementById('commits-chart-fallback');
  canvas.hidden = true;
  fallback.hidden = false;
  fallback.innerHTML = '';

  const maxCommits = Math.max(1, ...semanas.map(s => s.commits));
  for (const sem of semanas) {
    const col = document.createElement('div');
    col.className = 'fallback-bar-col';

    const count = document.createElement('span');
    count.className = 'fallback-bar-count';
    count.textContent = String(sem.commits);

    const bar = document.createElement('div');
    bar.className = 'fallback-bar';
    const pct = Math.max(4, Math.round((sem.commits / maxCommits) * 140));
    bar.style.height = `${pct}px`;

    const label = document.createElement('span');
    label.className = 'fallback-bar-label';
    label.textContent = formatearEtiquetaSemana(sem);

    if (Array.isArray(sem.desglose) && sem.desglose.length > 0) {
      col.title = sem.desglose
        .map(d => `${d.nombre}: ${d.commits} ${d.commits === 1 ? 'commit' : 'commits'}`)
        .join('\n');
    }

    col.appendChild(count);
    col.appendChild(bar);
    col.appendChild(label);
    fallback.appendChild(col);
  }
}

function renderizarTendenciaActividad() {
  const seccion = document.getElementById('activity-section');
  const mostrar = Boolean(estadoGlobal.config?.opciones?.mostrar_grafica_actividad);
  const txt = t();

  if (!mostrar) {
    if (estadoGlobal.chartInstance) {
      estadoGlobal.chartInstance.destroy();
      estadoGlobal.chartInstance = null;
    }
    seccion.hidden = true;
    return;
  }

  seccion.hidden = false;
  const metricas = estadoGlobal.tendencia || calcularTendenciaActividad(
    estadoGlobal.datos?.actividad_commits || [],
    estadoGlobal.reposVisibles
  );

  const topLang = (!metricas.lenguajePrincipalReciente || metricas.lenguajePrincipalReciente === 'Sin detectar')
    ? txt.undetectedLang
    : metricas.lenguajePrincipalReciente;
  document.getElementById('metric-top-language').textContent = topLang;

  const textoRacha = metricas.rachaActualDias === 1
    ? txt.streakOneDay
    : txt.streakManyDays(metricas.rachaActualDias);
  document.getElementById('metric-streak').textContent =
    metricas.rachaActualDias === 0 && metricas.mejorRachaReciente > 0
      ? txt.streakZeroWithBest(metricas.mejorRachaReciente)
      : textoRacha;

  document.getElementById('metric-total-commits').textContent =
    txt.activeDaysSuffix(metricas.totalCommitsPeriodo, metricas.diasActivosPeriodo);

  const etiquetas = metricas.semanas.map(s => `${txt.weekPrefix} ${formatearEtiquetaSemana(s)}`);
  const valores = metricas.semanas.map(s => s.commits);

  if (typeof window.Chart === 'function') {
    const canvas = document.getElementById('commits-chart');
    const fallback = document.getElementById('commits-chart-fallback');
    canvas.hidden = false;
    fallback.hidden = true;

    if (estadoGlobal.chartInstance) {
      estadoGlobal.chartInstance.destroy();
    }

    estadoGlobal.chartInstance = new window.Chart(canvas, {
      type: 'bar',
      data: {
        labels: etiquetas,
        datasets: [
          {
            label: txt.chartDatasetLabel,
            data: valores,
            backgroundColor: 'rgba(47, 129, 247, 0.78)',
            borderColor: '#58a6ff',
            borderWidth: 1,
            borderRadius: 5
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              afterBody(items) {
                const idx = items?.[0]?.dataIndex;
                if (idx === undefined || idx === null) return [];
                const sem = metricas.semanas[idx];
                const desglose = Array.isArray(sem?.desglose) ? sem.desglose : [];
                if (desglose.length === 0) return [];
                const uiTxt = t();
                const lines = [uiTxt.tooltipByRepoHeader];
                for (const item of desglose.slice(0, 6)) {
                  const unit = item.commits === 1 ? 'commit' : 'commits';
                  lines.push(`• ${item.nombre}: ${item.commits} ${unit}`);
                }
                if (desglose.length > 6) {
                  lines.push(uiTxt.tooltipMoreRepos(desglose.length - 6));
                }
                return lines;
              }
            }
          }
        },
        scales: {
          x: {
            ticks: { color: '#9da7b3' },
            grid: { display: false }
          },
          y: {
            beginAtZero: true,
            ticks: { color: '#9da7b3', precision: 0 },
            grid: { color: 'rgba(48, 54, 61, 0.6)' }
          }
        }
      }
    });
  } else {
    renderizarGraficaRespaldo(metricas.semanas);
  }
}

function actualizarBannerVistaPrevia() {
  const previewBox = document.getElementById('preview-banner');
  const previewText = document.getElementById('preview-banner-text');
  if (estadoGlobal.modoVistaPrevia && estadoGlobal.datos?.usuario?.github_username) {
    previewText.textContent = t().previewBannerNotice(estadoGlobal.datos.usuario.github_username);
    previewBox.hidden = false;
  } else {
    previewText.textContent = '';
    previewBox.hidden = true;
  }
}

function cambiarIdiomaUI(nuevoIdioma) {
  const normalizado = nuevoIdioma === 'en' ? 'en' : 'es';
  if (estadoGlobal.idiomaUI === normalizado) return;

  estadoGlobal.idiomaUI = normalizado;
  try {
    localStorage.setItem('portafolio_idioma_ui', normalizado);
  } catch {
    // Sin persistencia local en modo privado estricto
  }

  aplicarTextosInterfaz();
  actualizarBannerVistaPrevia();
  if (estadoGlobal.datos) {
    renderizarEncabezado(
      estadoGlobal.datos.usuario || estadoGlobal.config?.usuario,
      estadoGlobal.datos.metadata,
      estadoGlobal.datos.origen,
      estadoGlobal.reposVisibles.length
    );
    poblarSelectorLenguajes(estadoGlobal.reposVisibles);
    poblarSelectorFrameworks(estadoGlobal.reposVisibles);
    renderizarTarjetas();
    renderizarTendenciaActividad();
    if (estadoGlobal.repoDetalleAbierto) {
      poblarContenidoModalDetalle(estadoGlobal.repoDetalleAbierto);
    }
  }
}

function aplicarPayloadPortafolio(payload) {
  const banner = document.getElementById('alert-banner');
  if (payload.aviso) {
    banner.textContent = payload.aviso;
    banner.hidden = false;
  } else {
    banner.textContent = '';
    banner.hidden = true;
  }

  estadoGlobal.modoVistaPrevia = Boolean(payload.modo_vista_previa);
  estadoGlobal.config = payload.config;
  estadoGlobal.datos = payload;
  estadoGlobal.tendencia = payload.tendencia;
  estadoGlobal.reposVisibles = filtrarRepositoriosVisibles(
    payload.repositorios || [],
    payload.config?.sincronizacion || {}
  );

  actualizarBannerVistaPrevia();
  renderizarEncabezado(
    payload.usuario || payload.config?.usuario,
    payload.metadata,
    payload.origen,
    estadoGlobal.reposVisibles.length
  );
  poblarSelectorLenguajes(estadoGlobal.reposVisibles);
  poblarSelectorFrameworks(estadoGlobal.reposVisibles);
  renderizarTarjetas();
  renderizarTendenciaActividad();

  if (estadoGlobal.repoDetalleAbierto) {
    const actualizado = estadoGlobal.reposVisibles.find(
      r => r.id_repositorio === estadoGlobal.repoDetalleAbierto.id_repositorio
    );
    if (actualizado) {
      estadoGlobal.repoDetalleAbierto = actualizado;
      poblarContenidoModalDetalle(actualizado);
    }
  }
}

function separarListaCSV(valorTexto) {
  return String(valorTexto || '')
    .split(',')
    .map(item => item.trim())
    .filter(Boolean);
}

function mostrarFeedbackConfig(mensaje, tipo = 'ok') {
  const box = document.getElementById('config-feedback');
  const clase = tipo === 'error' ? 'error' : (tipo === 'info' ? 'info' : 'ok');
  box.className = `form-feedback ${clase}`;
  box.textContent = mensaje;
  box.hidden = false;
  const scrollBody = document.querySelector('#config-modal .modal-body-scroll');
  if (scrollBody) {
    scrollBody.scrollTop = 0;
  }
}

function ocultarFeedbackConfig() {
  const box = document.getElementById('config-feedback');
  box.textContent = '';
  box.hidden = true;
}

function aplicarPerfilEnCamposFormulario(perfil) {
  document.getElementById('cfg-github-username').value = perfil.github_username || '';
  document.getElementById('cfg-user-name').value = perfil.nombre || '';
  document.getElementById('cfg-user-email').value = perfil.correo || '';
  document.getElementById('cfg-extra-repos').value = (perfil.extra_repos || []).join(', ');
  document.getElementById('cfg-excluded-repos').value = (perfil.excluded_repos || []).join(', ');
}

function renderizarChipsPerfilesGuardados(cfg, activeKeyLower) {
  const bar = document.getElementById('cfg-saved-profiles');
  const perfilesObj = cfg?.perfiles_usuario || {};
  const entries = Object.entries(perfilesObj);
  bar.innerHTML = '';

  if (entries.length === 0) {
    bar.hidden = true;
    return;
  }

  bar.hidden = false;
  const label = document.createElement('span');
  label.className = 'saved-profiles-label';
  label.textContent = t().cfgSavedProfilesLabel;
  bar.appendChild(label);

  for (const [key, prof] of entries) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `profile-chip${key === activeKeyLower ? ' active' : ''}`;
    btn.textContent = `@${prof.github_username}`;
    btn.addEventListener('click', () => {
      aplicarPerfilEnCamposFormulario(prof);
      renderizarChipsPerfilesGuardados(cfg, key);
    });
    bar.appendChild(btn);
  }
}

function manejarEscrituraUsuarioGithub() {
  const cfg = estadoGlobal.config || {};
  const rawInput = document.getElementById('cfg-github-username').value.trim().replace(/^@+/, '');
  const key = rawInput.toLowerCase();
  const perfiles = cfg.perfiles_usuario || {};
  const activeKey = String(cfg?.usuario?.github_username || '').toLowerCase();

  if (key && perfiles[key]) {
    aplicarPerfilEnCamposFormulario(perfiles[key]);
    document.getElementById('cfg-github-username').value = rawInput;
    renderizarChipsPerfilesGuardados(cfg, key);
  } else if (key && key !== activeKey) {
    // Al escribir un usuario nuevo no guardado, limpiar campos específicos del usuario anterior
    document.getElementById('cfg-user-name').value = '';
    document.getElementById('cfg-user-email').value = '';
    document.getElementById('cfg-extra-repos').value = '';
    document.getElementById('cfg-excluded-repos').value = '';
    renderizarChipsPerfilesGuardados(cfg, '');
  }
}

function rellenarFormularioConfig(cfg) {
  const userCfg = cfg?.usuario || {};
  const syncCfg = cfg?.sincronizacion || {};
  const optsCfg = cfg?.opciones || {};

  document.getElementById('cfg-github-username').value = userCfg.github_username || '';
  document.getElementById('cfg-user-name').value = userCfg.nombre || '';
  document.getElementById('cfg-user-email').value = userCfg.correo || '';

  document.getElementById('cfg-excluded-topics').value = (syncCfg.excluded_topics || []).join(', ');
  document.getElementById('cfg-extra-repos').value = (syncCfg.extra_repos || []).join(', ');
  document.getElementById('cfg-excluded-repos').value = (syncCfg.excluded_repos || []).join(', ');

  document.getElementById('cfg-use-ai').checked = Boolean(optsCfg.generar_descripciones_ia ?? true);
  document.getElementById('cfg-show-chart').checked = Boolean(optsCfg.mostrar_grafica_actividad ?? true);
  document.getElementById('cfg-exclude-forks').checked = Boolean(syncCfg.exclude_forks ?? true);

  const metodo = optsCfg.metodo_actualizacion === 'client-side' ? 'client-side' : 'github-actions';
  document.getElementById('cfg-method-client').checked = metodo === 'client-side';
  document.getElementById('cfg-method-actions').checked = metodo === 'github-actions';

  const adminKeyGroup = document.getElementById('cfg-admin-key-group');
  adminKeyGroup.hidden = !Boolean(cfg?.admin_key_requerida);

  renderizarChipsPerfilesGuardados(cfg, String(userCfg.github_username || '').toLowerCase());
}

async function abrirModalConfiguracion() {
  const configModal = document.getElementById('config-modal');
  ocultarFeedbackConfig();

  try {
    const resp = await fetch('./api/config');
    if (resp.ok) {
      estadoGlobal.config = await resp.json();
    }
  } catch {
    // En modo estático sin backend usa la configuración en memoria
  }

  rellenarFormularioConfig(estadoGlobal.config);

  if (typeof configModal.showModal === 'function') {
    configModal.showModal();
  } else {
    configModal.setAttribute('open', '');
  }
}

function extraerDetalleErrorAPI(errBody, status) {
  if (!errBody) return `HTTP ${status}`;
  if (typeof errBody.detail === 'string') return errBody.detail;
  if (Array.isArray(errBody.detail) && errBody.detail.length > 0) {
    return errBody.detail.map(item => item.msg || JSON.stringify(item)).join(' | ');
  }
  return `HTTP ${status}`;
}

async function guardarConfiguracion(event) {
  event.preventDefault();
  ocultarFeedbackConfig();
  const txt = t();

  const saveBtn = document.getElementById('config-save-btn');
  const syncBtn = document.getElementById('cfg-sync-now-btn');
  const prevUsername = String(estadoGlobal.config?.usuario?.github_username || '').trim();
  const typedUsername = document.getElementById('cfg-github-username').value.trim().replace(/^@+/, '');
  const cambiandoUsuario = Boolean(typedUsername && typedUsername.toLowerCase() !== prevUsername.toLowerCase());

  const metodoRadio = document.querySelector('input[name="metodo_actualizacion"]:checked');
  const bodyPayload = {
    github_username: typedUsername || prevUsername,
    nombre: document.getElementById('cfg-user-name').value.trim(),
    correo: document.getElementById('cfg-user-email').value.trim(),
    excluded_topics: separarListaCSV(document.getElementById('cfg-excluded-topics').value),
    extra_repos: separarListaCSV(document.getElementById('cfg-extra-repos').value),
    excluded_repos: separarListaCSV(document.getElementById('cfg-excluded-repos').value),
    exclude_forks: document.getElementById('cfg-exclude-forks').checked,
    generar_descripciones_ia: document.getElementById('cfg-use-ai').checked,
    mostrar_grafica_actividad: document.getElementById('cfg-show-chart').checked,
    metodo_actualizacion: metodoRadio ? metodoRadio.value : 'github-actions'
  };

  saveBtn.disabled = true;
  syncBtn.disabled = true;
  if (cambiandoUsuario) {
    saveBtn.textContent = txt.cfgSwitchingUserBtn;
    const yaEnCache = Boolean(estadoGlobal.config?.perfiles_usuario?.[typedUsername.toLowerCase()]);
    if (!yaEnCache) {
      mostrarFeedbackConfig(txt.cfgSwitchingUserProgress(typedUsername), 'info');
    }
  }

  try {
    const headers = { 'Content-Type': 'application/json' };
    const adminKey = (document.getElementById('cfg-admin-key').value || '').trim();
    if (adminKey) {
      headers['X-Admin-Key'] = adminKey;
    }

    const resp = await fetch('./api/config', {
      method: 'PUT',
      headers,
      body: JSON.stringify(bodyPayload)
    });

    if (!resp.ok) {
      let errJson = null;
      try {
        errJson = await resp.json();
      } catch {
        errJson = null;
      }
      mostrarFeedbackConfig(extraerDetalleErrorAPI(errJson, resp.status), 'error');
      return;
    }

    const updatedPortfolio = await resp.json();
    if (window.location.search && typeof window.history?.replaceState === 'function') {
      window.history.replaceState({}, '', window.location.pathname);
    }
    aplicarPayloadPortafolio(updatedPortfolio);
    rellenarFormularioConfig(updatedPortfolio.config);

    const activeUser = updatedPortfolio.usuario?.github_username || bodyPayload.github_username;
    const msgExito = cambiandoUsuario
      ? txt.cfgSwitchedUserOk(activeUser, estadoGlobal.reposVisibles.length)
      : txt.cfgSavedOk(estadoGlobal.reposVisibles.length);
    mostrarFeedbackConfig(msgExito, 'ok');
  } catch {
    if (estadoGlobal.config) {
      estadoGlobal.config.sincronizacion = {
        ...(estadoGlobal.config.sincronizacion || {}),
        excluded_topics: bodyPayload.excluded_topics,
        extra_repos: bodyPayload.extra_repos,
        excluded_repos: bodyPayload.excluded_repos,
        exclude_forks: bodyPayload.exclude_forks
      };
      estadoGlobal.config.opciones = {
        ...(estadoGlobal.config.opciones || {}),
        generar_descripciones_ia: bodyPayload.generar_descripciones_ia,
        mostrar_grafica_actividad: bodyPayload.mostrar_grafica_actividad,
        metodo_actualizacion: bodyPayload.metodo_actualizacion
      };
      aplicarPayloadPortafolio({
        ...estadoGlobal.datos,
        config: estadoGlobal.config
      });
      mostrarFeedbackConfig(txt.cfgSavedFallback, 'error');
    }
  } finally {
    saveBtn.textContent = t().cfgSaveBtn;
    saveBtn.disabled = false;
    syncBtn.disabled = false;
  }
}

async function sincronizarManualmenteDesdeUI() {
  ocultarFeedbackConfig();
  const txt = t();
  const syncBtn = document.getElementById('cfg-sync-now-btn');
  const saveBtn = document.getElementById('config-save-btn');

  syncBtn.disabled = true;
  saveBtn.disabled = true;
  syncBtn.textContent = txt.cfgSyncingBtn;

  try {
    const headers = {};
    const adminKey = (document.getElementById('cfg-admin-key').value || '').trim();
    if (adminKey) {
      headers['X-Admin-Key'] = adminKey;
    }
    const resp = await fetch('./api/sync', { method: 'POST', headers });
    if (!resp.ok) {
      let errJson = null;
      try {
        errJson = await resp.json();
      } catch {
        errJson = null;
      }
      mostrarFeedbackConfig(extraerDetalleErrorAPI(errJson, resp.status), 'error');
      return;
    }

    const syncedPayload = await resp.json();
    aplicarPayloadPortafolio(syncedPayload);
    const cuota = syncedPayload.metadata?.rate_limit_restante;
    const sufijoCuota = cuota !== null && cuota !== undefined ? txt.cfgQuotaRemaining(cuota) : '';
    mostrarFeedbackConfig(txt.cfgSyncedOk(estadoGlobal.reposVisibles.length, sufijoCuota), 'ok');
  } catch {
    mostrarFeedbackConfig(txt.cfgSyncConnError, 'error');
  } finally {
    syncBtn.textContent = t().cfgSyncNowBtn;
    syncBtn.disabled = false;
    saveBtn.disabled = false;
  }
}

function configurarEventosUI() {
  document.getElementById('lang-es-btn').addEventListener('click', () => cambiarIdiomaUI('es'));
  document.getElementById('lang-en-btn').addEventListener('click', () => cambiarIdiomaUI('en'));

  const searchInput = document.getElementById('project-search');
  searchInput.addEventListener('input', e => {
    estadoGlobal.filtroBusqueda = e.target.value;
    renderizarTarjetas();
  });

  const langSelect = document.getElementById('language-filter');
  langSelect.addEventListener('change', e => {
    estadoGlobal.filtroLenguaje = e.target.value;
    renderizarTarjetas();
  });

  const fwSelect = document.getElementById('framework-filter');
  fwSelect.addEventListener('change', e => {
    estadoGlobal.filtroFramework = e.target.value;
    renderizarTarjetas();
  });

  // Pantalla 2: Modal de Detalle de Proyecto
  const modal = document.getElementById('project-modal');
  const cerrarDetalle = () => {
    estadoGlobal.repoDetalleAbierto = null;
    if (typeof modal.close === 'function') modal.close();
    else modal.removeAttribute('open');
  };

  document.getElementById('modal-close-btn').addEventListener('click', cerrarDetalle);
  document.getElementById('modal-secondary-close').addEventListener('click', cerrarDetalle);
  modal.addEventListener('close', () => {
    estadoGlobal.repoDetalleAbierto = null;
  });
  modal.addEventListener('click', e => {
    if (e.target === modal) cerrarDetalle();
  });

  // Pantalla 4: Modal de Configuración del Portafolio
  const configModal = document.getElementById('config-modal');
  const cerrarConfig = () => {
    if (typeof configModal.close === 'function') configModal.close();
    else configModal.removeAttribute('open');
  };

  document.getElementById('open-config-btn').addEventListener('click', abrirModalConfiguracion);
  document.getElementById('config-close-btn').addEventListener('click', cerrarConfig);
  document.getElementById('config-cancel-btn').addEventListener('click', cerrarConfig);
  configModal.addEventListener('click', e => {
    if (e.target === configModal) cerrarConfig();
  });

  document.getElementById('cfg-github-username').addEventListener('input', manejarEscrituraUsuarioGithub);
  document.getElementById('config-form').addEventListener('submit', guardarConfiguracion);
  document.getElementById('cfg-sync-now-btn').addEventListener('click', sincronizarManualmenteDesdeUI);
}

function obtenerUsuarioVistaPreviaURL() {
  try {
    const params = new URLSearchParams(window.location.search);
    return (params.get('user') || '').trim().replace(/^@+/, '');
  } catch {
    return '';
  }
}

async function obtenerPayloadServidorORespaldo() {
  const previewUser = obtenerUsuarioVistaPreviaURL();
  const endpoint = previewUser
    ? `./api/portfolio?user=${encodeURIComponent(previewUser)}`
    : './api/portfolio';

  let apiResp = null;
  try {
    apiResp = await fetch(endpoint);
  } catch {
    apiResp = null;
  }

  if (apiResp !== null) {
    if (apiResp.ok) {
      return await apiResp.json();
    }
    if (previewUser) {
      let errJson = null;
      try {
        errJson = await apiResp.json();
      } catch {
        errJson = null;
      }
      throw new Error(extraerDetalleErrorAPI(errJson, apiResp.status));
    }
  }

  const [cfgResp, bkpResp] = await Promise.all([
    fetch('./config.json'),
    fetch('./data/backup_portfolio.json')
  ]);
  if (!cfgResp.ok || !bkpResp.ok) {
    throw new Error('No se pudo conectar al backend FastAPI ni leer el respaldo local.');
  }

  const config = await cfgResp.json();
  const backup = await bkpResp.json();
  return {
    config,
    origen: 'respaldo-json',
    aviso: t().staticFallbackNotice,
    modo_vista_previa: false,
    metadata: backup.metadata,
    usuario: backup.usuario,
    repositorios: backup.repositorios,
    actividad_commits: backup.actividad_commits,
    tendencia: null
  };
}

async function iniciarPortafolio() {
  aplicarTextosInterfaz();
  configurarEventosUI();

  try {
    const payload = await obtenerPayloadServidorORespaldo();
    aplicarPayloadPortafolio(payload);
  } catch (err) {
    const banner = document.getElementById('alert-banner');
    banner.textContent = `${t().loadErrorPrefix}: ${err.message}`;
    banner.hidden = false;
    const previewUser = obtenerUsuarioVistaPreviaURL();
    if (previewUser) {
      const previewBox = document.getElementById('preview-banner');
      document.getElementById('preview-banner-text').textContent = t().previewBannerError(previewUser);
      previewBox.hidden = false;
    }
    document.getElementById('sync-status-text').textContent = t().loadErrorShort;
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', iniciarPortafolio);
} else {
  iniciarPortafolio();
}
