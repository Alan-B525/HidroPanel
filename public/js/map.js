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
  inaRiverGroup: null,
  inaRiverActive: localStorage.getItem('hidropanel_map_ina_rivers') !== 'false',

  // RainViewer radar
  radarData: null,
  radarLayerMap: null,
  radarFrames: [],
  radarCurrentFrameIndex: 0,
  radarAnimationTimer: null,
  radarOpacity: localStorage.getItem('hidropanel_radar_opacity') ? parseFloat(localStorage.getItem('hidropanel_radar_opacity')) : 0.70,
  radarActive: localStorage.getItem('hidropanel_radar_active') !== 'false',

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

    // Restaurar posición y zoom del mapa desde localStorage
    let savedCenter = [-26.5, -55.5];
    let savedZoom = 7;
    try {
      const posStr = localStorage.getItem('hidropanel_map_view');
      if (posStr) {
        const parsed = JSON.parse(posStr);
        if (parsed.lat && parsed.lng && parsed.zoom) {
          savedCenter = [parsed.lat, parsed.lng];
          savedZoom = parsed.zoom;
        }
      }
    } catch (_) {}

    this.map = L.map(containerId, {
      center: savedCenter,
      zoom: savedZoom,
      zoomControl: true,
      attributionControl: true
    });

    // Guardar posición al mover el mapa
    this.map.on('moveend', () => {
      try {
        const c = this.map.getCenter();
        const z = this.map.getZoom();
        localStorage.setItem('hidropanel_map_view', JSON.stringify({ lat: c.lat, lng: c.lng, zoom: z }));
      } catch (_) {}
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

    const esriSatellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
      maxZoom: 18
    });

    this.baseLayers = {
      'CARTO Dark Matter (Oscuro)': cartoDark,
      'Satélite HD (ESRI World Imagery)': esriSatellite,
      'CARTO Voyager (Claro)': cartoVoyager,
      'Relieve Topográfico (OpenTopoMap)': openTopo,
      'OpenStreetMap': openStreetMap
    };

    // Agregar capa predeterminada según el tema
    this.currentBaseLayer = isDark ? cartoDark : cartoVoyager;
    this.currentBaseLayer.addTo(this.map);

    // Grupos de capas superpuestas
    this.markersGroup = L.layerGroup().addTo(this.map);
    this.damsGroup = L.layerGroup().addTo(this.map);
    this.inaRiverGroup = L.layerGroup().addTo(this.map);

    // Control de capas
    const overlays = {
      'Estaciones Hidrométricas': this.markersGroup,
      'Centrales & Presas (Caudales)': this.damsGroup,
      'Tramos Fluviales INA (Corredor)': this.inaRiverGroup
    };

    this.layerControl = L.control.layers(this.baseLayers, overlays, {
      position: 'topright',
      collapsed: true
    }).addTo(this.map);

    // Renderizar presas inmediatamente
    this.renderDams();

    // Cargar tramos fluviales INA del corredor
    this.loadInaRivers();

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
        ? `<div style="font-size: 0.72rem; font-weight: 600; color: #b45309; margin-bottom: 4px;">Actualización demorada</div>`
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
              <span>Ver en Hidrómetros</span>
            </button>
          </div>
        </div>
      `;

      const tooltipContent = `<strong>${s.nombre}</strong>: ${valStr}${isFailed ? ' <span style="color:#d97706; font-weight:bold;">(Demorado)</span>' : ''}`;

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
        marker.off('click');
        marker.on('click', () => {
          window.goToStationCharts(s.id);
        });
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
      let markerIconSvg = '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/></svg>';

      if (isMeasurementStation) {
        markerBg = '#d97706';
        markerIconSvg = '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/></svg>';
      } else if (isYacyreta || isSpilling) {
        markerBg = isYacyreta ? '#059669' : '#ea580c';
        markerIconSvg = '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>';
      }

      const damIconHtml = `
        <div style="
          width: 26px; height: 26px;
          border-radius: 50%;
          background: ${markerBg};
          border: 2px solid #ffffff;
          box-shadow: 0 2px 6px rgba(0,0,0,0.35);
          display: flex; align-items: center; justify-content: center;
          color: #ffffff;
          cursor: pointer;
        " title="${d.nombre}">
          ${markerIconSvg}
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

            <div style="margin-top: 8px; display: flex; gap: 6px;">
              <button onclick="RepresasView.openDamHistoryModal('${d.codigo}')" style="background: #d97706; color: white; border: 0; padding: 6px 8px; border-radius: 6px; font-size: 0.72rem; font-weight: 700; cursor: pointer; flex: 1; display: flex; align-items: center; justify-content: center; box-shadow: 0 1px 2px rgba(0,0,0,0.1); transition: background 0.15s;" onmouseover="this.style.background='#b45309'" onmouseout="this.style.background='#d97706'">
                <span>Ver Caudales</span>
              </button>
              <button onclick="window.goToStationCharts('${d.codigo}')" style="background: #0284c7; color: white; border: 0; padding: 6px 8px; border-radius: 6px; font-size: 0.72rem; font-weight: 700; cursor: pointer; flex: 1; display: flex; align-items: center; justify-content: center; box-shadow: 0 1px 2px rgba(0,0,0,0.1); transition: background 0.15s;" onmouseover="this.style.background='#0369a1'" onmouseout="this.style.background='#0284c7'">
                <span>Ver Hidrómetro</span>
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
                <span>Ver en Hidrómetros</span>
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
            <div onclick="RepresasView.openDamHistoryModal('${d.codigo}')" style="cursor: pointer;" title="Abrir gráfico histórico de variables">
              <div style="font-weight: 800; font-size: 0.95rem; color: #0f172a; margin-bottom: 2px;">${d.nombre}</div>
            </div>
            <div style="font-size: 0.72rem; color: #64748b; margin-bottom: 8px;">${d.operador} • ${d.rio}${data.fuente ? ` • <span style="color: #0284c7; font-weight: 600;">${data.fuente}</span>` : ''}</div>

            <!-- Valores Afluente y Defluente -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 6px;">
              <div style="background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 6px; padding: 6px;">
                <div style="font-size: 0.62rem; text-transform: uppercase; font-weight: 700; color: #0369a1;">Afluente</div>
                <div style="font-family: var(--font-value); font-size: 1.05rem; font-weight: 800; color: #0284c7; margin-top: 2px; font-variant-numeric: tabular-nums;">${afluStr}</div>
              </div>
              <div style="background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 6px; padding: 6px;">
                <div style="font-size: 0.62rem; text-transform: uppercase; font-weight: 700; color: #047857;">Efluente</div>
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
              <button onclick="RepresasView.openDamHistoryModal('${d.codigo}')" style="background: #0284c7; color: white; border: 0; padding: 6px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: 700; cursor: pointer; width: 100%; display: flex; align-items: center; justify-content: center; gap: 5px; box-shadow: 0 1px 2px rgba(0,0,0,0.1); transition: background 0.15s;" onmouseover="this.style.background='#0369a1'" onmouseout="this.style.background='#0284c7'">
                <span>Ver Gráfico de Variables</span>
              </button>
            </div>
          </div>
        `;
        tooltipText = `<strong>${d.nombre}</strong><br/>Afluente: ${afluStr}<br/>Efluente: ${deflStr}`;
      }

      if (this._damMarkers.has(d.codigo)) {
        const marker = this._damMarkers.get(d.codigo);
        marker.setIcon(customIcon);
        marker.setPopupContent(popupHtml);
        marker.setTooltipContent(tooltipText);
        marker.off('click');
        marker.on('click', () => {
          if (d.codigo === 'YACYRETA') {
            window.goToStationCharts('ITUZAINGO');
          } else if (window.RepresasView && typeof RepresasView.openDamHistoryModal === 'function') {
            RepresasView.openDamHistoryModal(d.codigo);
          }
        });
      } else {
        const marker = L.marker([d.lat, d.lon], { icon: customIcon });
        marker.bindPopup(popupHtml);
        marker.bindTooltip(tooltipText, { direction: 'top', offset: [0, -10] });
        marker.on('click', () => {
          if (d.codigo === 'YACYRETA') {
            window.goToStationCharts('ITUZAINGO');
          } else if (window.RepresasView && typeof RepresasView.openDamHistoryModal === 'function') {
            RepresasView.openDamHistoryModal(d.codigo);
          }
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
        if (this.radarActive && this.map) {
          this.showRadarFrame(this.radarCurrentFrameIndex, false);
        }
      }
    } catch (e) {
      console.warn('No se pudo inicializar RainViewer API:', e);
    }
  },

  getOrCreateRadarLayer(index) {
    if (!this.radarLayerMap) this.radarLayerMap = new Map();
    if (this.radarLayerMap.has(index)) {
      return this.radarLayerMap.get(index);
    }
    const frame = this.radarFrames[index];
    if (!frame) return null;
    const host = this.radarData.host || 'https://tilecache.rainviewer.com';
    const tileUrl = `${host}${frame.path}/256/{z}/{x}/{y}/2/1_1.png`;
    const layer = L.tileLayer(tileUrl, {
      opacity: 0,
      zIndex: 500,
      className: 'radar-smooth-tile-layer'
    });
    this.radarLayerMap.set(index, layer);
    return layer;
  },

  toggleRadar(active) {
    if (active === undefined) {
      active = !this.radarActive;
    }
    this.radarActive = active;
    localStorage.setItem('hidropanel_radar_active', String(active));

    const toggleBtn = document.getElementById('radar-toggle-btn');
    const legend = document.getElementById('radar-legend-panel');

    if (!active) {
      this.stopRadarAnimation();
      if (this.radarLayerMap) {
        this.radarLayerMap.forEach(layer => {
          if (this.map && this.map.hasLayer(layer)) {
            layer.setOpacity(0);
            this.map.removeLayer(layer);
          }
        });
      }
      if (legend) legend.classList.add('hidden');
      if (toggleBtn) {
        toggleBtn.textContent = 'Radar: Inactivo';
        toggleBtn.className = 'px-2.5 py-1 rounded border border-slate-300 dark:border-slate-700 text-slate-400 dark:text-slate-500 text-xs font-semibold hover:bg-slate-100 dark:hover:bg-slate-800 transition';
      }
    } else {
      if (legend) legend.classList.remove('hidden');
      if (toggleBtn) {
        toggleBtn.textContent = 'Radar: Activo';
        toggleBtn.className = 'px-2.5 py-1 rounded border border-sky-500/40 text-sky-600 dark:text-sky-400 text-xs font-semibold hover:bg-sky-50 dark:hover:bg-sky-950/40 transition';
      }
      this.showRadarFrame(this.radarCurrentFrameIndex, false);
    }
    this.updateRadarUI();
  },

  showRadarFrame(index, smooth = true) {
    if (!this.radarData || !this.radarFrames || this.radarFrames.length === 0 || !this.map) return;

    if (index < 0) index = 0;
    if (index >= this.radarFrames.length) index = this.radarFrames.length - 1;

    const prevIndex = this.radarCurrentFrameIndex;
    this.radarCurrentFrameIndex = index;

    if (!this.radarActive) {
      this.updateRadarUI();
      return;
    }

    const currentLayer = this.getOrCreateRadarLayer(index);
    if (!currentLayer) return;

    // Asegurarse de que la capa actual esté agregada al mapa
    if (!this.map.hasLayer(currentLayer)) {
      currentLayer.addTo(this.map);
    }

    // Gestionar desvanecimiento suave de la capa anterior
    const prevLayer = (prevIndex !== index && this.radarLayerMap && this.radarLayerMap.has(prevIndex))
      ? this.radarLayerMap.get(prevIndex)
      : null;

    if (prevLayer && this.map.hasLayer(prevLayer)) {
      if (smooth) {
        prevLayer.setOpacity(0);
        setTimeout(() => {
          if (this.map && this.map.hasLayer(prevLayer) && this.radarCurrentFrameIndex !== prevIndex) {
            this.map.removeLayer(prevLayer);
          }
        }, 400);
      } else {
        prevLayer.setOpacity(0);
        this.map.removeLayer(prevLayer);
      }
    }

    // Calcular el siguiente índice para precarga predictiva
    const nextIndex = (index + 1) >= this.radarFrames.length ? 0 : (index + 1);

    // Retirar del mapa cualquier otra capa residual que no sea la actual, previa o siguiente
    if (this.radarLayerMap) {
      this.radarLayerMap.forEach((layer, idx) => {
        if (idx !== index && idx !== prevIndex && idx !== nextIndex && this.map.hasLayer(layer)) {
          layer.setOpacity(0);
          this.map.removeLayer(layer);
        }
      });
    }

    // Transición suave de la capa actual a la opacidad deseada
    requestAnimationFrame(() => {
      currentLayer.setOpacity(this.radarOpacity);
    });

    // Precargar silenciosamente el siguiente cuadro (opacidad 0) para navegación instantánea
    const nextLayer = this.getOrCreateRadarLayer(nextIndex);
    if (nextLayer && !this.map.hasLayer(nextLayer)) {
      nextLayer.setOpacity(0);
      nextLayer.addTo(this.map);
    }

    this.updateRadarUI();
  },

  updateRadarUI() {
    const slider = document.getElementById('radar-slider');
    const label = document.getElementById('radar-timestamp-label');
    const badge = document.getElementById('radar-frame-badge');

    if (slider && this.radarFrames && this.radarFrames.length > 0) {
      slider.max = Math.max(0, this.radarFrames.length - 1);
      slider.value = this.radarCurrentFrameIndex;
    }

    if (label && this.radarFrames && this.radarFrames[this.radarCurrentFrameIndex]) {
      const frame = this.radarFrames[this.radarCurrentFrameIndex];
      const ts = new Date(frame.time * 1000);
      label.textContent = ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' hs';

      if (badge) {
        const isLatest = this.radarCurrentFrameIndex === (this.radarFrames.length - 1);
        if (isLatest) {
          badge.textContent = 'En vivo';
          badge.className = 'text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-400 border border-emerald-300 dark:border-emerald-800';
        } else {
          const latestTime = this.radarFrames[this.radarFrames.length - 1].time;
          const diffMinutes = Math.round((latestTime - frame.time) / 60);
          badge.textContent = `-${diffMinutes} min`;
          badge.className = 'text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400 border border-slate-200 dark:border-slate-700';
        }
      }
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
    this.stopRadarAnimation();
    const btn = document.getElementById('radar-play-btn');
    if (btn) btn.textContent = 'Pausar';

    const tick = () => {
      if (!this.radarActive || !this.radarFrames || this.radarFrames.length === 0) {
        this.stopRadarAnimation();
        return;
      }

      let nextIndex = this.radarCurrentFrameIndex + 1;
      let delay = 1000; // 1 segundo por cuadro para cadencia meteorológica fluida

      if (nextIndex >= this.radarFrames.length) {
        nextIndex = 0;
        // Al llegar al cuadro más reciente (en vivo), pausar 2.2 segundos antes de reiniciar el ciclo
        delay = 2200;
      }

      this.showRadarFrame(nextIndex, true);
      this.radarAnimationTimer = setTimeout(tick, delay);
    };

    // Si ya estamos en el último cuadro, reiniciar desde el principio para ver toda la evolución temporal
    if (this.radarCurrentFrameIndex >= this.radarFrames.length - 1) {
      this.showRadarFrame(0, true);
    }

    this.radarAnimationTimer = setTimeout(tick, 1000);
  },

  stopRadarAnimation() {
    if (this.radarAnimationTimer) {
      clearTimeout(this.radarAnimationTimer);
      this.radarAnimationTimer = null;
    }
    const btn = document.getElementById('radar-play-btn');
    if (btn) btn.textContent = 'Reproducir';
  },

  stepRadar(delta) {
    this.stopRadarAnimation();
    if (!this.radarFrames || this.radarFrames.length === 0) return;
    let newIndex = this.radarCurrentFrameIndex + delta;
    if (newIndex < 0) newIndex = this.radarFrames.length - 1;
    if (newIndex >= this.radarFrames.length) newIndex = 0;
    this.showRadarFrame(newIndex, false);
  },

  setRadarOpacity(val) {
    this.radarOpacity = parseFloat(val);
    localStorage.setItem('hidropanel_radar_opacity', String(this.radarOpacity));
    if (this.radarActive && this.radarLayerMap && this.radarLayerMap.has(this.radarCurrentFrameIndex)) {
      const currentLayer = this.radarLayerMap.get(this.radarCurrentFrameIndex);
      if (this.map && this.map.hasLayer(currentLayer)) {
        currentLayer.setOpacity(this.radarOpacity);
      }
    }
    const label = document.getElementById('radar-opacity-label');
    if (label) label.textContent = `${Math.round(this.radarOpacity * 100)}%`;
  },

  // ==========================================================
  // TRAMOS FLUVIALES INA (CORREDOR IGUAZÚ - PARANÁ - CORRIENTES)
  // ==========================================================
  async loadInaRivers() {
    if (!this.map) return;
    if (!this.inaRiverGroup) {
      this.inaRiverGroup = L.layerGroup().addTo(this.map);
    }
    try {
      let res = await fetch('/api/ina/tramos?t=' + Date.now());
      if (!res.ok) {
        res = await fetch('ina_tramos.json?t=' + Date.now());
      }
      if (!res.ok) return;
      const data = await res.json();
      if (!data || !data.features || !data.features.length) return;

      this.inaRiverGroup.clearLayers();

      const geoLayer = L.geoJSON(data, {
        style: (feature) => {
          const color = feature.properties?.color || '#38bdf8';
          return {
            color: color,
            weight: 5.5,
            opacity: 0.85,
            lineCap: 'round',
            lineJoin: 'round'
          };
        },
        onEachFeature: (feature, layer) => {
          const p = feature.properties || {};
          const tooltipHtml = `
            <div style="font-family: var(--font-body); padding: 4px; min-width: 170px;">
              <div style="font-weight: 800; font-size: 0.85rem; color: #0f172a; margin-bottom: 2px;">${p.nombre || p.rio}</div>
              <div style="font-size: 0.72rem; color: #64748b; margin-bottom: 4px;">${p.rio}</div>
              <div style="display: flex; align-items: center; gap: 6px; margin-top: 4px; padding: 4px 6px; background: #f8fafc; border-radius: 4px; border: 1px solid #e2e8f0;">
                <span style="width: 10px; height: 10px; border-radius: 50%; background: ${p.color}; display: inline-block; shrink: 0;"></span>
                <span style="font-weight: 700; font-size: 0.75rem; color: ${p.color}; text-transform: uppercase;">${p.condicion_label || p.condicion}</span>
              </div>
              ${p.valor ? `<div style="font-size: 0.7rem; color: #475569; margin-top: 4px; font-variant-numeric: tabular-nums;">Valor: <strong>${p.valor}</strong> ${p.tendencia ? `(${p.tendencia})` : ''}</div>` : ''}
              <div style="font-size: 0.65rem; color: #94a3b8; border-top: 1px solid #f1f5f9; padding-top: 3px; margin-top: 4px;">
                Fuente: Instituto Nacional del Agua (INA)
              </div>
            </div>
          `;
          layer.bindTooltip(tooltipHtml, {
            sticky: true,
            className: 'ina-river-leaflet-tooltip'
          });

          layer.on('mouseover', function () {
            this.setStyle({ weight: 8, opacity: 1.0 });
          });
          layer.on('mouseout', function () {
            this.setStyle({ weight: 5.5, opacity: 0.85 });
          });
        }
      });

      this.inaRiverGroup.addLayer(geoLayer);
    } catch (e) {
      console.warn('Error cargando tramos fluviales INA:', e);
    }
  },

  toggleInaRivers(forceActive) {
    if (!this.map || !this.inaRiverGroup) return;
    const newState = (forceActive !== undefined) ? forceActive : !this.inaRiverActive;
    this.inaRiverActive = newState;
    localStorage.setItem('hidropanel_map_ina_rivers', String(newState));

    if (this.inaRiverActive) {
      if (!this.map.hasLayer(this.inaRiverGroup)) {
        this.map.addLayer(this.inaRiverGroup);
      }
    } else {
      if (this.map.hasLayer(this.inaRiverGroup)) {
        this.map.removeLayer(this.inaRiverGroup);
      }
    }

    const btn = document.getElementById('ina-rivers-toggle-btn');
    if (btn) {
      if (this.inaRiverActive) {
        btn.textContent = 'Ríos INA: Activo';
        btn.className = 'px-2.5 py-1 rounded border border-emerald-500/40 text-emerald-400 text-xs font-semibold hover:bg-emerald-950/40 transition';
      } else {
        btn.textContent = 'Ríos INA: Inactivo';
        btn.className = 'px-2.5 py-1 rounded border border-slate-700 text-slate-400 text-xs font-medium hover:bg-slate-800 transition';
      }
    }

    const legend = document.getElementById('ina-river-legend-panel');
    if (legend) {
      legend.style.display = this.inaRiverActive ? 'block' : 'none';
    }
  }
};

window.MapView = MapView;
