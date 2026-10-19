/**
 * public/js/app.js
 * Coordinador Principal de la Aplicación HidroPanel 2.0
 */

// Inicialización cuando el DOM está listo
document.addEventListener('DOMContentLoaded', async () => {
  // Aplicar tema inicial
  document.documentElement.setAttribute('data-theme', State.theme);
  updateThemeIcon();

  // Aplicar estado inicial de barra lateral
  updateSidebarUI(State.sidebarCollapsed);

  // Cargar catálogo de estaciones y situación general
  await loadInitialData();

  // Inicializar vista predeterminada: Caudales & Represas
  setViewMode('caudales');

  // Aplicar estado inicial de selector de curva
  updateChartSourceUI();

  // Iniciar monitoreo de sincronización automática y ciclo de polling en tiempo real
  initSyncTicker();
  startPollingCycle();

  // Atajos de teclado
  initShortcuts();

  // Botones de cambio de vista principales
  const viewNavMap = [
    { id: 'btn-view-caudales', mode: 'caudales' },
    { id: 'btn-view-charts', mode: 'charts' },
    { id: 'btn-view-map', mode: 'map' },
    { id: 'btn-view-simepar', mode: 'simepar' }
  ];
  viewNavMap.forEach(({ id, mode }) => {
    const btn = document.getElementById(id);
    if (btn) {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        setViewMode(mode);
      });
    }
  });

  // Botón modal de umbrales en cabecera
  const btnUmbrales = document.getElementById('btn-header-umbrales');
  if (btnUmbrales) {
    btnUmbrales.addEventListener('click', (e) => {
      e.preventDefault();
      openThresholdsModal();
    });
  }

  // Cierre de popovers al hacer click fuera
  document.addEventListener('click', (e) => {
    const pop = document.getElementById('simepar-calendar-popover');
    const btn = document.getElementById('simepar-calendar-btn');
    if (pop && !pop.classList.contains('hidden')) {
      if (!pop.contains(e.target) && !btn.contains(e.target)) {
        SimeparView.closeCalendar();
      }
    }
  });
});

async function loadInitialData() {
  try {
    // 1. Obtener situación general y alertas
    const sitData = await API.getSituation();
    if (sitData && sitData.success) {
      State.situation = sitData;
      if (sitData.sources_status && window.Components && typeof Components.renderSourcesHeader === 'function') {
        Components.renderSourcesHeader(sitData.sources_status);
      }
      Components.renderAlertBanner('alert-banner-container', sitData.alertas_activas, window.selectStation, sitData.estaciones_falla_reporte);
    }

    // 2. Obtener catálogo de estaciones
    const estData = await API.getStations();
    if (estData && estData.success) {
      State.stations = estData.estaciones || [];
      State.filteredStations = [...State.stations];

      // Conteo en sidebar
      const countEl = document.getElementById('catalog-count');
      if (countEl) countEl.textContent = `${State.stations.length} estaciones`;

      // Poblar selector del mapa
      const mapSelect = document.getElementById('map-station-select');
      if (mapSelect) {
        const seenMap = new Set();
        const mapOptions = ['<option value="">Ir a una estación...</option>'];
        for (const s of State.stations) {
          const clean = (s.nombre || '').trim();
          if (!clean) continue;
          const k = clean.toLowerCase();
          if (seenMap.has(k)) continue;
          seenMap.add(k);
          const altStr = (s.ultima_altura !== null && s.ultima_altura !== undefined) ? `${Number(s.ultima_altura).toFixed(2)}m` : '—';
          const pnaStr = (s.pna_altura !== null && s.pna_altura !== undefined) ? ` | ⚓ ${Number(s.pna_altura).toFixed(2)}m` : '';
          mapOptions.push(`<option value="${s.id}">${clean} (${altStr}${pnaStr})</option>`);
        }
        mapSelect.innerHTML = mapOptions.join('');
      }

      // Poblar selector de estación en vista de gráficos
      populateChartsStationSelect();

      // Seleccionar estación por defecto (Puerto Iguazú, Posadas o la primera)
      let defaultStation = State.stations.find(s => s.codigo === 'PUERTO_IGUAZU') ||
                           State.stations.find(s => s.codigo === 'POSADAS') ||
                           State.stations[0];

      if (defaultStation) {
        await selectStation(defaultStation.id, false);
      } else {
        Components.renderStationList(State.filteredStations, null, window.selectStation);
      }

      // Inicializar utilidades del Panel de Hidrología (Umbrales y Alertas)
      populateThresholdsEditor(defaultStation);
      renderSidebarAlerts();

      // Pre-cargar mapa de lluvias SIMEPAR en segundo plano para despliegue instantáneo
      if (window.SimeparView) {
        SimeparView.init().catch(e => console.warn('Pre-carga SIMEPAR diferida:', e));
      }
    }
  } catch (e) {
    console.error('Error cargando datos iniciales:', e);
    Components.showToast('Error de Conexión', 'No se pudo comunicar con el servidor backend', true);
  }
}

/**
 * Selección de estación activa
 */
