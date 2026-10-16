/**
 * public/js/simepar.js
 * Visualizador de Precipitación Diaria Acumulada SIMEPAR y Mini-Calendario
 */

const SimeparView = {
  dates: [],
  selectedDate: null,
  currentCalendarMonth: new Date(),
  calendarOpen: false,

  async init() {
    try {
      const data = await API.getSimeparMaps();
      if (data && data.success) {
        this.dates = data.fechas || [];
        this.selectedDate = data.ultima_fecha || (this.dates.length > 0 ? this.dates[0] : null);
        if (this.selectedDate) {
          const parts = this.selectedDate.split('-');
          this.currentCalendarMonth = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, 1);
        }
        this.renderImage();
        this.updateControls();
      }
    } catch (e) {
      console.error('Error al inicializar SIMEPAR:', e);
    }
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
  },

  updateControls() {
    const display = document.getElementById('simepar-calendar-display');
    const prevBtn = document.getElementById('btn-simepar-prev-day');
    const nextBtn = document.getElementById('btn-simepar-next-day');

    if (display) {
      if (this.selectedDate) {
        const parts = this.selectedDate.split('-');
        const d = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
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
    }
  },

  stepDate(delta) {
    if (this.dates.length === 0 || !this.selectedDate) return;
    const idx = this.dates.indexOf(this.selectedDate);
    if (idx === -1) return;

    // delta = -1 va hacia el pasado (idx + 1 en lista descendente)
    // delta = +1 va hacia el futuro (idx - 1 en lista descendente)
    const newIdx = idx - delta;
    if (newIdx >= 0 && newIdx < this.dates.length) {
      this.selectedDate = this.dates[newIdx];
      this.renderImage();
      this.updateControls();
      if (this.calendarOpen) this.renderCalendar();
    }
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
    this.currentCalendarMonth.setMonth(this.currentCalendarMonth.getMonth() + delta);
    this.renderCalendar();
  },

  goToLatest() {
    if (this.dates.length > 0) {
      this.selectedDate = this.dates[0];
      const parts = this.selectedDate.split('-');
      this.currentCalendarMonth = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, 1);
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

    // Días del mes
    const firstDay = new Date(year, month, 1).getDay(); // 0 Dom, 1 Lun
    const offset = (firstDay === 0 ? 6 : firstDay - 1); // 0 Lun .. 6 Dom
    const daysInMonth = new Date(year, month + 1, 0).getDate();

    let html = '';
    // Celdas vacías previas
    for (let i = 0; i < offset; i++) {
      html += '<div class="cal-day-cell disabled"></div>';
    }

    // Días del mes
    for (let day = 1; day <= daysInMonth; day++) {
      const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const hasMap = this.dates.includes(dateStr);
      const isSelected = dateStr === this.selectedDate;

      let cls = 'cal-day-cell';
      if (hasMap) cls += ' has-map';
      if (isSelected) cls += ' selected';
      if (!hasMap) cls += ' disabled';

      const clickHandler = hasMap ? `onclick="window.selectSimeparDate('${dateStr}')"` : '';
      html += `<div class="${cls}" ${clickHandler}>${day}</div>`;
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
