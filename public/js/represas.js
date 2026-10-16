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

    const fmt = (v) => (v !== undefined && v !== null ? Number(v).toLocaleString('es-AR', { maximumFractionDigits: 1 }) : '--');

    // 1. Hero Total hacia Yacyretá
    const totalEl = document.getElementById('rep-total-yacyreta');
    const itAporteEl = document.getElementById('rep-aporte-itaipu');
    const igAporteEl = document.getElementById('rep-aporte-iguazu');
    const itPctEl = document.getElementById('rep-pct-itaipu');
    const igPctEl = document.getElementById('rep-pct-iguazu');

    if (totalEl) totalEl.textContent = fmt(bal.caudal_total_m3s);
    if (itAporteEl) itAporteEl.textContent = `${fmt(bal.aporte_itaipu_m3s)} m³/s`;
    if (igAporteEl) igAporteEl.textContent = `${fmt(bal.aporte_iguazu_m3s)} m³/s`;
    if (itPctEl) itPctEl.textContent = `(${bal.pct_itaipu || 0}%)`;
    if (igPctEl) igPctEl.textContent = `(${bal.pct_iguazu || 0}%)`;

    // 2. Estado de Vertederos (Spillways)
    const itVertVal = Number(it.vertida || 0);
    const itSpillwayEl = document.getElementById('rep-it-spillway-badge');
    if (itSpillwayEl) {
      if (itVertVal > 0) {
        itSpillwayEl.className = 'text-[11px] font-bold px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/50 flex items-center gap-1';
        itSpillwayEl.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span> Vertedero Activo: ${fmt(itVertVal)} m³/s`;
      } else {
        itSpillwayEl.className = 'text-[11px] font-medium px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700';
        itSpillwayEl.textContent = 'Vertedero Cerrado (100% Turbinada)';
      }
    }

    const bxVertVal = Number(ig.baixo_iguazu_vertida || 0);
    const igSpillwayEl = document.getElementById('rep-ig-spillway-badge');
    if (igSpillwayEl) {
      if (bxVertVal > 0) {
        igSpillwayEl.className = 'text-[11px] font-bold px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/50 flex items-center gap-1';
        igSpillwayEl.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span> Vertedero Baixo: ${fmt(bxVertVal)} m³/s`;
      } else {
        igSpillwayEl.className = 'text-[11px] font-medium px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700';
        igSpillwayEl.textContent = 'Vertedero Cerrado';
      }
    }

    const formatDt = (val) => (window.Components && typeof Components.formatDateTime === 'function' ? Components.formatDateTime(val, true) : (val || '--'));

    // 3. Tarjeta Itaipú (ONS)
    const itDeflEl = document.getElementById('rep-it-defl');
    const itTurbEl = document.getElementById('rep-it-turb');
    const itVertEl = document.getElementById('rep-it-vert');
    const itAfluEl = document.getElementById('rep-it-aflu');
    const itCotaEl = document.getElementById('rep-it-cota');
    const itTimeEl = document.getElementById('rep-it-time');

    if (itDeflEl) itDeflEl.textContent = fmt(it.defluente);
    if (itTurbEl) itTurbEl.textContent = `${fmt(it.turbinada)} m³/s`;
    if (itVertEl) itVertEl.textContent = `${fmt(it.vertida)} m³/s`;
    if (itAfluEl) itAfluEl.textContent = `${fmt(it.afluente)} m³/s`;
    if (itCotaEl) itCotaEl.textContent = `${fmt(it.cota)} msnm`;
    if (itTimeEl) itTimeEl.textContent = formatDt(it.fecha);

    // 4. Tarjeta Baixo Iguaçu (ONS) - Datos directos de la central sin mezclar
    const bxDeflEl = document.getElementById('rep-bx-defl');
    const bxTurbEl = document.getElementById('rep-bx-turb');
    const bxVertEl = document.getElementById('rep-bx-vert');
    const bxAfluEl = document.getElementById('rep-bx-aflu');
    const bxCotaEl = document.getElementById('rep-bx-cota');
    const bxTimeEl = document.getElementById('rep-bx-time');

    if (bxDeflEl) bxDeflEl.textContent = fmt(ig.baixo_iguazu_defluente);
    if (bxTurbEl) bxTurbEl.textContent = `${fmt(ig.baixo_iguazu_turbinada)} m³/s`;
    if (bxVertEl) bxVertEl.textContent = `${fmt(ig.baixo_iguazu_vertida)} m³/s`;
    if (bxAfluEl) bxAfluEl.textContent = `${fmt(ig.baixo_iguazu_afluente)} m³/s`;
    if (bxCotaEl) bxCotaEl.textContent = `${fmt(ig.baixo_iguazu_cota)} msnm`;
    if (bxTimeEl) bxTimeEl.textContent = formatDt(ig.fecha);

    // 5. Tarjeta Porto Capanema (COPEL / ANA) - Solo fuente propia de Capanema
    const capCaudalEl = document.getElementById('rep-cap-caudal');
    const capReglaEl = document.getElementById('rep-cap-regla');
    const capTimeEl = document.getElementById('rep-cap-time');

    const cap = data.capanema || {};
    if (capCaudalEl) capCaudalEl.textContent = fmt(cap.caudal);
    if (capReglaEl) capReglaEl.textContent = cap.regla ? `${Number(cap.regla).toFixed(2)} m` : '-- m';
    if (capTimeEl) capTimeEl.textContent = formatDt(cap.fecha);

    // 6. Tarjeta Cataratas (COPEL / Parques) - Solo fuente propia de Cataratas
    const catCaudalEl = document.getElementById('rep-cat-caudal');
    const catReglaEl = document.getElementById('rep-cat-regla');
    const catTimeEl = document.getElementById('rep-cat-time');

    const cat = data.centrales_lista ? data.centrales_lista.find(c => c.codigo === 'CATARATAS') : null;
    const catCaudal = (cat && cat.caudal) ? cat.caudal : (data.cataratas ? data.cataratas.caudal : null);
    const catRegla = (cat && cat.regla) ? cat.regla : (data.cataratas ? data.cataratas.regla : null);
    const catFecha = (cat && cat.fecha) ? cat.fecha : (data.cataratas ? data.cataratas.fecha : null);

    if (catCaudalEl) catCaudalEl.textContent = fmt(catCaudal);
    if (catReglaEl) catReglaEl.textContent = catRegla ? `${Number(catRegla).toFixed(2)} m` : '-- m';
    if (catTimeEl) catTimeEl.textContent = formatDt(catFecha);

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
    const fmt = (v) => (v !== undefined && v !== null && v > 0 ? Number(v).toLocaleString('es-AR') : '--');

    // Mapeo por clave tolerante a acentos
    const norm = (str) => (str || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    const getFlow = (claveSubstr) => {
      const target = norm(claveSubstr);
      const match = centrales.find(c => norm(c.nombre).includes(target) || norm(c.clave || '').includes(target) || norm(c.codigo || '').includes(target));
      return match ? fmt(match.defluente || match.caudal) : '--';
    };

    const jupiaFlow = getFlow('jupi') || (data.jupia ? fmt(data.jupia.defluente) : '--');
    const primaveraFlow = getFlow('primavera') || (data.porto_primavera ? fmt(data.porto_primavera.defluente) : '--');
    const areiaFlow = getFlow('areia');
    const segredoFlow = getFlow('segredo');
    const santiagoFlow = getFlow('santiago');
    const osorioFlow = getFlow('osorio');
    const caxiasFlow = getFlow('caxias');
    const baixoFlow = fmt(ig.baixo_iguazu_defluente);
    const capanemaFlow = getFlow('capanema') || (data.capanema ? fmt(data.capanema.caudal) : '--');
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
            <div class="font-data font-bold text-slate-700 dark:text-slate-200 text-[11px]">${jupiaFlow} <span class="text-[9px] font-normal opacity-70">m³/s</span></div>
          </div>
          <span class="text-slate-300 dark:text-slate-600 text-[10px]">➔</span>

          <!-- Porto Primavera -->
          <div class="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 px-2 py-1 rounded-md shrink-0 text-center">
            <div class="text-[10px] text-slate-400 font-medium">P. Primavera</div>
            <div class="font-data font-bold text-slate-700 dark:text-slate-200 text-[11px]">${primaveraFlow} <span class="text-[9px] font-normal opacity-70">m³/s</span></div>
          </div>
          <span class="text-slate-300 dark:text-slate-600 text-[10px]">➔</span>

          <!-- Itaipú (Binacional) -->
          <div class="flex items-center gap-1.5 bg-sky-50 dark:bg-sky-950/40 border border-sky-300 dark:border-sky-800/80 px-2.5 py-1 rounded-lg shrink-0">
            <div class="text-[10px] font-bold text-sky-700 dark:text-sky-300">Itaipú</div>
            <span class="font-data font-extrabold text-sky-600 dark:text-sky-400 ml-1">${itaipuFlow}</span>
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
            <div class="font-data font-bold text-slate-700 dark:text-slate-200 text-[11px]">${areiaFlow}</div>
          </div>
          <span class="text-slate-300 dark:text-slate-600 text-[10px]">➔</span>

          <!-- Segredo -->
          <div class="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 px-2 py-1 rounded-md shrink-0 text-center">
            <div class="text-[10px] text-slate-400">Segredo</div>
            <div class="font-data font-bold text-slate-700 dark:text-slate-200 text-[11px]">${segredoFlow}</div>
          </div>
          <span class="text-slate-300 dark:text-slate-600 text-[10px]">➔</span>

          <!-- Santiago -->
          <div class="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 px-2 py-1 rounded-md shrink-0 text-center">
            <div class="text-[10px] text-slate-400">Santiago</div>
            <div class="font-data font-bold text-slate-700 dark:text-slate-200 text-[11px]">${santiagoFlow}</div>
          </div>
          <span class="text-slate-300 dark:text-slate-600 text-[10px]">➔</span>

          <!-- Osório -->
          <div class="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 px-2 py-1 rounded-md shrink-0 text-center">
            <div class="text-[10px] text-slate-400">Osório</div>
            <div class="font-data font-bold text-slate-700 dark:text-slate-200 text-[11px]">${osorioFlow}</div>
          </div>
          <span class="text-slate-300 dark:text-slate-600 text-[10px]">➔</span>

          <!-- Caxias -->
          <div class="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 px-2 py-1 rounded-md shrink-0 text-center">
            <div class="text-[10px] text-slate-400">Caxias</div>
            <div class="font-data font-bold text-slate-700 dark:text-slate-200 text-[11px]">${caxiasFlow}</div>
          </div>
          <span class="text-slate-300 dark:text-slate-600 text-[10px]">➔</span>

          <!-- Baixo Iguaçu (Destacada) -->
          <div class="bg-emerald-50 dark:bg-emerald-950/50 border border-emerald-300 dark:border-emerald-800 px-2.5 py-1 rounded-md shrink-0 text-center">
            <div class="text-[10px] font-bold text-emerald-700 dark:text-emerald-400">Baixo Iguaçu</div>
            <div class="font-data font-extrabold text-emerald-600 dark:text-emerald-300 text-[11px]">${baixoFlow} <span class="text-[9px] font-normal opacity-70">m³/s</span></div>
          </div>
          <span class="text-slate-300 dark:text-slate-600 text-[10px]">➔</span>

          <!-- Porto Capanema -->
          <div class="bg-amber-50/70 dark:bg-amber-950/40 border border-amber-300/80 dark:border-amber-800/60 px-2 py-1 rounded-md shrink-0 text-center">
            <div class="text-[10px] font-semibold text-amber-800 dark:text-amber-300">Capanema</div>
            <div class="font-data font-bold text-amber-600 dark:text-amber-300 text-[11px]">${capanemaFlow} <span class="text-[9px] font-normal opacity-70">m³/s</span></div>
          </div>
          <span class="text-slate-300 dark:text-slate-600 text-[10px]">➔</span>

          <!-- Cataratas (Destacada) -->
          <div class="bg-amber-50 dark:bg-amber-950/50 border border-amber-300 dark:border-amber-800 px-2.5 py-1 rounded-md shrink-0 text-center">
            <div class="text-[10px] font-bold text-amber-700 dark:text-amber-400">Cataratas</div>
            <div class="font-data font-extrabold text-amber-600 dark:text-amber-300 text-[11px]">${cataratasFlow} <span class="text-[9px] font-normal opacity-70">m³/s</span></div>
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

    const fmt = (v) => (v !== undefined && v !== null && v > 0 ? Number(v).toLocaleString('es-AR', { maximumFractionDigits: 1 }) : (v === 0 ? '0' : '--'));

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

      const cotaStr = c.cota ? `${c.cota} m` : (c.nivel ? `${c.nivel} m` : (c.regla ? `${c.regla} m` : '--'));
      const volStr = c.vol_pct ? `${c.vol_pct}%` : '--';
      const afluStr = fmt(c.afluente);
      const turbStr = fmt(c.turbinada);
      const vertNum = Number(c.vertida || 0);
      const vertStr = fmt(vertNum);
      const deflStr = fmt(c.defluente || c.caudal);

      const vertBadge = vertNum > 0
        ? `<span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 dark:bg-amber-950 text-amber-700 dark:text-amber-400 border border-amber-300 dark:border-amber-800">${vertStr}</span>`
        : `<span class="text-slate-400">0</span>`;

      return `
        <tr class="border-b border-slate-100 dark:border-slate-800/60 hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition ${rowHighlight}">
          <td class="py-2.5 px-3">
            <div class="font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
              <span>${c.nombre}</span>
              ${damBadge}
            </div>
            <div class="text-[10px] text-slate-400">${c.operador} • ${c.rio}${c.fuente ? ` • <span class="text-sky-600 dark:text-sky-400 font-medium">${c.fuente}</span>` : ''}</div>
          </td>
          <td class="py-2.5 px-3 font-mono">${cotaStr}</td>
          <td class="py-2.5 px-3 font-mono text-slate-500">${volStr}</td>
          <td class="py-2.5 px-3 font-mono text-slate-700 dark:text-slate-300">${afluStr}</td>
          <td class="py-2.5 px-3 font-mono text-sky-600 dark:text-sky-400 font-semibold">${turbStr}</td>
          <td class="py-2.5 px-3 font-mono">${vertBadge}</td>
          <td class="py-2.5 px-3 font-mono text-emerald-600 dark:text-emerald-400 font-bold">${deflStr}</td>
          <td class="py-2.5 px-3 font-mono text-[11px] text-slate-400">${(window.Components && typeof Components.formatDateTime === 'function' ? Components.formatDateTime(c.fecha) : c.fecha) || '--'}</td>
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

      const tot = p.total_yacyreta !== undefined ? Number(p.total_yacyreta) : null;
      const itDef = p.itaipu_defluente !== undefined ? Number(p.itaipu_defluente) : null;
      const igDef = p.iguazu_defluente !== undefined ? Number(p.iguazu_defluente) : null;
      const itTurb = p.itaipu_turbinada !== undefined ? Number(p.itaipu_turbinada) : null;
      const itVert = p.itaipu_vertida !== undefined ? Number(p.itaipu_vertida) : null;

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
              label: 'Total Hacia Yacyretá',
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
              label: 'Aporte Itaipú (Río Paraná)',
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
              label: 'Aporte Cascada Río Iguazú',
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

      this.toggleFloatingResetBtn('floating-reset-zoom-caudales', false);
    }

    // 2. Gráfico Desglose Itaipú (Turbinado vs Vertido)
    const canvasItaipu = document.getElementById('chartItaipuTurbinado');
    if (canvasItaipu) {
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
              label: 'Caudal Vertido (Vertedero)',
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

      this.toggleFloatingResetBtn('floating-reset-zoom-itaipu', false);
    }
  },

  async syncRepresasData() {
    const icon = document.getElementById('sync-represas-icon');
    if (icon) icon.classList.add('animate-spin');

    Components.showToast('ONS S3', 'Descargando dataset hidrológico oficial de ONS (Itaipú + Cuenca Iguazú)...');
    try {
      const res = await API.syncRepresas();
      if (res && res.success) {
        const total = res.total_yacyreta ? Number(res.total_yacyreta).toLocaleString('es-AR') : '--';
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
  }
};

window.RepresasView = RepresasView;
window.syncRepresasData = () => RepresasView.syncRepresasData();
window.setDamTableFilter = (filter) => RepresasView.setTableFilter(filter);
window.resetCaudalesZoom = () => RepresasView.resetCaudalesZoom();
window.resetItaipuZoom = () => RepresasView.resetItaipuZoom();
