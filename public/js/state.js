/**
 * public/js/state.js
 * Gestión de Estado Centralizado y Reactivo de HidroPanel 2.0
 */

const State = {
  stations: [],
  filteredStations: [],
  selectedStationId: localStorage.getItem('hidropanel_selected_station') ? parseInt(localStorage.getItem('hidropanel_selected_station'), 10) : null,
  selectedStationData: null,
  
  // Vista actual persistida: 'caudales' | 'charts' | 'map' | 'simepar'
  viewMode: localStorage.getItem('hidropanel_view_mode') || 'caudales',
  
  // Filtro temporal persistido
  range: localStorage.getItem('hidropanel_range') || '24h',
  
  // Fuente activa del gráfico: 'agp' | 'pna' | 'ambas' (por defecto 'agp')
  chartSource: localStorage.getItem('hidropanel_chart_source') || 'agp',

  setChartSource(source) {
    if (!['agp', 'pna', 'ambas'].includes(source)) return;
    this.chartSource = source;
    localStorage.setItem('hidropanel_chart_source', source);
  },

  // Modo de subplots persistido
  layout: parseInt(localStorage.getItem('hidropanel_layout'), 10) || 1,
  subplotStationIds: [null, null, null, null, null, null, null, null],
  subplotCotaModes: ['nivel', 'nivel', 'nivel', 'nivel', 'nivel', 'nivel', 'nivel', 'nivel'],

  ensureDefaultSubplotStations() {
    const defaultCodes = [
      'PUERTO_IGUAZU', 'POSADAS', 'CORRIENTES', 'ROSARIO',
      'ITUZAINGO', 'SANTAFE', 'PNJUPI', 'PNPPRI'
    ];
    if (!this.subplotStationIds[0] && this.selectedStationId) {
      this.subplotStationIds[0] = this.selectedStationId;
    }
    const assigned = new Set(this.subplotStationIds.filter(Boolean));
    for (let i = 0; i < 8; i++) {
      if (!this.subplotStationIds[i]) {
        let found = this.stations.find(s => defaultCodes.includes(s.codigo) && !assigned.has(s.id));
        if (!found) {
          found = this.stations.find(s => !assigned.has(s.id));
        }
        if (found) {
          this.subplotStationIds[i] = found.id;
          assigned.add(found.id);
        } else if (this.stations[i]) {
          this.subplotStationIds[i] = this.stations[i].id;
        }
      }
    }
  },

  // Calibración de Posadas (Cota msnm)
  posadasMode: 'nivel',
  posadasOffset: 71.53,

  isPosadasStation(st) {
    if (!st) return false;
    const name = (st.nombre || '').toLowerCase();
    const code = (st.codigo || '').toLowerCase();
    return name.includes('posadas') || code.includes('posadas');
  },

  // Barra lateral colapsada
  sidebarCollapsed: localStorage.getItem('hidropanel_sidebar_collapsed') === 'true',

  // Tema
  theme: localStorage.getItem('hidropanel_theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),

  // Situación y alertas
  situation: null,
  syncStatus: null,

  // Suscriptores de cambio
  listeners: {},

  on(event, callback) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(callback);
  },

  emit(event, payload) {
    if (this.listeners[event]) {
      this.listeners[event].forEach(fn => fn(payload));
    }
  },

  setTheme(theme) {
    this.theme = theme;
    localStorage.setItem('hidropanel_theme', theme);
    document.documentElement.setAttribute('data-theme', theme);
    document.documentElement.classList.toggle('dark', theme === 'dark');
    this.emit('themeChange', theme);
  },

  toggleTheme() {
    this.setTheme(this.theme === 'dark' ? 'light' : 'dark');
  },

  setSidebarCollapsed(collapsed) {
    this.sidebarCollapsed = collapsed;
    localStorage.setItem('hidropanel_sidebar_collapsed', String(collapsed));
    this.emit('sidebarChange', collapsed);
  },

  toggleSidebar() {
    this.setSidebarCollapsed(!this.sidebarCollapsed);
  },

  setViewMode(mode) {
    this.viewMode = mode;
    localStorage.setItem('hidropanel_view_mode', mode);
    this.emit('viewModeChange', mode);
  },

  setRange(range) {
    this.range = range;
    localStorage.setItem('hidropanel_range', range);
    this.emit('rangeChange', range);
  },

  setLayout(num) {
    this.layout = num;
    localStorage.setItem('hidropanel_layout', String(num));
    this.emit('layoutChange', num);
  },

  setSelectedStation(stationId) {
    this.selectedStationId = stationId;
    if (stationId) {
      localStorage.setItem('hidropanel_selected_station', String(stationId));
    }
    this.emit('stationSelected', stationId);
  }
};
