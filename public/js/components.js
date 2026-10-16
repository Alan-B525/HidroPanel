/**
 * public/js/components.js
 * Renderizadores de Componentes UI: Situación, Nivel-Bar, KPIs, Alertas y Tabla
 * Arquitectura Tailwind CSS (Slate / Sky / Emerald) con soporte Dark Mode
 */

const Components = {
  /**
   * Formateador unificado de fechas y horas para toda la plataforma
   * Normaliza formatos heterogéneos ('2026-10-16 11:00:00', '16/10/26 08h', '16/10/2026 08:00', ISO)
   * a un formato estándar argentino: DD/MM/YYYY HH:mm (con opción 'hs')
   */
  formatDateTime(val, showHs = false) {
    if (!val || val === '--' || val === 'Sin datos' || val === 'None' || val === 'null') return '--';
    const s = String(val).trim();

    // 1. Caso '16/10/26 08h', '16/10/2026 08h', '16/10/2026 08:00'
    let m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})(?:[T\s](\d{1,2})(?::(\d{2}))?(?::\d{2})?)?h?$/);
    if (m) {
      const d = m[1].padStart(2, '0');
      const mo = m[2].padStart(2, '0');
      let y = m[3];
      if (y.length === 2) y = '20' + y;
      const h = (m[4] !== undefined ? m[4] : '00').padStart(2, '0');
      const mi = (m[5] !== undefined ? m[5] : '00').padStart(2, '0');
      return `${d}/${mo}/${y} ${h}:${mi}${showHs ? ' hs' : ''}`;
    }

    // 2. Caso ISO '2026-10-16 11:00:00' o '2026-10-16T11:00:00'
    m = s.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T\s](\d{2}):(\d{2})(?::\d{2})?)?/);
    if (m) {
      const y = m[1];
      const mo = m[2];
      const d = m[3];
      const h = m[4] || '00';
      const mi = m[5] || '00';
      return `${d}/${mo}/${y} ${h}:${mi}${showHs ? ' hs' : ''}`;
    }

    return s;
  },

  /**
   * Renderiza la barra superior de alertas estilo Ticker / Carrusel Continuo
   * y el botón desplegable con el detalle completo de alertas y fallas de telemetría.
   */
  renderAlertBanner(containerId, activeAlerts, onSelectStation, failedStations = null) {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.classList.remove('hidden');
    container.classList.add('relative');

    const hasAlerts = activeAlerts && activeAlerts.length > 0;
    const sorted = hasAlerts ? [...activeAlerts].sort((a, b) => {
      const order = { evacuacion: 1, alerta: 2 };
      return (order[a.estado] || 99) - (order[b.estado] || 99);
    }) : [];

    const failed = failedStations || (window.State && window.State.situation ? window.State.situation.estaciones_falla_reporte : []) || [];

    Components._activeAlerts = sorted;
    Components._failedStations = failed;

    let itemsHtml = '';
    let badgeText = '';
    let badgeClass = '';

    if (hasAlerts) {
      badgeText = `ALERTAS CUENCA (${sorted.length})`;
      badgeClass = 'text-rose-400 border-rose-500/30';

      const renderItem = (a) => {
        const stateClass = `item-${a.estado}`;
        const dotColor = a.estado === 'evacuacion' ? 'bg-red-500 animate-pulse' : 'bg-amber-400';
        const valStr = (a.altura !== null && a.altura !== undefined) ? `${a.altura.toFixed(2)}m` : '--';
        const umbStr = a.umbrales && a.umbrales[a.estado] ? `(Umbral: ${a.umbrales[a.estado]}m)` : '';
        const trendIcon = a.tendencia === 'creciente' ? '▲' : (a.tendencia === 'bajante' ? '▼' : '―');
        const trendCol = a.tendencia === 'creciente' ? 'text-rose-400' : (a.tendencia === 'bajante' ? 'text-emerald-400' : 'text-slate-400');

        return `
          <div onclick="window.selectStationFromAlert(${a.id})" class="ticker-item ${stateClass}" title="Ver hidrograma de ${a.nombre}">
            <span class="w-2 h-2 rounded-full ${dotColor}"></span>
            <span class="font-bold text-slate-100">${a.nombre}:</span>
            <span class="font-data font-extrabold text-white">${valStr}</span>
            <span class="text-[10px] uppercase font-semibold opacity-90">${a.estado}</span>
            <span class="text-[9px] text-slate-300 font-mono">${umbStr}</span>
            <span class="${trendCol} text-[10px] font-bold">${trendIcon}</span>
          </div>
        `;
      };

      const baseItems = sorted.map(renderItem).join('');
      // Duplicar para conseguir el loop continuo perfecto
      itemsHtml = `${baseItems}${baseItems}`;
    } else {
      // Estado normal: ticker informativo y discreto
      badgeText = `CUENCA DEL PLATA`;
      badgeClass = 'text-emerald-400 border-emerald-500/30';

      const normalItems = [
        `<div class="ticker-item"><span class="w-2 h-2 rounded-full bg-emerald-400"></span><span class="font-medium">Niveles hidrológicos estables y dentro de rangos normales</span></div>`,
        `<div class="ticker-item"><span class="w-2 h-2 rounded-full bg-sky-400"></span><span class="font-medium">Prefectura Naval Argentina: 55 estaciones hidrométricas sincronizadas</span></div>`,
        `<div class="ticker-item"><span class="w-2 h-2 rounded-full bg-teal-400"></span><span class="font-medium">Yacyretá: Central y Vertederos operando según programa hidrológico</span></div>`,
        `<div class="ticker-item"><span class="w-2 h-2 rounded-full bg-emerald-400"></span><span class="font-medium">Monitoreo continuo de cotas y caudales en tiempo real</span></div>`
      ].join('');

      itemsHtml = `${normalItems}${normalItems}`;
    }

    const prevPanel = document.getElementById('alerts-dropdown-panel');
    const wasOpen = prevPanel && !prevPanel.classList.contains('hidden');

    container.innerHTML = `
      <div class="ticker-wrapper">
        <!-- Badge Fijo a la Izquierda -->
        <div class="ticker-badge ${badgeClass}">
          <span class="w-2 h-2 rounded-full ${hasAlerts ? 'bg-rose-500 animate-ping' : 'bg-emerald-400'}"></span>
          <span>${badgeText}</span>
        </div>

        <!-- Ticker Track con animación continua de carrusel (95s velocidad lenta y legible) -->
        <div class="ticker-track-container">
          <div class="ticker-track">
            ${itemsHtml}
          </div>
        </div>

        <!-- Botón Desplegable de Detalle de Alertas -->
        <div class="ticker-controls">
          <button id="btn-ticker-alerts-toggle" type="button" onclick="window.toggleAlertsDropdown(event)" 
                  class="flex items-center space-x-1.5 px-2.5 sm:px-3 py-1 rounded ${hasAlerts ? 'bg-rose-600 hover:bg-rose-700 active:bg-rose-800' : 'bg-[#008348] hover:bg-[#006e3c] active:bg-[#005a31]'} text-white font-bold text-[10px] tracking-wide uppercase transition shadow-xs cursor-pointer" 
                  title="Ver detalle completo de todas las alertas y estaciones">
            <span class="relative flex h-2 w-2">
              <span class="${hasAlerts ? 'animate-ping' : ''} absolute inline-flex h-full w-full rounded-full ${hasAlerts ? 'bg-rose-300' : 'bg-emerald-300'} opacity-75"></span>
              <span class="relative inline-flex rounded-full h-2 w-2 ${hasAlerts ? 'bg-rose-100' : 'bg-emerald-100'}"></span>
            </span>
            <span id="btn-ticker-alerts-label">DETALLE</span>
            <svg id="icon-alerts-dropdown-arrow" class="w-3 h-3 text-white/90 transition-transform duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- Menú Desplegable Flotante con el Detalle de Alertas y Fallas de Transmisión -->
      <div id="alerts-dropdown-panel" class="${wasOpen ? '' : 'hidden'} absolute right-2 top-[36px] w-[460px] max-w-[95vw] bg-white dark:bg-[#0b1c32] border border-slate-200 dark:border-slate-700/80 rounded-xl shadow-2xl z-50 overflow-hidden flex flex-col max-h-[78vh] animate-dropdown" style="display: ${wasOpen ? 'flex' : 'none'};" onclick="event.stopPropagation()">
        
        <!-- Header del Desplegable -->
        <div class="p-3 border-b border-slate-100 dark:border-slate-800/80 bg-slate-50 dark:bg-slate-900/60 flex items-center justify-between">
          <div class="flex items-center space-x-2">
            <span class="w-2.5 h-2.5 rounded-full ${hasAlerts ? 'bg-rose-500 animate-pulse' : 'bg-emerald-500'}"></span>
            <span class="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-100">
              Detalle de Alertas Hidrológicas
            </span>
          </div>
          <div class="flex items-center space-x-1.5">
            <button type="button" onclick="window.closeAlertsDropdown()" class="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-200/50 dark:hover:bg-slate-800 transition" title="Cerrar">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
          </div>
        </div>

        <!-- Pestañas de Selección: Alertas Hidrológicas vs Estaciones Sin Reporte -->
        <div class="flex items-center px-3 pt-2 bg-slate-50/50 dark:bg-slate-900/40 border-b border-slate-100 dark:border-slate-800/80 gap-3 text-xs font-semibold">
          <button id="tab-alerts-active" type="button" onclick="window.switchAlertsTab('active')" class="pb-2 border-b-2 border-emerald-500 text-emerald-600 dark:text-emerald-400 flex items-center gap-1.5 cursor-pointer">
            <span>🚨 Alertas Activas (${sorted.length})</span>
          </button>
          <button id="tab-alerts-failed" type="button" onclick="window.switchAlertsTab('failed')" class="pb-2 border-b-2 border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 flex items-center gap-1.5 cursor-pointer">
            <span>⚠️ Sin Reporte (${failed.length})</span>
          </button>
        </div>

        <!-- Buscador Rápido -->
        <div class="p-2 border-b border-slate-100 dark:border-slate-800/60 bg-white dark:bg-[#0b1c32]">
          <div class="relative">
            <svg class="w-3.5 h-3.5 absolute left-2.5 top-2 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
            </svg>
            <input id="input-search-alerts-dropdown" type="text" placeholder="Buscar por estación o código..." oninput="window.filterAlertsDropdown(this.value)" class="w-full bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700/80 rounded-lg pl-8 pr-2.5 py-1 text-xs text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500">
          </div>
        </div>

        <!-- Lista con Scroll -->
        <div id="alerts-dropdown-list-container" class="flex-1 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800/60 max-h-[52vh] p-1">
          <!-- Renderizado por Components.renderAlertsDropdownList() -->
        </div>

        <!-- Footer Informativo -->
        <div class="p-2.5 border-t border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/60 flex items-center justify-between text-[11px]">
          <span class="text-slate-500 dark:text-slate-400">Clic en una estación para ver su hidrograma</span>
        </div>
      </div>
    `;

    Components.renderAlertsDropdownList();
  },

  renderAlertsDropdownList(filterQuery = '') {
    const listContainer = document.getElementById('alerts-dropdown-list-container');
    if (!listContainer) return;

    const query = (filterQuery || '').toLowerCase().trim();
    const currentTab = Components._currentAlertsTab || 'active';

    if (currentTab === 'active') {
      const alerts = Components._activeAlerts || [];
      const filtered = query ? alerts.filter(a => (a.nombre || '').toLowerCase().includes(query) || (a.codigo || '').toLowerCase().includes(query) || (a.estado || '').toLowerCase().includes(query)) : alerts;

      if (filtered.length === 0) {
        listContainer.innerHTML = `
          <div class="p-6 text-center text-xs text-slate-400 dark:text-slate-500 space-y-1">
            <div class="text-emerald-500 font-bold text-sm">✓ Normalidad Hidrológica</div>
            <div>${query ? 'No se encontraron alertas para esa búsqueda.' : 'No hay alertas activas en la cuenca. Todos los niveles monitoreados se encuentran en rangos normales.'}</div>
          </div>
        `;
        return;
      }

      listContainer.innerHTML = filtered.map(a => {
        const dotColor = a.estado === 'evacuacion' ? 'bg-red-500 animate-pulse' : 'bg-amber-400';
        const badgeColors = {
          evacuacion: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300 border-red-300 dark:border-red-800',
          alerta: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300 border-amber-300 dark:border-amber-800'
        };
        const valStr = (a.altura !== null && a.altura !== undefined) ? `${a.altura.toFixed(2)} m` : '--';
        const umbVal = a.umbrales && a.umbrales[a.estado] ? `${a.umbrales[a.estado]} m` : null;
        const trendIcon = a.tendencia === 'creciente' ? '▲' : (a.tendencia === 'bajante' ? '▼' : '―');
        const trendCol = a.tendencia === 'creciente' ? 'text-rose-500' : (a.tendencia === 'bajante' ? 'text-emerald-500' : 'text-slate-400');
        const timeStr = a.timestamp ? a.timestamp.slice(11, 16) + ' hs' : '--:--';

        return `
          <div class="p-2.5 hover:bg-slate-50 dark:hover:bg-slate-800/60 transition cursor-pointer flex items-center justify-between gap-3 group" onclick="window.selectStationFromAlert(${a.id}); window.closeAlertsDropdown();">
            <div class="flex items-start space-x-2.5 min-w-0">
              <span class="w-2.5 h-2.5 rounded-full mt-1 shrink-0 ${dotColor}"></span>
              <div class="min-w-0">
                <div class="flex items-center space-x-1.5 flex-wrap gap-y-1">
                  <span class="font-bold text-xs text-slate-900 dark:text-slate-100 group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition">${a.nombre}</span>
                  <span class="text-[9px] font-bold px-1.5 py-0.2 rounded uppercase border ${badgeColors[a.estado] || badgeColors.alerta}">${a.estado}</span>
                  ${a.falla_reporte ? '<span class="text-[9px] font-bold text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/60 px-1 rounded border border-amber-300 dark:border-amber-800">⚠️ Sin reporte</span>' : ''}
                </div>
                <div class="text-[10px] text-slate-500 dark:text-slate-400 flex items-center space-x-1.5 mt-0.5">
                  <span>${a.codigo}</span>
                  <span>•</span>
                  <span>Lectura: ${timeStr}</span>
                  ${umbVal ? `<span class="text-slate-400 font-mono">• Umbral: ${umbVal}</span>` : ''}
                </div>
              </div>
            </div>
            <div class="text-right shrink-0 flex items-center space-x-2">
              <div>
                <div class="font-data font-extrabold text-sm text-slate-900 dark:text-white flex items-center justify-end space-x-1">
                  <span>${valStr}</span>
                  <span class="${trendCol} text-xs font-bold">${trendIcon}</span>
                </div>
                ${a.pna_altura !== null && a.pna_altura !== undefined ? `<div class="text-[9px] text-amber-600 dark:text-amber-400 font-mono font-semibold">⚓ ${a.pna_altura.toFixed(2)}m</div>` : ''}
              </div>
              <button type="button" onclick="event.stopPropagation(); window.toggleStationAlerts(${a.id});" class="p-1 rounded text-slate-400 hover:text-rose-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition" title="Silenciar / desactivar alertas para ${a.nombre}">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"/></svg>
              </button>
            </div>
          </div>
        `;
      }).join('');

    } else {
      // Tab 2: Fallas de Transmisión / Sin reporte
      const failed = Components._failedStations || [];
      const filtered = query ? failed.filter(f => (f.nombre || '').toLowerCase().includes(query) || (f.codigo || '').toLowerCase().includes(query)) : failed;

      if (filtered.length === 0) {
        listContainer.innerHTML = `
          <div class="p-6 text-center text-xs text-slate-400 dark:text-slate-500 space-y-1">
            <div class="text-emerald-500 font-bold text-sm">✓ Todas las Estaciones Reportando</div>
            <div>${query ? 'No se encontraron estaciones sin reporte para esa búsqueda.' : 'Todos los hidrómetros están transmitiendo dentro de sus ventanas horarias habituales.'}</div>
          </div>
        `;
        return;
      }

      listContainer.innerHTML = filtered.map(f => {
        const valStr = (f.ultima_altura !== null && f.ultima_altura !== undefined) ? `${f.ultima_altura.toFixed(2)} m` : '--';
        const timeStr = f.ultimo_timestamp || 'Sin datos';
        return `
          <div class="p-2.5 hover:bg-slate-50 dark:hover:bg-slate-800/60 transition cursor-pointer flex items-center justify-between gap-3 group" onclick="window.selectStation(${f.id}, true); window.closeAlertsDropdown();">
            <div class="flex items-start space-x-2.5 min-w-0">
              <span class="w-2.5 h-2.5 rounded-full mt-1 shrink-0 bg-amber-500"></span>
              <div class="min-w-0">
                <div class="flex items-center space-x-1.5 flex-wrap gap-y-1">
                  <span class="font-bold text-xs text-slate-900 dark:text-slate-100 group-hover:text-amber-600 dark:group-hover:text-amber-400 transition">${f.nombre}</span>
                  <span class="text-xs text-amber-500" title="Retraso en reporte">⚠️</span>
                </div>
                <div class="text-[10px] text-slate-500 dark:text-slate-400 font-mono mt-0.5">
                  Última actualización: ${timeStr}
                </div>
              </div>
            </div>
            <div class="text-right shrink-0">
              <div class="font-data font-bold text-xs text-slate-700 dark:text-slate-300">${valStr}</div>
              <span class="text-[10px] text-sky-600 dark:text-sky-400 font-medium group-hover:underline">Ver datos →</span>
            </div>
          </div>
        `;
      }).join('');
    }
  },

  toggleAlertsDropdown(event) {
    if (event) {
      if (typeof event.stopPropagation === 'function') event.stopPropagation();
      if (typeof event.preventDefault === 'function') event.preventDefault();
    }
    const panel = document.getElementById('alerts-dropdown-panel');
    const arrow = document.getElementById('icon-alerts-dropdown-arrow');
    if (!panel) return;

    const isHidden = panel.classList.contains('hidden') || panel.style.display === 'none';
    if (isHidden) {
      panel.classList.remove('hidden');
      panel.style.display = 'flex';
      if (arrow) arrow.classList.add('rotate-180');
      Components.renderAlertsDropdownList();
    } else {
      panel.classList.add('hidden');
      panel.style.display = 'none';
      if (arrow) arrow.classList.remove('rotate-180');
    }
  },

  closeAlertsDropdown() {
    const panel = document.getElementById('alerts-dropdown-panel');
    const arrow = document.getElementById('icon-alerts-dropdown-arrow');
    if (panel) {
      panel.classList.add('hidden');
      panel.style.display = 'none';
    }
    if (arrow) arrow.classList.remove('rotate-180');
  },

  switchAlertsTab(tab) {
    Components._currentAlertsTab = tab;
    const tabActive = document.getElementById('tab-alerts-active');
    const tabFailed = document.getElementById('tab-alerts-failed');

    if (tab === 'active') {
      if (tabActive) {
        tabActive.className = 'pb-2 border-b-2 border-emerald-500 text-emerald-600 dark:text-emerald-400 flex items-center gap-1.5 cursor-pointer';
      }
      if (tabFailed) {
        tabFailed.className = 'pb-2 border-b-2 border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 flex items-center gap-1.5 cursor-pointer';
      }
    } else {
      if (tabActive) {
        tabActive.className = 'pb-2 border-b-2 border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 flex items-center gap-1.5 cursor-pointer';
      }
      if (tabFailed) {
        tabFailed.className = 'pb-2 border-b-2 border-amber-500 text-amber-600 dark:text-amber-400 flex items-center gap-1.5 cursor-pointer';
      }
    }

    const input = document.getElementById('input-search-alerts-dropdown');
    Components.renderAlertsDropdownList(input ? input.value : '');
  },

  filterAlertsDropdown(query) {
    Components.renderAlertsDropdownList(query);
  },

  /**
   * Renderiza la tira de 3 tarjetas de Situación Actual
   */
  renderSituationStrip(kpis, station, isCota, offset) {
    if (!kpis) return;

    const currentValElem = document.getElementById('sit-current-val');
    const currentTrendElem = document.getElementById('sit-current-trend');
    const currentTimeElem = document.getElementById('sit-current-time');
    const currentRateElem = document.getElementById('sit-current-rate');

    const pnaValElem = document.getElementById('sit-pna-val');
    const pnaTrendElem = document.getElementById('sit-pna-trend');
    const pnaTimeElem = document.getElementById('sit-pna-time');
    const diffValElem = document.getElementById('sit-diff-val');

    const var24ValElem = document.getElementById('sit-24h-val');
    const varRangeElem = document.getElementById('sit-24h-range');

    const statusBadgeElem = document.getElementById('sit-status-badge');
    const statusTextElem = document.getElementById('sit-status-text');

    // 1. Valor actual AGP
    let val = kpis.ultima_altura;
    if (isCota && val !== null) {
      val = val + offset;
    }

    if (currentValElem) {
      currentValElem.textContent = val !== null ? val.toFixed(2) : '--';
    }

    // 2. Tendencia AGP
    if (currentTrendElem) {
      const t = kpis.tendencia || 'estable';
      if (t === 'sube') {
        currentTrendElem.className = 'text-[11px] px-2 py-0.5 rounded-md font-bold bg-rose-100 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300';
        currentTrendElem.innerHTML = '▲ Subiendo';
      } else if (t === 'baja') {
        currentTrendElem.className = 'text-[11px] px-2 py-0.5 rounded-md font-bold bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300';
        currentTrendElem.innerHTML = '▼ Bajando';
      } else {
        currentTrendElem.className = 'text-[11px] px-2 py-0.5 rounded-md font-bold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300';
        currentTrendElem.innerHTML = '▬ Estable';
      }
    }

    // 3. Velocidad cm/h
    if (currentRateElem) {
      const v = kpis.velocidad_cm_hora;
      if (v !== undefined && v !== 0) {
        const sign = v > 0 ? '+' : '';
        currentRateElem.textContent = `(${sign}${v} cm/h)`;
      } else {
        currentRateElem.textContent = '';
      }
    }

    if (currentTimeElem) {
      const formattedAgpTime = Components.formatDateTime(kpis.ultimo_timestamp, true);
      if (kpis.falla_reporte) {
        currentTimeElem.innerHTML = `<span class="text-slate-500 dark:text-slate-400 font-mono" title="Última actualización">${formattedAgpTime}</span> <span class="text-amber-500 font-bold ml-1" title="Retraso en actualización">⚠️</span>`;
      } else {
        currentTimeElem.textContent = kpis.ultimo_timestamp ? `Lectura: ${formattedAgpTime}` : 'Sin datos';
      }
    }

    const warnBox = document.getElementById('sit-transmission-warning');
    if (warnBox) {
      warnBox.classList.add('hidden');
    }

    // 4. Medición Oficial Prefectura Naval Argentina (PNA)
    let pnaVal = kpis.pna_altura;
    if (isCota && pnaVal !== null && pnaVal !== undefined) {
      pnaVal = pnaVal + offset;
    }
    if (pnaValElem) {
      pnaValElem.textContent = (pnaVal !== null && pnaVal !== undefined) ? pnaVal.toFixed(2) : '--';
    }

    const pnaTitleElem = document.getElementById('sit-pna-title');
    if (pnaTitleElem) {
      if (kpis.pna_puerto) {
        pnaTitleElem.innerHTML = `<span>⚓ Prefectura (${kpis.pna_puerto})</span>`;
      } else {
        pnaTitleElem.innerHTML = `<span>⚓ Prefectura Naval</span>`;
      }
    }

    if (pnaTrendElem) {
      const pnaState = (kpis.pna_estado_rio || '').toUpperCase().trim();
      if (pnaState.includes('CRECE')) {
        pnaTrendElem.className = 'text-[10px] px-1.5 py-0.5 rounded font-bold bg-rose-200/80 dark:bg-rose-950/60 text-rose-800 dark:text-rose-300';
        pnaTrendElem.innerHTML = '▲ Crece';
      } else if (pnaState.includes('BAJA')) {
        pnaTrendElem.className = 'text-[10px] px-1.5 py-0.5 rounded font-bold bg-emerald-200/80 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300';
        pnaTrendElem.innerHTML = '▼ Baja';
      } else if (pnaState.includes('ESTAC')) {
        pnaTrendElem.className = 'text-[10px] px-1.5 py-0.5 rounded font-bold bg-amber-200/70 dark:bg-amber-950/50 text-amber-900 dark:text-amber-200';
        pnaTrendElem.innerHTML = '⏸ Estacionario';
      } else if (pnaState) {
        pnaTrendElem.className = 'text-[10px] px-1.5 py-0.5 rounded font-bold bg-slate-200/70 dark:bg-slate-800 text-slate-700 dark:text-slate-300';
        pnaTrendElem.textContent = pnaState;
      } else {
        pnaTrendElem.className = 'text-[10px] px-1.5 py-0.5 rounded font-bold bg-slate-100 dark:bg-slate-800 text-slate-400';
        pnaTrendElem.textContent = '--';
      }
    }

    if (pnaTimeElem) {
      pnaTimeElem.textContent = kpis.pna_timestamp ? Components.formatDateTime(kpis.pna_timestamp, true) : 'Sin reporte PNA';
    }

    // 5. Diferencia Delta (AGP − PNA)
    if (diffValElem) {
      if (kpis.diferencia_agp_pna !== null && kpis.diferencia_agp_pna !== undefined) {
        const diff = kpis.diferencia_agp_pna;
        const sign = diff > 0 ? '+' : '';
        const absDiff = Math.abs(diff);
        let tag = '';
        let colorCls = 'text-emerald-600 dark:text-emerald-400';
        if (absDiff <= 0.05) {
          tag = '<span class="text-[9px] px-1.5 py-0.5 rounded font-sans font-semibold bg-emerald-100 dark:bg-emerald-950/70 text-emerald-700 dark:text-emerald-300 ml-1.5">Idéntica</span>';
        } else if (absDiff <= 0.40) {
          colorCls = 'text-sky-600 dark:text-sky-400';
          tag = '<span class="text-[9px] px-1.5 py-0.5 rounded font-sans font-semibold bg-sky-100 dark:bg-sky-950/70 text-sky-700 dark:text-sky-300 ml-1.5">Desvío local</span>';
        } else {
          colorCls = 'text-amber-600 dark:text-amber-400';
          tag = '<span class="text-[9px] px-1.5 py-0.5 rounded font-sans font-semibold bg-amber-100 dark:bg-amber-950/70 text-amber-700 dark:text-amber-300 ml-1.5">Cero distinto</span>';
        }
        diffValElem.innerHTML = `<span class="${colorCls} font-bold font-data">${sign}${diff.toFixed(2)} ${isCota ? 'msnm' : 'm'}</span>${tag}`;
      } else {
        diffValElem.innerHTML = '<span class="text-slate-400 font-sans text-[11px]">Sin puerto PNA emparejado</span>';
      }
    }

    // 6. Variación 24h y Rango
    if (var24ValElem) {
      if (kpis.variacion_24h !== null && kpis.variacion_24h !== undefined) {
        const sign = kpis.variacion_24h > 0 ? '+' : '';
        const colorCls = kpis.variacion_24h > 0 ? 'text-rose-600 dark:text-rose-400' : (kpis.variacion_24h < 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-700 dark:text-slate-200');
        var24ValElem.innerHTML = `<span class="${colorCls}">${sign}${kpis.variacion_24h.toFixed(2)} m</span>`;
      } else {
        var24ValElem.textContent = '--';
      }
    }

    if (varRangeElem) {
      const minStr = kpis.min_altura !== null ? `${kpis.min_altura.toFixed(2)} m` : '--';
      const maxStr = kpis.max_altura !== null ? `${kpis.max_altura.toFixed(2)} m` : '--';
      varRangeElem.textContent = `Mín: ${minStr} | Máx: ${maxStr}`;
    }

    // 7. Estado Hidrológico & Opción A (Precedencia PNA)
    const isSilenced = (kpis.alertas_activas === false) || (station && station.alertas_activas === false);

    if (isSilenced) {
      if (statusBadgeElem) {
        statusBadgeElem.className = 'w-3 h-3 rounded-full shrink-0 bg-slate-400 ring-2 ring-slate-400/40';
      }
      if (statusTextElem) {
        statusTextElem.textContent = 'SILENCIADO';
        statusTextElem.className = 'text-xs font-extrabold font-data text-slate-500 uppercase';
      }
      return;
    }

    const statusDots = {
      normal: 'bg-emerald-500',
      alerta: 'bg-orange-500',
      evacuacion: 'bg-red-600 animate-pulse'
    };

    const st = kpis.estado_hidrologico || 'normal';
    if (statusBadgeElem) {
      statusBadgeElem.className = `w-3 h-3 rounded-full shrink-0 ${statusDots[st] || 'bg-emerald-500'}`;
    }
    if (statusTextElem) {
      statusTextElem.textContent = st.toUpperCase();
      statusTextElem.className = 'text-xs font-extrabold font-data text-slate-900 dark:text-white uppercase';
    }
  },

  /**
   * Renderiza el indicador de nivel horizontal (Nivel-Bar Gauge)
   */
  renderNivelBar(kpis, station, activeSource = null) {
    const wrap = document.getElementById('nivel-bar-wrap');
    const bar = document.getElementById('nivel-bar-inner');
    const markerAlerta = document.getElementById('marker-alerta');
    const markerEvac = document.getElementById('marker-evacuacion');

    if (!wrap || !bar || !kpis) return;

    const source = activeSource || (window.State && State.chartSource) || 'agp';
    let alt = null;
    if (source === 'pna') {
      alt = (kpis.pna_altura !== null && kpis.pna_altura !== undefined) ? kpis.pna_altura : kpis.ultima_altura;
    } else {
      alt = (kpis.ultima_altura !== null && kpis.ultima_altura !== undefined) ? kpis.ultima_altura : kpis.pna_altura;
    }

    const umbrales = kpis.umbrales || {};
    const evac = umbrales.evacuacion;
    const alerta = umbrales.alerta;

    if (alt === null) {
      bar.style.width = '0%';
      if (markerAlerta) markerAlerta.classList.add('hidden');
      if (markerEvac) markerEvac.classList.add('hidden');
      return;
    }

    // Escala máxima calculada: 120% del nivel de evacuación, o 140% de la altura actual
    const maxScale = Math.max(evac ? evac * 1.15 : 10.0, alt * 1.25);
    const pct = Math.min(100, Math.max(3, (alt / maxScale) * 100));

    bar.style.width = `${pct}%`;

    // Clases según nivel oficial
    const barColors = {
      normal: 'bg-emerald-500',
      alerta: 'bg-orange-500',
      evacuacion: 'bg-red-600'
    };
    const st = kpis.estado_hidrologico || 'normal';
    bar.className = `nivel-bar-fill ${barColors[st] || 'bg-emerald-500'}`;

    // Actualizar leyenda inferior de umbrales oficiales (Alerta y Evacuación)
    const alertaEl = document.getElementById('lbl-val-alerta');
    const evacEl = document.getElementById('lbl-val-evac');

    if (alertaEl) alertaEl.textContent = alerta ? `${alerta.toFixed(2)} m` : '--';
    if (evacEl) evacEl.textContent = evac ? `${evac.toFixed(2)} m` : '--';
  },

  /**
   * Renderiza las tarjetas de Estadísticas del Período basándose en la fuente activa (AGP, PNA o Ambas)
   */
  renderKpiCards(kpis, isCota, offset, activeSource = 'agp', puntosAgp = [], puntosPna = []) {
    if (!kpis && (!puntosAgp || puntosAgp.length === 0) && (!puntosPna || puntosPna.length === 0)) return;

    const source = activeSource || (window.State && State.chartSource) || 'agp';

    const agpList = (puntosAgp || []).filter(p => p && p.y !== null && p.y !== undefined && !isNaN(p.y));
    const pnaList = (puntosPna || []).filter(p => p && p.y !== null && p.y !== undefined && !isNaN(p.y));

    let targetPoints = [];
    let sourceLabel = 'AGP';
    let badgeClass = 'bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300 border-sky-300 dark:border-sky-800';

    if (source === 'pna') {
      if (pnaList.length > 0) {
        targetPoints = pnaList;
        sourceLabel = 'Prefectura PNA';
        badgeClass = 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300 border-amber-300 dark:border-amber-800';
      } else if (agpList.length > 0) {
        targetPoints = agpList;
        sourceLabel = 'AGP (Sin PNA)';
        badgeClass = 'bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300 border-sky-300 dark:border-sky-800';
      }
    } else if (source === 'ambas') {
      if (agpList.length > 0 && pnaList.length > 0) {
        targetPoints = [...agpList, ...pnaList];
        sourceLabel = 'Unificada (AGP + PNA)';
        badgeClass = 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 border-emerald-300 dark:border-emerald-800';
      } else if (pnaList.length > 0) {
        targetPoints = pnaList;
        sourceLabel = 'Prefectura PNA';
        badgeClass = 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300 border-amber-300 dark:border-amber-800';
      } else {
        targetPoints = agpList;
        sourceLabel = 'AGP';
        badgeClass = 'bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300 border-sky-300 dark:border-sky-800';
      }
    } else {
      // Por defecto 'agp'
      if (agpList.length > 0) {
        targetPoints = agpList;
        sourceLabel = 'AGP';
        badgeClass = 'bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300 border-sky-300 dark:border-sky-800';
      } else if (pnaList.length > 0) {
        targetPoints = pnaList;
        sourceLabel = 'Prefectura PNA (Sin AGP)';
        badgeClass = 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300 border-amber-300 dark:border-amber-800';
      }
    }

    let max = null;
    let min = null;
    let avg = null;
    let var24 = null;
    let totalPoints = targetPoints.length;

    if (targetPoints.length > 0) {
      const vals = targetPoints.map(p => Number(p.y));
      max = Math.max(...vals);
      min = Math.min(...vals);
      const sum = vals.reduce((a, b) => a + b, 0);
      avg = sum / vals.length;

      // Calcular variación 24h cronológica para la fuente elegida
      if (source === 'agp' && kpis && kpis.variacion_24h !== null && kpis.variacion_24h !== undefined) {
        var24 = kpis.variacion_24h;
      } else {
        const sorted = [...targetPoints].sort((a, b) => {
          const ta = new Date((a.t || '').replace(' ', 'T')).getTime();
          const tb = new Date((b.t || '').replace(' ', 'T')).getTime();
          return ta - tb;
        });

        if (sorted.length >= 2) {
          const lastP = sorted[sorted.length - 1];
          const lastMs = new Date((lastP.t || '').replace(' ', 'T')).getTime();
          const targetMs = lastMs - (24 * 3600 * 1000);

          let closestPoint = null;
          let closestDiff = Infinity;
          for (let i = 0; i < sorted.length - 1; i++) {
            const pMs = new Date((sorted[i].t || '').replace(' ', 'T')).getTime();
            if (!isNaN(pMs)) {
              const diff = Math.abs(pMs - targetMs);
              if (diff < closestDiff) {
                closestDiff = diff;
                closestPoint = sorted[i];
              }
            }
          }

          if (closestPoint && !isNaN(lastP.y) && !isNaN(closestPoint.y)) {
            var24 = Number((lastP.y - closestPoint.y).toFixed(2));
          }
        }
      }
    } else if (kpis) {
      max = kpis.max_altura;
      min = kpis.min_altura;
      avg = kpis.promedio_altura;
      var24 = kpis.variacion_24h;
      totalPoints = kpis.total_puntos || 0;
    }

    let unit = 'm';
    if (isCota) {
      if (max !== null) max = Number((max + offset).toFixed(2));
      if (min !== null) min = Number((min + offset).toFixed(2));
      if (avg !== null) avg = Number((avg + offset).toFixed(2));
      unit = 'msnm';
    }

    const setVal = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.textContent = val !== null && val !== undefined ? val.toFixed(2) : '--';
    };

    setVal('kpi-val-current', (kpis && kpis.ultima_altura !== null) ? (isCota ? kpis.ultima_altura + offset : kpis.ultima_altura) : null);
    setVal('kpi-val-max', max);
    setVal('kpi-val-min', min);
    setVal('kpi-val-avg', avg);

    // Variación 24h
    const var24ValElem = document.getElementById('sit-24h-val');
    if (var24ValElem) {
      if (var24 !== null && var24 !== undefined && !isNaN(var24)) {
        const sign = var24 > 0 ? '+' : '';
        const colorCls = var24 > 0 ? 'text-rose-600 dark:text-rose-400' : (var24 < 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-700 dark:text-slate-200');
        var24ValElem.innerHTML = `<span class="${colorCls}">${sign}${var24.toFixed(2)} m</span>`;
      } else {
        var24ValElem.textContent = '--';
      }
    }

    // Badge de fuente activa en "Estadísticas del Período"
    const badgeEl = document.getElementById('kpi-source-badge');
    if (badgeEl) {
      badgeEl.textContent = sourceLabel;
      badgeEl.className = `text-[10px] px-2 py-0.5 rounded font-bold border transition-colors ${badgeClass}`;
    }

    document.querySelectorAll('.kpi-unit-label').forEach(el => el.textContent = unit);

    const timeEl = document.getElementById('kpi-time-current');
    if (timeEl) timeEl.textContent = Components.formatDateTime(kpis && kpis.ultimo_timestamp, true) || 'Sin datos';

    const countEl = document.getElementById('kpi-points-count');
    if (countEl) countEl.textContent = `${totalPoints} mediciones (${sourceLabel})`;
  },

  /**
   * Renderiza la tabla de mediciones recientes
   */
  renderRecentTable(recientes, isCota, offset) {
    const tbody = document.getElementById('readings-table-body');
    if (!tbody) return;

    if (!recientes || recientes.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" class="py-4 text-center text-slate-400">No hay mediciones en este período</td></tr>';
      return;
    }

    const unitSuffix = isCota ? 'msnm' : 'm';

    tbody.innerHTML = recientes.map(r => {
      // 1. Columna AGP (Telemetría directa)
      let agpStr = '<span class="text-slate-400">--</span>';
      const aVal = (r.altura_agp !== null && r.altura_agp !== undefined) ? r.altura_agp 
                 : ((r.altura !== null && r.altura !== undefined && (r.altura_pna === null || r.altura_pna === undefined)) ? r.altura : null);
      if (aVal !== null) {
        let v = aVal;
        if (isCota) v += offset;
        agpStr = `<span class="font-data font-bold text-sky-600 dark:text-sky-400">${v.toFixed(2)} <span class="text-[10px] text-slate-400 font-normal">${unitSuffix}</span></span>`;
      }

      // 2. Columna Prefectura PNA (Guardias oficiales)
      let pnaStr = '<span class="text-slate-400">--</span>';
      if (r.altura_pna !== null && r.altura_pna !== undefined) {
        let pv = r.altura_pna;
        if (isCota) pv += offset;
        const estStr = r.estado_pna ? ` <span class="text-[10px] font-sans font-bold text-amber-700 dark:text-amber-300">(${r.estado_pna})</span>` : '';
        pnaStr = `<span class="font-mono font-semibold text-amber-600 dark:text-amber-400" title="Prefectura Naval Argentina">⚓ ${pv.toFixed(2)} <span class="text-[10px] text-slate-400 font-normal">${unitSuffix}</span>${estStr}</span>`;
      }

      // 3. Columna Variación / Discrepancia
      let diffStr = '<span class="text-slate-400">▬ 0.00</span>';
      let diffCls = 'text-slate-400';
      if (r.variacion !== undefined && r.variacion !== null && Math.abs(r.variacion) >= 0.01) {
        const sign = r.variacion > 0 ? '+' : '';
        diffStr = `${sign}${r.variacion.toFixed(2)} m`;
        diffCls = r.variacion > 0 ? 'text-rose-600 dark:text-rose-400 font-bold' : 'text-emerald-600 dark:text-emerald-400 font-bold';
      } else if (r.diferencia !== undefined && r.diferencia !== null) {
        const sign = r.diferencia > 0 ? '+' : '';
        diffStr = `<span class="text-[10px] text-slate-500 dark:text-slate-400 font-mono" title="Diferencia telemétrica AGP - PNA">Δ ${sign}${r.diferencia.toFixed(2)}m</span>`;
        diffCls = 'text-slate-500';
      }

      return `
        <tr class="hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition">
          <td class="py-1.5 px-2.5 font-mono text-[11px] sm:text-xs text-slate-600 dark:text-slate-300">${Components.formatDateTime(r.timestamp)}</td>
          <td class="py-1.5 px-2.5 text-[11px] sm:text-xs">${agpStr}</td>
          <td class="py-1.5 px-2.5 text-[11px] sm:text-xs">${pnaStr}</td>
          <td class="py-1.5 px-2.5 font-mono text-[11px] sm:text-xs ${diffCls}">${diffStr}</td>
        </tr>
      `;
    }).join('');
  },

  /**
   * Renderiza la lista de estaciones en la barra lateral con estilo Tailwind limpio
   */
  renderStationList(stations, activeId, onSelectStation) {
    const container = document.getElementById('stations-list');
    if (!container) return;

    if (!stations || stations.length === 0) {
      container.innerHTML = '<div class="p-6 text-center text-xs text-slate-400">No se encontraron estaciones</div>';
      return;
    }

    const statusDots = {
      normal: 'bg-emerald-500',
      alerta: 'bg-orange-500',
      evacuacion: 'bg-red-600 animate-ping',
      sin_datos: 'bg-slate-400'
    };

    container.innerHTML = stations.map(s => {
      const isActive = s.id === activeId;
      const isSilenced = s.alertas_activas === false;
      const st = s.estado_hidrologico || 'normal';
      const valStr = s.ultima_altura !== null ? s.ultima_altura.toFixed(2) : '--';
      const pnaValStr = (s.pna_altura !== null && s.pna_altura !== undefined) ? s.pna_altura.toFixed(2) : null;
      const freq = s.frecuencia_minutos || 20;

      const activeBg = isActive
        ? 'bg-emerald-50 dark:bg-emerald-950/60 border-[#008348] dark:border-emerald-500 shadow-sm'
        : 'hover:bg-slate-100/70 dark:hover:bg-slate-800/60 border-transparent';

      const isFailed = s.falla_reporte === true;
      const dotClass = isSilenced 
        ? 'bg-slate-400 ring-1 ring-slate-400/50' 
        : (isFailed ? 'bg-amber-500 animate-pulse' : (statusDots[st] || 'bg-emerald-500'));
      const dotTitle = isSilenced 
        ? 'Alertas silenciadas/desactivadas' 
        : (isFailed ? `Falla de reporte (${s.tiempo_sin_reportar_str || 'sin datos'})` : `Estado: ${st}`);

      return `
        <div class="group flex items-center justify-between p-2 rounded-lg cursor-pointer border transition ${activeBg}" onclick="window.selectStation(${s.id})">
          <div class="flex items-center space-x-2.5 min-w-0">
            <span class="w-2.5 h-2.5 rounded-full shrink-0 ${dotClass}" title="${dotTitle}"></span>
            <div class="min-w-0">
              <div class="text-xs font-semibold text-slate-800 dark:text-slate-100 truncate group-hover:text-[#008348] dark:group-hover:text-emerald-400 transition" title="${s.nombre}">
                ${s.nombre}
                ${isSilenced ? '<span class="text-[9px] text-slate-400 ml-1 font-normal font-mono">(silenciada)</span>' : ''}
                ${isFailed ? '<span class="text-amber-500 text-xs ml-1" title="Retraso en reporte">⚠️</span>' : ''}
              </div>
              <div class="text-[10px] text-slate-400 flex items-center space-x-1.5 mt-0.5">
                <span>${freq} min</span>
                <span>•</span>
                <span>${s.ultimo_timestamp ? s.ultimo_timestamp.slice(11, 16) : '--:--'}</span>
              </div>
            </div>
          </div>
          <div class="text-right shrink-0 pl-2">
            <div class="flex items-baseline justify-end gap-0.5">
              <span class="font-data font-bold text-xs ${isActive ? 'text-[#008348] dark:text-emerald-400' : 'text-slate-700 dark:text-slate-200'}">${valStr}</span>
              <span class="text-[10px] text-slate-400 font-medium">m</span>
            </div>
            ${pnaValStr !== null ? `
              <div class="text-[10px] font-mono text-amber-600 dark:text-amber-400 font-semibold" title="Prefectura: ${pnaValStr}m (${s.pna_estado_rio || ''})">
                ⚓ ${pnaValStr}m
              </div>
            ` : ''}
          </div>
        </div>
      `;
    }).join('');
  },

  /**
   * Toast flotante para feedback de acciones
   */
  showToast(title, message, isError = false) {
    const toast = document.getElementById('toast');
    if (!toast) return;

    const iconEl = document.getElementById('toast-icon');
    const titleEl = document.getElementById('toast-title');
    const msgEl = document.getElementById('toast-msg');

    if (iconEl) iconEl.textContent = isError ? '✕' : '✓';
    if (iconEl) iconEl.className = isError ? 'text-rose-500 font-bold shrink-0' : 'text-emerald-500 font-bold shrink-0';
    if (titleEl) titleEl.textContent = title;
    if (msgEl) msgEl.textContent = message;

    toast.classList.remove('opacity-0', 'pointer-events-none', 'translate-y-3');
    toast.classList.add('opacity-100', 'pointer-events-auto', 'translate-y-0');

    clearTimeout(this._toastTimeout);
    this._toastTimeout = setTimeout(() => {
      toast.classList.remove('opacity-100', 'pointer-events-auto', 'translate-y-0');
      toast.classList.add('opacity-0', 'pointer-events-none', 'translate-y-3');
    }, 3800);
  }
};

window.Components = Components;
window.formatDateTimeUnified = Components.formatDateTime.bind(Components);