async function selectStation(stationId, flyMap = true) {
  State.selectedStationId = stationId;
  const station = State.stations.find(s => s.id === stationId);
  if (!station) return;

  // Sincronizar selector de estación en barra de gráficos
  const chartSelect = document.getElementById('charts-station-select');
  if (chartSelect) chartSelect.value = stationId;

  // Sincronizar editor de umbrales si el modal está abierto
  const modal = document.getElementById('modal-umbrales');
  if (modal && !modal.classList.contains('hidden')) {
    populateThresholdsEditor(station);
  }

  const coordsBadge = document.getElementById('station-coords-badge');
  if (coordsBadge) {
    coordsBadge.style.display = 'none';
  }

  // Panel de Cota Posadas
  const posadasPanel = document.getElementById('posadas-cota-panel');
  const isPosadas = station.codigo === 'POSADAS';
  if (posadasPanel) {
    posadasPanel.style.display = isPosadas ? 'inline-flex' : 'none';
  }

  // Mostrar loader de gráfico
  const loader = document.getElementById('chart-loader');
  if (loader) loader.style.display = 'flex';

  try {
    // Cargar mediciones
    const res = await API.getMeasurements(stationId, State.range);
    if (res && res.success) {
      State.selectedStationData = res;

      const isCota = isPosadas && State.posadasMode === 'cota';
      const offset = State.posadasOffset;

      // Renderizar Situación Actual
      Components.renderSituationStrip(res.kpis, station, isCota, offset);

      // Renderizar Nivel-Bar
      Components.renderNivelBar(res.kpis, station);

      // Renderizar KPIs según fuente seleccionada
      Components.renderKpiCards(
        res.kpis,
        isCota,
        offset,
        State.chartSource || 'agp',
        res.puntos || [],
        res.puntos_pna || []
      );

      // Renderizar Tabla
      Components.renderRecentTable(res.recientes, isCota, offset);

      // Renderizar Gráficos (Single o Subplots)
      if (State.layout === 1) {
        Charts.renderMainChart(
          'mainHeightChart',
          res.puntos || [],
          res.kpis,
          isCota,
          offset,
          State.theme === 'dark',
          res.puntos_pna || []
        );
        setTimeout(() => {
          if (Charts.mainChart) Charts.mainChart.resize();
        }, 50);
      } else {
        const grid = document.getElementById('subplots-grid');
        if (!grid || grid.children.length !== State.layout) {
          State.ensureDefaultSubplotStations();
          Charts.renderSubplots(
            'subplots-grid',
            State.layout,
            State.subplotStationIds,
            State.stations,
            State.range,
            State.theme === 'dark',
            window.selectStation
          );
        } else {
          State.subplotStationIds[0] = stationId;
          const sel0 = document.getElementById('subplot-select-0');
          if (sel0) sel0.value = stationId;
          Charts.loadSubplotData(0, stationId, false);
        }
      }

      // Si el mapa está inicializado, actualizar pines y centrar
      if (MapView.map) {
        MapView.renderStations(State.stations, stationId, window.selectStation);
        if (flyMap) MapView.flyToStation(station);
      }
    }
  } catch (e) {
    console.error('Error cargando mediciones de estación:', e);
    Components.showToast('Error', 'No se pudieron cargar mediciones para esta estación', true);
  } finally {
    if (loader) loader.style.display = 'none';
  }
}

/**
 * Filtro de búsqueda y cuenca en la barra lateral
 */
State.basinFilter = 'todas';

function setBasinFilter(basin) {
  State.basinFilter = basin;
  document.querySelectorAll('.btn-basin-filter').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-basin') === basin);
  });
  filterStations();
}

function filterStations() {
  const query = (document.getElementById('search-station').value || '').toLowerCase().trim();
  const basin = State.basinFilter || 'todas';

  let list = State.stations;
  if (basin === 'parana') {
    list = list.filter(s => {
      const name = (s.nombre + ' ' + s.codigo).toLowerCase();
      return !name.includes('paraguay') && !name.includes('pilcomayo') && !name.includes('formosa') && !name.includes('delta') && !name.includes('tigre') && !name.includes('zarate') && !name.includes('campana') && !name.includes('san pedro') && !name.includes('rosario') && !name.includes('san nicolas') && !name.includes('victoria') && !name.includes('santa fe') && !name.includes('baradero');
    });
  } else if (basin === 'paraguay') {
    list = list.filter(s => {
      const name = (s.nombre + ' ' + s.codigo).toLowerCase();
      return name.includes('paraguay') || name.includes('pilcomayo') || name.includes('formosa') || name.includes('clorinda') || name.includes('bermejo');
    });
  } else if (basin === 'delta') {
    list = list.filter(s => {
      const name = (s.nombre + ' ' + s.codigo).toLowerCase();
      return name.includes('delta') || name.includes('tigre') || name.includes('zarate') || name.includes('campana') || name.includes('san pedro') || name.includes('rosario') || name.includes('san nicolas') || name.includes('baradero') || name.includes('victoria') || name.includes('santa fe') || name.includes('palmas') || name.includes('guazu');
    });
  }

  if (query) {
    list = list.filter(s =>
      s.nombre.toLowerCase().includes(query) ||
      s.codigo.toLowerCase().includes(query)
    );
  }

  State.filteredStations = list;
  const countEl = document.getElementById('catalog-count');
  if (countEl) countEl.textContent = `${list.length} estaciones`;
  Components.renderStationList(State.filteredStations, State.selectedStationId, window.selectStation);
}

/**
 * Manejo de Vistas (Caudales & Represas vs Gráficos vs Mapa vs Lluvias SIMEPAR)
 */
async function setViewMode(mode) {
  State.setViewMode(mode);

  // Botones de pestañas superiores
  const viewBtns = {
    charts: document.getElementById('btn-view-charts'),
    caudales: document.getElementById('btn-view-caudales'),
    map: document.getElementById('btn-view-map'),
    simepar: document.getElementById('btn-view-simepar')
  };

  Object.entries(viewBtns).forEach(([viewKey, btn]) => {
    if (!btn) return;
    const isActive = viewKey === mode;
    btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
    const svg = btn.querySelector('svg');
    if (isActive) {
      btn.className = 'view-btn active flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold text-white bg-[#008348] border border-emerald-400/30 shadow-xs transition-all duration-150 cursor-pointer';
      if (svg) svg.className.baseVal = 'w-3.5 h-3.5 text-emerald-200';
    } else {
      btn.className = 'view-btn flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-slate-300 hover:text-white hover:bg-white/[0.08] border border-transparent transition-all duration-150 cursor-pointer';
      if (svg) svg.className.baseVal = 'w-3.5 h-3.5 text-slate-400';
    }
  });

  // Contenedores de vista
  const chartsView = document.getElementById('view-charts-container');
  const caudalesView = document.getElementById('view-caudales-container');
  const mapView = document.getElementById('view-map-container');
  const simeparView = document.getElementById('view-simepar-container');

  if (chartsView) {
    chartsView.style.display = mode === 'charts' ? 'flex' : 'none';
    chartsView.classList.toggle('hidden', mode !== 'charts');
  }
  if (caudalesView) {
    caudalesView.style.display = mode === 'caudales' ? 'flex' : 'none';
    caudalesView.classList.toggle('hidden', mode !== 'caudales');
  }
  if (mapView) {
    mapView.style.display = mode === 'map' ? 'flex' : 'none';
    mapView.classList.toggle('hidden', mode !== 'map');
  }
  if (simeparView) {
    simeparView.style.display = mode === 'simepar' ? 'flex' : 'none';
    simeparView.classList.toggle('hidden', mode !== 'simepar');
  }

  if (mode === 'caudales') {
    if (window.RepresasView && RepresasView.data) {
      RepresasView.renderOverview(RepresasView.data);
      RepresasView.renderSchematic(RepresasView.data);
      RepresasView.renderTable(RepresasView.data.centrales_lista || []);
      setTimeout(() => {
        if (RepresasView.caudalesChart) {
          RepresasView.caudalesChart.resize();
          RepresasView.caudalesChart.update('none');
        }
        if (RepresasView.itaipuChart) {
          RepresasView.itaipuChart.resize();
          RepresasView.itaipuChart.update('none');
        }
      }, 50);
    } else if (window.RepresasView) {
      RepresasView.init();
    }
  } else if (mode === 'charts') {
    if (State.layout > 1) {
      setLayout(State.layout);
    } else {
      const targetId = State.selectedStationId || (State.stations && State.stations[0] ? State.stations[0].id : null);
      if (targetId) {
        selectStation(targetId, false);
      }
      setTimeout(() => {
        if (Charts.mainChart) {
          Charts.mainChart.resize();
          Charts.mainChart.update('none');
        }
      }, 60);
    }
  } else if (mode === 'map') {
    MapView.init('map-leaflet', State.theme === 'dark');
    if (State.stations.length > 0) {
      MapView.renderStations(State.stations, State.selectedStationId, window.selectStation);
    }
    if (window.RepresasView && RepresasView.data) {
      MapView.renderDams(RepresasView.data);
    }
    if (MapView.map) MapView.map.invalidateSize();
    setTimeout(() => {
      if (MapView.map) MapView.map.invalidateSize();
    }, 100);
    setTimeout(() => {
      if (MapView.map) MapView.map.invalidateSize();
    }, 250);
  } else if (mode === 'simepar') {
    if (window.SimeparView && SimeparView.dates && SimeparView.dates.length > 0) {
      SimeparView.renderImage();
      SimeparView.updateControls();
    } else if (window.SimeparView) {
      await SimeparView.init();
    }
  }
}


