/**
 * public/js/charts.js
 * Motor de Gráficos de Alta Precisión de HidroPanel 2.0
 * 
 * Estilo fiel a la Prefectura Naval Argentina (PNA):
 * - Título: 'Registros del puerto [NOMBRE]'
 * - Subtítulo: 'haga click y arrastre para hacer zoom en un area determinada'
 * - Eje X: Título 'Fecha' con escala temporal continua
 * - Eje Y: Título 'Registro' (o 'Cota (msnm)') con cuadrícula sutil
 * - Umbrales PNA: Líneas horizontales finas (1.2px) con etiquetas 'Evacuación (XX.XX)' y 'Alerta (XX.XX)'
 * - Curva de Área: Trazo fino de 2px con relleno degradé vertical a 0% opacidad
 * - Curva Prefectura: Trazo discontinuo oro/ámbar con anclajes circulares
 * - Soporte Multi-Plot (1, 2, 4 u 8 gráficos) homogéneo y sincronizado
 */

/**
 * Plugin de Chart.js para dibujar líneas de umbral estilo Prefectura Naval Argentina (PNA)
 * Evita datasets ficticios gruesos, logrando trazos limpios de 1.2px con etiquetas en margen izquierdo
 */
const pnaPlotLinesPlugin = {
  id: 'pnaPlotLines',
  afterDraw(chart) {
    const opts = chart.options.plugins?.pnaPlotLines;
    if (!opts || !opts.umbrales) return;

    const { ctx, chartArea, scales } = chart;
    if (!chartArea || !scales) return;
    const y = scales.y || scales.y1;
    if (!y) return;
    const { left, right, top, bottom } = chartArea;
    const umb = opts.umbrales;
    const isDark = Boolean(opts.isDark);

    const lines = [
      { key: 'evacuacion', val: umb.evacuacion, label: 'Evacuación', color: '#dc2626', dash: [] },
      { key: 'alerta', val: umb.alerta, label: 'Alerta', color: '#d97706', dash: [] }
    ];

    ctx.save();
    lines.forEach(l => {
      if (l.val === null || l.val === undefined || isNaN(l.val)) return;
      const yPix = y.getPixelForValue(l.val);

      // Dibujar únicamente si cae dentro de la ventana visible del gráfico
      if (yPix < top - 2 || yPix > bottom + 2) return;

      // 1. Línea horizontal fina (1.2px) estilo PNA
      ctx.beginPath();
      ctx.lineWidth = 1.2;
      ctx.strokeStyle = l.color;
      ctx.setLineDash(l.dash || []);
      ctx.moveTo(left, yPix);
      ctx.lineTo(right, yPix);
      ctx.stroke();

      // 2. Etiqueta PNA en el margen izquierdo: ej. "Evacuación · 31.00m"
      const text = `${l.label} · ${Number(l.val).toFixed(2)}m`;
      ctx.font = '600 10px Inter, system-ui, sans-serif';
      ctx.setLineDash([]);
      const textWidth = ctx.measureText(text).width;
      const badgeX = left + 8;
      const badgeY = yPix;

      // Fondo semitransparente para legibilidad
      const padX = 4;
      const padY = 7;
      ctx.fillStyle = isDark ? 'rgba(13, 26, 41, 0.90)' : 'rgba(255, 255, 255, 0.92)';
      ctx.fillRect(badgeX - padX, badgeY - padY, textWidth + padX * 2, padY * 2);
      ctx.strokeStyle = l.color;
      ctx.lineWidth = 0.8;
      ctx.strokeRect(badgeX - padX, badgeY - padY, textWidth + padX * 2, padY * 2);

      // Texto de la etiqueta
      ctx.fillStyle = l.color;
      ctx.textBaseline = 'middle';
      ctx.fillText(text, badgeX, badgeY);
    });
    ctx.restore();
  }
};

// Registrar plugin globalmente en Chart.js
if (typeof Chart !== 'undefined') {
  Chart.register(pnaPlotLinesPlugin);
}

