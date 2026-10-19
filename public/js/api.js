/**
 * public/js/api.js
 * Cliente HTTP modular para la API REST de HidroPanel 2.0
 */

const API = {
  baseUrl: (typeof window !== 'undefined' && window.location.origin && window.location.origin !== 'null' && !window.location.origin.startsWith('file'))
    ? window.location.origin
    : 'http://localhost:8050',

  async getStations() {
    const res = await fetch(`${this.baseUrl}/api/estaciones`);
    if (!res.ok) throw new Error(`HTTP ${res.status} al cargar estaciones`);
    return await res.json();
  },

  async getSituation() {
    const res = await fetch(`${this.baseUrl}/api/situacion`);
    if (!res.ok) throw new Error(`HTTP ${res.status} al cargar situación`);
    return await res.json();
  },

  async getMeasurements(stationId, range = '24h') {
    const res = await fetch(`${this.baseUrl}/api/mediciones?estacion_id=${stationId}&rango=${range}`);
    if (!res.ok) throw new Error(`HTTP ${res.status} al cargar mediciones`);
    return await res.json();
  },

  async getCaudales() {
    const res = await fetch(`${this.baseUrl}/api/caudales`);
    if (!res.ok) throw new Error(`HTTP ${res.status} al cargar caudales y represas`);
    return await res.json();
  },

  async getSyncStatus() {
    const res = await fetch(`${this.baseUrl}/api/status_sync`);
    if (!res.ok) throw new Error(`HTTP ${res.status} al verificar sincronización`);
    return await res.json();
  },

  async getSimeparMaps() {
    const res = await fetch(`${this.baseUrl}/api/mapa_simepar`);
    if (!res.ok) throw new Error(`HTTP ${res.status} al cargar mapas SIMEPAR`);
    return await res.json();
  },

  async syncStation(stationId) {
    const res = await fetch(`${this.baseUrl}/api/sync`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ estacion_id: stationId })
    });
    return await res.json();
  },

  async syncAllStations(frequency = null) {
    const payload = { all: true };
    if (frequency) payload.frequency = frequency;
    const res = await fetch(`${this.baseUrl}/api/sync`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    return await res.json();
  },

  async syncAll() {
    const res = await fetch(`${this.baseUrl}/api/sync`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ all: true })
    });
    return await res.json();
  },

  async syncSimepar() {
    const res = await fetch(`${this.baseUrl}/api/sync_mapa_simepar`, {
      method: 'POST'
    });
    return await res.json();
  },

  async syncRepresas() {
    const res = await fetch(`${this.baseUrl}/api/sync_represas`, {
      method: 'POST'
    });
    return await res.json();
  },

  async getThresholds(codigo = null) {
    const url = codigo
      ? `${this.baseUrl}/api/umbrales?codigo=${encodeURIComponent(codigo)}`
      : `${this.baseUrl}/api/umbrales`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status} al obtener umbrales`);
    return await res.json();
  },

  async saveThresholds(codigo, { alerta, evacuacion, alertas_activas = true }) {
    const res = await fetch(`${this.baseUrl}/api/umbrales`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ codigo, alerta, evacuacion, alertas_activas })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status} al guardar umbrales`);
    return await res.json();
  },

  async resetThresholds(codigo) {
    const res = await fetch(`${this.baseUrl}/api/umbrales`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ codigo, reset: true })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status} al restablecer umbrales`);
    return await res.json();
  },

  async syncPrefectura(history = false) {
    const res = await fetch(`${this.baseUrl}/api/sync_prefectura`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ history: Boolean(history) })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status} al sincronizar con Prefectura`);
    return await res.json();
  },

  getExportUrl(stationId, range = 'todo', isCota = false, offset = 0.0) {
    return `${this.baseUrl}/api/export?estacion_id=${stationId}&rango=${range}&cota=${isCota ? '1' : '0'}&offset=${offset}`;
  }
};