/**
 * Manejo de Layout de Gráficos (1, 2, 4, 8)
 */
function setLayout(num) {
  State.setLayout(num);

  document.querySelectorAll('.btn-layout').forEach(btn => {
    btn.classList.toggle('active', parseInt(btn.getAttribute('data-layout')) === num);
  });

  const singleView = document.getElementById('single-plot-view');
  const multiView = document.getElementById('multi-plot-view');
  const posadasPanel = document.getElementById('posadas-cota-panel');

  if (num === 1) {
    if (singleView) {
      singleView.style.display = 'block';
      singleView.classList.remove('hidden');
    }
    if (multiView) {
      multiView.style.display = 'none';
      multiView.classList.add('hidden');
    }
    if (State.selectedStationId) {
      selectStation(State.selectedStationId, false);
    }
  } else {
    if (singleView) {
      singleView.style.display = 'none';
      singleView.classList.add('hidden');
    }
    if (multiView) {
      multiView.style.display = 'block';
      multiView.classList.remove('hidden');
    }
    if (posadasPanel) posadasPanel.style.display = 'none';

    State.ensureDefaultSubplotStations();

    Charts.renderSubplots(
      'subplots-grid',
      num,
      State.subplotStationIds,
      State.stations,
      State.range,
      State.theme === 'dark',
      window.selectStation
    );
  }
}

/**
 * Manejo de Rango Temporal (24h, 7d, 30d, Todo)
 */
function setRange(range) {
  State.setRange(range);

  document.querySelectorAll('.btn-range').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-range') === range);
  });

  if (State.layout === 1 && State.selectedStationId) {
    selectStation(State.selectedStationId, false);
  } else if (State.layout > 1) {
    for (let i = 0; i < State.layout; i++) {
      if (State.subplotStationIds[i]) {
        Charts.loadSubplotData(i, State.subplotStationIds[i], false);
      }
    }
  }
}

/**
 * Manejo de Selector de Curva ('agp' | 'pna' | 'ambas')
 */
function setChartSource(source) {
  State.setChartSource(source);
  updateChartSourceUI();

  if (State.layout === 1 && State.selectedStationId) {
    if (State.selectedStationData) {
      const res = State.selectedStationData;
      const station = State.stations.find(s => s.id === State.selectedStationId);
      const isPosadas = station && station.codigo === 'POSADAS';
      const isCota = isPosadas && State.posadasMode === 'cota';
      const offset = State.posadasOffset;

      Components.renderKpiCards(
        res.kpis,
        isCota,
        offset,
        source,
        res.puntos || [],
        res.puntos_pna || []
      );
      Charts.renderMainChart(
        'mainHeightChart',
        res.puntos || [],
        res.kpis,
        isCota,
        offset,
        State.theme === 'dark',
        res.puntos_pna || []
      );
    } else {
      selectStation(State.selectedStationId, false);
    }
  } else if (State.layout > 1) {
    for (let i = 0; i < State.layout; i++) {
      if (State.subplotStationIds[i]) {
        Charts.loadSubplotData(i, State.subplotStationIds[i], false);
      }
    }
  }
}

function updateChartSourceUI() {
  const current = State.chartSource || 'agp';
  const btns = {
    agp: document.getElementById('btn-chart-src-agp'),
    pna: document.getElementById('btn-chart-src-pna'),
    ambas: document.getElementById('btn-chart-src-ambas')
  };

  Object.entries(btns).forEach(([key, btn]) => {
    if (!btn) return;
    const isActive = key === current;
    btn.classList.toggle('active', isActive);
    if (isActive) {
      btn.className = 'btn-chart-src px-2.5 py-1 rounded font-bold transition active bg-sky-600 text-white shadow-xs';
    } else {
      btn.className = 'btn-chart-src px-2.5 py-1 rounded font-medium transition text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white';
    }
  });
}

/**
 * Selector de estaciones para la vista de gráficos
 */
function populateChartsStationSelect() {
  const select = document.getElementById('charts-station-select');
  if (!select || !State.stations || State.stations.length === 0) return;

  const seen = new Set();
  const options = [];
  for (const s of State.stations) {
    const cleanName = (s.nombre || '').trim();
    if (!cleanName) continue;
    const key = cleanName.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);

    const altStr = (s.ultima_altura !== null && s.ultima_altura !== undefined) ? `${Number(s.ultima_altura).toFixed(2)}m` : '—';
    const pnaStr = (s.pna_altura !== null && s.pna_altura !== undefined) ? ` | ⚓ ${Number(s.pna_altura).toFixed(2)}m` : '';
    const failNotice = s.falla_reporte ? ' ⚠️' : '';
    const label = `${cleanName} — AGP: ${altStr}${pnaStr}${failNotice}`;
    options.push(`<option value="${s.id}">${label}</option>`);
  }

  select.innerHTML = options.join('');

  if (State.selectedStationId) {
    select.value = State.selectedStationId;
  }
}

function selectStationByCode(code) {
  const st = State.stations.find(s => s.codigo === code);
  if (st) {
    selectStation(st.id, true);
  }
}

/**
 * Modal de Configuración de Umbrales Hidrológicos
 */