const Charts = {
  mainChart: null,
  subplotCharts: [],

  /**
   * Comprueba si el adaptador de fecha de Chart.js está disponible
   */
  hasDateAdapter() {
    return Boolean(
      typeof Chart !== 'undefined' &&
      Chart._adapters &&
      Chart._adapters._date
    );
  },

  /**
   * Muestra u oculta botones flotantes de reinicio de zoom
   */
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

  /**
   * Genera o actualiza el gráfico principal detallado (Modo 1)
   * Réplica estética de Prefectura Naval Argentina:
   * - Zoom horizontal interactivo (Click & Drag)
   * - Área azul con degradé a 0% opacidad
   * - Trazo PNA con marcadores destacados
   * - Líneas de umbral finas (1.2px) con etiquetas
   * - Eje X: 'Fecha' | Eje Y: 'Registro'
   */
  renderMainChart(canvasId, puntos, kpis, isCota, offset, isDark, puntosPna) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    const useTimeScale = this.hasDateAdapter();
    const rawPna = (puntosPna && puntosPna.length > 0)
      ? puntosPna
      : (kpis && kpis.puntos_pna && kpis.puntos_pna.length > 0 ? kpis.puntos_pna : []);

    const unitSuffix = isCota ? 'msnm' : 'm';

    // 1. Procesar puntos AGP (Telemetría en tiempo real)
    const agpPoints = [];
    const agpMap = new Map();
    (puntos || []).forEach(p => {
      let val = p.y;
      if (isCota && val !== null && val !== undefined) {
        val = Number((val + offset).toFixed(2));
      }
      const rawT = p.t || '';
      const isoT = rawT.replace(' ', 'T');
      const timeMs = new Date(isoT).getTime();
      if (!isNaN(timeMs) && val !== null && val !== undefined) {
        agpPoints.push({ x: timeMs, y: val, rawTime: rawT });
        agpMap.set(rawT, val);
      }
    });

    // 2. Procesar puntos Prefectura Naval Argentina (PNA)
    const pnaPoints = [];
    const pnaMap = new Map();
    rawPna.forEach(p => {
      let val = p.y;
      if (isCota && val !== null && val !== undefined) {
        val = Number((val + offset).toFixed(2));
      }
      const rawT = p.t || '';
      const isoT = rawT.replace(' ', 'T');
      const timeMs = new Date(isoT).getTime();
      if (!isNaN(timeMs) && val !== null && val !== undefined) {
        pnaPoints.push({ x: timeMs, y: val, estado: p.estado || '', rawTime: rawT });
        pnaMap.set(rawT, val);
      }
    });

    agpPoints.sort((a, b) => a.x - b.x);
    pnaPoints.sort((a, b) => a.x - b.x);

    // Fallback de categorías cuando no hay adaptador de fecha
    const allUniqueTimes = Array.from(new Set([...agpMap.keys(), ...pnaMap.keys()])).sort();
    const fallbackLabels = allUniqueTimes.map(t => (t.length >= 16 ? t.slice(5, 16) : t));
    const fallbackAgpData = allUniqueTimes.map(t => agpMap.get(t) ?? null);
    const fallbackPnaData = allUniqueTimes.map(t => pnaMap.get(t) ?? null);

    // Colores fieles a PNA y tokens
    const agpColor = isDark ? '#38bdf8' : '#0284c7';
    const pnaColor = isDark ? '#fbbf24' : '#d97706';
    const gridColor = isDark ? 'rgba(255, 255, 255, 0.07)' : 'rgba(15, 23, 42, 0.06)';
    const textColor = isDark ? '#94a3b8' : '#475569';
    const titleColor = isDark ? '#f1f5f9' : '#0f294a';

    // Degradé vertical de área idéntico a Highcharts PNA
    const chartHeight = canvas.clientHeight || 380;
    const gradient = ctx.createLinearGradient(0, 0, 0, chartHeight);
    if (isDark) {
      gradient.addColorStop(0, 'rgba(56, 189, 248, 0.28)');
      gradient.addColorStop(0.65, 'rgba(56, 189, 248, 0.04)');
      gradient.addColorStop(1, 'rgba(56, 189, 248, 0.00)');
    } else {
      gradient.addColorStop(0, 'rgba(2, 132, 199, 0.24)');
      gradient.addColorStop(0.65, 'rgba(2, 132, 199, 0.04)');
      gradient.addColorStop(1, 'rgba(2, 132, 199, 0.00)');
    }

    // Umbrales oficiales de seguridad
    const umbrales = (kpis && kpis.umbrales) ? kpis.umbrales : {};
    let alertaVal = umbrales.alerta ?? null;
    let evacVal = umbrales.evacuacion ?? null;

    if (isCota) {
      if (alertaVal !== null) alertaVal = Number((alertaVal + offset).toFixed(2));
      if (evacVal !== null) evacVal = Number((evacVal + offset).toFixed(2));
    }

    const activeSource = State.chartSource || 'agp';
    const hasAgpData = agpPoints.length > 0 || fallbackAgpData.some(v => v !== null);
    const hasPnaData = pnaPoints.length > 0 || fallbackPnaData.some(v => v !== null);

    // Determinar qué curvas graficar según preferencia del usuario
    const showBoth = (activeSource === 'ambas') && hasAgpData && hasPnaData;
    const showOnlyPna = (activeSource === 'pna') || (!hasAgpData && hasPnaData && activeSource !== 'agp');
    const showOnlyAgp = !showBoth && !showOnlyPna;

    const datasets = [];

    if (showBoth) {
      // Ambas fuentes superpuestas con 2 escalas de eje Y independientes
      datasets.push({
        label: isCota ? 'Medición AGP · Cota msnm' : 'Medición AGP',
        data: useTimeScale ? agpPoints : fallbackAgpData,
        yAxisID: 'y',
        borderColor: agpColor,
        borderWidth: 2.0,
        backgroundColor: gradient,
        fill: 'start',
        pointRadius: agpPoints.length > 120 ? 0 : 2.5,
        pointHoverRadius: 6,
        pointBackgroundColor: agpColor,
        pointBorderColor: '#ffffff',
        pointBorderWidth: 1.5,
        tension: 0.20,
        spanGaps: true,
        order: 2
      });
      datasets.push({
        label: isCota ? 'Prefectura PNA · Cota' : 'Prefectura PNA',
        data: useTimeScale ? pnaPoints : fallbackPnaData,
        yAxisID: 'y1',
        borderColor: pnaColor,
        backgroundColor: 'transparent',
        borderWidth: 1.8,
        borderDash: [5, 4],
        pointRadius: pnaPoints.length > 150 ? 3.5 : 4.5,
        pointHoverRadius: 7,
        pointBackgroundColor: pnaColor,
        pointBorderColor: '#ffffff',
        pointBorderWidth: 2,
        pointHoverBorderColor: '#ffffff',
        pointHoverBorderWidth: 2.5,
        tension: 0.12,
        fill: false,
        spanGaps: true,
        order: 1
      });
    } else if (showOnlyPna) {
      // Únicamente Prefectura PNA (1 sola curva, 1 solo eje Y a la izquierda)
      const pnaGradient = ctx.createLinearGradient(0, 0, 0, chartHeight);
      if (isDark) {
        pnaGradient.addColorStop(0, 'rgba(251, 191, 36, 0.28)');
        pnaGradient.addColorStop(0.65, 'rgba(251, 191, 36, 0.04)');
        pnaGradient.addColorStop(1, 'rgba(251, 191, 36, 0.00)');
      } else {
        pnaGradient.addColorStop(0, 'rgba(217, 119, 6, 0.24)');
        pnaGradient.addColorStop(0.65, 'rgba(217, 119, 6, 0.04)');
        pnaGradient.addColorStop(1, 'rgba(217, 119, 6, 0.00)');
      }

      datasets.push({
        label: isCota ? 'Prefectura PNA · Cota msnm' : 'Prefectura PNA',
        data: useTimeScale ? pnaPoints : fallbackPnaData,
        yAxisID: 'y',
        borderColor: pnaColor,
        backgroundColor: pnaGradient,
        fill: 'start',
        borderWidth: 2.0,
        pointRadius: pnaPoints.length > 150 ? 3.5 : 4.5,
        pointHoverRadius: 7,
        pointBackgroundColor: pnaColor,
        pointBorderColor: '#ffffff',
        pointBorderWidth: 2,
        tension: 0.15,
        spanGaps: true,
        order: 1
      });
    } else {
      // Únicamente Medición AGP (1 sola curva, 1 solo eje Y a la izquierda)
      datasets.push({
        label: isCota ? 'Medición AGP · Cota msnm' : 'Medición AGP',
        data: useTimeScale ? agpPoints : fallbackAgpData,
        yAxisID: 'y',
        borderColor: agpColor,
        borderWidth: 2.0,
        backgroundColor: gradient,
        fill: 'start',
        pointRadius: agpPoints.length > 120 ? 0 : 2.5,
        pointHoverRadius: 6,
        pointBackgroundColor: agpColor,
        pointBorderColor: '#ffffff',
        pointBorderWidth: 1.5,
        tension: 0.20,
        spanGaps: true,
        order: 1
      });
    }

    // Determinar nombre del puerto para el encabezado oficial PNA
    const station = State.stations.find(s => s.id === State.selectedStationId);
    const portName = (station ? (station.nombre || station.codigo) : '').toUpperCase();

    // Configuración de escalas X e Y con títulos PNA
    const xScaleConfig = useTimeScale
      ? {
          type: 'time',
          title: {
            display: true,
            text: 'Fecha',
            color: textColor,
            font: { family: 'Inter', size: 11, weight: '600' },
            padding: { top: 6 }
          },
          time: {
            tooltipFormat: 'dd/MM/yyyy HH:mm',
            displayFormats: {
              hour: 'dd/MM HH:mm',
              day: 'dd/MM',
              week: 'dd/MM'
            }
          },
          grid: { color: gridColor, borderDash: [3, 3] },
          ticks: {
            color: textColor,
            font: { family: 'Space Grotesk', size: 10, weight: '600' },
            maxRotation: 0,
            autoSkip: true,
            maxTicksLimit: 9
          }
        }
      : {
          type: 'category',
          title: {
            display: true,
            text: 'Fecha',
            color: textColor,
            font: { family: 'Inter', size: 11, weight: '600' },
            padding: { top: 6 }
          },
          grid: { color: gridColor, borderDash: [3, 3] },
          ticks: {
            color: textColor,
            font: { family: 'Space Grotesk', size: 10, weight: '600' },
            maxRotation: 0,
            autoSkip: true,
            maxTicksLimit: 9
          }
        };

    // Ajuste de escala Y con amortiguación
    const computeLimits = (values) => {
      const valid = values.filter(v => v !== null && v !== undefined && !isNaN(v));
      if (valid.length === 0) return { min: undefined, max: undefined };
      const minY = Math.min(...valid);
      const maxY = Math.max(...valid);
      const span = maxY - minY;
      if (span === 0) {
        return { min: Number((minY - 0.50).toFixed(2)), max: Number((maxY + 0.50).toFixed(2)) };
      } else if (span < 0.35) {
        const pad = (0.50 - span) / 2;
        return { min: Number((minY - pad).toFixed(2)), max: Number((maxY + pad).toFixed(2)) };
      } else {
        const pad = span * 0.08;
        return { min: Number((minY - pad).toFixed(2)), max: Number((maxY + pad).toFixed(2)) };
      }
    };

    const agpLimits = computeLimits(agpPoints.map(p => p.y));
    const pnaLimits = computeLimits(pnaPoints.map(p => p.y));
    const allLimits = computeLimits([...agpPoints.map(p => p.y), ...pnaPoints.map(p => p.y)]);

    let yScalesConfig;
    if (showBoth) {
      yScalesConfig = {
        y: {
          type: 'linear',
          position: 'left',
          title: {
            display: true,
            text: isCota ? 'AGP Cota msnm' : 'Altura AGP m',
            color: agpColor,
            font: { family: 'Inter', size: 11, weight: '700' },
            padding: { bottom: 6 }
          },
          min: agpLimits.min,
          max: agpLimits.max,
          grid: { color: gridColor, borderDash: [3, 3] },
          ticks: {
            color: agpColor,
            font: { family: 'Space Grotesk', size: 10, weight: '600' },
            callback: function (val) {
              return Number(val).toFixed(2) + ' ' + unitSuffix;
            }
          }
        },
        y1: {
          type: 'linear',
          position: 'right',
          title: {
            display: true,
            text: isCota ? 'PNA Cota msnm' : 'Prefectura PNA m',
            color: pnaColor,
            font: { family: 'Inter', size: 11, weight: '700' },
            padding: { bottom: 6 }
          },
          min: pnaLimits.min,
          max: pnaLimits.max,
          grid: { drawOnChartArea: false },
          ticks: {
            color: pnaColor,
            font: { family: 'Space Grotesk', size: 10, weight: '600' },
            callback: function (val) {
              return Number(val).toFixed(2) + ' ' + unitSuffix;
            }
          }
        }
      };
    } else if (showOnlyPna) {
      yScalesConfig = {
        y: {
          type: 'linear',
          position: 'left',
          title: {
            display: true,
            text: isCota ? 'Prefectura PNA Cota msnm' : 'Prefectura PNA m',
            color: pnaColor,
            font: { family: 'Inter', size: 11, weight: '700' },
            padding: { bottom: 6 }
          },
          min: pnaLimits.min,
          max: pnaLimits.max,
          grid: { color: gridColor, borderDash: [3, 3] },
          ticks: {
            color: pnaColor,
            font: { family: 'Space Grotesk', size: 10, weight: '600' },
            callback: function (val) {
              return Number(val).toFixed(2) + ' ' + unitSuffix;
            }
          }
        }
      };
    } else {
      yScalesConfig = {
        y: {
          type: 'linear',
          position: 'left',
          title: {
            display: true,
            text: isCota ? 'Medición AGP Cota msnm' : 'Medición AGP m',
            color: agpColor,
            font: { family: 'Inter', size: 11, weight: '700' },
            padding: { bottom: 6 }
          },
          min: agpLimits.min,
          max: agpLimits.max,
          grid: { color: gridColor, borderDash: [3, 3] },
          ticks: {
            color: agpColor,
            font: { family: 'Space Grotesk', size: 10, weight: '600' },
            callback: function (val) {
              return Number(val).toFixed(2) + ' ' + unitSuffix;
            }
          }
        }
      };
    }

    const canReuse = Boolean(
      this.mainChart &&
      this._mainMeta &&
      this._mainMeta.stationId === State.selectedStationId &&
      this._mainMeta.isCota === isCota &&
      this._mainMeta.source === activeSource &&
      this._mainMeta.isDark === isDark &&
      this._mainMeta.useTimeScale === useTimeScale &&
      this.mainChart.data &&
      this.mainChart.data.datasets &&
      this.mainChart.data.datasets.length === datasets.length
    );

    if (canReuse) {
      if (!useTimeScale) {
        this.mainChart.data.labels = fallbackLabels;
      }
      datasets.forEach((ds, idx) => {
        if (this.mainChart.data.datasets[idx]) {
          this.mainChart.data.datasets[idx].data = ds.data;
          this.mainChart.data.datasets[idx].label = ds.label;
        }
      });
      if (this.mainChart.options.plugins?.pnaPlotLines) {
        this.mainChart.options.plugins.pnaPlotLines.umbrales = {
          alerta: alertaVal,
          evacuacion: evacVal
        };
        this.mainChart.options.plugins.pnaPlotLines.unitSuffix = unitSuffix;
      }
      if (yScalesConfig.y && this.mainChart.options.scales.y) {
        this.mainChart.options.scales.y.min = yScalesConfig.y.min;
        this.mainChart.options.scales.y.max = yScalesConfig.y.max;
      }
      if (yScalesConfig.y1 && this.mainChart.options.scales.y1) {
        this.mainChart.options.scales.y1.min = yScalesConfig.y1.min;
        this.mainChart.options.scales.y1.max = yScalesConfig.y1.max;
      }
      this.mainChart.update('none');
      return;
    }

    if (this.mainChart) {
      this.mainChart.destroy();
      this.mainChart = null;
    }

    // Reiniciar dimensiones del canvas
    canvas.removeAttribute('width');
    canvas.removeAttribute('height');
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    canvas.style.display = 'block';

    this.mainChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: useTimeScale ? undefined : fallbackLabels,
        datasets: datasets
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        resizeDelay: 50,
        animation: { duration: 300 },
        interaction: {
          mode: 'index',
          intersect: false
        },
        plugins: {
          title: {
            display: Boolean(portName),
            text: `Registros del puerto ${portName}`,
            font: { family: 'Inter', size: 13, weight: '700' },
            color: titleColor,
            padding: { top: 4, bottom: 2 }
          },
          subtitle: {
            display: false
          },
          legend: {
            display: true,
            position: 'top',
            align: 'end',
            labels: {
              boxWidth: 12,
              boxHeight: 7,
              usePointStyle: false,
              padding: 10,
              color: textColor,
              font: { family: 'Inter', size: 11, weight: '600' }
            }
          },
          // Plugin de líneas de umbral finas estilo PNA
          pnaPlotLines: {
            isDark: isDark,
            unitSuffix: unitSuffix,
            umbrales: {
              alerta: alertaVal,
              evacuacion: evacVal
            }
          },
          tooltip: {
            backgroundColor: isDark ? 'rgba(7, 22, 40, 0.96)' : 'rgba(255, 255, 255, 0.98)',
            titleColor: isDark ? '#f8fafc' : '#0f294a',
            bodyColor: isDark ? '#cbd5e1' : '#334155',
            borderColor: isDark ? 'rgba(56, 189, 248, 0.35)' : 'rgba(2, 132, 199, 0.25)',
            borderWidth: 1,
            padding: 10,
            cornerRadius: 8,
            titleFont: { family: 'Space Grotesk', size: 11, weight: '700' },
            bodyFont: { family: 'JetBrains Mono', size: 11, weight: '600' },
            boxPadding: 4,
            usePointStyle: true,
            callbacks: {
              title: function (items) {
                if (!items || items.length === 0) return '';
                const item = items[0];
                if (useTimeScale && item.parsed && item.parsed.x) {
                  const d = new Date(item.parsed.x);
                  if (!isNaN(d.getTime())) {
                    const dd = String(d.getDate()).padStart(2, '0');
                    const mm = String(d.getMonth() + 1).padStart(2, '0');
                    const yyyy = d.getFullYear();
                    const hh = String(d.getHours()).padStart(2, '0');
                    const min = String(d.getMinutes()).padStart(2, '0');
                    return `📅 ${dd}/${mm}/${yyyy} ${hh}:${min} hs`;
                  }
                }
                return `📅 ${item.label}`;
              },
              label: function (context) {
                const yVal = context.parsed && context.parsed.y !== undefined ? context.parsed.y : context.raw;
                const dsLabel = context.dataset.label || '';
                const isPna = dsLabel.toLowerCase().includes('prefectura') || dsLabel.toLowerCase().includes('pna');
                const icon = isPna ? '⚓' : '🔷';
                return ` ${icon} ${dsLabel}: ${Number(yVal).toFixed(2)} ${unitSuffix}`;
              }
            }
          },
          // Zoom estilo PNA: Selección por arrastre horizontal (Drag to Zoom)
          zoom: {
            pan: { enabled: false },
            zoom: {
              drag: {
                enabled: true,
                backgroundColor: isDark ? 'rgba(56, 189, 248, 0.20)' : 'rgba(2, 132, 199, 0.16)',
                borderColor: isDark ? '#38bdf8' : '#0284c7',
                borderWidth: 1.5
              },
              pinch: { enabled: true },
              mode: 'x',
              onZoomComplete: () => {
                Charts.toggleFloatingResetBtn('floating-reset-zoom-main', true);
              }
            }
          }
        },
        scales: {
          x: xScaleConfig,
          ...yScalesConfig
        }
      }
    });

    this._mainMeta = {
      stationId: State.selectedStationId,
      isCota,
      source: activeSource,
      isDark,
      useTimeScale
    };

    this.toggleFloatingResetBtn('floating-reset-zoom-main', false);
  },

  /**
   * Restablece el zoom del gráfico principal
   */
  resetZoom() {
    if (this.mainChart && typeof this.mainChart.resetZoom === 'function') {
      this.mainChart.resetZoom();
      this.toggleFloatingResetBtn('floating-reset-zoom-main', false);
    }
  },

  /**
   * Restablece el zoom de un subplot específico
   */
  resetSubplotZoom(index) {
    const chart = this.subplotCharts[index];
    if (chart && typeof chart.resetZoom === 'function') {
      chart.resetZoom();
      this.toggleFloatingResetBtn(`subplot-floating-reset-${index}`, false);
    }
  },

  /**
   * Cambia el modo de cota (nivel vs cota) de un subplot individual (sólo Posadas)
   */
  setSubplotCotaMode(slotIdx, mode) {
    if (!['nivel', 'cota'].includes(mode)) return;
    State.subplotCotaModes[slotIdx] = mode;

    const btnNivel = document.getElementById(`subplot-btn-nivel-${slotIdx}`);
    const btnCota = document.getElementById(`subplot-btn-cota-${slotIdx}`);
    if (btnNivel && btnCota) {
      if (mode === 'cota') {
        btnCota.className = 'px-1.5 py-0.5 rounded font-bold transition bg-sky-600 text-white shadow-xs';
        btnNivel.className = 'px-1.5 py-0.5 rounded font-medium transition text-slate-500 hover:text-slate-900 dark:hover:text-white';
      } else {
        btnNivel.className = 'px-1.5 py-0.5 rounded font-bold transition bg-sky-600 text-white shadow-xs';
        btnCota.className = 'px-1.5 py-0.5 rounded font-medium transition text-slate-500 hover:text-slate-900 dark:hover:text-white';
      }
    }

    const stationId = State.subplotStationIds[slotIdx];
    if (stationId) {
      this.loadSubplotData(slotIdx, stationId, false);
    }
  },

  /**
   * Renderiza la cuadrícula de subplots múltiples (2, 4 u 8)
   * Garantiza dimensiones exactas en px para cada canvas evitando colapsos
   */
  async renderSubplots(containerId, count, stationIds, allStations, range, isDark, onSelectStation) {
    const container = document.getElementById(containerId);
    if (!container) return;

    // Destruir instancias previas
    this.subplotCharts.forEach(c => c && c.destroy());
    this.subplotCharts = [];

    // Asegurar estaciones predeterminadas coherentes
    State.ensureDefaultSubplotStations();

    // Clases de cuadrícula responsivas
    if (count === 2) {
      container.className = 'grid grid-cols-1 lg:grid-cols-2 gap-4';
    } else if (count === 4) {
      container.className = 'grid grid-cols-1 md:grid-cols-2 gap-4';
    } else {
      container.className = 'grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3.5';
    }
    container.innerHTML = '';

    // Altura en píxeles exacta y garantizada
    const heightPx = (count <= 2) ? 310 : ((count <= 4) ? 255 : 205);

    // Deduplicar estaciones para los selectores
    const seen = new Set();
    const distinctStations = [];
    (allStations || []).forEach(s => {
      const name = (s.nombre || s.codigo || '').trim();
      const key = name.toLowerCase();
      if (!seen.has(key)) {
        seen.add(key);
        distinctStations.push(s);
      }
    });

    for (let i = 0; i < count; i++) {
      const selectedId = stationIds[i] || (distinctStations[i] ? distinctStations[i].id : (allStations[i] ? allStations[i].id : null));
      stationIds[i] = selectedId;

      const station = allStations.find(s => s.id === selectedId) || null;
      const isPosadas = State.isPosadasStation(station);
      const isSlotCota = isPosadas && (State.subplotCotaModes[i] === 'cota');

      const card = document.createElement('div');
      card.className = 'card-panel rounded-xl p-3 flex flex-col relative transition shadow-sm';
      card.id = `subplot-card-${i}`;

      card.innerHTML = `
        <!-- Encabezado de Subplot con Selector -->
        <div class="flex items-center justify-between gap-2 mb-1.5 pb-1.5 border-b border-slate-100 dark:border-slate-800">
          <div class="flex-1 min-w-0">
            <select onchange="window.onSubplotStationChange(${i}, this.value)" id="subplot-select-${i}" 
                    class="w-full bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-xs font-semibold text-slate-800 dark:text-slate-200 rounded-lg px-2 py-1 focus:outline-none focus:border-sky-500 truncate cursor-pointer hover:border-sky-400 transition font-sans">
              ${distinctStations.map(s => {
                const alt = (s.ultima_altura !== null && s.ultima_altura !== undefined) ? `${s.ultima_altura.toFixed(2)}m` : '--';
                const pna = (s.pna_altura !== null && s.pna_altura !== undefined) ? ` | ⚓ ${s.pna_altura.toFixed(2)}m` : '';
                return `<option value="${s.id}" ${s.id === selectedId ? 'selected' : ''}>${s.nombre || s.codigo} · ${alt}${pna}</option>`;
              }).join('')}
            </select>
          </div>
          
          <div class="flex items-center space-x-1.5 shrink-0">
            <!-- Selector individual de Cota para Posadas -->
            <div id="subplot-cota-toggle-${i}" class="${isPosadas ? 'flex' : 'hidden'} items-center bg-slate-100 dark:bg-slate-900 p-0.5 rounded-md border border-slate-200 dark:border-slate-800 text-[10px]" title="Modo Cota / Nivel para Posadas">
              <button id="subplot-btn-nivel-${i}" type="button" onclick="Charts.setSubplotCotaMode(${i}, 'nivel')" class="px-1.5 py-0.5 rounded font-bold transition ${isSlotCota ? 'text-slate-500 hover:text-slate-900 dark:hover:text-white' : 'bg-sky-600 text-white shadow-xs'}">Nivel</button>
              <button id="subplot-btn-cota-${i}" type="button" onclick="Charts.setSubplotCotaMode(${i}, 'cota')" class="px-1.5 py-0.5 rounded font-bold transition ${isSlotCota ? 'bg-sky-600 text-white shadow-xs' : 'text-slate-500 hover:text-slate-900 dark:hover:text-white'}">Cota</button>
            </div>

            <!-- Badge Dual AGP + PNA -->
            <span id="subplot-badge-${i}" class="font-data font-bold text-xs text-sky-600 dark:text-sky-400 bg-slate-100 dark:bg-slate-900 px-2 py-0.5 rounded border border-slate-200 dark:border-slate-800">-- m</span>
            
            <!-- Botón Restablecer Zoom -->
            <button onclick="Charts.resetSubplotZoom(${i})" title="Restablecer Zoom" class="text-slate-400 hover:text-slate-800 dark:hover:text-white p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800 transition">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
            </button>

            <!-- Botón Enfocar en Modo 1 -->
            <button onclick="window.focusStationInSingleMode(${selectedId})" id="subplot-focus-btn-${i}" title="Enfocar en pantalla completa · Modo 1" class="text-slate-400 hover:text-slate-800 dark:hover:text-white p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800 transition">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"/></svg>
            </button>
          </div>
        </div>

        <!-- Canvas del Gráfico con altura en píxeles garantizada -->
        <div class="relative w-full" style="height: ${heightPx}px; min-height: ${heightPx}px;">
          <canvas id="subplot-canvas-${i}" style="width: 100%; height: 100%; display: block;"></canvas>

          <!-- Botón flotante Reiniciar Zoom -->
          <button id="subplot-floating-reset-${i}" onclick="Charts.resetSubplotZoom(${i})" class="hidden absolute top-2 right-2 z-10 px-2 py-0.5 rounded text-[11px] font-semibold bg-white/95 dark:bg-slate-900/95 text-sky-600 dark:text-sky-400 border border-slate-200 dark:border-slate-700 shadow-xs hover:bg-sky-50 dark:hover:bg-slate-800 transition backdrop-blur-xs items-center gap-1">
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
            <span>Reset</span>
          </button>
          
          <!-- Loader individual -->
          <div id="subplot-loader-${i}" class="hidden absolute inset-0 bg-white/80 dark:bg-slate-950/70 backdrop-blur-xs flex items-center justify-center rounded-lg z-10">
            <div class="w-5 h-5 border-2 border-sky-500 border-t-transparent rounded-full animate-spin"></div>
          </div>
        </div>
      `;
      container.appendChild(card);

      if (selectedId) {
        this.loadSubplotData(i, selectedId, false);
      }
    }

    // Asegurar reflow y adaptación de Chart.js
    setTimeout(() => {
      this.subplotCharts.forEach(c => {
        if (c) {
          c.resize();
          c.update('none');
        }
      });
    }, 60);
  },

  /**
   * Carga datos para un Subplot individual con estética PNA idéntica al gráfico principal
   */
  async loadSubplotData(slotIdx, stationId, silent = false) {
    const canvas = document.getElementById(`subplot-canvas-${slotIdx}`);
    if (!canvas) return;

    const loader = document.getElementById(`subplot-loader-${slotIdx}`);
    if (loader && !silent) loader.classList.remove('hidden');

    try {
      const data = await API.getMeasurements(stationId, State.range);
      if (loader && !silent) loader.classList.add('hidden');
      if (!data || !data.success) return;

      const station = State.stations.find(s => s.id === stationId);
      const isPosadas = State.isPosadasStation(station);
      const applyCota = isPosadas && (State.subplotCotaModes[slotIdx] === 'cota');
      const offset = applyCota ? (Number(State.posadasOffset) || 71.53) : 0;
      const unitSuffix = applyCota ? 'msnm' : 'm';

      const portName = (station ? (station.nombre || station.codigo) : 'Estación').toUpperCase();

      // Actualizar visibilidad del toggle de cota
      const toggleContainer = document.getElementById(`subplot-cota-toggle-${slotIdx}`);
      if (toggleContainer) {
        if (isPosadas) {
          toggleContainer.classList.remove('hidden');
          toggleContainer.classList.add('flex');
        } else {
          toggleContainer.classList.add('hidden');
          toggleContainer.classList.remove('flex');
        }
      }

      // Actualizar botón de enfoque
      const focusBtn = document.getElementById(`subplot-focus-btn-${slotIdx}`);
      if (focusBtn) {
        focusBtn.setAttribute('onclick', `window.focusStationInSingleMode(${stationId})`);
      }

      // Actualizar badge individual (dual AGP + PNA con delta)
      const badge = document.getElementById(`subplot-badge-${slotIdx}`);
      if (badge && data.kpis) {
        let agpValStr = '—';
        let agpValNum = null;
        if (data.kpis.ultima_altura !== null && data.kpis.ultima_altura !== undefined) {
          agpValNum = applyCota ? (data.kpis.ultima_altura + offset) : data.kpis.ultima_altura;
          agpValStr = `${agpValNum.toFixed(2)} ${unitSuffix}`;
        }
        let pnaValStr = '';
        if (data.kpis.pna_altura !== null && data.kpis.pna_altura !== undefined) {
          const pv = applyCota ? (data.kpis.pna_altura + offset) : data.kpis.pna_altura;
          let diffStr = '';
          if (agpValNum !== null) {
            const diff = agpValNum - pv;
            const sign = diff > 0 ? '+' : '';
            diffStr = ` · Δ ${sign}${diff.toFixed(2)}`;
          }
          pnaValStr = `<span class="text-amber-600 dark:text-amber-400 font-bold ml-1.5 font-mono text-[10px]" title="Prefectura: ${pv.toFixed(2)} ${unitSuffix}${diffStr}">⚓ ${pv.toFixed(2)}${diffStr}</span>`;
        }
        badge.innerHTML = `<span class="text-sky-600 dark:text-sky-400 font-bold font-data tabular-nums">${agpValStr}</span>${pnaValStr}`;
      }

      const isDark = State.theme === 'dark';
      const ctx = canvas.getContext('2d');
      const useTimeScale = this.hasDateAdapter();

      // Procesar puntos AGP
      const agpPoints = [];
      const agpMap = new Map();
      (data.puntos || []).forEach(p => {
        let val = p.y;
        if (applyCota && val !== null && val !== undefined) {
          val = Number((val + offset).toFixed(2));
        }
        const rawT = p.t || '';
        const isoT = rawT.replace(' ', 'T');
        const timeMs = new Date(isoT).getTime();
        if (!isNaN(timeMs) && val !== null && val !== undefined) {
          agpPoints.push({ x: timeMs, y: val, rawTime: rawT });
          agpMap.set(rawT, val);
        }
      });

      // Procesar puntos PNA
      const pnaPoints = [];
      const pnaMap = new Map();
      (data.puntos_pna || []).forEach(p => {
        let val = p.y;
        if (applyCota && val !== null && val !== undefined) {
          val = Number((val + offset).toFixed(2));
        }
        const rawT = p.t || '';
        const isoT = rawT.replace(' ', 'T');
        const timeMs = new Date(isoT).getTime();
        if (!isNaN(timeMs) && val !== null && val !== undefined) {
          pnaPoints.push({ x: timeMs, y: val, estado: p.estado || '', rawTime: rawT });
          pnaMap.set(rawT, val);
        }
      });

      agpPoints.sort((a, b) => a.x - b.x);
      pnaPoints.sort((a, b) => a.x - b.x);

      const allUniqueTimes = Array.from(new Set([...agpMap.keys(), ...pnaMap.keys()])).sort();
      const fallbackLabels = allUniqueTimes.map(t => (t.length >= 16 ? t.slice(5, 16) : t));
      const fallbackAgpData = allUniqueTimes.map(t => agpMap.get(t) ?? null);
      const fallbackPnaData = allUniqueTimes.map(t => pnaMap.get(t) ?? null);

      // Limpiar y preparar canvas
      canvas.removeAttribute('width');
      canvas.removeAttribute('height');
      canvas.style.width = '100%';
      canvas.style.height = '100%';
      canvas.style.display = 'block';

      const chartHeight = canvas.clientHeight || 240;
      const gradient = ctx.createLinearGradient(0, 0, 0, chartHeight);
      if (isDark) {
        gradient.addColorStop(0, 'rgba(56, 189, 248, 0.26)');
        gradient.addColorStop(0.65, 'rgba(56, 189, 248, 0.04)');
        gradient.addColorStop(1, 'rgba(56, 189, 248, 0.00)');
      } else {
        gradient.addColorStop(0, 'rgba(2, 132, 199, 0.22)');
        gradient.addColorStop(0.65, 'rgba(2, 132, 199, 0.04)');
        gradient.addColorStop(1, 'rgba(2, 132, 199, 0.00)');
      }

      const agpColor = isDark ? '#38bdf8' : '#0284c7';
      const pnaColor = isDark ? '#fbbf24' : '#d97706';
      const gridColor = isDark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(15, 23, 42, 0.05)';
      const textColor = isDark ? '#94a3b8' : '#475569';
      const titleColor = isDark ? '#f1f5f9' : '#0f294a';

      // Umbrales para este subplot
      const umbrales = (data.kpis && data.kpis.umbrales) ? data.kpis.umbrales : (station ? station.umbrales : {});
      let alertaVal = umbrales?.alerta ?? null;
      let evacVal = umbrales?.evacuacion ?? null;

      if (applyCota) {
        if (alertaVal !== null) alertaVal = Number((alertaVal + offset).toFixed(2));
        if (evacVal !== null) evacVal = Number((evacVal + offset).toFixed(2));
      }

      // Amortiguación Y y soporte según State.chartSource
      const activeSource = State.chartSource || 'agp';
      const hasSubAgp = agpPoints.length > 0 || fallbackAgpData.some(v => v !== null);
      const hasSubPna = pnaPoints.length > 0 || fallbackPnaData.some(v => v !== null);
      const showSubBoth = (activeSource === 'ambas') && hasSubAgp && hasSubPna;
      const showSubPnaOnly = (activeSource === 'pna') || (!hasSubAgp && hasSubPna && activeSource !== 'agp');
      const showSubAgpOnly = !showSubBoth && !showSubPnaOnly;

      const computeSubLimits = (values) => {
        const valid = values.filter(v => v !== null && v !== undefined && !isNaN(v));
        if (valid.length === 0) return { min: undefined, max: undefined };
        const minY = Math.min(...valid);
        const maxY = Math.max(...valid);
        const span = maxY - minY;
        if (span === 0) {
          return { min: Number((minY - 0.40).toFixed(2)), max: Number((maxY + 0.40).toFixed(2)) };
        } else if (span < 0.25) {
          const pad = (0.40 - span) / 2;
          return { min: Number((minY - pad).toFixed(2)), max: Number((maxY + pad).toFixed(2)) };
        } else {
          const pad = span * 0.08;
          return { min: Number((minY - pad).toFixed(2)), max: Number((maxY + pad).toFixed(2)) };
        }
      };

      const subAgpLimits = computeSubLimits(agpPoints.map(p => p.y));
      const subPnaLimits = computeSubLimits(pnaPoints.map(p => p.y));
      const subAllLimits = computeSubLimits([...agpPoints.map(p => p.y), ...pnaPoints.map(p => p.y)]);

      const datasets = [];

      if (showSubBoth) {
        datasets.push({
          label: 'Medición AGP',
          data: useTimeScale ? agpPoints : fallbackAgpData,
          yAxisID: 'y',
          borderColor: agpColor,
          borderWidth: 1.8,
          backgroundColor: gradient,
          fill: 'start',
          pointRadius: agpPoints.length > 100 ? 0 : 2,
          pointHoverRadius: 5,
          pointBackgroundColor: agpColor,
          pointBorderColor: '#ffffff',
          pointBorderWidth: 1.5,
          tension: 0.18,
          spanGaps: true,
          order: 2
        });
        datasets.push({
          label: 'Prefectura PNA',
          data: useTimeScale ? pnaPoints : fallbackPnaData,
          yAxisID: 'y1',
          borderColor: pnaColor,
          backgroundColor: 'transparent',
          borderWidth: 1.6,
          borderDash: [5, 3],
          pointRadius: pnaPoints.length > 100 ? 2.5 : 4,
          pointHoverRadius: 6,
          pointBackgroundColor: pnaColor,
          pointBorderColor: '#ffffff',
          pointBorderWidth: 1.5,
          tension: 0.12,
          fill: false,
          spanGaps: true,
          order: 1
        });
      } else if (showSubPnaOnly) {
        const subPnaGrad = ctx.createLinearGradient(0, 0, 0, chartHeight);
        if (isDark) {
          subPnaGrad.addColorStop(0, 'rgba(251, 191, 36, 0.26)');
          subPnaGrad.addColorStop(0.65, 'rgba(251, 191, 36, 0.04)');
          subPnaGrad.addColorStop(1, 'rgba(251, 191, 36, 0.00)');
        } else {
          subPnaGrad.addColorStop(0, 'rgba(217, 119, 6, 0.22)');
          subPnaGrad.addColorStop(0.65, 'rgba(217, 119, 6, 0.04)');
          subPnaGrad.addColorStop(1, 'rgba(217, 119, 6, 0.00)');
        }
        datasets.push({
          label: 'Prefectura PNA',
          data: useTimeScale ? pnaPoints : fallbackPnaData,
          yAxisID: 'y',
          borderColor: pnaColor,
          backgroundColor: subPnaGrad,
          fill: 'start',
          borderWidth: 1.8,
          pointRadius: pnaPoints.length > 100 ? 2.5 : 4,
          pointHoverRadius: 6,
          pointBackgroundColor: pnaColor,
          pointBorderColor: '#ffffff',
          pointBorderWidth: 1.5,
          tension: 0.15,
          spanGaps: true,
          order: 1
        });
      } else {
        datasets.push({
          label: 'Medición AGP',
          data: useTimeScale ? agpPoints : fallbackAgpData,
          yAxisID: 'y',
          borderColor: agpColor,
          borderWidth: 1.8,
          backgroundColor: gradient,
          fill: 'start',
          pointRadius: agpPoints.length > 100 ? 0 : 2,
          pointHoverRadius: 5,
          pointBackgroundColor: agpColor,
          pointBorderColor: '#ffffff',
          pointBorderWidth: 1.5,
          tension: 0.18,
          spanGaps: true,
          order: 1
        });
      }

      const isMultiDense = State.layout > 4;

      let subYScales;
      if (showSubBoth) {
        subYScales = {
          y: {
            type: 'linear',
            position: 'left',
            title: {
              display: true,
              text: applyCota ? 'AGP Cota' : 'AGP m',
              color: agpColor,
              font: { family: 'Inter', size: 9, weight: '700' },
              padding: { bottom: 2 }
            },
            min: subAgpLimits.min,
            max: subAgpLimits.max,
            grid: { color: gridColor, borderDash: [2, 2] },
            ticks: {
              color: agpColor,
              font: { size: 9, family: 'Space Grotesk' },
              callback: (v) => Number(v).toFixed(1)
            }
          },
          y1: {
            type: 'linear',
            position: 'right',
            title: {
              display: true,
              text: applyCota ? 'PNA Cota' : 'PNA m',
              color: pnaColor,
              font: { family: 'Inter', size: 9, weight: '700' },
              padding: { bottom: 2 }
            },
            min: subPnaLimits.min,
            max: subPnaLimits.max,
            grid: { drawOnChartArea: false },
            ticks: {
              color: pnaColor,
              font: { size: 9, family: 'Space Grotesk' },
              callback: (v) => Number(v).toFixed(1)
            }
          }
        };
      } else if (showSubPnaOnly) {
        subYScales = {
          y: {
            type: 'linear',
            position: 'left',
            title: {
              display: true,
              text: applyCota ? 'PNA Cota' : 'PNA m',
              color: pnaColor,
              font: { family: 'Inter', size: 9, weight: '700' },
              padding: { bottom: 2 }
            },
            min: subPnaLimits.min,
            max: subPnaLimits.max,
            grid: { color: gridColor, borderDash: [2, 2] },
            ticks: {
              color: pnaColor,
              font: { size: 9, family: 'Space Grotesk' },
              callback: (v) => Number(v).toFixed(1)
            }
          }
        };
      } else {
        subYScales = {
          y: {
            type: 'linear',
            position: 'left',
            title: {
              display: true,
              text: applyCota ? 'AGP Cota' : 'AGP m',
              color: agpColor,
              font: { family: 'Inter', size: 9, weight: '700' },
              padding: { bottom: 2 }
            },
            min: subAgpLimits.min,
            max: subAgpLimits.max,
            grid: { color: gridColor, borderDash: [2, 2] },
            ticks: {
              color: agpColor,
              font: { size: 9, family: 'Space Grotesk' },
              callback: (v) => Number(v).toFixed(1)
            }
          }
        };
      }

      const prevChart = this.subplotCharts[slotIdx];
      const prevMeta = this._subplotMeta ? this._subplotMeta[slotIdx] : null;
      const canReuseSubplot = Boolean(
        prevChart &&
        prevMeta &&
        prevMeta.stationId === stationId &&
        prevMeta.applyCota === applyCota &&
        prevMeta.source === activeSource &&
        prevMeta.isDark === isDark &&
        prevMeta.useTimeScale === useTimeScale &&
        prevChart.data &&
        prevChart.data.datasets &&
        prevChart.data.datasets.length === datasets.length
      );

      if (canReuseSubplot) {
        if (!useTimeScale) prevChart.data.labels = fallbackLabels;
        datasets.forEach((ds, idx) => {
          if (prevChart.data.datasets[idx]) {
            prevChart.data.datasets[idx].data = ds.data;
            prevChart.data.datasets[idx].label = ds.label;
          }
        });
        if (prevChart.options.plugins?.pnaPlotLines) {
          prevChart.options.plugins.pnaPlotLines.umbrales = {
            alerta: alertaVal,
            evacuacion: evacVal
          };
          prevChart.options.plugins.pnaPlotLines.unitSuffix = unitSuffix;
        }
        if (subYScales.y && prevChart.options.scales.y) {
          prevChart.options.scales.y.min = subYScales.y.min;
          prevChart.options.scales.y.max = subYScales.y.max;
        }
        if (subYScales.y1 && prevChart.options.scales.y1) {
          prevChart.options.scales.y1.min = subYScales.y1.min;
          prevChart.options.scales.y1.max = subYScales.y1.max;
        }
        prevChart.update('none');
        return;
      }

      if (this.subplotCharts[slotIdx]) {
        this.subplotCharts[slotIdx].destroy();
        this.subplotCharts[slotIdx] = null;
      }

      canvas.removeAttribute('width');
      canvas.removeAttribute('height');
      canvas.style.width = '100%';
      canvas.style.height = '100%';
      canvas.style.display = 'block';

      const chart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: useTimeScale ? undefined : fallbackLabels,
          datasets: datasets
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            title: {
              display: true,
              text: `Registros del puerto ${portName}`,
              font: { family: 'Inter', size: isMultiDense ? 10 : 11, weight: '700' },
              color: titleColor,
              padding: { top: 2, bottom: 1 }
            },
            subtitle: {
              display: false
            },
            legend: {
              display: true,
              position: 'top',
              align: 'end',
              labels: {
                boxWidth: 9,
                boxHeight: 5,
                font: { size: 9, family: 'Inter', weight: '600' },
                color: textColor
              }
            },
            // Plugin de líneas de umbral finas estilo PNA para cada subplot
            pnaPlotLines: {
              isDark: isDark,
              unitSuffix: unitSuffix,
              umbrales: {
                alerta: alertaVal,
                evacuacion: evacVal
              }
            },
            tooltip: {
              backgroundColor: isDark ? 'rgba(7, 22, 40, 0.96)' : 'rgba(255, 255, 255, 0.98)',
              titleColor: isDark ? '#f8fafc' : '#0f294a',
              bodyColor: isDark ? '#cbd5e1' : '#334155',
              borderColor: isDark ? 'rgba(56, 189, 248, 0.3)' : 'rgba(2, 132, 199, 0.2)',
              borderWidth: 1,
              padding: 8,
              cornerRadius: 6,
              titleFont: { family: 'Space Grotesk', size: 10, weight: '700' },
              bodyFont: { family: 'JetBrains Mono', size: 10 },
              callbacks: {
                title: (items) => {
                  if (!items || items.length === 0) return '';
                  const item = items[0];
                  if (useTimeScale && item.parsed && item.parsed.x) {
                    const d = new Date(item.parsed.x);
                    if (!isNaN(d.getTime())) {
                      const dd = String(d.getDate()).padStart(2, '0');
                      const mm = String(d.getMonth() + 1).padStart(2, '0');
                      const hh = String(d.getHours()).padStart(2, '0');
                      const min = String(d.getMinutes()).padStart(2, '0');
                      return `📅 ${dd}/${mm} ${hh}:${min} hs`;
                    }
                  }
                  return item.label;
                },
                label: (c) => {
                  const yVal = c.parsed && c.parsed.y !== undefined ? c.parsed.y : c.raw;
                  const isPna = (c.dataset.label || '').toLowerCase().includes('pna') || (c.dataset.label || '').toLowerCase().includes('prefectura');
                  const icon = isPna ? '⚓' : '🔷';
                  return ` ${icon} ${c.dataset.label}: ${Number(yVal).toFixed(2)} ${unitSuffix}`;
                }
              }
            },
            zoom: {
              pan: { enabled: false },
              zoom: {
                drag: {
                  enabled: true,
                  backgroundColor: isDark ? 'rgba(56, 189, 248, 0.20)' : 'rgba(2, 132, 199, 0.16)',
                  borderColor: isDark ? '#38bdf8' : '#0284c7',
                  borderWidth: 1.5
                },
                pinch: { enabled: true },
                mode: 'x',
                onZoomComplete: () => {
                  Charts.toggleFloatingResetBtn(`subplot-floating-reset-${slotIdx}`, true);
                }
              }
            }
          },
          scales: {
            x: useTimeScale
              ? {
                  type: 'time',
                  title: {
                    display: true,
                    text: 'Fecha',
                    color: textColor,
                    font: { family: 'Inter', size: 10, weight: '600' },
                    padding: { top: 4 }
                  },
                  grid: { color: gridColor, borderDash: [2, 2] },
                  ticks: { color: textColor, font: { size: 9, family: 'Space Grotesk' }, maxTicksLimit: 6 }
                }
              : {
                  type: 'category',
                  title: {
                    display: true,
                    text: 'Fecha',
                    color: textColor,
                    font: { family: 'Inter', size: 10, weight: '600' },
                    padding: { top: 4 }
                  },
                  grid: { color: gridColor, borderDash: [2, 2] },
                  ticks: { color: textColor, font: { size: 9, family: 'Space Grotesk' }, maxTicksLimit: 6 }
                },
            ...subYScales
          }
        }
      });

      this.subplotCharts[slotIdx] = chart;
      this._subplotMeta = this._subplotMeta || [];
      this._subplotMeta[slotIdx] = {
        stationId,
        applyCota,
        source: activeSource,
        isDark,
        useTimeScale
      };
      this.toggleFloatingResetBtn(`subplot-floating-reset-${slotIdx}`, false);
    } catch (e) {
      if (loader && !silent) loader.classList.add('hidden');
      console.error(`Error cargando subplot ${slotIdx}:`, e);
    }
  }
};

window.Charts = Charts;
