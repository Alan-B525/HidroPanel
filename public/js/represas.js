/**
 * public/js/represas.js
 * Visualizador y Analizador de Caudales Fluviales y Presas Hidroeléctricas.
 * Integración ONS Open Data S3 + Telemetría de Cascada de los Ríos Paraná e Iguazú.
 */

const RepresasView = {
  caudalesChart: null,
  itaipuChart: null,
  data: null,
  tableFilter: 'todas',
  damModalState: {
    activeCode: 'PNITAI',
    activeMonth: null,
    activeRange: 'all',
    activeVariables: new Set(['defluente', 'turbinada', 'vertida']),
    data: null,
    chart: null,
    _isDark: false
  },

  async init() {
    await this.loadData();
  },

  async loadData() {
    try {
      const res = await API.getCaudales();
      if (res && res.success) {
        this.data = res;
        this.renderOverview(res);
        this.renderSchematic(res);
        this.renderTable(res.centrales_lista || []);
        this.renderCharts(res.timeline || [], State.theme === 'dark');

        // Notificar también al mapa si ya está inicializado para pintar caudales en los marcadores de presas
        if (window.MapView && MapView.map) {
          MapView.renderDams(res);
        }
      }
    } catch (e) {
      console.error('Error cargando caudales:', e);
      Components.showToast('Error', 'No se pudieron cargar datos de caudales de represas', true);
    }
  },

  renderOverview(data) {
    const bal = data.balance_yacyreta || {};
    const it = data.itaipu || {};
    const ig = data.iguazu || {};

    const fmt = (v) => (v !== undefined && v !== null && !isNaN(v) ? Number(v).toLocaleString('es-AR', { maximumFractionDigits: 1 }) : '—');

    // 1. Hero Total hacia Yacyretá
    const totalEl = document.getElementById('rep-total-yacyreta');
    const itAporteEl = document.getElementById('rep-aporte-itaipu');
    const igAporteEl = document.getElementById('rep-aporte-iguazu');
    const itPctEl = document.getElementById('rep-pct-itaipu');
    const igPctEl = document.getElementById('rep-pct-iguazu');

    if (totalEl) totalEl.textContent = fmt(bal.caudal_total_m3s);
    if (itAporteEl) itAporteEl.textContent = bal.aporte_itaipu_m3s != null ? `${fmt(bal.aporte_itaipu_m3s)} m³/s` : '—';
    if (igAporteEl) igAporteEl.textContent = bal.aporte_iguazu_m3s != null ? `${fmt(bal.aporte_iguazu_m3s)} m³/s` : '—';
    if (itPctEl) itPctEl.textContent = bal.pct_itaipu != null ? `${bal.pct_itaipu}%` : '';
    if (igPctEl) igPctEl.textContent = bal.pct_iguazu != null ? `${bal.pct_iguazu}%` : '';

    // 2. Estado de Vertederos (Spillways)
    const itVertVal = Number(it.vertida || 0);
    const itSpillwayEl = document.getElementById('rep-it-spillway-badge');
    if (itSpillwayEl) {
      if (itVertVal > 0) {
        itSpillwayEl.className = 'text-[11px] font-bold px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/50 flex items-center gap-1 tabular-nums';
        itSpillwayEl.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span> Vertedero Activo: ${fmt(itVertVal)} m³/s`;
      } else {
        itSpillwayEl.className = 'text-[11px] font-medium px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700';
        itSpillwayEl.textContent = 'Vertedero Cerrado';
      }
    }

    const bxVertVal = Number(ig.baixo_iguazu_vertida || 0);
    const igSpillwayEl = document.getElementById('rep-ig-spillway-badge');
    if (igSpillwayEl) {
      if (bxVertVal > 0) {
        igSpillwayEl.className = 'text-[11px] font-bold px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/50 flex items-center gap-1 tabular-nums';
        igSpillwayEl.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span> Vertedero Baixo: ${fmt(bxVertVal)} m³/s`;
      } else {
        igSpillwayEl.className = 'text-[11px] font-medium px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700';
        igSpillwayEl.textContent = 'Vertedero Cerrado';
      }
    }

    const formatDt = (val) => (window.Components && typeof Components.formatDateTime === 'function' ? Components.formatDateTime(val, true) : (val || '—'));

    // 3. Tarjeta Itaipú (ONS)
    const itDeflEl = document.getElementById('rep-it-defl');
    const itTurbEl = document.getElementById('rep-it-turb');
    const itVertEl = document.getElementById('rep-it-vert');
    const itAfluEl = document.getElementById('rep-it-aflu');
    const itCotaEl = document.getElementById('rep-it-cota');
    const itTimeEl = document.getElementById('rep-it-time');

    if (itDeflEl) itDeflEl.textContent = fmt(it.defluente);
    if (itTurbEl) itTurbEl.textContent = it.turbinada != null ? `${fmt(it.turbinada)} m³/s` : '—';
    if (itVertEl) itVertEl.textContent = it.vertida != null ? `${fmt(it.vertida)} m³/s` : '—';
    if (itAfluEl) itAfluEl.textContent = it.afluente != null ? `${fmt(it.afluente)} m³/s` : '—';
    if (itCotaEl) itCotaEl.textContent = it.cota != null ? `${fmt(it.cota)} msnm` : '—';
    if (itTimeEl) {
      itTimeEl.innerHTML = window.Components && typeof Components.renderFreshnessBadge === 'function'
        ? Components.renderFreshnessBadge('ONS', it.fecha)
        : formatDt(it.fecha);
    }

    // 4. Tarjeta Baixo Iguaçu (ONS) - Datos directos de la central sin mezclar
    const bxDeflEl = document.getElementById('rep-bx-defl');
    const bxTurbEl = document.getElementById('rep-bx-turb');
    const bxVertEl = document.getElementById('rep-bx-vert');
    const bxAfluEl = document.getElementById('rep-bx-aflu');
    const bxCotaEl = document.getElementById('rep-bx-cota');
    const bxTimeEl = document.getElementById('rep-bx-time');

    if (bxDeflEl) bxDeflEl.textContent = fmt(ig.baixo_iguazu_defluente);
    if (bxTurbEl) bxTurbEl.textContent = ig.baixo_iguazu_turbinada != null ? `${fmt(ig.baixo_iguazu_turbinada)} m³/s` : '—';
    if (bxVertEl) bxVertEl.textContent = ig.baixo_iguazu_vertida != null ? `${fmt(ig.baixo_iguazu_vertida)} m³/s` : '—';
    if (bxAfluEl) bxAfluEl.textContent = ig.baixo_iguazu_afluente != null ? `${fmt(ig.baixo_iguazu_afluente)} m³/s` : '—';
    if (bxCotaEl) bxCotaEl.textContent = ig.baixo_iguazu_cota != null ? `${fmt(ig.baixo_iguazu_cota)} msnm` : '—';
    if (bxTimeEl) {
      bxTimeEl.innerHTML = window.Components && typeof Components.renderFreshnessBadge === 'function'
        ? Components.renderFreshnessBadge('ONS', ig.fecha)
        : formatDt(ig.fecha);
    }

    // 5. Tarjeta Porto Capanema (COPEL / ANA) - Solo fuente propia de Capanema
    const capCaudalEl = document.getElementById('rep-cap-caudal');
    const capReglaEl = document.getElementById('rep-cap-regla');
    const capTimeEl = document.getElementById('rep-cap-time');

    const cap = data.capanema || {};
    if (capCaudalEl) capCaudalEl.textContent = fmt(cap.caudal);
    if (capReglaEl) capReglaEl.textContent = cap.regla != null ? `${Number(cap.regla).toFixed(2)} m` : '—';
    if (capTimeEl) {
      capTimeEl.innerHTML = window.Components && typeof Components.renderFreshnessBadge === 'function'
        ? Components.renderFreshnessBadge('COPEL', cap.fecha)
        : formatDt(cap.fecha);
    }

    // 6. Tarjeta Cataratas (COPEL / Parques) - Solo fuente propia de Cataratas
    const catCaudalEl = document.getElementById('rep-cat-caudal');
    const catReglaEl = document.getElementById('rep-cat-regla');
    const catTimeEl = document.getElementById('rep-cat-time');

    const cat = data.centrales_lista ? data.centrales_lista.find(c => c.codigo === 'CATARATAS') : null;
    const catCaudal = (cat && cat.caudal != null) ? cat.caudal : (data.cataratas ? data.cataratas.caudal : null);
    const catRegla = (cat && cat.regla != null) ? cat.regla : (data.cataratas ? data.cataratas.regla : null);
    const catFecha = (cat && cat.fecha) ? cat.fecha : (data.cataratas ? data.cataratas.fecha : null);

    if (catCaudalEl) catCaudalEl.textContent = fmt(catCaudal);
    if (catReglaEl) catReglaEl.textContent = catRegla != null ? `${Number(catRegla).toFixed(2)} m` : '—';
    if (catTimeEl) {
      catTimeEl.innerHTML = window.Components && typeof Components.renderFreshnessBadge === 'function'
        ? Components.renderFreshnessBadge('COPEL', catFecha)
        : formatDt(catFecha);
    }

    // 7. Etiqueta de actualización ONS
    const syncLabel = document.getElementById('rep-sync-label');
    if (syncLabel) {
      syncLabel.textContent = data.ultima_actualizacion_ons
        ? `Sincronizado ONS: ${formatDt(data.ultima_actualizacion_ons)}`
        : 'Sincronizado ONS';
    }
  },

  renderSchematic(data) {
    const container = document.getElementById('river-schematic-flow');
    if (!container) return;

    const it = data.itaipu || {};
    const ig = data.iguazu || {};
    const bal = data.balance_yacyreta || {};
    const centrales = data.centrales_lista || [];
    const fmt = (v) => (v !== undefined && v !== null && !isNaN(v) && v > 0 ? Number(v).toLocaleString('es-AR') : '—');

    // Mapeo por clave tolerante a acentos
    const norm = (str) => (str || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    const getFlow = (claveSubstr) => {
      const target = norm(claveSubstr);
      const match = centrales.find(c => norm(c.nombre).includes(target) || norm(c.clave || '').includes(target) || norm(c.codigo || '').includes(target));
      if (match) {
        const val = match.defluente ?? match.caudal ?? match.flow_out_m3s;
        if (val !== undefined && val !== null && !isNaN(val)) return fmt(val);
      }
      return '—';
    };

    const jupiaFlow = getFlow('jupi') !== '—' ? getFlow('jupi') : (data.jupia ? fmt(data.jupia.defluente ?? data.jupia.flow_out_m3s) : '—');
    const primaveraFlow = getFlow('primavera') !== '—' ? getFlow('primavera') : (data.porto_primavera ? fmt(data.porto_primavera.defluente ?? data.porto_primavera.flow_out_m3s) : '—');
    const areiaFlow = getFlow('areia');
    const segredoFlow = getFlow('segredo') !== '—'
      ? getFlow('segredo')
      : (data.segredo_copel && (data.segredo_copel.defluente != null || data.segredo_copel.flow_out_m3s != null)
         ? fmt(data.segredo_copel.defluente ?? data.segredo_copel.flow_out_m3s)
         : '—');
    const santiagoFlow = getFlow('santiago');
    const osorioFlow = getFlow('osorio');
    const caxiasFlow = getFlow('caxias');
    const baixoFlow = fmt(ig.baixo_iguazu_defluente);
    const capanemaFlow = getFlow('capanema') !== '—' ? getFlow('capanema') : (data.capanema ? fmt(data.capanema.caudal) : '—');
    const cataratasFlow = fmt(ig.cataratas_caudal);
    const itaipuFlow = fmt(it.defluente);
    const totalFlow = fmt(bal.caudal_total_m3s);

    container.innerHTML = `
      <div class="flex flex-col space-y-2.5 text-xs">
        
        <!-- Brazo Río Paraná: Cascada Jupiá -> Porto Primavera -> Itaipú -->
        <div class="flex items-center gap-1.5 overflow-x-auto pb-1">
          <span class="text-[11px] font-bold text-sky-600 dark:text-sky-400 w-24 shrink-0 flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-full bg-sky-500"></span>
            <span>Río Paraná:</span>
          </span>

          <!-- Jupiá -->
          <div class="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 px-2 py-1 rounded-md shrink-0 text-center">
            <div class="text-[10px] text-slate-400 font-medium">Jupiá</div>
            <div class="font-data font-bold text-slate-700 dark:text-slate-200 text-[11px] tabular-nums">${jupiaFlow} <span class="text-[9px] font-normal opacity-70">m³/s</span></div>
          </div>
          <span class="text-slate-300 dark:text-slate-600 text-[10px]">➔</span>

          <!-- Porto Primavera -->
          <div class="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 px-2 py-1 rounded-md shrink-0 text-center">
            <div class="text-[10px] text-slate-400 font-medium">P. Primavera</div>
            <div class="font-data font-bold text-slate-700 dark:text-slate-200 text-[11px] tabular-nums">${primaveraFlow} <span class="text-[9px] font-normal opacity-70">m³/s</span></div>
          </div>
          <span class="text-slate-300 dark:text-slate-600 text-[10px]">➔</span>

          <!-- Itaipú (Binacional) -->
          <div class="flex items-center gap-1.5 bg-sky-50 dark:bg-sky-950/40 border border-sky-300 dark:border-sky-800/80 px-2.5 py-1 rounded-lg shrink-0">
            <div class="text-[10px] font-bold text-sky-700 dark:text-sky-300">Itaipú</div>
            <span class="font-data font-extrabold text-sky-600 dark:text-sky-400 ml-1 tabular-nums">${itaipuFlow}</span>
            <span class="text-[9px] text-slate-400">m³/s</span>
          </div>
        </div>

        <!-- Brazo Río Iguazú: Cascada Simplificada -->
        <div class="flex items-center gap-1.5 overflow-x-auto pb-1">
          <span class="text-[11px] font-bold text-emerald-600 dark:text-emerald-400 w-24 shrink-0 flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
            <span>Río Iguazú:</span>
          </span>

          <!-- Areia -->
          <div class="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 px-2 py-1 rounded-md shrink-0 text-center">
            <div class="text-[10px] text-slate-400">Areia</div>
            <div class="font-data font-bold text-slate-700 dark:text-slate-200 text-[11px] tabular-nums">${areiaFlow}</div>
          </div>
          <span class="text-slate-300 dark:text-slate-600 text-[10px]">➔</span>

          <!-- Segredo -->
          <div class="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 px-2 py-1 rounded-md shrink-0 text-center">
            <div class="text-[10px] text-slate-400">Segredo</div>
            <div class="font-data font-bold text-slate-700 dark:text-slate-200 text-[11px] tabular-nums">${segredoFlow}</div>
          </div>
          <span class="text-slate-300 dark:text-slate-600 text-[10px]">➔</span>

          <!-- Santiago -->
          <div class="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 px-2 py-1 rounded-md shrink-0 text-center">
            <div class="text-[10px] text-slate-400">Santiago</div>
            <div class="font-data font-bold text-slate-700 dark:text-slate-200 text-[11px] tabular-nums">${santiagoFlow}</div>
          </div>
          <span class="text-slate-300 dark:text-slate-600 text-[10px]">➔</span>

          <!-- Osório -->
          <div class="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 px-2 py-1 rounded-md shrink-0 text-center">
            <div class="text-[10px] text-slate-400">Osório</div>
            <div class="font-data font-bold text-slate-700 dark:text-slate-200 text-[11px] tabular-nums">${osorioFlow}</div>
          </div>
          <span class="text-slate-300 dark:text-slate-600 text-[10px]">➔</span>

          <!-- Caxias -->
          <div class="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 px-2 py-1 rounded-md shrink-0 text-center">
            <div class="text-[10px] text-slate-400">Caxias</div>
            <div class="font-data font-bold text-slate-700 dark:text-slate-200 text-[11px] tabular-nums">${caxiasFlow}</div>
          </div>
          <span class="text-slate-300 dark:text-slate-600 text-[10px]">➔</span>

          <!-- Baixo Iguaçu (Destacada) -->
          <div class="bg-emerald-50 dark:bg-emerald-950/50 border border-emerald-300 dark:border-emerald-800 px-2.5 py-1 rounded-md shrink-0 text-center">
            <div class="text-[10px] font-bold text-emerald-700 dark:text-emerald-400">Baixo Iguaçu</div>
            <div class="font-data font-extrabold text-emerald-600 dark:text-emerald-300 text-[11px] tabular-nums">${baixoFlow} <span class="text-[9px] font-normal opacity-70">m³/s</span></div>
          </div>
          <span class="text-slate-300 dark:text-slate-600 text-[10px]">➔</span>

          <!-- Porto Capanema -->
          <div class="bg-amber-50/70 dark:bg-amber-950/40 border border-amber-300/80 dark:border-amber-800/60 px-2 py-1 rounded-md shrink-0 text-center">
            <div class="text-[10px] font-semibold text-amber-800 dark:text-amber-300">Capanema</div>
            <div class="font-data font-bold text-amber-600 dark:text-amber-300 text-[11px] tabular-nums">${capanemaFlow} <span class="text-[9px] font-normal opacity-70">m³/s</span></div>
          </div>
          <span class="text-slate-300 dark:text-slate-600 text-[10px]">➔</span>

          <!-- Cataratas (Destacada) -->
          <div class="bg-amber-50 dark:bg-amber-950/50 border border-amber-300 dark:border-amber-800 px-2.5 py-1 rounded-md shrink-0 text-center">
            <div class="text-[10px] font-bold text-amber-700 dark:text-amber-400">Cataratas</div>
            <div class="font-data font-extrabold text-amber-600 dark:text-amber-300 text-[11px] tabular-nums">${cataratasFlow} <span class="text-[9px] font-normal opacity-70">m³/s</span></div>
          </div>
        </div>

      </div>
    `;
  },

  setTableFilter(category) {
    this.tableFilter = category;
    document.querySelectorAll('.btn-dam-filter').forEach(btn => {
      btn.classList.toggle('active', btn.getAttribute('data-filter') === category);
    });

    if (this.data && this.data.centrales_lista) {
      this.renderTable(this.data.centrales_lista);
    }
  },

  renderTable(centrales) {
    const tbody = document.getElementById('represas-table-body');
    if (!tbody) return;

    if (!centrales || centrales.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" class="text-center py-4 text-slate-400">Sin datos de centrales</td></tr>';
      return;
    }

    let filtered = centrales;
    if (this.tableFilter === 'parana') {
      filtered = centrales.filter(c => c.rio && c.rio.toLowerCase().includes('paran'));
    } else if (this.tableFilter === 'iguazu') {
      filtered = centrales.filter(c => c.rio && c.rio.toLowerCase().includes('iguaz') && !c.rio.toLowerCase().includes('afluente'));
    } else if (this.tableFilter === 'afluentes') {
      filtered = centrales.filter(c => c.rio && (c.rio.toLowerCase().includes('jord') || c.rio.toLowerCase().includes('afluente')));
    }

    const fmt = (v) => (v !== undefined && v !== null && !isNaN(v) ? Number(v).toLocaleString('es-AR', { maximumFractionDigits: 1 }) : '—');

    tbody.innerHTML = filtered.map(c => {
      const isItaipu = c.nombre.toLowerCase().includes('itaip');
      const isBaixo = c.nombre.toLowerCase().includes('baixo');
      const isCataratas = c.nombre.toLowerCase().includes('catarata');
      const isCapanema = c.nombre.toLowerCase().includes('capanema');
      const isJupia = c.nombre.toLowerCase().includes('jupi');
      const isPrimavera = c.nombre.toLowerCase().includes('primavera');

      let rowHighlight = '';
      if (isItaipu) rowHighlight = 'bg-sky-50/50 dark:bg-sky-950/20 font-medium';
      else if (isJupia || isPrimavera) rowHighlight = 'bg-sky-50/30 dark:bg-sky-950/15 font-medium';
      else if (isBaixo) rowHighlight = 'bg-emerald-50/50 dark:bg-emerald-950/20 font-medium';
      else if (isCataratas || isCapanema) rowHighlight = 'bg-amber-50/40 dark:bg-amber-950/20';

      let damBadge = '';
      if (isItaipu) damBadge = '<span class="text-[9px] px-1.5 py-0.5 rounded bg-sky-100 dark:bg-sky-900 text-sky-700 dark:text-sky-300 font-sans font-bold">Binacional</span>';
      else if (isJupia || isPrimavera) damBadge = '<span class="text-[9px] px-1.5 py-0.5 rounded bg-sky-100/70 dark:bg-sky-950 text-sky-700 dark:text-sky-400 font-sans font-semibold border border-sky-300/50">Alto Paraná</span>';
      else if (isCapanema || isCataratas) damBadge = '<span class="text-[9px] px-1.5 py-0.5 rounded bg-amber-100/80 dark:bg-amber-950 text-amber-700 dark:text-amber-400 font-sans font-semibold border border-amber-300/60">Medición</span>';

      const cotaVal = c.cota ?? c.level_m ?? c.nivel ?? c.regla;
      const cotaStr = cotaVal !== undefined && cotaVal !== null ? `${Number(cotaVal).toFixed(2)} m` : '—';
      const volStr = c.vol_pct ? `${c.vol_pct}%` : '—';
      const afluVal = c.afluente ?? c.flow_in_m3s;
      const afluStr = afluVal !== undefined && afluVal !== null ? fmt(afluVal) : '—';
      const turbVal = c.turbinada ?? c.flow_turbined_m3s;
      const turbStr = turbVal !== undefined && turbVal !== null ? fmt(turbVal) : '—';
      const vertNum = Number(c.vertida ?? c.flow_spilled_m3s ?? 0);
      const vertStr = fmt(vertNum);
      const deflVal = c.defluente ?? c.caudal ?? c.flow_out_m3s;
      const deflStr = deflVal !== undefined && deflVal !== null ? fmt(deflVal) : '—';

      const vertBadge = vertNum > 0
        ? `<span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 dark:bg-amber-950 text-amber-700 dark:text-amber-400 border border-amber-300 dark:border-amber-800 tabular-nums">${vertStr}</span>`
        : `<span class="text-slate-400 tabular-nums">0</span>`;

      const damDate = c.fecha || c.measured_at;
      const damSrc = c.fuente || c.source || 'ONS';
      const freshnessBadge = window.Components && typeof Components.renderFreshnessBadge === 'function'
        ? Components.renderFreshnessBadge(damSrc, damDate)
        : ((window.Components && typeof Components.formatDateTime === 'function' ? Components.formatDateTime(damDate) : damDate) || '—');

      return `
        <tr onclick="RepresasView.openDamHistoryModal('${c.codigo}')" class="border-b border-slate-100 dark:border-slate-800/60 hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition cursor-pointer ${rowHighlight}" title="Haga clic para ver el histórico de caudales y niveles">
          <td class="py-2.5 px-3">
            <div class="font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
              <span>${c.nombre}</span>
              ${damBadge}
              <svg class="w-3 h-3 text-slate-400 opacity-50 shrink-0 ml-1 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a2 2 0 01-2 2H6a2 2 0 01-2-2V4z"/></svg>
            </div>
            <div class="text-[10px] text-slate-400">${c.operador} • ${c.rio}</div>
          </td>
          <td class="py-2.5 px-3 font-mono tabular-nums">${cotaStr}</td>
          <td class="py-2.5 px-3 font-mono tabular-nums text-slate-500">${volStr}</td>
          <td class="py-2.5 px-3 font-mono tabular-nums text-slate-700 dark:text-slate-300">${afluStr}</td>
          <td class="py-2.5 px-3 font-mono tabular-nums text-sky-600 dark:text-sky-400 font-semibold">${turbStr}</td>
          <td class="py-2.5 px-3 font-mono tabular-nums">${vertBadge}</td>
          <td class="py-2.5 px-3 font-mono tabular-nums text-emerald-600 dark:text-emerald-400 font-bold">${deflStr}</td>
          <td class="py-2.5 px-3 font-mono tabular-nums text-[11px] text-slate-400">${freshnessBadge}</td>
        </tr>
      `;
    }).join('');
  },

  toggleFloatingResetBtn(btnId, show) {
    const btn = document.getElementById(btnId);
    if (!btn) return;
    if (show) {
      btn.classList.remove('hidden');
      btn.classList.add('flex');
    } else {
      btn.classList.add('hidden');
      btn.classList.remove('flex');
    }
  },

  resetCaudalesZoom() {
    if (this.caudalesChart && typeof this.caudalesChart.resetZoom === 'function') {
      this.caudalesChart.resetZoom();
      this.toggleFloatingResetBtn('floating-reset-zoom-caudales', false);
    }
  },

  resetItaipuZoom() {
    if (this.itaipuChart && typeof this.itaipuChart.resetZoom === 'function') {
      this.itaipuChart.resetZoom();
      this.toggleFloatingResetBtn('floating-reset-zoom-itaipu', false);
    }
  },

  renderCharts(timeline, isDark) {
    if (!timeline || timeline.length === 0) return;

    const useTimeScale = window.Charts && typeof Charts.hasDateAdapter === 'function' ? Charts.hasDateAdapter() : false;

    const labels = [];
    const timeTotal = [];
    const timeItaipu = [];
    const timeIguazu = [];
    const timeTurbinada = [];
    const timeVertida = [];

    const scalarTotal = [];
    const scalarItaipu = [];
    const scalarIguazu = [];
    const scalarTurbinada = [];
    const scalarVertida = [];

    timeline.forEach(p => {
      const raw = p.t || '';
      let displayLabel = raw;
      if (window.Components && typeof Components.formatDateTime === 'function') {
        const full = Components.formatDateTime(raw);
        displayLabel = full.length >= 16 ? full.slice(0, 5) + ' ' + full.slice(11, 16) : full;
      } else if (raw.length >= 16) {
        displayLabel = raw.slice(5, 16);
      }
      labels.push(displayLabel);
      const isoT = raw.replace(' ', 'T');

      const parseVal = (v) => (v !== undefined && v !== null && !isNaN(Number(v))) ? Number(v) : null;

      const tot = parseVal(p.total_yacyreta);
      const itDef = parseVal(p.itaipu_defluente);
      const igDef = parseVal(p.iguazu_defluente);
      const itTurb = parseVal(p.itaipu_turbinada);
      const itVert = parseVal(p.itaipu_vertida);

      timeTotal.push({ x: isoT, y: tot });
      timeItaipu.push({ x: isoT, y: itDef });
      timeIguazu.push({ x: isoT, y: igDef });
      timeTurbinada.push({ x: isoT, y: itTurb });
      timeVertida.push({ x: isoT, y: itVert });

      scalarTotal.push(tot);
      scalarItaipu.push(itDef);
      scalarIguazu.push(igDef);
      scalarTurbinada.push(itTurb);
      scalarVertida.push(itVert);
    });

    const gridColor = isDark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(15, 23, 42, 0.06)';
    const textColor = isDark ? '#94a3b8' : '#64748b';

    const xScaleConfig = useTimeScale
      ? {
          type: 'time',
          time: {
            tooltipFormat: 'yyyy-MM-dd HH:mm',
            displayFormats: { hour: 'dd/MM HH:mm', day: 'dd/MM' }
          },
          grid: { color: gridColor },
          ticks: { color: textColor, font: { family: 'JetBrains Mono', size: 10 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 7 }
        }
      : {
          type: 'category',
          grid: { color: gridColor },
          ticks: { color: textColor, font: { family: 'JetBrains Mono', size: 10 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 7 }
        };

    const tooltipConfig = {
      backgroundColor: isDark ? 'rgba(6, 19, 36, 0.96)' : 'rgba(255, 255, 255, 0.98)',
      titleColor: isDark ? '#f8fafc' : '#0f294a',
      bodyColor: isDark ? '#94a3b8' : '#334155',
      borderColor: isDark ? '#1b3a63' : '#cbd5e1',
      borderWidth: 1,
      padding: 10,
      cornerRadius: 8,
      titleFont: { family: 'JetBrains Mono', size: 11 },
      bodyFont: { family: 'Space Grotesk', size: 12, weight: '700' },
      callbacks: {
        label: (ctx) => {
          const yVal = ctx.parsed && ctx.parsed.y !== undefined ? ctx.parsed.y : ctx.raw;
          return ` ${ctx.dataset.label}: ${Number(yVal).toLocaleString('es-AR')} m³/s`;
        }
      }
    };

    // 1. Gráfico de Caudal Total a Yacyretá vs Aportes (Estilo PNA)
    const canvasCaudales = document.getElementById('chartCaudalesYacyreta');
    if (canvasCaudales) {
      if (this.caudalesChart && this._caudalesIsDark === isDark && this.caudalesChart.data.datasets.length === 3) {
        if (!useTimeScale) this.caudalesChart.data.labels = labels;
        this.caudalesChart.data.datasets[0].data = useTimeScale ? timeTotal : scalarTotal;
        this.caudalesChart.data.datasets[1].data = useTimeScale ? timeItaipu : scalarItaipu;
        this.caudalesChart.data.datasets[2].data = useTimeScale ? timeIguazu : scalarIguazu;
        this.caudalesChart.data.datasets[2].label = 'Río Iguazú';
        this.caudalesChart.update('none');
      } else {
        if (this.caudalesChart) this.caudalesChart.destroy();
        const ctxC = canvasCaudales.getContext('2d');
        const hC = canvasCaudales.clientHeight || 250;

        const gradTotal = ctxC.createLinearGradient(0, 0, 0, hC);
        if (isDark) {
          gradTotal.addColorStop(0, 'rgba(16, 185, 129, 0.32)');
          gradTotal.addColorStop(0.7, 'rgba(16, 185, 129, 0.06)');
          gradTotal.addColorStop(1, 'rgba(16, 185, 129, 0.00)');
        } else {
          gradTotal.addColorStop(0, 'rgba(16, 185, 129, 0.28)');
          gradTotal.addColorStop(0.7, 'rgba(16, 185, 129, 0.04)');
          gradTotal.addColorStop(1, 'rgba(16, 185, 129, 0.00)');
        }

        const gradItaipu = ctxC.createLinearGradient(0, 0, 0, hC);
        if (isDark) {
          gradItaipu.addColorStop(0, 'rgba(56, 189, 248, 0.20)');
          gradItaipu.addColorStop(1, 'rgba(56, 189, 248, 0.00)');
        } else {
          gradItaipu.addColorStop(0, 'rgba(2, 132, 199, 0.18)');
          gradItaipu.addColorStop(1, 'rgba(2, 132, 199, 0.00)');
        }

        this.caudalesChart = new Chart(ctxC, {
          type: 'line',
          data: {
            labels: useTimeScale ? undefined : labels,
            datasets: [
              {
                label: 'Total',
                data: useTimeScale ? timeTotal : scalarTotal,
                borderColor: '#10b981',
                backgroundColor: gradTotal,
                fill: 'start',
                borderWidth: 2.2,
                tension: 0.12,
                pointRadius: scalarTotal.length > 100 ? 0 : 2,
                pointHoverRadius: 5,
                pointBackgroundColor: '#10b981',
                spanGaps: true
              },
              {
                label: 'Aporte Itaipú',
                data: useTimeScale ? timeItaipu : scalarItaipu,
                borderColor: isDark ? '#38bdf8' : '#0284c7',
                backgroundColor: gradItaipu,
                fill: 'start',
                borderWidth: 2,
                tension: 0.12,
                pointRadius: scalarItaipu.length > 100 ? 0 : 2,
                pointHoverRadius: 5,
                spanGaps: true
              },
              {
                label: 'Río Iguazú',
                data: useTimeScale ? timeIguazu : scalarIguazu,
                borderColor: '#f59e0b',
                backgroundColor: 'transparent',
                fill: false,
                borderWidth: 2,
                borderDash: [6, 4],
                tension: 0.12,
                pointRadius: scalarIguazu.length > 100 ? 0 : 2,
                pointHoverRadius: 5,
                spanGaps: true
              }
            ]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 300 },
            interaction: { mode: 'index', intersect: false },
            plugins: {
              legend: {
                position: 'top',
                labels: {
                  color: textColor,
                  font: { size: 11, family: 'Inter', weight: 'bold' },
                  boxWidth: 12
                }
              },
              tooltip: tooltipConfig,
              zoom: {
                pan: { enabled: false },
                zoom: {
                  drag: {
                    enabled: true,
                    backgroundColor: isDark ? 'rgba(16, 185, 129, 0.22)' : 'rgba(16, 185, 129, 0.16)',
                    borderColor: '#10b981',
                    borderWidth: 1.5
                  },
                  pinch: { enabled: true },
                  mode: 'x',
                  onZoomComplete: () => {
                    RepresasView.toggleFloatingResetBtn('floating-reset-zoom-caudales', true);
                  }
                }
              }
            },
            scales: {
              x: xScaleConfig,
              y: {
                grid: { color: gridColor },
                ticks: {
                  color: textColor,
                  font: { family: 'Space Grotesk', size: 10, weight: '600' },
                  callback: (v) => `${Number(v).toLocaleString('es-AR')} m³/s`
                }
              }
            }
          }
        });
        this._caudalesIsDark = isDark;
      }

      this.toggleFloatingResetBtn('floating-reset-zoom-caudales', false);
    }

    // 2. Gráfico Desglose Itaipú (Turbinado vs Vertido)
    const canvasItaipu = document.getElementById('chartItaipuTurbinado');
    if (canvasItaipu) {
      if (this.itaipuChart && this._itaipuIsDark === isDark && this.itaipuChart.data.datasets.length === 2) {
        if (!useTimeScale) this.itaipuChart.data.labels = labels;
        this.itaipuChart.data.datasets[0].data = useTimeScale ? timeTurbinada : scalarTurbinada;
        this.itaipuChart.data.datasets[1].data = useTimeScale ? timeVertida : scalarVertida;
        this.itaipuChart.update('none');
      } else {
        if (this.itaipuChart) this.itaipuChart.destroy();
        const ctxI = canvasItaipu.getContext('2d');
        const hI = canvasItaipu.clientHeight || 250;

        const gradTurb = ctxI.createLinearGradient(0, 0, 0, hI);
        if (isDark) {
          gradTurb.addColorStop(0, 'rgba(56, 189, 248, 0.32)');
          gradTurb.addColorStop(0.7, 'rgba(56, 189, 248, 0.05)');
          gradTurb.addColorStop(1, 'rgba(56, 189, 248, 0.00)');
        } else {
          gradTurb.addColorStop(0, 'rgba(2, 132, 199, 0.28)');
          gradTurb.addColorStop(0.7, 'rgba(2, 132, 199, 0.04)');
          gradTurb.addColorStop(1, 'rgba(2, 132, 199, 0.00)');
        }

        const gradVert = ctxI.createLinearGradient(0, 0, 0, hI);
        if (isDark) {
          gradVert.addColorStop(0, 'rgba(249, 115, 22, 0.32)');
          gradVert.addColorStop(0.7, 'rgba(249, 115, 22, 0.05)');
          gradVert.addColorStop(1, 'rgba(249, 115, 22, 0.00)');
        } else {
          gradVert.addColorStop(0, 'rgba(249, 115, 22, 0.26)');
          gradVert.addColorStop(0.7, 'rgba(249, 115, 22, 0.04)');
          gradVert.addColorStop(1, 'rgba(249, 115, 22, 0.00)');
        }

        this.itaipuChart = new Chart(ctxI, {
          type: 'line',
          data: {
            labels: useTimeScale ? undefined : labels,
            datasets: [
              {
                label: 'Caudal Turbinado',
                data: useTimeScale ? timeTurbinada : scalarTurbinada,
                borderColor: isDark ? '#38bdf8' : '#0284c7',
                backgroundColor: gradTurb,
                fill: 'start',
                borderWidth: 2,
                tension: 0.12,
                pointRadius: scalarTurbinada.length > 100 ? 0 : 2,
                pointHoverRadius: 5,
                spanGaps: true
              },
              {
                label: 'Caudal Vertido',
                data: useTimeScale ? timeVertida : scalarVertida,
                borderColor: '#f97316',
                backgroundColor: gradVert,
                fill: 'start',
                borderWidth: 2,
                tension: 0.12,
                pointRadius: scalarVertida.length > 100 ? 0 : 2,
                pointHoverRadius: 5,
                spanGaps: true
              }
            ]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 300 },
            interaction: { mode: 'index', intersect: false },
            plugins: {
              legend: {
                position: 'top',
                labels: {
                  color: textColor,
                  font: { size: 11, family: 'Inter', weight: 'bold' },
                  boxWidth: 12
                }
              },
              tooltip: tooltipConfig,
              zoom: {
                pan: { enabled: false },
                zoom: {
                  drag: {
                    enabled: true,
                    backgroundColor: isDark ? 'rgba(56, 189, 248, 0.22)' : 'rgba(2, 132, 199, 0.18)',
                    borderColor: isDark ? '#38bdf8' : '#0284c7',
                    borderWidth: 1.5
                  },
                  pinch: { enabled: true },
                  mode: 'x',
                  onZoomComplete: () => {
                    RepresasView.toggleFloatingResetBtn('floating-reset-zoom-itaipu', true);
                  }
                }
              }
            },
            scales: {
              x: xScaleConfig,
              y: {
                grid: { color: gridColor },
                ticks: {
                  color: textColor,
                  font: { family: 'Space Grotesk', size: 10, weight: '600' },
                  callback: (v) => `${Number(v).toLocaleString('es-AR')} m³/s`
                }
              }
            }
          }
        });
        this._itaipuIsDark = isDark;
      }

      this.toggleFloatingResetBtn('floating-reset-zoom-itaipu', false);
    }
  },

  async syncRepresasData() {
    const icon = document.getElementById('sync-represas-icon');
    if (icon) icon.classList.add('animate-spin');

    Components.showToast('ONS S3', 'Descargando dataset hidrológico oficial de ONS: Itaipú y Cuenca Iguazú...');
    try {
      const res = await API.syncRepresas();
      if (res && res.success) {
        const total = res.total_yacyreta ? Number(res.total_yacyreta).toLocaleString('es-AR') : '—';
        Components.showToast('ONS Actualizado', `Datos hidrológicos sincronizados. Caudal a Yacyretá: ${total} m³/s.`);
        await this.loadData();
      } else {
        Components.showToast('Aviso ONS', res.error || 'Sincronización completada sin cambios.');
      }
    } catch (e) {
      Components.showToast('Error ONS', e.message, true);
    } finally {
      if (icon) icon.classList.remove('animate-spin');
    }
  },

  /* ============================================================
     HISTÓRICO HORARIO ONS POR CENTRAL (MODAL & CHART)
     ============================================================ */
  openDamHistoryModal(codigo) {
    const modal = document.getElementById('modal-dam-history');
    if (modal) {
      modal.style.display = 'flex';
      modal.classList.remove('hidden');
    }
    const targetCode = codigo || this.damModalState.activeCode || 'PNITAI';
    this.loadDamHistory(targetCode, this.damModalState.activeMonth);
  },

  closeDamHistoryModal() {
    const modal = document.getElementById('modal-dam-history');
    if (this.damModalState.isFullscreen) {
      this.toggleDamModalFullscreen();
    }
    if (modal) {
      modal.style.display = 'none';
      modal.classList.add('hidden');
    }
  },

  toggleDamModalFullscreen() {
    const dialog = document.getElementById('modal-dam-dialog');
    const modal = document.getElementById('modal-dam-history');
    const iconExpand = document.getElementById('dam-modal-icon-expand');
    const iconCollapse = document.getElementById('dam-modal-icon-collapse');
    const btn = document.getElementById('dam-modal-btn-fullscreen');
    if (!dialog || !modal) return;

    this.damModalState.isFullscreen = !this.damModalState.isFullscreen;

    if (this.damModalState.isFullscreen) {
      modal.classList.remove('p-1', 'sm:p-2.5');
      modal.classList.add('p-0');
      dialog.classList.remove('w-[98vw]', 'max-w-[1850px]', 'h-[95vh]', 'rounded-2xl');
      dialog.classList.add('fixed', 'inset-0', 'w-screen', 'h-screen', 'max-w-none', 'rounded-none', 'm-0', 'border-0');
      if (iconExpand) iconExpand.classList.add('hidden');
      if (iconCollapse) iconCollapse.classList.remove('hidden');
      if (btn) btn.title = 'Salir de pantalla completa';
    } else {
      modal.classList.add('p-1', 'sm:p-2.5');
      modal.classList.remove('p-0');
      dialog.classList.add('w-[98vw]', 'max-w-[1850px]', 'h-[95vh]', 'rounded-2xl');
      dialog.classList.remove('fixed', 'inset-0', 'w-screen', 'h-screen', 'max-w-none', 'rounded-none', 'm-0', 'border-0');
      if (iconExpand) iconExpand.classList.remove('hidden');
      if (iconCollapse) iconCollapse.classList.add('hidden');
      if (btn) btn.title = 'Pantalla completa (Maximizar)';
    }

    setTimeout(() => {
      if (this.damModalState.chart) {
        this.damModalState.chart.resize();
      }
    }, 100);
  },

  handleDamModalBackdropClick(e) {
    if (e && e.target && e.target.id === 'modal-dam-history') {
      this.closeDamHistoryModal();
    }
  },

  async onDamStationSelectChange(val) {
    if (val && val !== this.damModalState.activeCode) {
      return await this.loadDamHistory(val, this.damModalState.activeMonth);
    }
  },

  async onDamMonthSelectChange(val) {
    this.damModalState.activeMonth = val || null;
    return await this.loadDamHistory(this.damModalState.activeCode, this.damModalState.activeMonth);
  },

  toggleDamVariable(varId, checked) {
    if (checked) {
      this.damModalState.activeVariables.add(varId);
    } else {
      if (this.damModalState.activeVariables.size > 1) {
        this.damModalState.activeVariables.delete(varId);
      } else {
        const checkbox = document.getElementById(`dam-chk-${varId}`);
        if (checkbox) checkbox.checked = true;
        if (window.Components && typeof Components.showToast === 'function') {
          Components.showToast('Visualizador', 'Debe seleccionar al menos una variable para el gráfico.');
        }
        return;
      }
    }
    this.renderDamHistoryChart();
  },

  setDamTimeRange(range) {
    this.damModalState.activeRange = range;
    document.querySelectorAll('.btn-dam-range').forEach(btn => {
      const match = btn.getAttribute('data-range') === range;
      btn.classList.toggle('active', match);
      btn.classList.toggle('bg-white', match);
      btn.classList.toggle('dark:bg-slate-700', match);
      btn.classList.toggle('text-sky-600', match);
      btn.classList.toggle('dark:text-sky-300', match);
      btn.classList.toggle('shadow-xs', match);
    });
    this.renderDamHistoryChart();
  },

  resetDamZoom() {
    if (this.damModalState.chart && typeof this.damModalState.chart.resetZoom === 'function') {
      this.damModalState.chart.resetZoom();
      this.toggleFloatingResetBtn('dam-modal-floating-reset-zoom', false);
    }
  },

  async loadDamHistory(codigo, mes) {
    const loadingEl = document.getElementById('dam-modal-loading');
    if (loadingEl) loadingEl.classList.remove('hidden');

    this.damModalState.activeCode = codigo;
    if (mes !== undefined) this.damModalState.activeMonth = mes;

    try {
      const res = await API.getDamHistory(codigo, this.damModalState.activeMonth);
      if (!res || !res.success) {
        throw new Error((res && res.error) || 'No se pudieron obtener datos de la central seleccionada.');
      }

      this.damModalState.data = res;
      this.damModalState.activeCode = res.codigo || codigo;

      const titleEl = document.getElementById('dam-modal-title');
      if (titleEl) titleEl.textContent = res.nombre || codigo;

      const subEl = document.getElementById('dam-modal-subtitle');
      if (subEl) {
        const parts = [res.operador, res.rio].filter(Boolean);
        subEl.textContent = parts.join(' · ');
      }

      const badgeEl = document.getElementById('dam-modal-source-badge');
      if (badgeEl) badgeEl.textContent = res.fuente || 'ONS';

      // Asegurar que activeVariables contenga variables válidas con datos de la central
      const availableVarsWithData = (res.variables || []).filter(v => v.has_data !== false);
      const availableVarIds = new Set(availableVarsWithData.map(v => v.id));
      const hasAnyWithData = Array.from(this.damModalState.activeVariables).some(id => availableVarIds.has(id));
      if (!hasAnyWithData || this.damModalState.activeVariables.size === 0) {
        this.damModalState.activeVariables.clear();
        (res.variables || []).forEach(v => {
          if (v.default && v.has_data !== false) this.damModalState.activeVariables.add(v.id);
        });
        if (this.damModalState.activeVariables.size === 0 && availableVarsWithData.length > 0) {
          this.damModalState.activeVariables.add(availableVarsWithData[0].id);
        }
      }

      this.populateDamStationSelector(res.centrales_disponibles || []);
      this.populateDamMonthSelector(res.periodos_disponibles || res.meses_disponibles || [], res.periodo || res.mes);
      this.populateDamVariables(res.variables || []);
      this.renderDamHistoryChart();

    } catch (err) {
      console.error('Error cargando histórico de represa:', err);
      if (window.Components && typeof Components.showToast === 'function') {
        Components.showToast('Histórico ONS', err.message || 'Error al conectar con la base histórica', true);
      }
    } finally {
      if (loadingEl) loadingEl.classList.add('hidden');
    }
  },

  populateDamStationSelector(centrales) {
    const sel = document.getElementById('dam-modal-station-select');
    if (!sel || !centrales || centrales.length === 0) return;

    const currentVal = this.damModalState.activeCode;
    const groups = {};
    centrales.forEach(c => {
      const grp = c.grupo || c.rio || 'Otras Centrales';
      if (!groups[grp]) groups[grp] = [];
      groups[grp].push(c);
    });

    let html = '';
    for (const [grpName, dams] of Object.entries(groups)) {
      html += `<optgroup label="${grpName}">`;
      dams.forEach(d => {
        const isSel = (d.codigo === currentVal) ? 'selected' : '';
        html += `<option value="${d.codigo}" ${isSel}>${d.nombre} · ${d.codigo}</option>`;
      });
      html += `</optgroup>`;
    }
    sel.innerHTML = html;
    sel.value = currentVal;
  },

  populateDamMonthSelector(periodos, selectedPeriod) {
    const sel = document.getElementById('dam-modal-month-select');
    if (!sel) return;

    if (!periodos || periodos.length === 0) {
      sel.innerHTML = '<option value="all">Todo el Histórico</option>';
      return;
    }

    const hasGroups = periodos.some(p => p.grupo);
    let html = '';
    if (hasGroups) {
      const groups = {};
      periodos.forEach(p => {
        const grp = p.grupo || 'Otros';
        if (!groups[grp]) groups[grp] = [];
        groups[grp].push(p);
      });
      for (const [grpName, items] of Object.entries(groups)) {
        html += `<optgroup label="${grpName}">`;
        items.forEach(item => {
          const itemVal = item.id || item.codigo;
          const isSel = (selectedPeriod && (selectedPeriod === itemVal || selectedPeriod === item.id || selectedPeriod === item.codigo)) ? 'selected' : '';
          html += `<option value="${itemVal}" ${isSel}>${item.label || itemVal}</option>`;
        });
        html += `</optgroup>`;
      }
    } else {
      periodos.forEach(m => {
        const mId = m.id || m.codigo;
        const isSel = (selectedPeriod && (selectedPeriod === mId || selectedPeriod === m.id || selectedPeriod === m.codigo)) ? 'selected' : '';
        html += `<option value="${mId}" ${isSel}>${m.label || mId}</option>`;
      });
    }
    sel.innerHTML = html;
    if (selectedPeriod) sel.value = selectedPeriod;
  },

  populateDamVariables(variables) {
    const container = document.getElementById('dam-modal-variables-container');
    if (!container) return;

    if (!variables || variables.length === 0) {
      container.innerHTML = '<span class="text-xs text-slate-400">Sin variables configuradas</span>';
      return;
    }

    if (this.damModalState.activeVariables.size === 0) {
      variables.forEach(v => {
        if (v.default && v.has_data !== false) this.damModalState.activeVariables.add(v.id);
      });
    }

    container.innerHTML = variables.map(v => {
      const isChecked = this.damModalState.activeVariables.has(v.id);
      const hasData = v.has_data !== false;
      const opacityClass = hasData ? '' : 'opacity-40 hover:opacity-75';

      return `
        <label class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg text-[11px] font-semibold cursor-pointer border transition select-none shrink-0 whitespace-nowrap ${opacityClass} ${
          isChecked
            ? 'bg-slate-100 dark:bg-slate-800 border-slate-300 dark:border-slate-700 text-slate-900 dark:text-slate-100 shadow-2xs'
            : 'bg-transparent border-transparent text-slate-400 hover:text-slate-700 dark:hover:text-slate-300'
        }" title="${v.nombre}">
          <input type="checkbox" id="dam-chk-${v.id}" ${isChecked ? 'checked' : ''} onchange="RepresasView.toggleDamVariable('${v.id}', this.checked)" class="w-3.5 h-3.5 rounded text-sky-600 focus:ring-sky-500 border-slate-300 dark:border-slate-600 cursor-pointer">
          <span class="w-2 h-2 rounded-full shrink-0" style="background-color: ${v.color || '#0284c7'};"></span>
          <span>${v.nombre}</span>
        </label>
      `;
    }).join('');
  },

  renderDamHistoryChart() {
    const canvas = document.getElementById('damHistoryChart');
    if (!canvas) return;

    const data = this.damModalState.data;
    if (!data || !data.puntos || data.puntos.length === 0) {
      if (this.damModalState.chart) {
        this.damModalState.chart.destroy();
        this.damModalState.chart = null;
      }
      return;
    }

    const isDark = (typeof State !== 'undefined' && State.theme === 'dark') || document.documentElement.classList.contains('dark') || document.documentElement.getAttribute('data-theme') === 'dark';
    const gridColor = isDark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(15, 23, 42, 0.06)';
    const textColor = isDark ? '#94a3b8' : '#64748b';

    let rawPoints = data.puntos;
    const range = this.damModalState.activeRange;
    if (range === '48h') {
      rawPoints = rawPoints.slice(-48);
    } else if (range === '7d') {
      rawPoints = rawPoints.slice(-168);
    } else if (range === '30d') {
      rawPoints = rawPoints.slice(-720);
    }

    const useTimeScale = window.Charts && typeof Charts.hasDateAdapter === 'function' ? Charts.hasDateAdapter() : false;

    const labels = [];
    const isMultiMonth = rawPoints.length > 800;
    rawPoints.forEach(p => {
      const raw = p.t || '';
      let displayLabel = raw;
      if (window.Components && typeof Components.formatDateTime === 'function') {
        const full = Components.formatDateTime(raw);
        if (isMultiMonth) {
          displayLabel = full.slice(0, 5);
        } else {
          displayLabel = full.length >= 16 ? full.slice(0, 5) + ' ' + full.slice(11, 16) : full;
        }
      } else if (raw.length >= 16) {
        displayLabel = isMultiMonth ? raw.slice(8, 10) + '/' + raw.slice(5, 7) : raw.slice(5, 16);
      }
      labels.push(displayLabel);
    });

    const availableVars = data.variables || [];
    const activeVarIds = this.damModalState.activeVariables;

    let hasFlowAxis = false;
    let hasLevelAxis = false;
    let hasVolAxis = false;

    const datasets = [];

    availableVars.forEach(v => {
      if (!activeVarIds.has(v.id)) return;

      const yAxisID = v.eje || 'y';
      if (yAxisID === 'y') hasFlowAxis = true;
      if (yAxisID === 'y1') hasLevelAxis = true;
      if (yAxisID === 'y2') hasVolAxis = true;

      const ptsData = rawPoints.map(p => {
        const rawVal = p[v.id];
        const val = (rawVal !== undefined && rawVal !== null && !isNaN(Number(rawVal))) ? Number(rawVal) : null;
        if (useTimeScale) {
          const raw = p.t || '';
          const isoT = raw.replace(' ', 'T');
          const timeMs = new Date(isoT).getTime();
          return { x: timeMs, y: val };
        }
        return val;
      });

      datasets.push({
        label: v.nombre,
        data: ptsData,
        unit: v.unidad,
        borderColor: v.color || '#0284c7',
        backgroundColor: (v.color || '#0284c7') + '15',
        borderWidth: 2,
        tension: 0.15,
        fill: false,
        pointRadius: rawPoints.length > 100 ? 0 : 2,
        pointHoverRadius: 5,
        yAxisID: yAxisID,
        spanGaps: true
      });
    });

    const tooltipConfig = {
      enabled: true,
      mode: 'index',
      intersect: false,
      backgroundColor: isDark ? 'rgba(6, 19, 36, 0.96)' : 'rgba(255, 255, 255, 0.98)',
      titleColor: isDark ? '#f8fafc' : '#0f294a',
      bodyColor: isDark ? '#94a3b8' : '#334155',
      borderColor: isDark ? '#1b3a63' : '#cbd5e1',
      borderWidth: 1,
      padding: 10,
      bodyFont: { family: 'Space Grotesk', size: 11 },
      titleFont: { family: 'Space Grotesk', size: 11, weight: 'bold' },
      callbacks: {
        label: (ctx) => {
          const val = ctx.parsed.y;
          const unit = ctx.dataset.unit || '';
          const label = ctx.dataset.label || '';
          if (val === null || val === undefined || isNaN(val)) return ` ${label}: —`;
          return ` ${label}: ${Number(val).toLocaleString('es-AR', { maximumFractionDigits: 1 })} ${unit}`;
        }
      }
    };

    let xScaleConfig = {
      grid: { color: gridColor },
      ticks: {
        color: textColor,
        font: { family: 'Space Grotesk', size: 10 },
        maxRotation: 0,
        autoSkip: true,
        maxTicksLimit: 12
      }
    };

    if (useTimeScale) {
      xScaleConfig = {
        type: 'time',
        time: {
          unit: range === '48h' ? 'hour' : 'day',
          displayFormats: {
            hour: 'HH:mm',
            day: 'dd/MM'
          },
          tooltipFormat: 'dd/MM/yyyy HH:mm'
        },
        grid: { color: gridColor },
        ticks: {
          color: textColor,
          font: { family: 'Space Grotesk', size: 10 },
          maxRotation: 0,
          autoSkip: true,
          maxTicksLimit: 12
        }
      };
    }

    const scalesConfig = {
      x: xScaleConfig,
      y: {
        type: 'linear',
        display: hasFlowAxis,
        position: 'left',
        grid: { color: gridColor },
        ticks: {
          color: textColor,
          font: { family: 'Space Grotesk', size: 10, weight: '600' },
          callback: (v) => `${Number(v).toLocaleString('es-AR')} m³/s`
        }
      },
      y1: {
        type: 'linear',
        display: hasLevelAxis,
        position: 'right',
        grid: { drawOnChartArea: false },
        ticks: {
          color: '#06b6d4',
          font: { family: 'Space Grotesk', size: 10, weight: '600' },
          callback: (v) => `${Number(v).toFixed(1)} m`
        }
      },
      y2: {
        type: 'linear',
        display: hasVolAxis,
        position: 'right',
        min: 0,
        max: 100,
        grid: { drawOnChartArea: false },
        ticks: {
          color: '#ec4899',
          font: { family: 'Space Grotesk', size: 10, weight: '600' },
          callback: (v) => `${v}%`
        }
      }
    };

    if (this.damModalState.chart && this.damModalState._isDark === isDark) {
      this.damModalState.chart.data.labels = useTimeScale ? undefined : labels;
      this.damModalState.chart.data.datasets = datasets;
      this.damModalState.chart.options.scales = scalesConfig;
      this.damModalState.chart.update('none');
    } else {
      if (this.damModalState.chart) {
        this.damModalState.chart.destroy();
      }

      this.damModalState.chart = new Chart(canvas, {
        type: 'line',
        data: {
          labels: useTimeScale ? undefined : labels,
          datasets: datasets
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: {
            mode: 'index',
            intersect: false
          },
          plugins: {
            legend: {
              display: true,
              position: 'top',
              labels: {
                color: textColor,
                font: { family: 'Space Grotesk', size: 11, weight: '600' },
                boxWidth: 12,
                boxHeight: 12,
                usePointStyle: true
              }
            },
            tooltip: tooltipConfig,
            zoom: {
              pan: { enabled: false },
              zoom: {
                drag: {
                  enabled: true,
                  backgroundColor: isDark ? 'rgba(56, 189, 248, 0.22)' : 'rgba(2, 132, 199, 0.18)',
                  borderColor: isDark ? '#38bdf8' : '#0284c7',
                  borderWidth: 1.5
                },
                pinch: { enabled: true },
                mode: 'x',
                onZoomComplete: () => {
                  RepresasView.toggleFloatingResetBtn('dam-modal-floating-reset-zoom', true);
                }
              }
            }
          },
          scales: scalesConfig
        }
      });
      this.damModalState._isDark = isDark;
    }

    this.toggleFloatingResetBtn('dam-modal-floating-reset-zoom', false);
  }
};

window.RepresasView = RepresasView;
window.syncRepresasData = () => RepresasView.syncRepresasData();
window.setDamTableFilter = (filter) => RepresasView.setTableFilter(filter);
window.resetCaudalesZoom = () => RepresasView.resetCaudalesZoom();
window.resetItaipuZoom = () => RepresasView.resetItaipuZoom();
window.openDamHistoryModal = (codigo) => RepresasView.openDamHistoryModal(codigo);
window.closeDamHistoryModal = () => RepresasView.closeDamHistoryModal();

window.toggleDamModalFullscreen = () => RepresasView.toggleDamModalFullscreen();

// Atajo de teclado Escape para cerrar modal o salir de pantalla completa
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    const modal = document.getElementById('modal-dam-history');
    if (modal && modal.style.display !== 'none' && !modal.classList.contains('hidden')) {
      if (RepresasView.damModalState.isFullscreen) {
        RepresasView.toggleDamModalFullscreen();
      } else {
        RepresasView.closeDamHistoryModal();
      }
    }
  }
});