async function openThresholdsModal(stationId = null) {
  const modal = document.getElementById('modal-umbrales');
  if (!modal) {
    console.error('Modal umbrales no encontrado');
    return;
  }
  modal.style.display = 'flex';
  modal.classList.remove('hidden');

  // Si las estaciones no están cargadas, cargarlas de la API
  if (!State.stations || State.stations.length === 0) {
    try {
      const data = await API.getStations();
      if (data && data.success) {
        State.stations = data.estaciones || [];
        State.filteredStations = [...State.stations];
      }
    } catch (e) {
      console.warn('Error precargando estaciones en modal:', e);
    }
  }

  const targetId = stationId || State.selectedStationId || (State.stations[0] ? State.stations[0].id : null);
  const station = State.stations.find(s => s.id === targetId) || State.stations[0];
  if (station) {
    populateThresholdsEditor(station);
  }
}

function closeThresholdsModal() {
  const modal = document.getElementById('modal-umbrales');
  if (modal) {
    modal.style.display = 'none';
    modal.classList.add('hidden');
  }
}

function handleModalBackdropClick(event) {
  if (event.target.id === 'modal-umbrales') {
    closeThresholdsModal();
  }
}

function populateThresholdsEditor(station) {
  if (!station && State.stations.length > 0) {
    station = State.stations.find(s => s.id === State.selectedStationId) || State.stations[0];
  }
  if (!station) return;

  // 1. Selector de estación dentro del modal
  const select = document.getElementById('threshold-station-select');
  if (select) {
    if (select.options.length === 0 || select.options.length !== State.stations.length) {
      const seen = new Set();
      const options = [];
      for (const s of State.stations) {
        const cleanName = (s.nombre || '').trim();
        if (!cleanName) continue;
        const key = cleanName.toLowerCase();
        if (seen.has(key)) continue;
        seen.add(key);

        const altStr = (s.ultima_altura !== null && s.ultima_altura !== undefined) ? `${Number(s.ultima_altura).toFixed(2)}m` : '—';
        const pnaStr = (s.pna_altura !== null && s.pna_altura !== undefined) ? ` | ⚓ PNA: ${Number(s.pna_altura).toFixed(2)}m` : '';
        const failNotice = s.falla_reporte ? ' ⚠️' : '';
        options.push(`<option value="${s.id}">${cleanName} (AGP: ${altStr}${pnaStr})${failNotice}</option>`);
      }
      select.innerHTML = options.join('');
    }
    select.value = station.id;
  }

  // 2. Telemetría de la estación
  const nameEl = document.getElementById('threshold-preview-name');
  const basinEl = document.getElementById('threshold-preview-basin');
  const heightEl = document.getElementById('threshold-preview-height');
  const statusEl = document.getElementById('threshold-preview-status');

  if (nameEl) nameEl.textContent = `${station.nombre} (${station.codigo})`;
  if (basinEl) {
    const rioStr = station.rio || 'Cuenca del Plata';
    const failNotice = station.falla_reporte ? ' <span class="text-amber-500 font-bold ml-1" title="Retraso en reporte">⚠️</span>' : '';
    basinEl.innerHTML = `Río / Cuenca: ${rioStr} • Muestreo esperado: cada ${station.frecuencia_minutos || 20} min${failNotice}`;
  }
  if (heightEl) {
    const agpStr = (station.ultima_altura !== null && station.ultima_altura !== undefined)
      ? `${Number(station.ultima_altura).toFixed(2)} m`
      : '—';
    const pnaStr = (station.pna_altura !== null && station.pna_altura !== undefined)
      ? `${Number(station.pna_altura).toFixed(2)} m`
      : null;
    if (pnaStr !== null) {
      heightEl.innerHTML = `<span class="text-sky-600 dark:text-sky-400 font-bold tabular-nums">${agpStr}</span> <span class="text-slate-400 font-normal">|</span> <span class="text-amber-600 dark:text-amber-400 font-bold tabular-nums" title="Prefectura">⚓ ${pnaStr}</span>`;
    } else {
      heightEl.innerHTML = `<span class="text-sky-600 dark:text-sky-400 font-bold tabular-nums">${agpStr}</span>`;
    }
  }

  // 3. Sincronización del Interruptor de Alertas Activas / Silenciadas
  const activeCheckbox = document.getElementById('input-thresh-active');
  const isActive = station.alertas_activas !== false && (station.umbrales?.alertas_activas !== false);
  if (activeCheckbox) {
    activeCheckbox.checked = isActive;
    onThresholdActiveToggle(isActive);
  }

  const st = station.estado_hidrologico || 'normal';
  const badgeColors = {
    normal: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300',
    alerta: 'bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300',
    evacuacion: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300',
    desactivado: 'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300'
  };

  if (statusEl) {
    if (!isActive) {
      statusEl.className = 'text-[10px] font-bold px-2 py-1 rounded-md uppercase bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300';
      statusEl.textContent = 'ALERTAS SILENCIADAS';
    } else {
      statusEl.className = `text-[10px] font-bold px-2 py-1 rounded-md uppercase ${badgeColors[st] || badgeColors.normal}`;
      statusEl.textContent = st.toUpperCase();
    }
  }

  // 4. Inputs numéricos de los umbrales oficiales PNA (Alerta y Evacuación)
  const umb = station.umbrales || {};
  const setInp = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.value = (val !== null && val !== undefined) ? val : '';
  };

  setInp('input-thresh-alerta', umb.alerta);
  setInp('input-thresh-evacuacion', umb.evacuacion);

  // 5. Tabla de referencia y conmutación de todas las estaciones
  const searchInput = document.getElementById('input-thresh-table-search');
  renderThresholdModalQuickList(searchInput ? searchInput.value : '', station.id);
}

function onThresholdActiveToggle(checked) {
  const badge = document.getElementById('badge-thresh-active-state');
  if (badge) {
    if (checked) {
      badge.className = 'text-[10px] font-bold px-2 py-0.5 rounded-full uppercase shrink-0 bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300';
      badge.textContent = 'ACTIVO';
    } else {
      badge.className = 'text-[10px] font-bold px-2 py-0.5 rounded-full uppercase shrink-0 bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-400';
      badge.textContent = 'SILENCIADA';
    }
  }
}

function filterThresholdModalTable(query) {
  const select = document.getElementById('threshold-station-select');
  const currentId = select ? parseInt(select.value) : State.selectedStationId;
  renderThresholdModalQuickList(query, currentId);
}

