/**
 * public/js/simepar.js
 * Visualizador de Precipitación Diaria Acumulada SIMEPAR y Mini-Calendario Interactivo.
 * Controles de reproducción Play/Pausa, fotogramas N/Total, y atajos de teclado.
 */

const SimeparView = {
  dates: [],
  selectedDate: null,
  currentCalendarMonth: new Date(),
  calendarOpen: false,
  isPlaying: false,
  playTimer: null,
  keyboardBound: false,

  async init() {
    try {
      const data = await API.getSimeparMaps();
      if (data && data.success) {
        this.dates = data.fechas || [];
        this.selectedDate = data.ultima_fecha || (this.dates.length > 0 ? this.dates[0] : null);
        if (this.selectedDate) {
          const parts = this.selectedDate.split('-');
          this.currentCalendarMonth = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, 1);
        }
        this.renderImage();
        this.updateControls();
      }
    } catch (e) {
      console.error('Error al inicializar SIMEPAR:', e);
    }

    this.bindKeyboardShortcuts();
  },

  renderImage() {
    const img = document.getElementById('simepar-map-img');
    const dlBtn = document.getElementById('btn-download-simepar-img');
    if (!this.selectedDate) return;

    const url = `/api/mapa_simepar/${this.selectedDate}.png`;
    if (img) img.src = url;
    if (dlBtn) {
      dlBtn.href = url;
      dlBtn.download = `SIMEPAR_${this.selectedDate}.png`;
    }

    // Pre-cargar el fotograma cronológico siguiente para evitar parpadeos
    if (this.dates && this.dates.length > 1) {
      const curIdx = this.dates.indexOf(this.selectedDate);
      const nextIdx = curIdx <= 0 ? this.dates.length - 1 : curIdx - 1;
      const preloadDate = this.dates[nextIdx];
      if (preloadDate) {
        const preloadImg = new Image();
        preloadImg.src = `/api/mapa_simepar/${preloadDate}.png`;
      }
    }
  },

  updateControls() {
    const display = document.getElementById('simepar-calendar-display');
    const prevBtn = document.getElementById('btn-simepar-prev-day');
    const nextBtn = document.getElementById('btn-simepar-next-day');
    const counterEl = document.getElementById('simepar-frame-counter');

    if (display) {
      if (this.selectedDate) {
        const parts = this.selectedDate.split('-');
        const d = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
        display.textContent = d.toLocaleDateString('es-AR', { day: '2-digit', month: 'short', year: 'numeric' });
      } else {
        display.textContent = 'Sin mapas';
      }
    }

    if (this.dates.length > 0 && this.selectedDate) {
      const idx = this.dates.indexOf(this.selectedDate);
      // dates está ordenado descendente (0 es la más reciente)
      if (prevBtn) prevBtn.disabled = (idx >= this.dates.length - 1);
      if (nextBtn) nextBtn.disabled = (idx <= 0);

      if (counterEl) {
        const chronologicalNum = this.dates.length - idx;
        counterEl.textContent = `${chronologicalNum} / ${this.dates.length}`;
        counterEl.title = `Fotograma ${chronologicalNum} de ${this.dates.length} (${this.selectedDate})`;
      }
    } else {
      if (counterEl) counterEl.textContent = '— / —';
    }
  },

  selectDate(dateStr) {
    if (!dateStr || !this.dates.includes(dateStr)) return;
    this.selectedDate = dateStr;
    const parts = this.selectedDate.split('-');
    this.currentCalendarMonth = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, 1);
    this.renderImage();
    this.updateControls();
    if (this.calendarOpen) this.renderCalendar();
  },

  selectDateByIndex(idx) {
    if (idx < 0 || idx >= this.dates.length) return;
    this.selectDate(this.dates[idx]);
  },

  stepDate(delta) {
    if (this.dates.length === 0 || !this.selectedDate) return;
    const idx = this.dates.indexOf(this.selectedDate);
    if (idx === -1) return;

    // delta = -1 va hacia el pasado (idx + 1 en lista descendente)
    // delta = +1 va hacia el futuro (idx - 1 en lista descendente)
    const newIdx = idx - delta;
    if (newIdx >= 0 && newIdx < this.dates.length) {
      this.selectDateByIndex(newIdx);
    }
  },

  togglePlay() {
    if (this.isPlaying) {
      this.stopPlay();
    } else {
      this.startPlay();
    }
  },

  startPlay() {
    if (this.dates.length <= 1) return;
    this.isPlaying = true;
    this.closeCalendar();
    this.updatePlayBtnUI();

    this.playTimer = setInterval(() => {
      if (!this.isPlaying || this.dates.length <= 1) {
        this.stopPlay();
        return;
      }
      const currentIdx = this.dates.indexOf(this.selectedDate);
      // Avanzar cronológicamente (hacia el presente: decrementar índice)
      const nextIdx = (currentIdx <= 0) ? (this.dates.length - 1) : (currentIdx - 1);
      this.selectDateByIndex(nextIdx);
    }, 850);
  },

  stopPlay() {
    this.isPlaying = false;
    if (this.playTimer) {
      clearInterval(this.playTimer);
      this.playTimer = null;
    }
    this.updatePlayBtnUI();
  },

  updatePlayBtnUI() {
    const playBtn = document.getElementById('btn-simepar-play');
    const playIcon = document.getElementById('simepar-play-icon');
    const playText = document.getElementById('simepar-play-text');
    if (!playBtn) return;

    if (this.isPlaying) {
      if (playIcon) playIcon.textContent = '⏸';
      if (playText) playText.textContent = 'Pausar';
      playBtn.className = 'px-2.5 py-1.5 bg-amber-600 hover:bg-amber-500 active:bg-amber-700 text-white rounded-lg flex items-center justify-center transition text-xs font-bold gap-1 shadow-xs cursor-pointer';
    } else {
      if (playIcon) playIcon.textContent = '▶';
      if (playText) playText.textContent = 'Animar';
      playBtn.className = 'px-2.5 py-1.5 bg-sky-600 hover:bg-sky-500 active:bg-sky-700 text-white rounded-lg flex items-center justify-center transition text-xs font-bold gap-1 shadow-xs cursor-pointer';
    }
  },

  bindKeyboardShortcuts() {
    if (this.keyboardBound) return;
    this.keyboardBound = true;

    document.addEventListener('keydown', (e) => {
      // Activar únicamente cuando la pestaña SIMEPAR esté activa y no se esté escribiendo en un input
      if (State.viewMode !== 'simepar') return;
      const tag = (e.target && e.target.tagName) ? e.target.tagName.toLowerCase() : '';
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return;

      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        this.stopPlay();
        this.stepDate(-1); // Día anterior
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        this.stopPlay();
        this.stepDate(1); // Día posterior
      } else if (e.key === ' ' || e.code === 'Space') {
        e.preventDefault();
        this.togglePlay();
      }
    });
  },

  toggleCalendar() {
    this.calendarOpen = !this.calendarOpen;
    const popover = document.getElementById('simepar-calendar-popover');
    if (popover) {
      popover.classList.toggle('hidden', !this.calendarOpen);
      if (this.calendarOpen) this.renderCalendar();
    }
  },

  closeCalendar() {
    this.calendarOpen = false;
    const popover = document.getElementById('simepar-calendar-popover');
    if (popover) popover.classList.add('hidden');
  },

  changeMonth(delta) {
    this.currentCalendarMonth.setDate(1);
    this.currentCalendarMonth.setMonth(this.currentCalendarMonth.getMonth() + delta);
    this.renderCalendar();
  },

  goToLatest() {
    if (this.dates.length > 0) {
      this.selectedDate = this.dates[0];
      const parts = this.selectedDate.split('-');
      this.currentCalendarMonth = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, 1);
      this.renderImage();
      this.updateControls();
      this.closeCalendar();
    }
  },

  renderCalendar() {
    const label = document.getElementById('simepar-month-label');
    const grid = document.getElementById('simepar-days-grid');
    if (!label || !grid) return;

    const year = this.currentCalendarMonth.getFullYear();
    const month = this.currentCalendarMonth.getMonth();

    label.textContent = this.currentCalendarMonth.toLocaleDateString('es-AR', { month: 'long', year: 'numeric' });

    // Días del mes (Lunes como primer día)
    const firstDay = new Date(year, month, 1).getDay(); // 0 Dom, 1 Lun
    const offset = (firstDay === 0 ? 6 : firstDay - 1);
    const daysInMonth = new Date(year, month + 1, 0).getDate();

    let html = '';
    // Celdas vacías previas
    for (let i = 0; i < offset; i++) {
      html += '<div class="cal-day-empty"></div>';
    }

    // Días del mes
    for (let day = 1; day <= daysInMonth; day++) {
      const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const hasMap = this.dates.includes(dateStr);
      const isSelected = (dateStr === this.selectedDate);

      if (hasMap) {
        const selClass = isSelected ? ' selected' : '';
        html += `<button type="button" onclick="window.selectSimeparDate('${dateStr}')" class="cal-day-btn has-map${selClass}" title="Mapa disponible: ${day}/${month + 1}/${year}">
          <span>${day}</span>
          <span class="map-dot"></span>
        </button>`;
      } else {
        html += `<div class="cal-day-disabled">${day}</div>`;
      }
    }

    grid.innerHTML = html;
  },

  async syncMapOnDemand() {
    try {
      Components.showToast('SIMEPAR', 'Descargando mapa diario de precipitación...');
      const res = await API.syncSimepar();
      if (res && res.success) {
        Components.showToast('SIMEPAR', `Mapa de ${res.fecha} descargado con éxito.`);
        await this.init();
      } else {
        Components.showToast('Error SIMEPAR', res.error || 'No se pudo descargar mapa', true);
      }
    } catch (e) {
      Components.showToast('Error', e.message, true);
    }
  }
};

window.SimeparView = SimeparView;
window.stepSimeparDate = (delta) => {
  if (window.SimeparView) {
    SimeparView.stopPlay();
    SimeparView.stepDate(delta);
  }
};
window.toggleSimeparCalendar = () => {
  if (window.SimeparView) SimeparView.toggleCalendar();
};
window.changeSimeparMonth = (delta) => {
  if (window.SimeparView) SimeparView.changeMonth(delta);
};
window.selectSimeparDate = (dateStr) => {
  if (window.SimeparView) {
    SimeparView.stopPlay();
    SimeparView.selectDate(dateStr);
    SimeparView.closeCalendar();
  }
};
window.goToLatestSimeparDate = () => {
  if (window.SimeparView) {
    SimeparView.stopPlay();
    SimeparView.goToLatest();
  }
};
window.syncSimeparMap = () => {
  if (window.SimeparView) SimeparView.syncMapOnDemand();
};
