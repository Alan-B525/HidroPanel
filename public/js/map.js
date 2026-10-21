/**
 * public/js/map.js
 * Mapa Interactivo con Leaflet, Capas CARTO con API Key, OpenTopoMap,
 * Marcadores de Estaciones, Red de Presas Hidroeléctricas y Radar RainViewer en Vivo.
 */

const CARTO_API_KEY = 'cb1_4cxk_1_8864ef59c9c9dc72a002e72f';

// Coordenadas geográficas oficiales de las principales presas y estaciones de la cuenca
const DAM_COORDINATES = [
  {
    codigo: 'PNJUPI',
    nombre: 'Jupiá',
    lat: -20.7758,
    lon: -51.6267,
    rio: 'Río Paraná (Alto Paraná)',
    operador: 'CTG Brasil',
    tipo: 'Central Hidroeléctrica'
  },
  {
    codigo: 'PNPPRI',
    nombre: 'Porto Primavera',
    lat: -22.4757,
    lon: -52.9587,
    rio: 'Río Paraná (Alto Paraná)',
    operador: 'Auren Energia',
    tipo: 'Central Hidroeléctrica'
  },
  {
    codigo: 'PNITAI',
    nombre: 'Itaipú Binacional',
    lat: -25.4081,
    lon: -54.5887,
    rio: 'Río Paraná',
    operador: 'Itaipú Binacional (Brasil/Paraguay)',
    tipo: 'Presa Binacional'
  },
  {
    codigo: 'IGGBMU',
    nombre: 'Foz do Areia',
    lat: -26.0067,
    lon: -51.6691,
    rio: 'Río Iguazú (Cabecera)',
    operador: 'COPEL',
    tipo: 'Gran Reservorio de Cabecera'
  },
  {
    codigo: 'IGSEGR',
    nombre: 'Segredo',
    lat: -25.7903,
    lon: -52.1125,
    rio: 'Río Iguazú',
    operador: 'COPEL',
    tipo: 'Central Hidroeléctrica'
  },
  {
    codigo: 'IGSSAN',
    nombre: 'Salto Santiago',
    lat: -25.6178,
    lon: -52.6133,
    rio: 'Río Iguazú',
    operador: 'ENGIE',
    tipo: 'Central Hidroeléctrica'
  },
  {
    codigo: 'IGSOSO',
    nombre: 'Salto Osório',
    lat: -25.5376,
    lon: -53.0090,
    rio: 'Río Iguazú',
    operador: 'ENGIE',
    tipo: 'Central Hidroeléctrica'
  },
  {
    codigo: 'IGSCAX',
    nombre: 'Salto Caxias',
    lat: -25.5431,
    lon: -53.4981,
    rio: 'Río Iguazú',
    operador: 'COPEL',
    tipo: 'Central Hidroeléctrica'
  },
  {
    codigo: 'IGUHBI',
    nombre: 'Baixo Iguaçu',
    lat: -25.5033,
    lon: -53.6717,
    rio: 'Río Iguazú',
    operador: 'COPEL / Neoenergia',
    tipo: 'Central Hidroeléctrica'
  },
  {
    codigo: 'JDJORD',
    nombre: 'Jordão',
    lat: -25.7533,
    lon: -52.0525,
    rio: 'Río Jordão (Cuenca Iguazú)',
    operador: 'COPEL',
    tipo: 'Central Hidroeléctrica'
  },
  {
    codigo: 'IGFND',
    nombre: 'Fundão',
    lat: -25.7034,
    lon: -52.0020,
    rio: 'Río Jordão (Cuenca Iguazú)',
    operador: 'COPEL / Elejor',
    tipo: 'Central Hidroeléctrica'
  },
  {
    codigo: 'IGSCL',
    nombre: 'Santa Clara',
    lat: -25.6456,
    lon: -51.9569,
    rio: 'Río Jordão (Cuenca Iguazú)',
    operador: 'COPEL / Elejor',
    tipo: 'Central Hidroeléctrica'
  },
  {
    codigo: 'CAPANEMA',
    nombre: 'Porto Capanema',
    lat: -25.5808,
    lon: -53.9219,
    rio: 'Río Iguazú',
    operador: 'COPEL / ANA',
    tipo: 'Punto de Medición Fluviométrica'
  },
  {
    codigo: 'CATARATAS',
    nombre: 'Cataratas',
    lat: -25.6831,
    lon: -54.4406,
    rio: 'Río Iguazú',
    operador: 'Parque Nacional Iguazú / COPEL',
    tipo: 'Punto de Medición Fluviométrica'
  },
  {
    codigo: 'YACYRETA',
    nombre: 'Central Hidroeléctrica Yacyretá',
    lat: -27.4828,
    lon: -56.7358,
    rio: 'Río Paraná',
    operador: 'Entidad Binacional Yacyretá (Argentina/Paraguay)',
    tipo: 'Presa de Destino Final'
  }
];