function renderThresholdModalQuickList(query = '', activeStationId = null) {
  const quickList = document.getElementById('threshold-modal-quick-list');
  if (!quickList || !State.stations) return;

  const q = (query || '').toLowerCase().trim();
  let stations = State.stations;
  if (q) {
    stations = stations.filter(s => 
      (s.nombre || '').toLowerCase().includes(q) || 
      (s.codigo || '').toLowerCase().includes(q) || 
      (s.rio || '').toLowerCase().includes(q)
    );
  }

  if (stations.length === 0) {
    quickList.innerHTML = `
      <tr>
        <td colspan="7" class="py-4 text-center text-xs text-slate-400 font-sans">
          No se encontraron estaciones para "${query}"
        </td>
      </tr>
    `;
    return;
  }

  quickList.innerHTML = stations.map(s => {
    const u = s.umbrales || {};
    const isCur = s.id === (activeStationId || State.selectedStationId);
    const isAct = s.alertas_activas !== false && (u.alertas_activas !== false);
    const isFail = s.falla_reporte === true;

    return `
      <tr class="transition ${isCur ? 'bg-sky-50 dark:bg-sky-950/40 font-bold' : 'hover:bg-slate-50 dark:hover:bg-slate-900/40'}">
        <td class="py-2 px-3 text-slate-800 dark:text-slate-100 font-sans font-semibold">
          <div>${s.nombre}</div>
          <div class="text-[10px] font-normal text-slate-400 flex items-center gap-1 font-mono">
            <span>${s.codigo}</span>
            ${isFail ? `<span class="text-amber-500 font-bold ml-1" title="Última lectura: ${s.ultimo_timestamp || 'Sin datos'}">⚠️</span>` : ''}
          </div>
        </td>
        <td class="py-2 px-2 text-center">
          <button type="button" onclick="window.toggleStationAlerts(${s.id})" class="px-2 py-0.5 rounded text-[10px] font-bold ${isAct ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 hover:bg-rose-100 hover:text-rose-700 dark:hover:bg-rose-950 dark:hover:text-rose-300' : 'bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-400 hover:bg-emerald-100 hover:text-emerald-700 dark:hover:bg-emerald-950 dark:hover:text-emerald-300'} transition cursor-pointer" title="${isAct ? 'Clic para desactivar alertas para ' + s.nombre : 'Clic para activar alertas para ' + s.nombre}">
            ${isAct ? '🔔 Activa' : '🔕 Desactivada'}
          </button>
        </td>
        <td class="py-2 px-2 text-center text-orange-600 dark:text-orange-400 font-mono tabular-nums">${u.alerta !== null && u.alerta !== undefined ? Number(u.alerta).toFixed(2) : '—'}</td>
        <td class="py-2 px-2 text-center text-rose-600 dark:text-rose-400 font-mono tabular-nums">${u.evacuacion !== null && u.evacuacion !== undefined ? Number(u.evacuacion).toFixed(2) : '—'}</td>
        <td class="py-2 px-2 text-center">
          <button type="button" onclick="onThresholdStationSelected(${s.id})" class="px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 hover:bg-sky-100 dark:bg-slate-800 dark:hover:bg-sky-950/60 text-slate-700 dark:text-slate-300 hover:text-sky-700 dark:hover:text-sky-400 transition cursor-pointer">
            ${isCur ? 'Editando' : 'Editar'}
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

async function toggleStationAlerts(stationId) {
  const station = State.stations.find(s => s.id === stationId);
  if (!station) return;
  const currentActive = station.alertas_activas !== false && (station.umbrales?.alertas_activas !== false);
  const newActive = !currentActive;

  try {
    const res = await API.saveThresholds(station.codigo, {
      alertas_activas: newActive
    });
    if (res && res.success) {
      station.alertas_activas = newActive;
      if (station.umbrales) station.umbrales.alertas_activas = newActive;
      Components.showToast(
        newActive ? 'Alertas Habilitadas' : 'Alertas Desactivadas',
        `Alertas ${newActive ? 'activadas' : 'silenciadas'} para ${station.nombre}`
      );

      // Refrescar situación global y alertas
      const sitData = await API.getSituation();
      if (sitData && sitData.success) {
        State.situation = sitData;
        Components.renderAlertBanner('alert-banner-container', sitData.alertas_activas, window.selectStation, sitData.estaciones_falla_reporte);
      }

      // Refrescar catálogo
      const updatedCat = await API.getStations();
      if (updatedCat && updatedCat.success) {
        State.stations = updatedCat.estaciones || [];
        State.filteredStations = [...State.stations];
        Components.renderStationList(State.filteredStations, State.selectedStationId, window.selectStation);
      }

      // Si el modal de umbrales está visible, refrescar editor y tabla
      const modal = document.getElementById('modal-umbrales');
      if (modal && !modal.classList.contains('hidden')) {
        const select = document.getElementById('threshold-station-select');
        const curId = select ? parseInt(select.value) : station.id;
        const currentSt = State.stations.find(s => s.id === curId) || station;
        populateThresholdsEditor(currentSt);
      }

      // Si la estación actual en gráficos es esta, recargar visualización
      if (State.selectedStationId === station.id && State.selectedStationData) {
        await selectStation(station.id, false);
      }
    }
  } catch (err) {
    console.error('Error conmutando alertas:', err);
    Components.showToast('Error', err.message, true);
  }
}

function onThresholdStationSelected(stationId) {
  const station = State.stations.find(s => s.id === parseInt(stationId));
  if (station) {
    populateThresholdsEditor(station);
  }
}

function selectThresholdStation(stationId) {
  const station = State.stations.find(s => s.id === stationId);
  if (station) {
    populateThresholdsEditor(station);
  }
}

async function handleThresholdsFormSubmit(event) {
  if (event) event.preventDefault();
  const select = document.getElementById('threshold-station-select');
  if (!select) return;
  const stationId = parseInt(select.value);
  const station = State.stations.find(s => s.id === stationId);
  if (!station) return;

  const getNum = (id) => {
    const el = document.getElementById(id);
    if (!el) return null;
    const v = el.value.trim();
    return v === '' ? null : parseFloat(v);
  };

  const activeCheckbox = document.getElementById('input-thresh-active');
  const payload = {
    alerta: getNum('input-thresh-alerta'),
    evacuacion: getNum('input-thresh-evacuacion'),
    alertas_activas: activeCheckbox ? activeCheckbox.checked : true
  };

  const btn = document.getElementById('btn-save-thresholds');
  if (btn) btn.disabled = true;

  try {
    const res = await API.saveThresholds(station.codigo, payload);
    if (res && res.success) {
      station.umbrales = res.umbrales;
      Components.showToast('Umbrales guardados', `Niveles actualizados para ${station.nombre}`);

      // Recalcular situación global y alertas
      const sitData = await API.getSituation();
      if (sitData && sitData.success) {
        State.situation = sitData;
        Components.renderAlertBanner('alert-banner-container', sitData.alertas_activas, window.selectStation, sitData.estaciones_falla_reporte);
      }

      // Actualizar catálogo de estaciones
      const updatedCatalog = await API.getStations();
      if (updatedCatalog && updatedCatalog.success) {
        State.stations = updatedCatalog.estaciones || [];
        State.filteredStations = [...State.stations];
      }

      // Si es la estación actualmente activa en gráficos, recargar visualización
      if (State.selectedStationId === station.id) {
        await selectStation(station.id, false);
      }

      const updatedSt = State.stations.find(s => s.id === station.id) || station;
      populateThresholdsEditor(updatedSt);
    } else {
      Components.showToast('Error', res.error || 'No se pudieron guardar los umbrales', true);
    }
  } catch (err) {
    console.error('Error al guardar umbrales:', err);
    Components.showToast('Error al guardar', err.message, true);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function handleResetThresholds() {
  const select = document.getElementById('threshold-station-select');
  if (!select) return;
  const stationId = parseInt(select.value);
  const station = State.stations.find(s => s.id === stationId);
  if (!station) return;

  try {
    const res = await API.resetThresholds(station.codigo);
    if (res && res.success) {
      station.umbrales = res.umbrales;
      Components.showToast('Umbrales restablecidos', `Valores restaurados para ${station.nombre}`);

      const sitData = await API.getSituation();
      if (sitData && sitData.success) {
        State.situation = sitData;
        Components.renderAlertBanner('alert-banner-container', sitData.alertas_activas, window.selectStation, sitData.estaciones_falla_reporte);
      }

      const updatedCatalog = await API.getStations();
      if (updatedCatalog && updatedCatalog.success) {
        State.stations = updatedCatalog.estaciones || [];
        State.filteredStations = [...State.stations];
      }

      if (State.selectedStationId === station.id) {
        await selectStation(station.id, false);
      }

      const updatedSt = State.stations.find(s => s.id === station.id) || station;
      populateThresholdsEditor(updatedSt);
    }
  } catch (err) {
    Components.showToast('Error', err.message, true);
  }
}

/**
 * Sincronización oficial bajo demanda con Prefectura Naval Argentina (PNA)
 */
async function handleSyncPrefecturaClick() {
  const icon = document.getElementById('sync-pna-icon');
  const btn = document.getElementById('btn-sync-pna');
  if (icon) icon.classList.add('animate-spin');
  if (btn) btn.disabled = true;

  try {
    const res = await API.syncPrefectura();
    if (res && res.success) {
      Components.showToast('Prefectura Sincronizada', `${res.updated_stations} umbrales actualizados desde PNA`);

      // Recargar catálogo de estaciones
      const estData = await API.getStations();
      if (estData && estData.success) {
        State.stations = estData.estaciones || [];
        State.filteredStations = [...State.stations];
        populateChartsStationSelect();
      }

      // Recalcular situación general
      const sitData = await API.getSituation();
      if (sitData && sitData.success) {
        State.situation = sitData;
        Components.renderAlertBanner('alert-banner-container', sitData.alertas_activas, window.selectStation, sitData.estaciones_falla_reporte);
      }

      // Actualizar el editor del modal con la estación actualmente seleccionada
      const select = document.getElementById('threshold-station-select');
      const currentStationId = select ? parseInt(select.value) : State.selectedStationId;
      const st = State.stations.find(s => s.id === currentStationId) || State.stations[0];
      if (st) populateThresholdsEditor(st);

      // Si está en gráficos, refrescar vista
      if (State.selectedStationId) {
        await selectStation(State.selectedStationId, false);
      }
    } else {
      Components.showToast('Error', res.error || 'No se pudo sincronizar con Prefectura', true);
    }
  } catch (err) {
    console.error('Error sincronizando Prefectura:', err);
    Components.showToast('Error de conexión', err.message, true);
  } finally {
    if (icon) icon.classList.remove('animate-spin');
    if (btn) btn.disabled = false;
  }
}

// Compatibilidad con funciones previas (stubs seguros)
function toggleSidebar() {
  openThresholdsModal();
}
function updateSidebarUI() {}
function switchSidebarTab() {}
function renderSidebarAlerts() {}
function openThresholdsSidebar(stationId = null) {
  openThresholdsModal(stationId);
}

/**
 * Manejo de Tema (Claro / Oscuro)
 */
function toggleTheme() {
  State.toggleTheme();
  updateThemeIcon();

  if (MapView.map) {
    MapView.updateBaseTile(State.theme === 'dark');
  }

  if (State.viewMode === 'caudales' && window.RepresasView && RepresasView.data) {
    RepresasView.renderCharts(RepresasView.data.timeline || [], State.theme === 'dark');
  } else if (State.layout === 1 && State.selectedStationId && State.selectedStationData) {
    const isPosadas = State.selectedStationData.estacion.codigo === 'POSADAS';
    const isCota = isPosadas && State.posadasMode === 'cota';
    Charts.renderMainChart(
      'mainHeightChart',
      State.selectedStationData.puntos || [],
      State.selectedStationData.kpis,
      isCota,
      State.posadasOffset,
      State.theme === 'dark'
    );
  } else if (State.layout > 1) {
    Charts.renderSubplots(
      'subplots-grid',
      State.layout,
      State.subplotStationIds,
      State.stations,
      State.range,
      State.theme === 'dark',
      window.selectStation
    );
  }
}

function updateThemeIcon() {
  const isDark = State.theme === 'dark';
  const sunIcon = document.getElementById('theme-icon-sun');
  const moonIcon = document.getElementById('theme-icon-moon');
  if (sunIcon) sunIcon.style.display = isDark ? 'inline-block' : 'none';
  if (moonIcon) moonIcon.style.display = isDark ? 'none' : 'inline-block';
}

/**
 * Cota Posadas
 */
function setPosadasMode(mode) {
  State.posadasMode = mode;
  document.getElementById('btn-posadas-nivel').classList.toggle('active', mode === 'nivel');
  document.getElementById('btn-posadas-cota').classList.toggle('active', mode === 'cota');

  if (State.selectedStationId) {
    selectStation(State.selectedStationId, false);
  }
}

function setPosadasOffset(val) {
  const num = parseFloat(val);
  if (!isNaN(num)) {
    State.posadasOffset = num;
    if (State.posadasMode === 'cota' && State.selectedStationId) {
      selectStation(State.selectedStationId, false);
    }
  }
}

/**
 * Descarga CSV
 */
function downloadCSV() {
  if (!State.selectedStationId) return;
  const isPosadas = State.selectedStationData && State.selectedStationData.estacion.codigo === 'POSADAS';
  const isCota = isPosadas && State.posadasMode === 'cota';
  const url = API.getExportUrl(State.selectedStationId, State.range, isCota, State.posadasOffset);
  window.location.href = url;
}

/**
 * Polling en Tiempo Real (cada 60s) y Gestión de Visibilidad
 */
let _pollTimer = null;
let _isPolling = false;
const POLL_INTERVAL_MS = 60000;

async function pollRealtimeData() {
  if (document.hidden || _isPolling) return;
  _isPolling = true;

  try {
    // 1. Recargar situación general, alertas y estado de fuentes
    const sitData = await API.getSituation();
    if (sitData && sitData.success) {
      State.situation = sitData;
      if (sitData.sources_status && window.Components && typeof Components.renderSourcesHeader === 'function') {
        Components.renderSourcesHeader(sitData.sources_status);
      }
      Components.renderAlertBanner('alert-banner-container', sitData.alertas_activas, window.selectStation, sitData.estaciones_falla_reporte);
    }

    // 2. Recargar catálogo de estaciones (actualiza alturas en memoria)
    const estData = await API.getStations();
    if (estData && estData.success) {
      State.stations = estData.estaciones || [];
      const searchInput = document.getElementById('search-station');
      if (!searchInput || !searchInput.value.trim()) {
        filterStations();
      }
    }

    // 3. Actualizar la vista activa de forma suave sin destruir componentes
    if (State.viewMode === 'caudales') {
      if (window.RepresasView && typeof RepresasView.loadData === 'function') {
        await RepresasView.loadData();
      }
    } else if (State.viewMode === 'charts') {
      if (State.layout === 1 && State.selectedStationId) {
        await selectStation(State.selectedStationId, false);
      } else if (State.layout > 1) {
        for (let i = 0; i < State.layout; i++) {
          if (State.subplotStationIds[i]) {
            Charts.loadSubplotData(i, State.subplotStationIds[i], true);
          }
        }
      }
    } else if (State.viewMode === 'map') {
      if (window.MapView && MapView.map) {
        MapView.renderStations(State.stations, State.selectedStationId, window.selectStation);
        if (window.RepresasView && RepresasView.data) {
          MapView.renderDams(RepresasView.data);
        }
      }
    }
  } catch (err) {
    console.warn('Advertencia en ciclo de polling:', err);
  } finally {
    _isPolling = false;
  }
}

function startPollingCycle() {
  stopPollingCycle();
  _pollTimer = setInterval(() => {
    if (!document.hidden) {
      pollRealtimeData();
    }
  }, POLL_INTERVAL_MS);
}

function stopPollingCycle() {
  if (_pollTimer) {
    clearInterval(_pollTimer);
    _pollTimer = null;
  }
}

// Escuchar cambios de visibilidad para suspender y reactivar peticiones sin desperdicio
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) {
    pollRealtimeData();
    startPollingCycle();
  } else {
    stopPollingCycle();
  }
});

/**
 * Sincronización Global Unificada bajo demanda (invoca POST /api/sync)
 */
async function syncAll() {
  const syncBtn = document.getElementById('btn-sync-all');
  const syncIcon = document.getElementById('sync-icon');
  const syncText = document.getElementById('sync-btn-label') || document.getElementById('sync-text');

  if (syncIcon) syncIcon.classList.add('animate-spin');
  if (syncBtn) syncBtn.disabled = true;
  if (syncText) syncText.textContent = 'Actualizando...';

  Components.showToast('Sincronizando', 'Consultando telemetría oficial y fuentes en paralelo...');

  try {
    const res = await API.syncAll();

    if (res && res.cooldown) {
      const waitSec = res.wait_seconds || 60;
      Components.showToast('Enfriamiento', res.message || `Espera ${waitSec}s antes de otra sincronización manual.`);
      return;
    }

    // Refrescar todas las vistas de forma inmediata
    await pollRealtimeData();

    if (window.RepresasView && typeof RepresasView.loadData === 'function') {
      await RepresasView.loadData();
    }

    Components.showToast('Actualizado', 'Datos sincronizados exitosamente.');
  } catch (err) {
    console.error('Error durante sincronización global:', err);
    Components.showToast('Error de sincronización', err.message || 'No se pudieron actualizar los datos', true);
  } finally {
    if (syncIcon) syncIcon.classList.remove('animate-spin');
    if (syncBtn) syncBtn.disabled = false;
    if (syncText) syncText.textContent = 'Actualizar';
  }
}

async function syncCurrentStation() {
  return syncAll();
}

async function syncAllStations() {
  return syncAll();
}

/**
 * Monitoreo de Sincronización Automática y Fuentes
 */
function initSyncTicker() {
  const updateTicker = async () => {
    try {
      const data = await API.getSyncStatus();
      if (data && data.success) {
        State.syncStatus = data;
        const syncBadge = document.getElementById('header-sync-status');
        if (syncBadge && data.next_auto_sync) {
          syncBadge.textContent = `Próx. Auto-Sync: ${data.next_auto_sync}`;
        }
        if (data.sources_status && window.Components && typeof Components.renderSourcesHeader === 'function') {
          Components.renderSourcesHeader(data.sources_status);
        }
      }
    } catch (e) {
      // Ignorar errores transitorios de red
    }
  };

  updateTicker();
  setInterval(updateTicker, 30000);
}

/**
 * Atajos de teclado
 */
function initShortcuts() {
  document.addEventListener('keydown', (e) => {
    // Ctrl + B o Cmd + B para abrir / alternar modal de umbrales
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
      e.preventDefault();
      const modal = document.getElementById('modal-umbrales');
      if (modal && !modal.classList.contains('hidden')) {
        closeThresholdsModal();
      } else {
        openThresholdsModal();
      }
    }
    // Escape para cerrar modal de umbrales, desplegable de alertas y calendario
    if (e.key === 'Escape') {
      closeThresholdsModal();
      if (window.Components && typeof Components.closeAlertsDropdown === 'function') {
        Components.closeAlertsDropdown();
      }
      SimeparView.closeCalendar();
    }
  });

  // Cerrar desplegable de alertas si se hace clic fuera de él
  document.addEventListener('click', (e) => {
    const panel = document.getElementById('alerts-dropdown-panel');
    const toggleBtn = document.getElementById('btn-ticker-alerts-toggle');
    if (panel && !panel.classList.contains('hidden')) {
      if (!panel.contains(e.target) && !toggleBtn?.contains(e.target)) {
        if (window.Components && typeof Components.closeAlertsDropdown === 'function') {
          Components.closeAlertsDropdown();
        }
      }
    }
  });
}

// ==========================================================
// EXPOSICIÓN GLOBAL A WINDOW PARA EVENT HANDLERS EN HTML
// ==========================================================
window.selectStation = selectStation;
window.selectStationFromAlert = (id) => {
  setViewMode('charts');
  setLayout(1);
  selectStation(id, true);
};
window.filterStations = filterStations;
window.setBasinFilter = setBasinFilter;
window.setViewMode = setViewMode;
window.setLayout = setLayout;
window.setRange = setRange;
window.toggleSidebar = toggleSidebar;
window.toggleTheme = toggleTheme;
window.setPosadasMode = setPosadasMode;
window.setPosadasOffset = setPosadasOffset;
window.downloadCSV = downloadCSV;
window.resetZoom = () => Charts.resetZoom();
window.syncAll = syncAll;
window.syncCurrentStation = syncAll;
window.syncAllStations = syncAll;

// DESPLEGABLE DE ALERTAS & TICKER
window.toggleAlertsDropdown = (e) => {
  if (window.Components && typeof Components.toggleAlertsDropdown === 'function') {
    Components.toggleAlertsDropdown(e);
  }
};
window.closeAlertsDropdown = () => {
  if (window.Components && typeof Components.closeAlertsDropdown === 'function') {
    Components.closeAlertsDropdown();
  }
};
window.switchAlertsTab = (tab) => {
  if (window.Components && typeof Components.switchAlertsTab === 'function') {
    Components.switchAlertsTab(tab);
  }
};
window.filterAlertsDropdown = (q) => {
  if (window.Components && typeof Components.filterAlertsDropdown === 'function') {
    Components.filterAlertsDropdown(q);
  }
};

window.onSubplotStationChange = (index, val) => {
  const stationId = parseInt(val);
  State.subplotStationIds[index] = stationId;
  Charts.loadSubplotData(index, stationId, false);
};

window.goToStationCharts = async (stationIdOrCode) => {
  let targetId = null;
  if (typeof stationIdOrCode === 'number') {
    targetId = stationIdOrCode;
  } else if (typeof stationIdOrCode === 'string') {
    const num = parseInt(stationIdOrCode);
    if (!isNaN(num) && String(num) === stationIdOrCode.trim()) {
      targetId = num;
    } else {
      const code = stationIdOrCode.trim().toUpperCase();
      let st = State.stations.find(s => s.codigo && s.codigo.toUpperCase() === code);
      if (!st) {
        st = State.stations.find(s => s.nombre && s.nombre.toUpperCase().includes(code));
      }
      if (st) targetId = st.id;
    }
  }

  if (!targetId) {
    try {
      const res = await API.getStations();
      if (res && res.success) {
        State.stations = res.estaciones || [];
        if (typeof stationIdOrCode === 'string') {
          const code = stationIdOrCode.trim().toUpperCase();
          let st = State.stations.find(s => s.codigo && s.codigo.toUpperCase() === code);
          if (!st) st = State.stations.find(s => s.nombre && s.nombre.toUpperCase().includes(code));
          if (st) targetId = st.id;
        }
      }
    } catch (e) {
      console.warn('Error refrescando estaciones:', e);
    }
  }

  if (targetId) {
    // 1. Cambiar a la pestaña de Hidrómetros (Gráficos)
    setViewMode('charts');

    // 2. Establecer la vista en modo de un solo gráfico (layout = 1)
    setLayout(1);

    // 3. Seleccionar la estación y cargar sus mediciones
    await selectStation(targetId, false);

    // 4. Scroll suave hacia la vista de hidrómetros
    const chartsView = document.getElementById('view-charts-container');
    if (chartsView) {
      chartsView.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  } else {
    setViewMode('caudales');
  }
};

window.focusStationInSingleMode = window.goToStationCharts;

// SIMEPAR
window.selectSimeparDate = (dateStr) => {
  SimeparView.selectedDate = dateStr;
  const parts = dateStr.split('-');
  SimeparView.currentCalendarMonth = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, 1);
  SimeparView.renderImage();
  SimeparView.updateControls();
  SimeparView.closeCalendar();
};
window.stepSimeparDate = (delta) => SimeparView.stepDate(delta);
window.toggleSimeparCalendar = () => SimeparView.toggleCalendar();
window.changeSimeparMonth = (delta) => SimeparView.changeMonth(delta);
window.goToLatestSimeparDate = () => SimeparView.goToLatest();
window.syncSimeparMap = () => SimeparView.syncMapOnDemand();

// RADAR
window.toggleRadar = (active) => MapView.toggleRadar(active);
window.toggleRadarPlay = () => MapView.toggleRadarPlay();
window.stepRadarSlider = (val) => MapView.showRadarFrame(parseInt(val));
window.setRadarOpacity = (val) => MapView.setRadarOpacity(val);
window.zoomMapToRegion = (reg) => MapView.zoomToRegion(reg);
window.onMapStationSelectChange = (id) => {
  if (id) {
    const stId = parseInt(id);
    const station = State.stations.find(s => s.id === stId);
    if (station) {
      selectStation(stId, true);
    }
  }
};

// REPRESAS / CAUDALES
window.syncRepresasData = () => {
  if (window.RepresasView) window.RepresasView.syncRepresasData();
};

// PANEL OPERATIVO & CONFIGURACIÓN DE UMBRALES EN MODAL
window.populateChartsStationSelect = populateChartsStationSelect;
window.selectStationByCode = selectStationByCode;
window.openThresholdsModal = openThresholdsModal;
window.closeThresholdsModal = closeThresholdsModal;
window.handleModalBackdropClick = handleModalBackdropClick;
window.openThresholdsSidebar = openThresholdsModal;
window.onThresholdStationSelected = onThresholdStationSelected;
window.selectThresholdStation = selectThresholdStation;
window.handleThresholdsFormSubmit = handleThresholdsFormSubmit;
window.handleResetThresholds = handleResetThresholds;
window.handleSyncPrefecturaClick = handleSyncPrefecturaClick;
window.renderSidebarAlerts = renderSidebarAlerts;
window.switchSidebarTab = switchSidebarTab;
window.onThresholdActiveToggle = onThresholdActiveToggle;
window.filterThresholdModalTable = filterThresholdModalTable;
window.toggleStationAlerts = toggleStationAlerts;
window.renderThresholdModalQuickList = renderThresholdModalQuickList;
window.setChartSource = setChartSource;
window.pollRealtimeData = pollRealtimeData;