const MapView = {
  map: null,
  baseLayers: {},
  currentBaseLayer: null,
  layerControl: null,
  markersGroup: null,
  damsGroup: null,

  // RainViewer radar
  radarData: null,
  radarLayer: null,
  radarFrames: [],
  radarCurrentFrameIndex: 0,
  radarAnimationTimer: null,
  radarOpacity: 0.70,
  radarActive: false,

  init(containerId, isDark) {
    if (this.map) {
      setTimeout(() => this.map.invalidateSize(), 150);
      return;
    }

    const el = document.getElementById(containerId);
    if (!el) return;

    if (el._leaflet_id) {
      el._leaflet_id = null;
    }

    this.map = L.map(containerId, {
      center: [-26.5, -55.5],
      zoom: 7,
      zoomControl: true,
      attributionControl: true
    });

    // Definición de capas base utilizando la API Key provista por el usuario
    const cartoVoyager = L.tileLayer(
      `https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png?key=${CARTO_API_KEY}`,
      {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 19
      }
    );

    const cartoDark = L.tileLayer(
      `https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png?key=${CARTO_API_KEY}`,
      {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 19
      }
    );

    const openTopo = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
      attribution: 'Map data: &copy; <a href="https://openstreetmap.org">OSM</a>, SRTM | Style: &copy; <a href="https://opentopomap.org">OpenTopoMap</a>',
      maxZoom: 17
    });

    const openStreetMap = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19
    });

    this.baseLayers = {
      'CARTO Voyager (Claro)': cartoVoyager,
      'CARTO Dark Matter (Oscuro)': cartoDark,
      'Relieve Topográfico (OpenTopoMap)': openTopo,
      'OpenStreetMap': openStreetMap
    };

    // Agregar capa predeterminada según el tema
    this.currentBaseLayer = isDark ? cartoDark : cartoVoyager;
    this.currentBaseLayer.addTo(this.map);

    // Grupos de capas superpuestas
    this.markersGroup = L.layerGroup().addTo(this.map);
    this.damsGroup = L.layerGroup().addTo(this.map);

    // Control de capas
    const overlays = {
      'Estaciones Hidrométricas': this.markersGroup,
      'Centrales & Presas (Caudales)': this.damsGroup
    };

    this.layerControl = L.control.layers(this.baseLayers, overlays, {
      position: 'topright',
      collapsed: true
    }).addTo(this.map);

    // Renderizar presas inmediatamente
    this.renderDams();

    // Inicializar radar RainViewer en segundo plano
    this.initRainViewer();

    setTimeout(() => {
      if (this.map) this.map.invalidateSize();
    }, 200);
  },

  updateBaseTile(isDark) {
    if (!this.map || !this.baseLayers) return;
    const targetLayer = isDark ? this.baseLayers['CARTO Dark Matter (Oscuro)'] : this.baseLayers['CARTO Voyager (Claro)'];

    if (this.currentBaseLayer && this.map.hasLayer(this.currentBaseLayer)) {
      this.map.removeLayer(this.currentBaseLayer);
    }
    this.currentBaseLayer = targetLayer;
    this.currentBaseLayer.addTo(this.map);
  },

  renderStations(stations, selectedId, onSelectStation) {
    if (!this.markersGroup) return;

    this._stationMarkers = this._stationMarkers || new Map();
    const currentIds = new Set();

    const statusColors = {
      normal: '#10b981',
      alerta: '#ea580c',
      evacuacion: '#dc2626',
      desactivacion: '#64748b',
      desactivado: '#64748b',
      sin_datos: '#94a3b8'
    };

    stations.forEach(s => {
      if (!s.latitud || !s.longitud) return;
      currentIds.add(s.id);

      const st = s.estado_hidrologico || 'normal';
      const color = statusColors[st] || statusColors.normal;
      const isSelected = s.id === selectedId;
      const isFailed = s.falla_reporte === true;
      const radius = isSelected ? 8 : (isFailed ? 6.5 : 5.5);

      const valStr = (s.ultima_altura !== null && s.ultima_altura !== undefined) ? `${Number(s.ultima_altura).toFixed(2)} m` : '—';
      const timeStr = (window.Components && typeof Components.formatDateTime === 'function' ? Components.formatDateTime(s.ultimo_timestamp, true) : (s.ultimo_timestamp || '—'));

      const failNotice = isFailed
        ? `<div style="font-size: 0.72rem; font-weight: 600; color: #b45309; margin-bottom: 4px;">⚠️ Actualización demorada</div>`
        : '';

      const popupContent = `
        <div style="font-family: var(--font-body); padding: 4px; min-width: 190px;">
          <div onclick="window.goToStationCharts(${s.id})" style="cursor: pointer;" title="Ir a pestaña de Hidrómetros">
            <div style="font-weight: 800; font-size: 0.95rem; color: #0284c7; margin-bottom: 2px;">${s.nombre}</div>
            <div style="font-size: 0.72rem; color: #64748b; margin-bottom: 6px;">Código: ${s.codigo}</div>
          </div>
          ${failNotice}
          <div style="display: flex; align-items: baseline; gap: 4px; margin-bottom: 4px;">
            <span style="font-family: var(--font-value); font-size: 1.25rem; font-weight: 800; color: #0f172a; font-variant-numeric: tabular-nums;">${valStr}</span>
          </div>
          <div style="font-size: 0.68rem; color: #64748b; margin-bottom: 6px; font-variant-numeric: tabular-nums;">Lectura: ${timeStr}</div>
          <div style="display: inline-block; font-size: 0.65rem; font-weight: 700; text-transform: uppercase; padding: 2px 6px; border-radius: 9999px; background: ${color}20; color: ${color}; border: 1px solid ${color};">
            Estado: ${st}
          </div>
          <div style="margin-top: 8px;">
            <button onclick="window.goToStationCharts(${s.id})" style="background: #0284c7; color: white; border: 0; padding: 6px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: 700; cursor: pointer; width: 100%; display: flex; align-items: center; justify-content: center; gap: 5px; box-shadow: 0 1px 2px rgba(0,0,0,0.1); transition: background 0.15s;" onmouseover="this.style.background='#0369a1'" onmouseout="this.style.background='#0284c7'">
              <span>📈 Ver en Hidrómetros (1 Gráfico)</span>
            </button>
          </div>
        </div>
      `;

      const tooltipContent = `<strong>${s.nombre}</strong>: ${valStr}${isFailed ? ' <span style="color:#d97706; font-weight:bold;">⚠️</span>' : ''}`;

      if (this._stationMarkers.has(s.id)) {
        const marker = this._stationMarkers.get(s.id);
        marker.setLatLng([s.latitud, s.longitud]);
        marker.setStyle({
          radius: radius,
          fillColor: color,
          color: isSelected ? '#ffffff' : (isFailed ? '#f59e0b' : '#071c33'),
          weight: isSelected ? 2.5 : (isFailed ? 2.0 : 1.2),
          dashArray: isFailed && !isSelected ? '3, 3' : null,
          opacity: 1,
          fillOpacity: 0.95
        });
        marker.setPopupContent(popupContent);
        marker.setTooltipContent(tooltipContent);
      } else {
        const marker = L.circleMarker([s.latitud, s.longitud], {
          radius: radius,
          fillColor: color,
          color: isSelected ? '#ffffff' : (isFailed ? '#f59e0b' : '#071c33'),
          weight: isSelected ? 2.5 : (isFailed ? 2.0 : 1.2),
          dashArray: isFailed && !isSelected ? '3, 3' : null,
          opacity: 1,
          fillOpacity: 0.95
        });
        marker.bindPopup(popupContent);
        marker.bindTooltip(tooltipContent, { direction: 'top', offset: [0, -6] });
        marker.on('click', () => {
          if (onSelectStation) onSelectStation(s.id);
        });
        marker.on('dblclick', (e) => {
          L.DomEvent.stop(e);
          window.goToStationCharts(s.id);
        });
        this.markersGroup.addLayer(marker);
        this._stationMarkers.set(s.id, marker);
      }
    });

    for (const [id, marker] of this._stationMarkers.entries()) {
      if (!currentIds.has(id)) {
        this.markersGroup.removeLayer(marker);
        this._stationMarkers.delete(id);
      }
    }
  },

  renderDams(caudalesData = null) {
    if (!this.damsGroup) return;

    this._damMarkers = this._damMarkers || new Map();
    const currentCodes = new Set();

    const damsMap = {};
    if (caudalesData && caudalesData.centrales_lista) {
      caudalesData.centrales_lista.forEach(c => {
        damsMap[c.codigo] = c;
      });
    }

    DAM_COORDINATES.forEach(d => {
      currentCodes.add(d.codigo);
      const data = damsMap[d.codigo] || {};
      const isMeasurementStation = d.codigo === 'CATARATAS' || d.codigo === 'CAPANEMA' || (d.tipo && d.tipo.includes('Medición'));
      const isYacyreta = d.codigo === 'YACYRETA';

      // Caudales clave
      const aflu = isYacyreta
        ? (caudalesData?.balance_yacyreta?.caudal_total_m3s || null)
        : (data.afluente !== undefined && data.afluente !== null && data.afluente > 0 ? data.afluente : null);

      const defl = data.defluente !== undefined && data.defluente !== null && data.defluente > 0 ? data.defluente : null;
      const caudalMedido = data.caudal !== undefined && data.caudal !== null && data.caudal > 0 ? data.caudal : null;

      const afluStr = aflu !== null ? `${Number(aflu).toLocaleString('es-AR')} m³/s` : '—';
      const deflStr = defl !== null ? `${Number(defl).toLocaleString('es-AR')} m³/s` : (caudalMedido !== null ? `${Number(caudalMedido).toLocaleString('es-AR')} m³/s` : '—');
      const caudalStr = caudalMedido !== null ? `${Number(caudalMedido).toLocaleString('es-AR')} m³/s` : deflStr;

      const reglaVal = (data.regla !== undefined && data.regla !== null) ? `${Number(data.regla).toFixed(2)} m` : null;
      const cotaVal = (data.cota !== undefined && data.cota !== null && data.cota > 0) ? `${Number(data.cota).toFixed(2)}` : null;
      const volPctVal = (data.vol_pct !== undefined && data.vol_pct !== null && data.vol_pct > 0) ? `${Number(data.vol_pct).toFixed(1)}` : null;

      const vert = Number(data.vertida || 0);
      const isSpilling = vert > 0;
      const turb = Number(data.turbinada || 0);

      // Icono distintivo para presas hidroeléctricas y estaciones de medición
      let markerBg = '#0284c7';
      let markerIcon = '💧';

      if (isMeasurementStation) {
        markerBg = '#d97706';
        markerIcon = '📏';
      } else if (isYacyreta) {
        markerBg = '#059669';
        markerIcon = '⚡';
      } else if (isSpilling) {
        markerBg = '#ea580c';
        markerIcon = '⚡';
      }

      const damIconHtml = `
        <div style="
          width: 26px; height: 26px;
          border-radius: 50%;
          background: ${markerBg};
          border: 2px solid #ffffff;
          box-shadow: 0 2px 6px rgba(0,0,0,0.35);
          display: flex; align-items: center; justify-content: center;
          color: #ffffff; font-size: 11px; font-weight: bold;
          cursor: pointer;
        " title="${d.nombre}">
          ${markerIcon}
        </div>
      `;

      const customIcon = L.divIcon({
        className: 'custom-dam-marker',
        html: damIconHtml,
        iconSize: [26, 26],
        iconAnchor: [13, 13]
      });

      let popupHtml = '';
      let tooltipText = '';

      if (isMeasurementStation) {
        // Pop-up para puntos de medición fluviométrica (Porto Capanema, Cataratas)
        popupHtml = `
          <div style="font-family: var(--font-body); padding: 4px; min-width: 200px;">
            <div style="font-size: 0.65rem; font-weight: 700; text-transform: uppercase; color: #d97706; letter-spacing: 0.05em; margin-bottom: 2px;">${d.tipo}</div>
            <div onclick="window.goToStationCharts('${d.codigo}')" style="cursor: pointer;" title="Ir a pestaña de Hidrómetros">
              <div style="font-weight: 800; font-size: 0.95rem; color: #0f172a; margin-bottom: 2px;">${d.nombre}</div>
            </div>
            <div style="font-size: 0.72rem; color: #64748b; margin-bottom: 8px;">${d.operador} • ${d.rio}</div>

            <div style="background: #fffbeb; border: 1px solid #fde68a; border-radius: 6px; padding: 8px; margin-bottom: 6px;">
              <div style="font-size: 0.65rem; text-transform: uppercase; font-weight: 700; color: #b45309;">Caudal Medido (Pasante):</div>
              <div style="font-family: var(--font-value); font-size: 1.25rem; font-weight: 800; color: #d97706; margin-top: 2px; font-variant-numeric: tabular-nums;">${caudalStr}</div>
              ${reglaVal ? `<div style="font-size: 0.72rem; color: #78350f; font-weight: 600; margin-top: 4px; font-variant-numeric: tabular-nums;">Nivel de regla: ${reglaVal}</div>` : ''}
            </div>

            ${data.fecha && data.fecha !== '—' && data.fecha !== '--' ? `
              <div style="font-size: 0.65rem; color: #94a3b8; border-top: 1px solid #f1f5f9; padding-top: 4px; margin-top: 4px; font-variant-numeric: tabular-nums;">
                Lectura de telemetría: ${data.fecha}
              </div>
            ` : ''}

            <div style="margin-top: 8px;">
              <button onclick="window.goToStationCharts('${d.codigo}')" style="background: #d97706; color: white; border: 0; padding: 6px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: 700; cursor: pointer; width: 100%; display: flex; align-items: center; justify-content: center; gap: 5px; box-shadow: 0 1px 2px rgba(0,0,0,0.1); transition: background 0.15s;" onmouseover="this.style.background='#b45309'" onmouseout="this.style.background='#d97706'">
                <span>📈 Ver en Hidrómetros (1 Gráfico)</span>
              </button>
            </div>
          </div>
        `;
        tooltipText = `<strong>${d.nombre}</strong><br/>Caudal: ${caudalStr}${reglaVal ? ` • Regla: ${reglaVal}` : ''}`;

      } else if (isYacyreta) {
        // Pop-up para Central Hidroeléctrica Yacyretá
        popupHtml = `
          <div style="font-family: var(--font-body); padding: 4px; min-width: 215px;">
            <div style="font-size: 0.65rem; font-weight: 700; text-transform: uppercase; color: #059669; letter-spacing: 0.05em; margin-bottom: 2px;">${d.tipo}</div>
            <div onclick="window.goToStationCharts('ITUZAINGO')" style="cursor: pointer;" title="Ir a pestaña de Hidrómetros">
              <div style="font-weight: 800; font-size: 0.95rem; color: #0f172a; margin-bottom: 2px;">${d.nombre}</div>
            </div>
            <div style="font-size: 0.72rem; color: #64748b; margin-bottom: 8px;">${d.operador} • ${d.rio}</div>

            <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; padding: 8px; margin-bottom: 6px;">
              <div style="font-size: 0.65rem; text-transform: uppercase; font-weight: 700; color: #166534;">Aporte Afluente en Tránsito (Itaipú + Iguazú):</div>
              <div style="font-family: var(--font-value); font-size: 1.25rem; font-weight: 800; color: #15803d; margin-top: 2px; font-variant-numeric: tabular-nums;">${afluStr}</div>
            </div>

            <div style="font-size: 0.68rem; color: #64748b;">
              Confluencia hidrológica directa hacia el embalse de Yacyretá.
            </div>

            <div style="margin-top: 8px;">
              <button onclick="window.goToStationCharts('ITUZAINGO')" style="background: #059669; color: white; border: 0; padding: 6px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: 700; cursor: pointer; width: 100%; display: flex; align-items: center; justify-content: center; gap: 5px; box-shadow: 0 1px 2px rgba(0,0,0,0.1); transition: background 0.15s;" onmouseover="this.style.background='#047857'" onmouseout="this.style.background='#059669'">
                <span>📈 Ver en Hidrómetros (1 Gráfico)</span>
              </button>
            </div>
          </div>
        `;
        tooltipText = `<strong>${d.nombre}</strong><br/>Aporte en tránsito: ${afluStr}`;

      } else {
        // Pop-up para Centrales Hidroeléctricas: Muestra Afluentes y Defluentes
        popupHtml = `
          <div style="font-family: var(--font-body); padding: 4px; min-width: 220px;">
            <div style="font-size: 0.65rem; font-weight: 700; text-transform: uppercase; color: #0284c7; letter-spacing: 0.05em; margin-bottom: 2px;">${d.tipo}</div>
            <div onclick="window.goToStationCharts('${d.codigo}')" style="cursor: pointer;" title="Ir a pestaña de Hidrómetros">
              <div style="font-weight: 800; font-size: 0.95rem; color: #0f172a; margin-bottom: 2px;">${d.nombre}</div>
            </div>
            <div style="font-size: 0.72rem; color: #64748b; margin-bottom: 8px;">${d.operador} • ${d.rio}${data.fuente ? ` • <span style="color: #0284c7; font-weight: 600;">${data.fuente}</span>` : ''}</div>

            <!-- Valores Afluente y Defluente -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 6px;">
              <div style="background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 6px; padding: 6px;">
                <div style="font-size: 0.62rem; text-transform: uppercase; font-weight: 700; color: #0369a1;">📥 Afluente</div>
                <div style="font-family: var(--font-value); font-size: 1.05rem; font-weight: 800; color: #0284c7; margin-top: 2px; font-variant-numeric: tabular-nums;">${afluStr}</div>
              </div>
              <div style="background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 6px; padding: 6px;">
                <div style="font-size: 0.62rem; text-transform: uppercase; font-weight: 700; color: #047857;">📤 Defluente</div>
                <div style="font-family: var(--font-value); font-size: 1.05rem; font-weight: 800; color: #059669; margin-top: 2px; font-variant-numeric: tabular-nums;">${deflStr}</div>
              </div>
            </div>

            ${(turb > 0 || isSpilling) ? `
              <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 5px 6px; font-size: 0.7rem; color: #475569; margin-bottom: 6px; display: flex; justify-content: space-between; font-variant-numeric: tabular-nums;">
                <span>Turbinado: <strong>${Number(turb).toLocaleString('es-AR')} m³/s</strong></span>
                ${isSpilling ? `<span style="color: #ea580c; font-weight: 700;">Vertedero: ${Number(vert).toLocaleString('es-AR')} m³/s</span>` : '<span style="color: #94a3b8;">Vertedero: 0</span>'}
              </div>
            ` : ''}

            ${cotaVal ? `
              <div style="font-size: 0.7rem; color: #64748b; margin-bottom: 4px; font-variant-numeric: tabular-nums;">
                Nivel Embalse: <strong style="color: #0f172a;">${cotaVal} msnm</strong> ${volPctVal ? `(${volPctVal}% útil)` : ''}
              </div>
            ` : ''}

            ${data.fecha && data.fecha !== '—' && data.fecha !== '--' ? `
              <div style="font-size: 0.65rem; color: #94a3b8; border-top: 1px solid #f1f5f9; padding-top: 4px; margin-top: 4px; font-variant-numeric: tabular-nums;">
                Último registro ONS: ${data.fecha}
              </div>
            ` : ''}

            <div style="margin-top: 8px;">
              <button onclick="window.goToStationCharts('${d.codigo}')" style="background: #0284c7; color: white; border: 0; padding: 6px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: 700; cursor: pointer; width: 100%; display: flex; align-items: center; justify-content: center; gap: 5px; box-shadow: 0 1px 2px rgba(0,0,0,0.1); transition: background 0.15s;" onmouseover="this.style.background='#0369a1'" onmouseout="this.style.background='#0284c7'">
                <span>📈 Ver en Hidrómetros (1 Gráfico)</span>
              </button>
            </div>
          </div>
        `;
        tooltipText = `<strong>${d.nombre}</strong><br/>📥 Afluente: ${afluStr}<br/>📤 Defluente: ${deflStr}`;
      }

      if (this._damMarkers.has(d.codigo)) {
        const marker = this._damMarkers.get(d.codigo);
        marker.setIcon(customIcon);
        marker.setPopupContent(popupHtml);
        marker.setTooltipContent(tooltipText);
      } else {
        const marker = L.marker([d.lat, d.lon], { icon: customIcon });
        marker.bindPopup(popupHtml);
        marker.bindTooltip(tooltipText, { direction: 'top', offset: [0, -10] });
        marker.on('dblclick', (e) => {
          L.DomEvent.stop(e);
          window.goToStationCharts(d.codigo);
        });
        this.damsGroup.addLayer(marker);
        this._damMarkers.set(d.codigo, marker);
      }
    });

    for (const [code, marker] of this._damMarkers.entries()) {
      if (!currentCodes.has(code)) {
        this.damsGroup.removeLayer(marker);
        this._damMarkers.delete(code);
      }
    }
  },

  flyToStation(station) {
    if (!this.map || !station || !station.latitud || !station.longitud) return;
    this.map.flyTo([station.latitud, station.longitud], 11, { duration: 1.0 });
  },

  zoomToRegion(region) {
    if (!this.map) return;
    const regions = {
      alto_parana: { center: [-21.8, -52.3], zoom: 7 },
      iguazu: { center: [-25.6, -54.4], zoom: 9 },
      paraguay: { center: [-25.5, -57.5], zoom: 8 },
      medio: { center: [-31.7, -60.5], zoom: 8 },
      delta: { center: [-34.4, -58.4], zoom: 9 },
      represas: { center: [-24.2, -53.8], zoom: 6 }
    };

    const target = regions[region];
    if (target) {
      this.map.flyTo(target.center, target.zoom, { duration: 1.0 });
    }
  },

  // ==========================================================
  // RAINVIEWER RADAR DE PRECIPITACIONES EN TIEMPO REAL
  // ==========================================================
  async initRainViewer() {
    try {
      const res = await fetch('https://api.rainviewer.com/public/weather-maps.json');
      if (!res.ok) return;
      this.radarData = await res.json();

      if (this.radarData && this.radarData.radar && this.radarData.radar.past) {
        this.radarFrames = this.radarData.radar.past;
        this.radarCurrentFrameIndex = this.radarFrames.length - 1;
        this.updateRadarUI();
      }
    } catch (e) {
      console.warn('No se pudo inicializar RainViewer API:', e);
    }
  },

  toggleRadar(active) {
    this.radarActive = active;
    const controls = document.getElementById('radar-controls-panel');
    const legend = document.getElementById('radar-legend-panel');

    if (controls) controls.classList.toggle('hidden', !active);
    if (legend) legend.classList.toggle('hidden', !active);

    if (active) {
      this.showRadarFrame(this.radarCurrentFrameIndex);
    } else {
      if (this.radarLayer && this.map) {
        this.map.removeLayer(this.radarLayer);
        this.radarLayer = null;
      }
      this.stopRadarAnimation();
    }
  },

  showRadarFrame(index) {
    if (!this.radarData || !this.radarFrames || this.radarFrames.length === 0 || !this.map) return;

    if (index < 0) index = 0;
    if (index >= this.radarFrames.length) index = this.radarFrames.length - 1;
    this.radarCurrentFrameIndex = index;

    const frame = this.radarFrames[index];
    const host = this.radarData.host || 'https://tilecache.rainviewer.com';
    const tileUrl = `${host}${frame.path}/256/{z}/{x}/{y}/2/1_1.png`;

    if (this.radarLayer) {
      this.map.removeLayer(this.radarLayer);
    }

    this.radarLayer = L.tileLayer(tileUrl, {
      opacity: this.radarOpacity,
      zIndex: 500
    }).addTo(this.map);

    this.updateRadarUI();
  },

  updateRadarUI() {
    const slider = document.getElementById('radar-slider');
    const label = document.getElementById('radar-timestamp-label');

    if (slider) {
      slider.max = Math.max(0, this.radarFrames.length - 1);
      slider.value = this.radarCurrentFrameIndex;
    }

    if (label && this.radarFrames[this.radarCurrentFrameIndex]) {
      const ts = new Date(this.radarFrames[this.radarCurrentFrameIndex].time * 1000);
      label.textContent = ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' hs';
    }
  },

  toggleRadarPlay() {
    if (this.radarAnimationTimer) {
      this.stopRadarAnimation();
    } else {
      this.playRadarAnimation();
    }
  },

  playRadarAnimation() {
    const btn = document.getElementById('radar-play-btn');
    if (btn) btn.innerHTML = '❚❚ Pausar';

    this.radarAnimationTimer = setInterval(() => {
      let nextIndex = this.radarCurrentFrameIndex + 1;
      if (nextIndex >= this.radarFrames.length) nextIndex = 0;
      this.showRadarFrame(nextIndex);
    }, 600);
  },

  stopRadarAnimation() {
    if (this.radarAnimationTimer) {
      clearInterval(this.radarAnimationTimer);
      this.radarAnimationTimer = null;
    }
    const btn = document.getElementById('radar-play-btn');
    if (btn) btn.innerHTML = '▶ Reproducir';
  },

  setRadarOpacity(val) {
    this.radarOpacity = parseFloat(val);
    if (this.radarLayer) {
      this.radarLayer.setOpacity(this.radarOpacity);
    }
    const label = document.getElementById('radar-opacity-label');
    if (label) label.textContent = `${Math.round(this.radarOpacity * 100)}%`;
  }
};

window.MapView = MapView;
