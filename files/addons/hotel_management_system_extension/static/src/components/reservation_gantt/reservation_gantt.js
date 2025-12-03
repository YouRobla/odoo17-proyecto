/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUnmount, onPatched, useState, xml } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

const { DateTime, Interval } = luxon;
const MONTHS_RANGE = 12; // 6 meses hacia atrás y 6 hacia adelante
const STATE_TRANSITIONS = Object.freeze({
    // Estados principales (8 estados únicos)
    initial: ['confirmed', 'cancelled'],           // BORRADOR
    confirmed: ['checkin', 'cancelled', 'no_show'], // CONFIRMADA
    checkin: ['checkout', 'cancelled'],            // CHECK-IN
    checkout: ['cleaning_needed'],                 // CHECK-OUT
    cleaning_needed: ['room_ready'],               // LIMPIEZA NECESARIA
    room_ready: ['confirmed'],                     // HABITACION LISTA
    cancelled: [],                                 // CANCELADA (terminal)
    no_show: [],                                   // NO SE PRESENTO (terminal)

    // Estados legacy del sistema base (compatibilidad)
    draft: ['confirmed', 'cancelled'],
    allot: ['checkin', 'cancelled', 'no_show'],
    check_in: ['checkout', 'cancelled'],
    checkout_pending: ['checkout'],
    pending: ['confirmed', 'cancelled'],
    room_assigned: ['checkin', 'cancelled', 'no_show'],
});

// =============================================================================
// FUNCIONES DE VALIDACIÓN DE TRANSICIONES
// =============================================================================

/**
 * Validar si una transición de estado es permitida
 * @param {string} currentState - Estado actual
 * @param {string} newState - Nuevo estado
 * @returns {boolean} - True si la transición es válida
 */
function isValidStateTransition(currentState, newState) {
    const allowedTransitions = STATE_TRANSITIONS[currentState] || [];
    return allowedTransitions.includes(newState);
}

/**
 * Obtener las transiciones disponibles para un estado
 * @param {string} currentState - Estado actual
 * @returns {Array} - Array de estados permitidos
 */
function getAvailableTransitions(currentState) {
    return STATE_TRANSITIONS[currentState] || [];
}

/**
 * Obtener el siguiente estado lógico en el flujo
 * @param {string} currentState - Estado actual
 * @returns {string|null} - Siguiente estado o null si no hay flujo definido
 */
function getNextLogicalState(currentState) {
    const flow = {
        initial: 'confirmed',
        confirmed: 'room_assigned',
        room_assigned: 'checkin',
        checkin: 'checkout',
        checkout: 'cleaning_needed',
        cleaning_needed: 'room_ready',
        room_ready: 'confirmed', // Nueva reserva
    };
    return flow[currentState] || null;
}

const STATUS_DEFINITIONS = Object.freeze({
    // Estados principales (8 estados únicos)
    initial: {
        key: 'initial',
        label: _t('BORRADOR'),
        description: _t('Reserva en estado borrador, no activa.'),
        isBlocking: false,
        color: '#A9A9A9',
        legendClass: 'draft',
        emoji: '⚫'
    },
    confirmed: {
        key: 'confirmed',
        label: _t('CONFIRMADA'),
        description: _t('Reserva confirmada y garantizada.'),
        isBlocking: true,
        color: '#00BFA5',
        legendClass: 'confirmed',
        emoji: '🟢'
    },
    checkin: {
        key: 'checkin',
        label: _t('CHECK-IN'),
        description: _t('Huésped en la habitación, estancia en curso.'),
        isBlocking: true,
        color: '#FF6B35',
        legendClass: 'checkin',
        emoji: '🟠'
    },
    checkout: {
        key: 'checkout',
        label: _t('CHECK-OUT'),
        description: _t('Huésped salió, habitación finalizada.'),
        isBlocking: false,
        color: '#1A237E',
        legendClass: 'checkout',
        emoji: '🔵'
    },
    cleaning_needed: {
        key: 'cleaning_needed',
        label: _t('LIMPIEZA NECESARIA'),
        description: _t('Habitación necesita limpieza.'),
        isBlocking: false,
        color: '#FF9800',
        legendClass: 'cleaning_needed',
        emoji: '🟡'
    },
    room_ready: {
        key: 'room_ready',
        label: _t('HABITACION LISTA'),
        description: _t('Habitación limpia y lista para nuevos huéspedes.'),
        isBlocking: false,
        color: '#4CAF50',
        legendClass: 'room_ready',
        emoji: '🟢'
    },
    cancelled: {
        key: 'cancelled',
        label: _t('CANCELADA'),
        description: _t('Reserva cancelada.'),
        isBlocking: false,
        color: '#D32F2F',
        legendClass: 'cancelled',
        emoji: '🔴'
    },
    no_show: {
        key: 'no_show',
        label: _t('NO SE PRESENTO'),
        description: _t('El huésped no se presentó.'),
        isBlocking: false,
        color: '#7c5bba',
        legendClass: 'no-show',
        emoji: '🟣'
    },

    // Estados Legacy (Compatibilidad) - Mapeados a estados principales
    draft: {
        key: 'draft',
        label: _t('BORRADOR'),
        description: _t('Reserva en borrador (estado legacy).'),
        isBlocking: false,
        color: '#A9A9A9',
        legendClass: 'draft',
        emoji: '⚫'
    },
    confirm: {
        key: 'confirm',
        label: _t('CONFIRMADA'),
        description: _t('Reserva confirmada (estado legacy).'),
        isBlocking: true,
        color: '#00BFA5',
        legendClass: 'confirmed',
        emoji: '🟢'
    },
    check_in: {
        key: 'check_in',
        label: _t('CHECK-IN'),
        description: _t('Huésped en habitación (estado legacy).'),
        isBlocking: true,
        color: '#FF6B35',
        legendClass: 'checkin',
        emoji: '🟠'
    },
    allot: {
        key: 'allot',
        label: _t('CHECK-IN'),
        description: _t('Habitación asignada (estado legacy).'),
        isBlocking: true,
        color: '#FF6B35',
        legendClass: 'checkin',
        emoji: '🟠'
    },
    checkout_pending: {
        key: 'checkout_pending',
        label: _t('CHECK-OUT PENDIENTE'),
        description: _t('Check-out pendiente (estado legacy).'),
        isBlocking: false,
        color: '#1A237E',
        legendClass: 'checkout_pending',
        emoji: '🔵'
    },
    pending: {
        key: 'pending',
        label: _t('PENDIENTE'),
        description: _t('Reserva pendiente de confirmación (estado legacy).'),
        isBlocking: false,
        color: '#00BFA5',
        legendClass: 'pending',
        emoji: '🟢'
    },
    room_assigned: {
        key: 'room_assigned',
        label: _t('HABITACIÓN ASIGNADA'),
        description: _t('Habitación asignada (estado legacy).'),
        isBlocking: true,
        color: '#FF6B35',
        legendClass: 'room_assigned',
        emoji: '🟠'
    },
    cancel: {
        key: 'cancel',
        label: _t('CANCELADA'),
        description: _t('Reserva cancelada (estado legacy).'),
        isBlocking: false,
        color: '#D32F2F',
        legendClass: 'cancelled',
        emoji: '🔴'
    },
    done: {
        key: 'done',
        label: _t('FINALIZADA'),
        description: _t('Reserva finalizada (estado legacy).'),
        isBlocking: false,
        color: '#4CAF50',
        legendClass: 'done',
        emoji: '🟢'
    },
});

const DEFAULT_STATUS = Object.freeze({
    key: 'unknown',
    label: _t('Desconocido'),
    description: _t('Estado de reserva desconocido.'),
    isBlocking: false,
    color: '#7B1FA2',
    legendClass: 'unknown',
    emoji: '🟣'
});

// =============================================================================
// --- Funciones de Utilidad ---
// =============================================================================
const Utils = Object.freeze({


    /**
     * Extraer tipo de habitación desde el nombre de la habitación
     * @param {string} roomName - Nombre de la habitación
     * @returns {string} Tipo de habitación
     */
    extractRoomType(roomName) {
        if (!roomName) return '';
        return roomName.split(' ')[0] || '';
    },

    /**
     * Get customer name in uppercase
     * @param {string} name - Customer name
     * @returns {string} Uppercase name
     */
    getCustomerNameUpper(name) {
        if (!name || typeof name !== 'string') return '';
        const upperName = name.toUpperCase();
        // Truncar a 8 caracteres máximo para evitar que la barra se extienda
        return upperName.length > 8 ? upperName.substring(0, 8) + '...' : upperName;
    },

    /**
     * Obtener color del estado de forma segura
     * @param {string} state - Estado de la reserva
     * @returns {string} Código de color hexadecimal
     */
    getStateColor(state) {
        const statusDef = STATUS_DEFINITIONS[state];
        return statusDef?.color || DEFAULT_STATUS.color;
    },

    /**
     * Obtener ID del array de forma segura desde tupla/objeto de Odoo
     * @param {Array|Object|number} value - Valor del cual extraer el ID
     * @returns {number|null} ID o null
     */
    extractId(value) {
        if (!value) return null;
        if (Array.isArray(value)) return value[0] || null;
        if (typeof value === 'object' && value.id) return value.id;
        if (typeof value === 'number') return value;
        return null;
    },

    /**
     * Formatear fecha para mostrar
     * @param {string} isoDate - Cadena de fecha ISO
     * @param {string} format - Cadena de formato Luxon
     * @returns {string} Fecha formateada
     */
    formatDate(isoDate, format = 'dd/MM/yyyy') {
        try {
            return DateTime.fromISO(isoDate).toFormat(format);
        } catch {
            return '';
        }
    },

    /**
     * Verificar si la fecha es válida
     * @param {string} isoDate - Cadena de fecha ISO
     * @returns {boolean} True si es válida
     */
    isValidDate(isoDate) {
        return DateTime.fromISO(isoDate).isValid;
    }
});

// =============================================================================
// --- Clase Auxiliar Mejorada del Selector de Celdas ---
// =============================================================================
class GanttCellSelector {
    constructor(component) {
        this.component = component;
        this.state = useState({
            active: false,
            roomId: null,
            startDay: null,
            endDay: null,
            hoveredDay: null,
            hoveredRoomId: null,
            isValidSelection: true,
        });

        // Bind event handlers
        this._onGlobalMouseUp = this._onGlobalMouseUp.bind(this);
        this._onGlobalMouseMove = this._onGlobalMouseMove.bind(this);
        this._onGlobalKeyDown = this._onGlobalKeyDown.bind(this);

        // Add global event listeners
        this._addEventListeners();
    }

    destroy() {
        this._removeEventListeners();
    }

    _addEventListeners() {
        document.addEventListener('mouseup', this._onGlobalMouseUp, { passive: true });
        document.addEventListener('mousemove', this._onGlobalMouseMove, { passive: true });
        document.addEventListener('keydown', this._onGlobalKeyDown);
    }

    _removeEventListeners() {
        document.removeEventListener('mouseup', this._onGlobalMouseUp);
        document.removeEventListener('mousemove', this._onGlobalMouseMove);
        document.removeEventListener('keydown', this._onGlobalKeyDown);
    }

    /**
     * Iniciar selección de celda
     * @param {Event} ev - Evento del ratón
     * @param {number} roomId - ID de la habitación
     * @param {number} day - Número del día
     * @returns {boolean} True si la selección se inició
     */
    start(ev, roomId, day) {
        // Prevent selection on occupied cells or past days
        const today = DateTime.now().toISODate();
        const selectedDate = this.component.getDayDate(day).toISODate();

        if (this.component.isDayOccupied(roomId, day) || selectedDate < today) {
            return false;
        }

        ev.preventDefault();
        ev.stopPropagation();

        // Initialize selection
        Object.assign(this.state, {
            active: true,
            roomId,
            startDay: day,
            endDay: day,
            hoveredDay: day,
            hoveredRoomId: roomId,
            isValidSelection: true,
            warningShown: false,
        });

        document.body.classList.add('gantt-selecting');
        return true;
    }

    /**
     * Actualizar estado de hover
     * @param {number} roomId - ID de la habitación
     * @param {number} day - Número del día
     */
    updateHover(roomId, day) {
        if (!this.state.active) return;

        const today = DateTime.now().toISODate();
        const selectedDate = this.component.getDayDate(day).toISODate();

        // Don't allow extending selection to past days
        if (selectedDate < today) return;

        this.state.hoveredDay = day;
        this.state.hoveredRoomId = roomId;

        // Only allow selection in the same room
        if (roomId === this.state.roomId) {
            this.state.endDay = day;
            this._validateSelection();
            
            // Mostrar advertencia solo una vez por selección si se invade una celda ocupada
            if (!this.state.isValidSelection && !this.state.warningShown) {
                this.state.warningShown = true;
                this.component.notification.add(
                    _t('El rango seleccionado se superpone con la reserva existente.'),
                    {
                        type: 'warning',
                        title: _t('Selección no válida')
                    }
                );
            }
        }
    }

    _validateSelection() {
        if (!this.state.active) return;

        const { roomId, startDay, endDay } = this.state;
        const selectionStart = Math.min(startDay, endDay);
        const selectionEnd = Math.max(startDay, endDay);

        // Check if range is available
        this.state.isValidSelection = this.component.isRangeAvailable(roomId, selectionStart, selectionEnd);
    }

    _onGlobalMouseMove(ev) {
        if (!this.state.active) return;

        // Find the closest cell to cursor
        const cellElement = this._findCellFromPoint(ev.clientX, ev.clientY);
        if (cellElement) {
            const day = parseInt(cellElement.dataset.day);
            const roomElement = cellElement.closest('.gantt_row_content');
            if (roomElement && day) {
                const roomId = this._getRoomIdFromElement(roomElement);
                if (roomId) {
                    this.updateHover(roomId, day);
                }
            }
        }
    }

    _onGlobalMouseUp() {
        if (this.state.active) {
            this._finalize();
        }
    }

    _onGlobalKeyDown(ev) {
        if (this.state.active && ev.key === 'Escape') {
            this._cancel();
        }
    }

    _findCellFromPoint(x, y) {
        const elements = document.elementsFromPoint(x, y);
        return elements.find(el => el.classList.contains('day_cell') && el.dataset.day);
    }

    _getRoomIdFromElement(rowElement) {
        // Find row index to get roomId
        const allRows = Array.from(document.querySelectorAll('.gantt_row_content'));
        const rowIndex = allRows.indexOf(rowElement);
        if (rowIndex >= 0 && rowIndex < this.component.filteredRooms.length) {
            return this.component.filteredRooms[rowIndex].id;
        }
        return null;
    }

    async _finalize() {
        const { roomId, startDay, endDay, isValidSelection } = this.state;

        if (roomId != null && startDay != null && endDay != null && isValidSelection) {
            const selectionStart = Math.min(startDay, endDay);
            const selectionEnd = Math.max(startDay, endDay);

            // Create reservation
            await this.component.createNewReservation(roomId, selectionStart, selectionEnd);
        } else if (!isValidSelection) {
            this.component.notification.add(
                _t('El rango seleccionado se superpone con la reserva existente.'),
                {
                    type: 'warning',
                    title: _t('Selección no válida')
                }
            );
        }

        this._reset();
    }

    _cancel() {
        this.component.notification.add(_t('Selección cancelada'), { type: 'info' });
        this._reset();
    }

    _reset() {
        Object.assign(this.state, {
            active: false,
            roomId: null,
            startDay: null,
            endDay: null,
            hoveredDay: null,
            hoveredRoomId: null,
            isValidSelection: true,
            warningShown: false,
        });

        document.body.classList.remove('gantt-selecting');
    }

    // Template helper methods
    getOverlayStyle() {
        if (!this.state.active) return 'display: none;';

        const roomIndex = this.component.filteredRooms.findIndex(room => room.id === this.state.roomId);
        if (roomIndex === -1) return 'display: none;';

        return `grid-column: 2; grid-row: ${roomIndex + 2};`;
    }

    getSelectionStyle() {
        if (!this.state.active) return 'display: none;';

        const start = Math.min(this.state.startDay, this.state.endDay);
        const end = Math.max(this.state.startDay, this.state.endDay);
        const duration = end - start + 1;

        return `grid-column: ${start} / span ${duration};`;
    }

    getSelectionClass() {
        const classes = ['gantt_selection_overlay'];
        if (!this.state.isValidSelection) {
            classes.push('invalid-selection');
        }
        return classes.join(' ');
    }

    getSelectionText() {
        if (!this.state.active) return '';

        const startDay = Math.min(this.state.startDay, this.state.endDay);
        const endDay = Math.max(this.state.startDay, this.state.endDay);
        const duration = endDay - startDay + 1;

        const startDate = this.component.getDayDate(startDay).toFormat('dd/MM');
        const endDate = this.component.getDayDate(endDay).toFormat('dd/MM');

        let text = `${startDate} - ${endDate} (${duration} ${_t('day')}${duration > 1 ? 's' : ''})`;

        if (!this.state.isValidSelection) {
            text += ` - ⚠️ ${_t('Conflictos con la reserva existente')}`;
        }

        return text;
    }

    /**
     * Check if specific cell is hovered
     * @param {number} roomId - Room ID
     * @param {number} day - Day number
     * @returns {boolean} True if hovered
     */
    isCellHovered(roomId, day) {
        if (!this.state.active) return false;

        const start = Math.min(this.state.startDay, this.state.endDay);
        const end = Math.max(this.state.startDay, this.state.endDay);

        return roomId === this.state.roomId && day >= start && day <= end;
    }
}

// =============================================================================
// --- Main Component: ReservationGantt ---
// =============================================================================
export class ReservationGantt extends Component {
    static props = {
        // Props estáticas requeridas por Odoo 17 para acciones de cliente
        action: { type: Object, optional: true },
        actionId: { type: Number, optional: true },
        className: { type: String, optional: true },
    };

    // static components = {
    //     RoomPanel,
    // };

    static template = xml`
<div class="o_reservation_gantt" t-att-class="{ 'loading': state.isLoading }">

    <div class="gantt-toolbar">
        <div class="toolbar-left">
            <div class="control-group">
                <label for="month-select" t-esc="_t('Mes')"/>
                <select id="month-select" t-model="state.selectedMonth" t-on-change="onMonthChange" class="form-select">
                    <option t-foreach="state.months" t-as="month" t-key="month.value" t-att-value="month.value" t-esc="month.label"/>
                </select>
            </div>
            <div class="control-group">
                <label for="hotel-select" t-esc="_t('Hotel')"/>
                <select id="hotel-select" t-model="state.selectedHotel" t-on-change="onHotelChange" class="form-select">
                    <option value="" t-esc="_t('Todos los Hoteles')"/>
                    <option t-foreach="state.hotels" t-as="hotel" t-key="hotel.id" t-att-value="hotel.id" t-esc="hotel.name"/>
                </select>
            </div>
            <div class="control-group">
                <label for="room-type-select" t-esc="_t('Habitación')"/>
                <select id="room-type-select" t-model="state.selectedRoomType" t-on-change="onRoomTypeChange" class="form-select">
                    <option value="" t-esc="_t('Todas')"/>
                    <option t-foreach="state.roomTypes" t-as="type" t-key="type" t-att-value="type" t-esc="type"/>
                </select>
            </div>
            <button class="btn btn-primary btn-today" t-on-click="goToToday" t-esc="_t('Hoy')"/>
            <button class="btn btn-secondary o_refresh_btn" t-on-click="() => this.refreshData()">
                <i class="fa fa-refresh"/>
                <span t-esc="_t('Actualizar')"/>
            </button>
        </div>
        <div class="toolbar-right">
            <div class="gantt-legend">
                <div t-foreach="legendItems" t-as="item" t-key="item.key" class="legend-item" title="item.description">
                    <span class="legend-emoji" t-esc="item.emoji"/>
                    <span class="legend-text" t-esc="item.label"/>
                </div>
            </div>
        </div>
    </div>

    <div class="gantt-stats">
        <div class="stat-item">
            <span class="stat-label" t-esc="_t('Habitaciones Mostradas')"/>
            <span class="stat-value" t-esc="filteredRooms.length"/>
        </div>
        <div class="stat-item">
            <span class="stat-label" t-esc="_t('Reservas Activas')"/>
            <span class="stat-value" t-esc="activeReservationsCount"/>
        </div>
        <div class="stat-item">
            <span class="stat-label" t-esc="_t('Tasa de Ocupación')"/>
            <span class="stat-value" t-esc="occupancyRate"/>
        </div>
    </div>

    <!-- Navegación de Meses Prominente -->
    <div class="gantt-month-navigation">
        <div class="month-nav-container">
            <button class="month-nav-btn month-nav-prev" t-on-click="onPrevMonth" title="Mes anterior">
                <i class="fa fa-chevron-left"></i>
            </button>
            <div class="month-display">
                <span class="month-name" t-esc="currentMonthName"/>
                <span class="month-year" t-esc="currentYear"/>
            </div>
            <button class="month-nav-btn month-nav-next" t-on-click="onNextMonth" title="Mes siguiente">
                <i class="fa fa-chevron-right"></i>
            </button>
        </div>
    </div>

    <div class="gantt-container-wrapper">
        <div t-if="state.isLoading" class="gantt-loader-container">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden" t-esc="_t('Cargando...')"/>
            </div>
        </div>
        <div class="gantt-container" t-att-style="gridTemplateColumnsStyle">
            <div class="gantt_header_row">
                <div class="gantt_cell gantt_header_cell header_room gantt-header-cell">
                    <span t-esc="_t('Habitaciones (%s)', filteredRooms.length)"/>
                </div>
                <div class="gantt_header_days">
                    <div t-foreach="state.month_info.days" t-as="day" t-key="day"
                         t-att-class="'gantt_cell gantt_header_cell header_day gantt-header-cell ' + getDayHeaderClass(day)">
                        <div class="day-number" t-esc="day"/>
                        <div class="day-name" t-esc="getDayName(day)"/>
                    </div>
                </div>
            </div>

            <div t-if="!state.isLoading and !filteredRooms.length" class="empty-state">
                <div class="empty-icon">🏨</div>
                <div class="empty-message" t-esc="_t('No se encontraron habitaciones')"/>
                <div class="empty-suggestion" t-esc="_t('Intente cambiar los filtros o el mes seleccionado.')"/>
            </div>

            <t t-foreach="filteredRooms" t-as="room" t-key="room.id">
                <div class="gantt_cell room_name_cell" 
                     t-att-style="'grid-row: ' + (room_index + 2)"
                     t-att-class="state.hoveredRowId === room.id ? 'row-hovered' : ''">
                    <div class="room-name" t-esc="room.name"/>
                    <div class="room-description" t-if="room.product_website_description" t-esc="room.product_website_description"/>
                </div>
                <div class="gantt_row_content" 
                     t-att-style="'grid-row: ' + (room_index + 2)"
                     t-on-mouseenter="() => this.onRowMouseEnter(room.id)"
                     t-on-mouseleave="() => this.onRowMouseLeave(room.id)">
                    <div t-foreach="state.month_info.days" t-as="day" t-key="day"
                         t-att-class="'gantt_cell day_cell ' + getDayHeaderClass(day) + (this.cellSelector.isCellHovered(room.id, day) ? ' cell-hovered' : '') + (this.isDayOccupied(room.id, day) ? ' cell-occupied' : ' cell-available')"
                         t-att-data-day="day"
                         t-att-data-room-id="room.id"
                         t-on-mousedown="(ev) => this.cellSelector.start(ev, room.id, day)"
                         t-on-mouseenter="(ev) => this.cellSelector.updateHover(room.id, day)"
                         t-on-click="(ev) => this.onEmptyCellClick(ev, room.id, day)" />

                    <t t-foreach="getReservationsForRoom(room.id)" t-as="res" t-key="res.id">
                        <div t-att-class="'gantt_reservation_bar state_' + (res.state || res.status_bar) + (this.isCheckoutSoon(res) ? ' checkout_soon' : '')"
                             t-att-style="getReservationStyle(res)"
                             t-on-mouseenter="(ev) => this.showTooltip(ev, res)"
                             t-on-mousemove="(ev) => this.showTooltip(ev, res)"
                             t-on-mouseleave="this.hideTooltip"
                             t-att-data-res-id="res.id"
                             t-on-click="this.onReservationClick">
                            <div class="gantt_reservation_content">
                                <span class="gantt_reservation_label" t-esc="Utils.getCustomerNameUpper(res.customer_name)"/>
                                <span class="gantt_reservation_duration" t-esc="getReservationDurationLabel(res)"/>
                                <span class="gantt_reservation_status_emoji" t-esc="this._getStatusDefinition(res.state || res.status_bar).emoji"/>
                            </div>
                        </div>
                    </t>
                    
                    <!-- Selection overlay for this specific room -->
                    <div t-if="cellSelector.state.active and cellSelector.state.roomId === room.id" 
                         t-att-class="cellSelector.getSelectionClass()" 
                         t-att-style="cellSelector.getSelectionStyle()">
                        <div class="selection-info">
                            <span t-esc="cellSelector.getSelectionText()"/>
                        </div>
                    </div>
                </div>
            </t>
        </div>
    </div>

    <!-- Tooltip -->
    <div t-if="state.tooltip.visible" 
         class="gantt-tooltip-custom" 
         aria-live="polite" 
         t-att-style="'left:' + state.tooltip.x + 'px; top:' + state.tooltip.y + 'px; border-left-color:' + state.tooltip.data.statusColor + ';'">
        <div><strong t-esc="state.tooltip.data.customer"/></div>
        <div>
            <span t-esc="_t('Desde')"/>: <strong t-esc="state.tooltip.data.start"/>
        </div>
        <div>
            <span t-esc="_t('Hasta')"/>: <strong t-esc="state.tooltip.data.end"/>
        </div>
        <div>
            <span t-esc="_t('Duración')"/>: <strong t-esc="state.tooltip.data.duration"/>
        </div>
        <div class="tooltip-price">
            <span t-esc="_t('Precio')"/>: <strong t-esc="state.tooltip.data.price"/>
        </div>
        <div class="tooltip-status">
            <span t-esc="_t('Estado')"/>: <span class="tooltip-status-indicator" t-att-style="'color:' + state.tooltip.data.statusColor + ';'" t-esc="state.tooltip.data.status"/>
        </div>
        <div class="tooltip-status-description">
            <em t-esc="state.tooltip.data.statusDescription"/>
        </div>
        
        <!-- Información contextual del cambio de habitación -->
        <div t-if="state.tooltip.data.isRoomChangeSegment" class="tooltip-segment-info">
            <div class="segment-header">
                <span t-esc="_t('Información de Cambio de Habitación')"/>
            </div>
            <div class="segment-details">
                <span t-if="state.tooltip.data.segmentInfo.isFirstSegment" class="segment-badge first-segment">
                    <span t-esc="_t('Primero')"/>
                </span>
                <span t-if="state.tooltip.data.segmentInfo.isLastSegment" class="segment-badge last-segment">
                    <span t-esc="_t('Último')"/>
                </span>
                <span t-if="state.tooltip.data.segmentInfo.hasNextSegment" class="segment-badge has-next">
                    <span t-esc="_t('Continúa')"/>
                </span>
            </div>
            
            <!-- Información detallada del cambio de habitación -->
            <div class="room-change-summary">
                <div class="change-info-item">
                    <span class="change-label">
                        <span t-esc="_t('Habitación Actual')"/>: 
                        <strong t-esc="state.tooltip.data.currentRoom"/>
                    </span>
                </div>
                
                <!-- Mostrar habitación destino si es origen, o habitación origen si es destino -->
                <div t-if="state.tooltip.data.segmentInfo.isRoomChangeOrigin and state.tooltip.data.segmentInfo.nextRoomId" class="change-info-item">
                    <span class="change-label">
                        <span t-esc="_t('Habitación Destino')"/>: 
                        <strong t-esc="state.tooltip.data.segmentInfo.nextRoomName || state.tooltip.data.segmentInfo.nextRoomId"/>
                    </span>
                </div>
                
                <div t-if="state.tooltip.data.segmentInfo.isRoomChangeDestination and state.tooltip.data.segmentInfo.previousRoomId" class="change-info-item">
                    <span class="change-label">
                        <span t-esc="_t('Habitación Origen')"/>: 
                        <strong t-esc="state.tooltip.data.segmentInfo.previousRoomName || state.tooltip.data.segmentInfo.previousRoomId"/>
                    </span>
                </div>
                
                <!-- Información de conectividad -->
                <div t-if="state.tooltip.data.segmentInfo.connectedBookingId" class="change-info-item">
                    <span class="change-label">
                        <span t-esc="_t('Reserva Conectada')"/>: 
                        <strong t-esc="state.tooltip.data.segmentInfo.connectedBookingId"/>
                    </span>
                </div>
                
                <!-- Estado del cambio -->
                <div class="change-info-item">
                    <span class="change-label">
                        <span t-esc="_t('Estado del Cambio')"/>: 
                        <span t-if="state.tooltip.data.segmentInfo.isRoomChangeOrigin" class="status-badge origin">
                            <span t-esc="_t('Origen')"/>
                        </span>
                        <span t-elif="state.tooltip.data.segmentInfo.isRoomChangeDestination" class="status-badge destination">
                            <span t-esc="_t('Destino')"/>
                        </span>
                        <span t-else="" class="status-badge intermediate">
                            <span t-esc="_t('Intermedio')"/>
                        </span>
                    </span>
                </div>
                
                <!-- Duración del segmento -->
                <div class="change-info-item">
                    <span class="change-label">
                        <span t-esc="_t('Duración del Segmento')"/>: 
                        <strong t-esc="state.tooltip.data.duration"/>
                    </span>
                </div>
            </div>
        </div>
    </div>
    
</div>
    `;

    // ===============================
    // Setup and Service Initialization
    // ===============================
    setup() {
        this.rpc = useService("rpc");
        this.notification = useService("notification");
        this.action = useService("action");
        this.user = useService("user");

        this.state = useState({
            hotels: [],
            selectedHotel: '',
            rooms: [],
            reservations: [],
            month_info: { days: [], month_name: '', first_day_str: '' },
            months: this._getMonthsList(),
            selectedMonth: DateTime.now().toFormat('yyyy-MM'),
            roomTypes: [],
            selectedRoomType: '',
            reservationStates: Object.keys(STATUS_DEFINITIONS),
            selectedState: '',
            isLoading: true,
            hoveredRowId: null,
            tooltip: {
                visible: false,
                x: 0,
                y: 0,
                data: {},
            }
        });

        this.reservationsByRoomAndDay = new Map();
        // Mapa separado para disponibilidad: almacena información detallada sobre ocupación por día
        // Estructura: Map<roomId, Map<day, {type: 'full_day'|'half_day_morning'|'half_day_afternoon', reservation: res}>>
        this.availabilityByRoomAndDay = new Map();
        this.roomChangeSegments = new Map();
        this.cellSelector = new GanttCellSelector(this);

        onWillStart(async () => {
            await this._loadHotels();
            await this._loadData();
        });

        onWillUnmount(() => {
            this.cellSelector.destroy();
        });
    }

    // ===============================
    // Métodos de Carga de Datos
    // ===============================
    _getMonthsList() {
        const months = [];
        const now = DateTime.now();
        for (let i = -MONTHS_RANGE / 2; i <= MONTHS_RANGE / 2; i++) {
            const month = now.plus({ months: i });
            const monthLabel = month.setLocale('es').toFormat('MMMM yyyy');
            const capitalizedLabel = monthLabel.charAt(0).toUpperCase() + monthLabel.slice(1);
            months.push({
                value: month.toFormat('yyyy-MM'),
                label: capitalizedLabel,
            });
        }
        return months;
    }

    async _loadHotels() {
        try {
            const response = await this.rpc('/hotel/get_hotels', {});

            if (response && response.success && response.hotels) {
                this.state.hotels = response.hotels || [];

                if (!this.state.selectedHotel && this.state.hotels.length) {
                    this.state.selectedHotel = this.state.hotels[0].id;
                }
            } else {
                this.state.hotels = [];
            }
        } catch (error) {
            this.notification.add(_t('No se pudieron cargar hoteles.'), { type: 'danger' });
            this.state.hotels = [];
        }
    }

    async _loadData() {
        this.state.isLoading = true;
        try {
            const [year, month] = this.state.selectedMonth.split('-').map(Number);
            const targetDate = DateTime.fromObject({ year, month, day: 1 });

            const data = await this.rpc("/hotel/gantt_data", {
                target_date: targetDate.toISODate(),
                hotel_id: this.state.selectedHotel || null,
            });

            this.state.rooms = data.rooms || [];
            this.state.reservations = data.reservations || [];
            this.state.month_info = data.month_info || { days: [], month_name: '', first_day_str: '' };


            // Extract room types from filtered rooms (based on selected hotel)
            const filteredRoomsForTypes = this.state.selectedHotel && this.state.selectedHotel !== '' && this.state.selectedHotel !== 'undefined' && this.state.selectedHotel !== undefined && this.state.selectedHotel !== null && this.state.selectedHotel !== 'null'
                ? this.state.rooms.filter(r => {
                    const roomHotelId = Utils.extractId(r.hotel_id);
                    const selectedHotelId = parseInt(this.state.selectedHotel);
                    return roomHotelId === selectedHotelId;
                })
                : this.state.rooms;

            this.state.roomTypes = [...new Set(
                filteredRoomsForTypes
                    .map(room => Utils.extractRoomType(room.name))
                    .filter(Boolean)
            )].sort();

            this._buildReservationMap();
        } catch (error) {
            this.notification.add(_t('No se pudo cargar los datos del calendario: ') + error.message, { type: 'danger' });
        } finally {
            this.state.isLoading = false;
        }
    }

    _buildReservationMap() {
        try {
            this.reservationsByRoomAndDay.clear();
            this.availabilityByRoomAndDay.clear();
            this.roomChangeSegments.clear();

            const reservationsByBooking = new Map();
            for (const res of this.state.reservations) {
                if (!res || !res.booking_id) {
                    continue;
                }
                const bookingId = Utils.extractId(res.booking_id) || res.id;
                if (!reservationsByBooking.has(bookingId)) {
                    reservationsByBooking.set(bookingId, []);
                }
                reservationsByBooking.get(bookingId).push(res);
            }

            for (const [bookingId, bookingReservations] of reservationsByBooking) {
                try {
                    bookingReservations.sort((a, b) => {
                        const dateA = DateTime.fromISO(a.date_start);
                        const dateB = DateTime.fromISO(b.date_start);
                        return dateA.toMillis() - dateB.toMillis();
                    });

                    // Process all reservations as regular reservations (no special room change handling)
                    for (const res of bookingReservations) {
                        this._processRegularReservation(res);
                        // También procesar para detección de conflictos
                        this._processConflictDetection(res);
                    }
                } catch (bookingError) {
                    // Error procesando booking
                }
            }
        } catch (error) {
            throw error;
        }
    }

    _processRoomChangeSegments(bookingId, reservations) {
        // Group consecutive reservations by room
        const segments = [];
        let currentSegment = {
            roomId: Utils.extractId(reservations[0].room_id),
            reservations: [reservations[0]],
            startDate: DateTime.fromISO(reservations[0].date_start),
            endDate: DateTime.fromISO(reservations[0].date_end),
            segmentIndex: 0
        };

        for (let i = 1; i < reservations.length; i++) {
            const res = reservations[i];
            const resRoomId = Utils.extractId(res.room_id);
            const resStartDate = DateTime.fromISO(res.date_start);

            // Processing reservation

            // Check if this is a continuation in the same room or a room change
            if (resRoomId === currentSegment.roomId && 
                resStartDate.diff(currentSegment.endDate, 'days').days <= 1) {
                // Same room, consecutive or same day - extend current segment
                currentSegment.reservations.push(res);
                currentSegment.endDate = DateTime.fromISO(res.date_end);
            } else {
                // Different room or gap - start new segment
                segments.push(currentSegment);
                currentSegment = {
                    roomId: resRoomId,
                    reservations: [res],
                    startDate: resStartDate,
                    endDate: DateTime.fromISO(res.date_end),
                    segmentIndex: segments.length
                };
            }
        }
        segments.push(currentSegment);

        // Store segments for this booking
        this.roomChangeSegments.set(bookingId, segments);

        // Process each segment
        segments.forEach((segment, index) => {
            const isFirstSegment = index === 0;
            const isLastSegment = index === segments.length - 1;
            const hasNextSegment = index < segments.length - 1;

            // Processing segment

            // Process segment reservations

            segment.reservations.forEach(res => {
                const roomId = Utils.extractId(res.room_id);
                if (!this.reservationsByRoomAndDay.has(roomId)) {
                    this.reservationsByRoomAndDay.set(roomId, new Map());
                }

                const roomMap = this.reservationsByRoomAndDay.get(roomId);

                try {
                    const startDateTime = DateTime.fromISO(res.date_start);
                    const endDateTime = DateTime.fromISO(res.date_end);
                    const resInterval = Interval.fromDateTimes(startDateTime, endDateTime);

                    let dayCursor = resInterval.start.startOf('day');
                    const checkoutDay = resInterval.end.startOf('day');

                    // Para segmentos de cambio de habitación, usar checkout inclusivo
                    while (dayCursor <= checkoutDay) {
                        if (dayCursor.toFormat('yyyy-MM') === this.state.selectedMonth) {
                            // Add segment metadata to reservation
                            const resWithSegment = {
                                ...res,
                                isRoomChangeSegment: true,
                                segmentIndex: index,
                                isFirstSegment,
                                isLastSegment,
                                hasNextSegment,
                                totalSegments: segments.length,
                                nextSegmentRoomId: hasNextSegment ? Utils.extractId(segments[index + 1].room_id) : null,
                                previousSegmentRoomId: index > 0 ? Utils.extractId(segments[index - 1].room_id) : null
                            };
                            roomMap.set(dayCursor.day, resWithSegment);
                        }
                        dayCursor = dayCursor.plus({ days: 1 });
                    }
                } catch (error) {
                    // Error al procesar las fechas del segmento
                }
            });
        });
    }

    _processRegularReservation(res) {
        if (!res.room_id) return;

        const roomId = Utils.extractId(res.room_id);
        if (!roomId) return;

        if (!this.reservationsByRoomAndDay.has(roomId)) {
            this.reservationsByRoomAndDay.set(roomId, new Map());
        }
        if (!this.availabilityByRoomAndDay.has(roomId)) {
            this.availabilityByRoomAndDay.set(roomId, new Map());
        }

        const roomMap = this.reservationsByRoomAndDay.get(roomId);
        const availabilityMap = this.availabilityByRoomAndDay.get(roomId);

        try {
            const startDateTime = DateTime.fromISO(res.date_start);
            const endDateTime = DateTime.fromISO(res.date_end);
            
            // Obtener información de horas del backend
            const isHalfDayCheckin = res.is_half_day_checkin || false;
            const isHalfDayCheckout = res.is_half_day_checkout || false;
            const checkInHour = res.check_in_hour;
            const checkOutHour = res.check_out_hour;
            
            // Usar startOf('day') solo al inicio del bucle
            let dayCursor = startDateTime.startOf('day');
            const checkoutDay = endDateTime.startOf('day');
            
            // Determinar si el checkout es a medio día (antes de las 12 PM)
            // Si es así, el día de checkout NO debe estar ocupado en disponibilidad
            const isCheckoutHalfDay = isHalfDayCheckout && checkOutHour !== null && checkOutHour < 12;
            
            // Para reservas regulares, usar checkout exclusivo (no incluir el día de checkout)
            // PERO: si el checkout es a medio día, el día de checkout NO debe estar ocupado en disponibilidad
            while (dayCursor < checkoutDay) {
                if (dayCursor.toFormat('yyyy-MM') === this.state.selectedMonth) {
                    // Lógica de visualización: marcar día para mostrar la barra
                    roomMap.set(dayCursor.day, res);
                    
                    // Lógica de disponibilidad: determinar qué parte del día está ocupada
                    const isFirstDay = dayCursor.hasSame(startDateTime, 'day');
                    const isLastDay = dayCursor.hasSame(checkoutDay.minus({ days: 1 }), 'day');
                    
                    let availabilityType = 'full_day'; // Por defecto, día completo ocupado
                    
                    // Si es el primer día y el check-in es a medio día (después de las 12 PM)
                    if (isFirstDay && isHalfDayCheckin && checkInHour !== null && checkInHour >= 12) {
                        availabilityType = 'half_day_afternoon'; // Solo tarde ocupada
                    }
                    // Si es el último día y el check-out es a medio día (antes de las 12 PM)
                    else if (isLastDay && isCheckoutHalfDay) {
                        availabilityType = 'half_day_morning'; // Solo mañana ocupada
                    }
                    
                    // Almacenar información de disponibilidad
                    availabilityMap.set(dayCursor.day, {
                        type: availabilityType,
                        reservation: res
                    });
                }
                dayCursor = dayCursor.plus({ days: 1 });
            }
            
            // IMPORTANTE: Si el checkout es a medio día (antes de las 12 PM), 
            // el día de checkout NO debe estar ocupado en disponibilidad
            // La barra visual puede extenderse hasta ese día, pero la disponibilidad no
            // Esto permite que la habitación esté disponible en la tarde del día de checkout
        } catch (error) {
            // Error al procesar las fechas de la reserva
        }
    }

    _processConflictDetection(res) {
        if (!res.room_id) return;

        const roomId = Utils.extractId(res.room_id);
        if (!roomId) return;

        if (!this.reservationsByRoomAndDay.has(roomId)) {
            this.reservationsByRoomAndDay.set(roomId, new Map());
        }

        const roomMap = this.reservationsByRoomAndDay.get(roomId);

        try {
            const startDateTime = DateTime.fromISO(res.date_start);
            const endDateTime = DateTime.fromISO(res.date_end);
            
            // Para detección de conflictos, usar checkout inclusivo (incluir el día de checkout)
            let dayCursor = startDateTime.startOf('day');
            const checkoutDay = endDateTime.startOf('day');
            
            // Incluir todos los días que visualmente ocupa la barra
            while (dayCursor <= checkoutDay) {
                if (dayCursor.toFormat('yyyy-MM') === this.state.selectedMonth) {
                    // Solo marcar para conflicto si no hay ya una reserva en ese día
                    if (!roomMap.has(dayCursor.day)) {
                        roomMap.set(dayCursor.day, { ...res, conflictOnly: true });
                    }
                }
                dayCursor = dayCursor.plus({ days: 1 });
            }
        } catch (error) {
            // Error al procesar la detección de conflictos
        }
    }

    // ===============================
    // Propiedades Computadas (Getters)
    // ===============================
    get filteredRooms() {
        let rooms = [...this.state.rooms];

        // Filtrar por hotel seleccionado
        if (this.state.selectedHotel && this.state.selectedHotel !== '' && this.state.selectedHotel !== 'undefined' && this.state.selectedHotel !== undefined && this.state.selectedHotel !== null && this.state.selectedHotel !== 'null') {
            const selectedHotelId = parseInt(this.state.selectedHotel);

            rooms = rooms.filter(r => {
                const roomHotelId = Utils.extractId(r.hotel_id);
                return roomHotelId === selectedHotelId;
            });
        }

        // Filtrar por tipo de habitación
        if (this.state.selectedRoomType) {
            rooms = rooms.filter(r =>
                Utils.extractRoomType(r.name) === this.state.selectedRoomType
            );
        }

        return rooms;
    }

    get filteredReservations() {
        return this.state.selectedState
            ? this.state.reservations.filter(r => r.state === this.state.selectedState)
            : [...this.state.reservations];
    }

    get activeReservationsCount() {
        return this.state.reservations.filter(r =>
            r.state === 'confirmed' || r.state === 'checkin'
        ).length;
    }

    get occupancyRate() {
        if (!this.state.month_info.first_day_str) return "0%";

        try {
            const totalRooms = this.filteredRooms.length;
            if (!totalRooms) return '0%';

            // Contar habitaciones ocupadas (solo CHECK-IN)
            const occupiedRooms = new Set();
            for (const res of this.state.reservations) {
                if (res.state === 'checkin') {
                    const roomId = Utils.extractId(res.room_id);
                    if (roomId) {
                        occupiedRooms.add(roomId);
                    }
                }
            }

            const rate = (occupiedRooms.size / totalRooms) * 100;
            return `${Math.min(100, Math.round(rate))}%`;
        } catch (error) {
            return '0%';
        }
    }

    get gridTemplateColumnsStyle() {
        return `grid-template-columns: 220px 1fr;`;
    }


    get legendItems() {
        // Estados ordenados según el flujo lógico del ciclo de vida de una reserva
        const mainStates = [
            'initial',          // 1. BORRADOR (inicio del proceso)
            'confirmed',        // 2. CONFIRMADA (reserva activa)
            'checkin',          // 3. CHECK-IN (huésped llegó)
            'checkout',         // 4. CHECK-OUT (huésped se fue)
            'cleaning_needed',  // 5. LIMPIEZA NECESARIA (habitación necesita limpieza)
            'room_ready',       // 6. HABITACION LISTA (habitación limpia y lista)
            'cancelled',        // 7. CANCELADA (estado terminal)
            'no_show'           // 8. NO SE PRESENTO (estado terminal)
        ];

        const legend = [];

        // Agregar solo los estados principales en orden lógico
        for (const stateKey of mainStates) {
            const stateDef = STATUS_DEFINITIONS[stateKey];
            if (stateDef) {
                legend.push(stateDef);
            }
        }

        return legend;
    }

    get currentMonthName() {
        try {
            const [year, month] = this.state.selectedMonth.split('-').map(Number);
            const date = DateTime.fromObject({ year, month, day: 1 });
            const monthName = date.setLocale('es').toFormat('MMMM');
            return monthName.charAt(0).toUpperCase() + monthName.slice(1);
        } catch (error) {
            const monthName = DateTime.now().setLocale('es').toFormat('MMMM');
            return monthName.charAt(0).toUpperCase() + monthName.slice(1);
        }
    }

    get currentYear() {
        try {
            const [year] = this.state.selectedMonth.split('-').map(Number);
            return year;
        } catch (error) {
            return DateTime.now().year;
        }
    }



    // ===============================
    // Manejadores de Eventos
    // ===============================
    onMonthChange(ev) {
        this.state.selectedMonth = ev.target.value;
        this._loadData();
    }

    onHotelChange(ev) {
        this.state.selectedHotel = ev.target.value;
        // Limpiar el filtro de tipo de habitación cuando se cambia el hotel
        this.state.selectedRoomType = '';
        this._loadData();
    }

    onRoomTypeChange(ev) {
        this.state.selectedRoomType = ev.target.value;
    }

    goToToday() {
        this.state.selectedMonth = DateTime.now().toFormat('yyyy-MM');
        this._loadData();
    }

    refreshData() {
        this._loadData();
    }













    onPrevMonth() {
        this._changeMonth(-1);
    }

    onNextMonth() {
        this._changeMonth(1);
    }
    
    /**
     * Cambia el mes actual
     * @param {number} direction - Dirección del cambio (-1 para anterior, 1 para siguiente)
     */
    _changeMonth(direction) {
        const [year, month] = this.state.selectedMonth.split('-').map(Number);
        const currentDate = DateTime.fromObject({ year, month, day: 1 });
        const newDate = direction > 0 
            ? currentDate.plus({ months: 1 })
            : currentDate.minus({ months: 1 });
        
        this.state.selectedMonth = newDate.toFormat('yyyy-MM');
        this._loadData();
    }

    onReservationClick(ev) {
        ev.stopPropagation();
        const resId = ev.currentTarget.dataset.resId;
        const reservation = this.state.reservations.find(r => String(r.id) === String(resId));

        if (!reservation) {
            this.notification.add(_t('Reserva no encontrada'), { type: 'warning' });
            return;
        }

        // Validar y preservar el estado original
        this._validateAndPreserveOriginalState(reservation);

        // Mostrar notificación de seguimiento si es un cambio de habitación
        this._showRoomChangeNotification(reservation);

        // Open the complete booking in a larger modal window
        this.action.doAction({
            name: _t('Reservation: %s', reservation.customer_name),
            type: 'ir.actions.act_window',
            res_model: 'hotel.booking',
            res_id: Utils.extractId(reservation.booking_id) || reservation.id,
            views: [[false, 'form']],
            target: 'new',
            context: {
                create: false,
                edit: true,
            },
            flags: {
                mode: 'edit',
                hasSearchView: false,
                hasFilters: false,
                hasTimeRangeMenu: false,
                hasFavoriteMenu: false,
                hasFavorites: false,
                hasGroupBy: false,
            }
        }, {
            onClose: () => this._loadData(),
        });
    }



    async onEmptyCellClick(ev, roomId, day) {
        // Only open if there's no reservation on that day/room, no active selection and it's not a past day
        const today = DateTime.now().toISODate();
        const selectedDate = this.getDayDate(day).toISODate();

        // Verificar si hay una reserva en limpieza en este día
        const roomMap = this.reservationsByRoomAndDay.get(roomId);
        const hasCleaningReservation = roomMap && roomMap.get(day) && roomMap.get(day).state === 'cleaning_needed';

        if (!this.cellSelector.state.active &&
            !this.isDayOccupied(roomId, day) &&
            !hasCleaningReservation &&
            selectedDate >= today) {
            await this.createNewReservation(roomId, day, day);
        } else if (hasCleaningReservation) {
            // Mostrar mensaje específico para habitaciones en limpieza
            this.notification.add(
                _t('No se puede crear una reserva: la habitación está en proceso de limpieza. Complete la limpieza primero.'),
                {
                    type: 'warning',
                    title: _t('Habitación en Limpieza')
                }
            );
        }
    }

    // ===============================
    // Renderizado de Reservas (1 mes estable)
    // ===============================
    getReservationStyle(res) {
        const [year, month] = this.state.selectedMonth.split('-').map(Number);
        const monthStart = DateTime.fromObject({ year, month, day: 1 });
        const monthEnd = monthStart.endOf('month');

        try {
            // Fechas de la reserva
            const resStart = DateTime.fromISO(res.date_start);
            const resEnd = DateTime.fromISO(res.date_end);

            if (!resStart.isValid || !resEnd.isValid) {
                return 'display: none;';
            }

            // Visualizar dentro del mes seleccionado
            let barStart = resStart < monthStart ? monthStart : resStart;
            let barEnd = resEnd > monthEnd ? monthEnd : resEnd;

            if (barEnd < monthStart || barStart > monthEnd) {
                return 'display: none;';
            }

            // Obtener información de horas del backend (preferir datos del API si están disponibles)
            const checkInHour = res.check_in_hour !== undefined && res.check_in_hour !== null 
                ? res.check_in_hour 
                : (resStart.hour);
            const checkOutHour = res.check_out_hour !== undefined && res.check_out_hour !== null 
                ? res.check_out_hour 
                : (resEnd.hour);
            const checkInMinute = res.check_in_minute !== undefined && res.check_in_minute !== null
                ? res.check_in_minute
                : (resStart.minute || 0);
            const checkOutMinute = res.check_out_minute !== undefined && res.check_out_minute !== null
                ? res.check_out_minute
                : (resEnd.minute || 0);

            // Calcular posición y ancho proporcional según horas
            const startCol = barStart.day;
            const endCol = barEnd.day;
            
            // Calcular el porcentaje del día para el inicio (0-100%)
            // Si la reserva comienza en este día específico, usar la hora exacta
            let startOffsetPercent = 0;
            if (startCol === resStart.day) {
                if (checkInHour !== null && checkInHour !== undefined) {
                    // Calcular minutos totales desde medianoche
                    const totalMinutes = checkInHour * 60 + checkInMinute;
                    // Convertir a porcentaje del día (1440 minutos = 24 horas)
                    startOffsetPercent = (totalMinutes / 1440) * 100;
                } else {
                    // Fallback: usar la hora de resStart
                    const totalMinutes = resStart.hour * 60 + (resStart.minute || 0);
                    startOffsetPercent = (totalMinutes / 1440) * 100;
                }
            }

            // Calcular el porcentaje del día para el final (0-100%)
            let endOffsetPercent = 100;
            if (endCol === resEnd.day) {
                if (checkOutHour !== null && checkOutHour !== undefined) {
                    // Calcular minutos totales desde medianoche
                    const totalMinutes = checkOutHour * 60 + checkOutMinute;
                    // Convertir a porcentaje del día
                    endOffsetPercent = (totalMinutes / 1440) * 100;
                } else {
                    // Fallback: usar la hora de resEnd
                    const totalMinutes = resEnd.hour * 60 + (resEnd.minute || 0);
                    endOffsetPercent = (totalMinutes / 1440) * 100;
                }
            }
            
            // Si tenemos información de duración del API, usarla para validar/ajustar
            if (res.duration_hours !== undefined && res.duration_hours !== null) {
                // Validar que el cálculo sea consistente con la duración reportada
                const calculatedHours = ((endOffsetPercent - startOffsetPercent) / 100) * 24;
                // Si hay una diferencia significativa, ajustar usando la duración del API
                if (Math.abs(calculatedHours - res.duration_hours) > 0.5 && duration === 0) {
                    // Ajustar endOffsetPercent basándose en la duración real
                    endOffsetPercent = startOffsetPercent + (res.duration_hours / 24 * 100);
                }
            }

            // Calcular duración en días
            let duration = endCol - startCol;
            
            // Para reservas de pocas horas (mismo día), asegurar que el cálculo sea correcto
            if (duration < 0) duration = 0;
            
            // Si es el mismo día, verificar que endOffsetPercent sea mayor que startOffsetPercent
            if (duration === 0) {
                if (endOffsetPercent <= startOffsetPercent) {
                    // Si el final es antes o igual al inicio, calcular basándose en duración mínima
                    // Para reservas de pocas horas, usar al menos 1% del día (14.4 minutos)
                    const minDurationPercent = 1; // 1% = 14.4 minutos
                    endOffsetPercent = Math.max(startOffsetPercent + minDurationPercent, endOffsetPercent);
                }
                
                // Asegurar que para reservas muy cortas (menos de 1 hora) se muestren correctamente
                const durationPercent = endOffsetPercent - startOffsetPercent;
                if (durationPercent < 0.5) {
                    // Mínimo 0.5% del día (7.2 minutos) para que sea visible
                    endOffsetPercent = startOffsetPercent + 0.5;
                }
            }

            // Obtener el número total de días del mes para calcular porcentajes correctos
            const totalDaysInMonth = this.state.month_info.days.length;
            
            // Calcular posición y ancho en porcentajes del ancho total del mes
            // Cada día representa (100 / totalDaysInMonth)% del ancho total
            const dayWidthPercent = 100 / totalDaysInMonth;
            
            // Calcular left: posición desde el inicio del mes
            // (startCol - 1) días completos + offset del primer día
            const daysBeforeStart = startCol - 1;
            const leftPercent = (daysBeforeStart * dayWidthPercent) + (startOffsetPercent * dayWidthPercent / 100);
            
            // Calcular width: ancho total de la reserva
            let widthPercent;
            if (duration === 0) {
                // Mismo día: ancho = diferencia de porcentajes del día
                widthPercent = (endOffsetPercent - startOffsetPercent) * dayWidthPercent / 100;
            } else {
                // Múltiples días:
                // - Días completos intermedios: duration * dayWidthPercent
                // - Parte del primer día: (100 - startOffsetPercent) * dayWidthPercent / 100
                // - Parte del último día: endOffsetPercent * dayWidthPercent / 100
                const intermediateDaysWidth = duration * dayWidthPercent;
                const firstDayPartialWidth = (100 - startOffsetPercent) * dayWidthPercent / 100;
                const lastDayPartialWidth = endOffsetPercent * dayWidthPercent / 100;
                widthPercent = firstDayPartialWidth + intermediateDaysWidth + lastDayPartialWidth;
            }
            
            // Asegurar ancho mínimo
            if (widthPercent < 2) widthPercent = 2;
            
            // Usar posicionamiento absoluto con left y width en porcentajes del contenedor total
            let style = `position: absolute; left: ${leftPercent}%; width: ${widthPercent}%; `;
            style += `overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; font-size: 0.9em;`;

            if (res.isRoomChangeSegment) {
                style += this._getRoomChangeSegmentStyle(res);
            }

            return style;
        } catch (error) {
            return 'display: none;';
        }
    }

    _getRoomChangeSegmentStyle(res) {
        const segmentColors = [
            '#4CAF50',  // Green for first segment
            '#2196F3',  // Blue for second segment
            '#FF9800',  // Orange for third segment
            '#9C27B0',  // Purple for fourth segment
            '#F44336',  // Red for fifth segment
            '#00BCD4',  // Cyan for sixth segment
            '#795548',  // Brown for seventh segment
            '#607D8B'   // Blue Grey for eighth segment
        ];

        const color = segmentColors[res.segmentIndex % segmentColors.length];
        let style = `background: linear-gradient(135deg, ${color}, ${color}dd); border-left: 4px solid ${color};`;

        // Add connector indicators
        if (res.hasNextSegment) {
            style += `position: relative;`;
        }

        if (res.isFirstSegment) {
            style += `border-top-left-radius: 4px; border-bottom-left-radius: 4px;`;
        }

        if (res.isLastSegment) {
            style += `border-top-right-radius: 4px; border-bottom-right-radius: 4px;`;
        }

        return style;
    }

    getConnectorStyle(res) {
        if (!res.isRoomChangeSegment || !res.hasNextSegment) {
            return 'display: none;';
        }

        // Creating connector for reservation

        const [year, month] = this.state.selectedMonth.split('-').map(Number);
        const monthStart = DateTime.fromObject({ year, month, day: 1 });
        const monthEnd = monthStart.endOf('month');

        try {
            const resStart = DateTime.fromISO(res.date_start);
            const resEnd = DateTime.fromISO(res.date_end);

            if (!resStart.isValid || !resEnd.isValid) {
                return 'display: none;';
            }

            let barStart = resStart < monthStart ? monthStart : resStart;
            let barEnd = resEnd > monthEnd ? monthEnd : resEnd;

            if (barEnd < monthStart || barStart > monthEnd) {
                return 'display: none;';
            }

            const startCol = barStart.day;
            const endCol = barEnd.day;
            const duration = Math.max(1, endCol - startCol + 1);

            // Position connector at the end of the current segment
            const connectorPosition = startCol + duration;
            
            
            // Obtener información de la habitación siguiente
            const nextRoomName = res.nextSegmentRoomId ? this._getRoomName(res.nextSegmentRoomId) : 'Siguiente Habitación';
            
            return `grid-column: ${connectorPosition} / ${connectorPosition + 1}; 
                    background: linear-gradient(90deg, #FFD700 0%, #FFA500 50%, transparent 100%);
                    height: 4px;
                    position: absolute;
                    top: 50%;
                    transform: translateY(-50%);
                    z-index: 10;
                    border-radius: 2px;
                    box-shadow: 0 2px 6px rgba(255, 215, 0, 0.4);
                    cursor: pointer;
                    transition: all 0.3s ease;
                    animation: connectorPulse 2s ease-in-out infinite;
                    
                    /* Tooltip para el conector */
                    &::after {
                        content: '→ ${nextRoomName}';
                        position: absolute;
                        right: -8px;
                        top: -12px;
                        background: rgba(0, 0, 0, 0.8);
                        color: white;
                        padding: 4px 8px;
                        border-radius: 4px;
                        font-size: 11px;
                        white-space: nowrap;
                        opacity: 0;
                        transform: translateY(-5px);
                        transition: all 0.3s ease;
                        pointer-events: none;
                        z-index: 15;
                    }
                    
                    &:hover {
                        background: linear-gradient(90deg, #FFD700 0%, #FF8C00 50%, transparent 100%);
                        box-shadow: 0 4px 12px rgba(255, 215, 0, 0.6);
                        transform: translateY(-50%) scaleY(1.5);
                        
                        &::after {
                            opacity: 1;
                            transform: translateY(0);
                        }
                    }`;
        } catch (error) {
            return 'display: none;';
        }
    }

    _getRoomName(roomId) {
        if (!roomId) return _t('Habitación Desconocida');
        
        // Si es un array [id, name], devolver el nombre
        if (Array.isArray(roomId) && roomId.length > 1) {
            return roomId[1];
        }
        
        // Si es solo un ID, buscar en la lista de habitaciones
        const roomIdNum = Array.isArray(roomId) ? roomId[0] : roomId;
        const room = this.state.rooms.find(r => r.id === roomIdNum);
        return room ? room.name : _t('Habitación Desconocida');
    }

    /**
     * Mostrar notificación de seguimiento para cambios de habitación
     * @param {Object} res - Reserva con información de cambio de habitación
     */
    _showRoomChangeNotification(res) {
        if (!res.isRoomChangeSegment) return;

        const currentRoom = this._getRoomName(res.room_id);
        const nextRoom = res.nextSegmentRoomId ? this._getRoomName(res.nextSegmentRoomId) : null;
        const previousRoom = res.previousSegmentRoomId ? this._getRoomName(res.previousSegmentRoomId) : null;

        let notificationMessage = '';
        let notificationType = 'info';

        if (res.isFirstSegment && res.hasNextSegment) {
            notificationMessage = _t('⚠️ Atención: Esta reserva continuará en otra habitación. Próxima habitación: %s', nextRoom);
            notificationType = 'warning';
        } else if (res.isLastSegment && res.previousSegmentRoomId) {
            notificationMessage = _t('✅ Reserva completada. Habitación anterior: %s', previousRoom);
            notificationType = 'success';
        } else if (res.hasNextSegment) {
            notificationMessage = _t('🔄 Cambio de habitación en progreso. Próxima habitación: %s', nextRoom);
            notificationType = 'info';
        }

        if (notificationMessage) {
            this._displayNotification(notificationMessage, notificationType, {
                reservationId: res.id,
                customerName: res.customer_name,
                currentRoom: currentRoom,
                nextRoom: nextRoom,
                previousRoom: previousRoom
            });
        }
    }

    /**
     * Mostrar notificación en la interfaz
     * @param {string} message - Mensaje de la notificación
     * @param {string} type - Tipo de notificación (info, warning, success, error)
     * @param {Object} data - Datos adicionales de la notificación
     */
    _displayNotification(message, type = 'info', data = {}) {
        // Crear elemento de notificación
        const notification = document.createElement('div');
        notification.className = `room-change-notification notification-${type}`;
        notification.innerHTML = `
            <div class="notification-content">
                <div class="notification-message">${message}</div>
                <div class="notification-actions">
                    <button class="btn-notification-dismiss" onclick="this.parentElement.parentElement.parentElement.remove()">×</button>
                </div>
            </div>
        `;

        // Agregar estilos inline para la notificación
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10000;
            background: ${this._getNotificationColor(type)};
            color: white;
            padding: 12px 16px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            max-width: 400px;
            animation: slideInRight 0.3s ease-out;
        `;

        // Agregar al DOM
        document.body.appendChild(notification);

        // Auto-remover después de 5 segundos
        setTimeout(() => {
            if (notification.parentElement) {
                notification.style.animation = 'slideOutRight 0.3s ease-in';
                setTimeout(() => {
                    if (notification.parentElement) {
                        notification.remove();
                    }
                }, 300);
            }
        }, 5000);
    }

    /**
     * Obtener color de notificación según el tipo
     * @param {string} type - Tipo de notificación
     * @returns {string} - Color hexadecimal
     */
    _getNotificationColor(type) {
        const colors = {
            info: 'linear-gradient(135deg, #2196F3, #1976D2)',
            warning: 'linear-gradient(135deg, #FF9800, #F57C00)',
            success: 'linear-gradient(135deg, #4CAF50, #45a049)',
            error: 'linear-gradient(135deg, #F44336, #D32F2F)'
        };
        return colors[type] || colors.info;
    }

    /**
     * Validar y preservar el estado original de las reservas
     * @param {Object} reservation - Reserva a validar
     * @returns {boolean} - True si el estado se preserva correctamente
     */
    _validateAndPreserveOriginalState(reservation) {
        if (!reservation || !reservation.isRoomChangeSegment) {
            return true;
        }

        // Validar que la reserva original mantenga su estado
        const originalState = reservation.originalState || reservation.status_bar;
        const currentState = reservation.status_bar;

        // Si es el primer segmento, debe mantener el estado original
        if (reservation.isFirstSegment && originalState && currentState !== originalState) {
            // Mostrar notificación de advertencia
            this._displayNotification(
                _t('⚠️ Advertencia: El estado original de la reserva no se ha preservado correctamente.'),
                'warning',
                {
                    reservationId: reservation.id,
                    originalState: originalState,
                    currentState: currentState
                }
            );
            
            return false;
        }

        // Validar que los segmentos intermedios mantengan consistencia
        if (!reservation.isFirstSegment && !reservation.isLastSegment) {
            const expectedState = 'checkin'; // Los segmentos intermedios deben estar en check-in
            if (currentState !== expectedState) {
                this._displayNotification(
                    _t('⚠️ Estado inconsistente en segmento de cambio de habitación.'),
                    'warning',
                    {
                        reservationId: reservation.id,
                        expectedState: expectedState,
                        currentState: currentState
                    }
                );
                
                return false;
            }
        }

        return true;
    }

    /**
     * Restaurar el estado original de una reserva si es necesario
     * @param {Object} reservation - Reserva a restaurar
     */
    _restoreOriginalState(reservation) {
        if (!reservation || !reservation.isRoomChangeSegment || !reservation.isFirstSegment) {
            return;
        }

        const originalState = reservation.originalState;
        if (originalState && reservation.status_bar !== originalState) {
            // Aquí se podría implementar la lógica para restaurar el estado
            // Por ejemplo, llamando a una función del backend
            this._displayNotification(
                _t('🔄 Restaurando estado original de la reserva...'),
                'info',
                {
                    reservationId: reservation.id,
                    restoredState: originalState
                }
            );
        }
    }

    // ===============================
    // Tooltips y Utilidades
    // ===============================
    showTooltip(ev, res) {
        // Verificar si es una reserva con cambio de habitación
        const connectedBookingId = res.connected_booking_id || res.split_from_booking_id;
        const isRoomChangeOrigin = res.is_room_change_origin || false;
        const isRoomChangeDestination = res.is_room_change_destination || false;
        
        // Verificar si es un cambio de habitación real
        const hasRoomChangeDetection = connectedBookingId || isRoomChangeOrigin || isRoomChangeDestination;
        
        // Solo resaltar si realmente es un cambio de habitación
        if (hasRoomChangeDetection) {
            this._highlightRoomChangeBars(res);
        } else {
            this._clearRoomChangeHighlight();
        }
        
        const status = this._getStatusDefinition(res.state || res.status_bar);
        const start = Utils.formatDate(res.date_start);

        // Para el tooltip, mostramos el último día real de estancia (que ahora es el checkout)
        // Esto es consistente con la representación visual del Gantt
        const checkoutDate = DateTime.fromISO(res.date_end);
        const end = Utils.formatDate(checkoutDate.toISO());

        const duration = this.getReservationDurationLabel(res);

        // Formatear precio de forma segura
        const totalAmount = res.total_amount || 0;
        const currencySymbol = res.currency_symbol || '$';
        const formattedPrice = `${currencySymbol} ${totalAmount.toFixed(2)}`;

        // Obtener información de habitaciones para el tooltip
        const currentRoomName = this._getRoomName(res.room_id);
        const nextRoomName = res.nextSegmentRoomId ? this._getRoomName(res.nextSegmentRoomId) : null;
        const previousRoomName = res.previousSegmentRoomId ? this._getRoomName(res.previousSegmentRoomId) : null;

        // Obtener información adicional del cambio de habitación
        const tooltipConnectedBookingId = res.connected_booking_id || res.split_from_booking_id;
        const tooltipIsRoomChangeOrigin = res.is_room_change_origin || false;
        const tooltipIsRoomChangeDestination = res.is_room_change_destination || false;
        
        // Determinar si es un cambio de habitación (segmento o reserva conectada)
        const hasRoomChange = res.isRoomChangeSegment || tooltipConnectedBookingId || tooltipIsRoomChangeOrigin || tooltipIsRoomChangeDestination;

        const tooltipData = {
            customer: res.customer_name || _t('Cliente Desconocido'),
            start,
            end,
            duration,
            status: `${status.emoji} ${status.label}`,
            statusDescription: status.description,
            statusColor: status.color,
            price: formattedPrice,
            currentRoom: currentRoomName,
            // Room change segment information
            isRoomChangeSegment: hasRoomChange,
            segmentInfo: hasRoomChange ? {
                segmentNumber: res.segmentIndex !== undefined ? res.segmentIndex + 1 : 1,
                totalSegments: res.totalSegments || 2,
                isFirstSegment: res.isFirstSegment !== undefined ? res.isFirstSegment : isRoomChangeOrigin,
                isLastSegment: res.isLastSegment !== undefined ? res.isLastSegment : isRoomChangeDestination,
                hasNextSegment: res.hasNextSegment !== undefined ? res.hasNextSegment : isRoomChangeOrigin,
                nextRoomId: res.nextSegmentRoomId,
                nextRoomName: nextRoomName,
                previousRoomId: res.previousSegmentRoomId,
                previousRoomName: previousRoomName,
                currentRoomName: currentRoomName,
                connectedBookingId: connectedBookingId,
                isRoomChangeOrigin: isRoomChangeOrigin,
                isRoomChangeDestination: isRoomChangeDestination
            } : null
        };

        // Calcular posición del tooltip relativa a la barra de reserva
        const tooltipWidth = 240; // Aproximado
        const tooltipHeight = 110; // Aproximado

        // Obtener el elemento de la barra de reserva para calcular el posicionamiento correcto
        const reservationBar = ev.currentTarget;
        const barRect = reservationBar.getBoundingClientRect();

        // Calcular posición basada en el final de la barra visual
        const [year, month] = this.state.selectedMonth.split('-').map(Number);
        const monthStart = DateTime.fromObject({ year, month, day: 1 });

        // Obtener fechas de la reserva
        const resStart = DateTime.fromISO(res.date_start);
        const resEnd = DateTime.fromISO(res.date_end);

        // Obtener el día final visual (el día de checkout es ahora el día final real)
        const visualEndDay = resEnd.day;

        // Obtener el ancho real de la celda desde la cuadrícula
        const gridContainer = document.querySelector('.gantt-container');
        if (gridContainer && visualEndDay <= this.state.month_info.days.length) {
            const gridRect = gridContainer.getBoundingClientRect();
            const totalDays = this.state.month_info.days.length;
            const cellWidth = (gridRect.width - 220) / totalDays; // 220px es el ancho de la columna de habitaciones

            // Calcular la posición del día final visual (final de la barra)
            const visualEndPosition = gridRect.left + 220 + (visualEndDay - 1) * cellWidth;

            // Posicionar tooltip al final de la barra visual
            let x = visualEndPosition + 8; // 8px de desplazamiento desde el final de la barra visual
            let y = barRect.top - (tooltipHeight / 2) + (barRect.height / 2); // Centrar verticalmente en la barra

            // Asegurar que el tooltip no se salga de la pantalla
            if (window.innerWidth && x + tooltipWidth > window.innerWidth) {
                // Posicionar a la izquierda del final de la barra visual en su lugar
                x = visualEndPosition - tooltipWidth - 8;
            }

            if (y < 10) {
                y = 10; // Margen superior mínimo
            }
            if (window.innerHeight && y + tooltipHeight > window.innerHeight) {
                y = window.innerHeight - tooltipHeight - 10;
            }

            this.state.tooltip = {
                visible: true,
                x,
                y,
                data: tooltipData,
            };
        } else {
            // Volver al posicionamiento original si falla el cálculo
            let x = barRect.right + 8; // 8px de desplazamiento desde la barra
            let y = barRect.top - (tooltipHeight / 2) + (barRect.height / 2); // Centrar verticalmente en la barra

            // Asegurar que el tooltip no se salga de la pantalla
            if (window.innerWidth && x + tooltipWidth > window.innerWidth) {
                // Posicionar a la izquierda de la barra en su lugar
                x = barRect.left - tooltipWidth - 8;
            }

            if (y < 10) {
                y = 10; // Margen superior mínimo
            }
            if (window.innerHeight && y + tooltipHeight > window.innerHeight) {
                y = window.innerHeight - tooltipHeight - 10;
            }

            this.state.tooltip = {
                visible: true,
                x,
                y,
                data: tooltipData,
            };
        }
    }

    hideTooltip() {
        this.state.tooltip.visible = false;
        this.state.tooltip.data = {};
        
        // Limpiar resaltado de cambio de habitación
        this._clearRoomChangeHighlight();
    }

    /**
     * Resalta las barras relacionadas con un cambio de habitación
     * @param {Object} res - Reserva con cambio de habitación
     */
    _highlightRoomChangeBars(res) {
        // Limpiar resaltado previo
        this._clearRoomChangeHighlight();
        
        // Obtener ID de reserva actual
        const currentResId = res.id;
        const connectedBookingId = res.connected_booking_id || res.split_from_booking_id;
        
        // Buscar todas las reservas relacionadas con este cambio de habitación
        const relatedReservations = this._findRelatedRoomChangeReservations(currentResId, connectedBookingId);
        
        // Resaltar cada reserva relacionada
        relatedReservations.forEach((relatedRes, index) => {
            const barElement = document.querySelector(`[data-res-id="${relatedRes.id}"]`);
            
            if (barElement) {
                barElement.classList.add('room-change-highlight');
                
                // Añadir indicador visual de conexión
                this._addRoomChangeIndicator(barElement, relatedRes);
            }
        });
    }
    
    /**
     * Encuentra todas las reservas relacionadas con un cambio de habitación
     * @param {number} currentResId - ID de la reserva actual
     * @param {number} connectedBookingId - ID de la reserva conectada
     * @returns {Array} - Array de reservas relacionadas
     */
    _findRelatedRoomChangeReservations(currentResId, connectedBookingId) {
        const relatedReservations = [];
        const currentReservation = this.state.reservations.find(r => r.id === currentResId);
        
        if (!currentReservation) {
            return relatedReservations;
        }
        
        // Buscar en todas las reservas del estado
        for (const reservation of this.state.reservations) {
            // Verificar si es la reserva actual
            if (reservation.id === currentResId) {
                relatedReservations.push(reservation);
                continue;
            }
            
            // LÓGICA ESPECÍFICA: Solo buscar reservas realmente conectadas
            let isRelated = false;
            
            // 1. Verificar si está conectada por campos específicos de cambio de habitación
            if (reservation.connected_booking_id === connectedBookingId || 
                reservation.split_from_booking_id === connectedBookingId ||
                reservation.connected_booking_id === currentResId ||
                reservation.split_from_booking_id === currentResId) {
                isRelated = true;
            }
            
            // 2. Verificar si está conectada por connected_booking_id del currentReservation
            if (currentReservation.connected_booking_id && 
                reservation.booking_id === currentReservation.connected_booking_id) {
                isRelated = true;
            }
            
            // 3. Verificar si está conectada por split_from_booking_id del currentReservation
            if (currentReservation.split_from_booking_id && 
                reservation.booking_id === currentReservation.split_from_booking_id) {
                isRelated = true;
            }
            
            // 4. Verificar si ambas reservas tienen el mismo connected_booking_id
            if (currentReservation.connected_booking_id && 
                reservation.connected_booking_id === currentReservation.connected_booking_id &&
                reservation.id !== currentResId) {
                isRelated = true;
            }
            
            if (isRelated) {
                relatedReservations.push(reservation);
            }
        }
        
        return relatedReservations;
    }
    
    /**
     * Añade indicador visual de conexión a una barra
     * @param {HTMLElement} barElement - Elemento de la barra
     * @param {Object} reservation - Datos de la reserva
     */
    _addRoomChangeIndicator(barElement, reservation) {
        // Determinar tipo de cambio
        const isOrigin = reservation.is_room_change_origin || false;
        const isDestination = reservation.is_room_change_destination || false;
        
        // Añadir clase específica según el tipo
        if (isOrigin) {
            barElement.classList.add('room-change-origin');
        } else if (isDestination) {
            barElement.classList.add('room-change-destination');
        } else {
            barElement.classList.add('room-change-transition');
        }
        
        // Crear indicador de conexión
        const indicator = document.createElement('div');
        indicator.className = 'room-change-connector';
        
        // Icono según el tipo de cambio
        let icon = '🔗';
        if (isOrigin) icon = '📤'; // Salida
        else if (isDestination) icon = '📥'; // Entrada
        else icon = '🔄'; // Transición
        
        indicator.innerHTML = icon;
        indicator.title = isOrigin ? 'Origen del cambio' : isDestination ? 'Destino del cambio' : 'Transición';
        
        indicator.style.cssText = `
            position: absolute;
            top: -8px;
            right: -8px;
            background: #ff6b35;
            color: white;
            border-radius: 50%;
            width: 16px;
            height: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 10px;
            z-index: 10;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
            cursor: pointer;
            transition: all 0.2s ease;
        `;
        
        barElement.appendChild(indicator);
    }
    
    /**
     * Limpia el resaltado de cambio de habitación
     */
    _clearRoomChangeHighlight() {
        // Remover clase de resaltado de todas las barras
        const highlightedBars = document.querySelectorAll('.room-change-highlight');
        highlightedBars.forEach(bar => {
            bar.classList.remove(
                'room-change-highlight',
                'room-change-origin',
                'room-change-destination',
                'room-change-transition'
            );
        });
        
        // Remover indicadores de conexión
        const connectors = document.querySelectorAll('.room-change-connector');
        connectors.forEach(connector => {
            connector.remove();
        });
    }

    /**
     * Obtener el nombre de una habitación por su ID
     * @param {number|Array} roomId - ID de la habitación o array [id, name]
     * @returns {string} - Nombre de la habitación
     */
    _getRoomName(roomId) {
        if (!roomId) return _t('Habitación Desconocida');
        
        // Si es un array [id, name], devolver el nombre
        if (Array.isArray(roomId) && roomId.length > 1) {
            return roomId[1];
        }
        
        // Si es solo un ID, buscar en la lista de habitaciones
        const roomIdNum = Array.isArray(roomId) ? roomId[0] : roomId;
        const room = this.state.rooms.find(r => r.id === roomIdNum);
        return room ? room.name : _t('Habitación Desconocida');
    }

    /**
     * Mostrar notificación de seguimiento para cambios de habitación
     * @param {Object} res - Reserva con información de cambio de habitación
     */
    _showRoomChangeNotification(res) {
        if (!res.isRoomChangeSegment) return;

        const currentRoom = this._getRoomName(res.room_id);
        const nextRoom = res.nextSegmentRoomId ? this._getRoomName(res.nextSegmentRoomId) : null;
        const previousRoom = res.previousSegmentRoomId ? this._getRoomName(res.previousSegmentRoomId) : null;

        let notificationMessage = '';
        let notificationType = 'info';

        if (res.isFirstSegment && res.hasNextSegment) {
            notificationMessage = _t('⚠️ Atención: Esta reserva continuará en otra habitación. Próxima habitación: %s', nextRoom);
            notificationType = 'warning';
        } else if (res.isLastSegment && res.previousSegmentRoomId) {
            notificationMessage = _t('✅ Reserva completada. Habitación anterior: %s', previousRoom);
            notificationType = 'success';
        } else if (res.hasNextSegment) {
            notificationMessage = _t('🔄 Cambio de habitación en progreso. Próxima habitación: %s', nextRoom);
            notificationType = 'info';
        }

        if (notificationMessage) {
            this._displayNotification(notificationMessage, notificationType, {
                reservationId: res.id,
                customerName: res.customer_name,
                currentRoom: currentRoom,
                nextRoom: nextRoom,
                previousRoom: previousRoom
            });
        }
    }

    /**
     * Mostrar notificación en la interfaz
     * @param {string} message - Mensaje de la notificación
     * @param {string} type - Tipo de notificación (info, warning, success, error)
     * @param {Object} data - Datos adicionales de la notificación
     */
    _displayNotification(message, type = 'info', data = {}) {
        // Crear elemento de notificación
        const notification = document.createElement('div');
        notification.className = `room-change-notification notification-${type}`;
        notification.innerHTML = `
            <div class="notification-content">
                <div class="notification-message">${message}</div>
                <div class="notification-actions">
                    <button class="btn-notification-dismiss" onclick="this.parentElement.parentElement.parentElement.remove()">×</button>
                </div>
            </div>
        `;

        // Agregar estilos inline para la notificación
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10000;
            background: ${this._getNotificationColor(type)};
            color: white;
            padding: 12px 16px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            max-width: 400px;
            animation: slideInRight 0.3s ease-out;
        `;

        // Agregar al DOM
        document.body.appendChild(notification);

        // Auto-remover después de 5 segundos
        setTimeout(() => {
            if (notification.parentElement) {
                notification.style.animation = 'slideOutRight 0.3s ease-in';
                setTimeout(() => {
                    if (notification.parentElement) {
                        notification.remove();
                    }
                }, 300);
            }
        }, 5000);
    }

    /**
     * Obtener color de notificación según el tipo
     * @param {string} type - Tipo de notificación
     * @returns {string} - Color CSS
     */
    _getNotificationColor(type) {
        const colors = {
            info: 'linear-gradient(135deg, #2196F3, #1976D2)',
            warning: 'linear-gradient(135deg, #FF9800, #F57C00)',
            success: 'linear-gradient(135deg, #4CAF50, #45a049)',
            error: 'linear-gradient(135deg, #F44336, #D32F2F)'
        };
        return colors[type] || colors.info;
    }

    /**
     * Validar y preservar el estado original de las reservas
     * @param {Object} reservation - Reserva a validar
     * @returns {boolean} - True si el estado se preserva correctamente
     */
    _validateAndPreserveOriginalState(reservation) {
        if (!reservation || !reservation.isRoomChangeSegment) {
            return true;
        }

        // Validar que la reserva original mantenga su estado
        const originalState = reservation.originalState || reservation.status_bar;
        const currentState = reservation.status_bar;

        // Si es el primer segmento, debe mantener el estado original
        if (reservation.isFirstSegment && originalState && currentState !== originalState) {
            // Mostrar notificación de advertencia
            this._displayNotification(
                _t('⚠️ Advertencia: El estado original de la reserva no se ha preservado correctamente.'),
                'warning',
                {
                    reservationId: reservation.id,
                    originalState: originalState,
                    currentState: currentState
                }
            );
            
            return false;
        }

        // Validar que los segmentos intermedios mantengan consistencia
        if (!reservation.isFirstSegment && !reservation.isLastSegment) {
            const expectedState = 'checkin'; // Los segmentos intermedios deben estar en check-in
            if (currentState !== expectedState) {
                this._displayNotification(
                    _t('⚠️ Estado inconsistente en segmento de cambio de habitación.'),
                    'warning',
                    {
                        reservationId: reservation.id,
                        expectedState: expectedState,
                        currentState: currentState
                    }
                );
                
                return false;
            }
        }

        return true;
    }

    /**
     * Restaurar el estado original de una reserva si es necesario
     * @param {Object} reservation - Reserva a restaurar
     */
    _restoreOriginalState(reservation) {
        if (!reservation || !reservation.isRoomChangeSegment || !reservation.isFirstSegment) {
            return;
        }

        const originalState = reservation.originalState;
        if (originalState && reservation.status_bar !== originalState) {
            // Aquí se podría implementar la lógica para restaurar el estado
            // Por ejemplo, llamando a una función del backend
            this._displayNotification(
                _t('🔄 Restaurando estado original de la reserva...'),
                'info',
                {
                    reservationId: reservation.id,
                    restoredState: originalState
                }
            );
        }
    }

    // ===============================
    // Métodos de Lógica de Negocio
    // ===============================
    getReservationsForRoom(roomId) {
        const roomMap = this.reservationsByRoomAndDay.get(roomId);
        if (!roomMap) return [];

        const reservations = Array.from(roomMap.values());
        // Remove duplicates - important for multi-day reservations
        const uniqueReservations = reservations.filter((res, index, self) => 
            index === self.findIndex(r => r.id === res.id)
        );
        return uniqueReservations;
    }


    _getDayCellWidth() {
        try {
            if (this._cachedDayCellWidth && this._cachedDayCellWidth > 0) {
                return this._cachedDayCellWidth;
            }
            const cell = document.querySelector('.gantt_row_content .day_cell');
            if (cell) {
                this._cachedDayCellWidth = cell.getBoundingClientRect().width;
                return this._cachedDayCellWidth;
            }
        } catch (_) {}
        return 0;
    }

    // Métodos auxiliares

    extractStyleValue(style, property) {
        const regex = new RegExp(`${property}:\\s*([\\d.]+)px`);
        const match = style.match(regex);
        return match ? parseFloat(match[1]) : 0;
    }

    getCrossRoomConnectors(roomId) {
        const connectors = [];
        
        // Find all room change segments that have next segments in different rooms
        for (const [bookingId, segments] of this.roomChangeSegments) {
            for (let i = 0; i < segments.length - 1; i++) {
                const currentSegment = segments[i];
                const nextSegment = segments[i + 1];
                
                // If current segment is in this room and next segment is in a different room
                if (Utils.extractId(currentSegment.roomId) === roomId && 
                    Utils.extractId(currentSegment.roomId) !== Utils.extractId(nextSegment.roomId)) {
                    
                    // Find the target room index
                    const targetRoomIndex = this.filteredRooms.findIndex(room => 
                        Utils.extractId(room.id) === Utils.extractId(nextSegment.roomId)
                    );
                    
                    if (targetRoomIndex !== -1) {
                        connectors.push({
                            id: `connector_${bookingId}_${i}`,
                            fromRoomId: Utils.extractId(currentSegment.roomId),
                            toRoomId: Utils.extractId(nextSegment.roomId),
                            fromRoomIndex: this.filteredRooms.findIndex(room => 
                                Utils.extractId(room.id) === Utils.extractId(currentSegment.roomId)
                            ),
                            toRoomIndex: targetRoomIndex,
                            fromDate: currentSegment.endDate,
                            toDate: nextSegment.startDate,
                            bookingId: bookingId
                        });
                    }
                }
            }
        }
        
        return connectors;
    }

    getCrossRoomConnectorStyle(connector) {
        const [year, month] = this.state.selectedMonth.split('-').map(Number);
        const monthStart = DateTime.fromObject({ year, month, day: 1 });
        const monthEnd = monthStart.endOf('month');

        try {
            const fromDate = connector.fromDate;
            const toDate = connector.toDate;

            // Check if connector should be visible in current month
            if (fromDate < monthStart || toDate > monthEnd) {
                return 'display: none;';
            }

            const fromDay = fromDate.day;
            const toDay = toDate.day;
            
            // Calculate positions
            const fromRoomIndex = connector.fromRoomIndex;
            const toRoomIndex = connector.toRoomIndex;
            
            // Position connector at the end of the from segment
            const connectorPosition = fromDay;
            
            // Calculate vertical position (from room to next room)
            const fromRow = fromRoomIndex + 2; // +2 because of header row
            const toRow = toRoomIndex + 2;
            
            // Cross-room connector
            
            return `grid-column: ${connectorPosition} / ${connectorPosition + 1};
                    grid-row: ${fromRow} / ${toRow + 1};
                    background: linear-gradient(180deg, transparent 0%, #ff0000 50%, transparent 100%);
                    width: 2px;
                    position: absolute;
                    left: 50%;
                    transform: translateX(-50%);
                    z-index: 15;
                    border-radius: 1px;
                    box-shadow: 0 0 4px rgba(255, 0, 0, 0.5);`;
        } catch (error) {
            return 'display: none;';
        }
    }

    getDayDate(day) {
        const [year, month] = this.state.selectedMonth.split('-').map(Number);
        return DateTime.fromObject({ year, month, day });
    }

    getDayName(day) {
        return this.getDayDate(day).setLocale('es').toFormat('ccc');
    }

    getDayHeaderClass(day) {
        const date = this.getDayDate(day);
        const classes = [];

        if (date.hasSame(DateTime.now(), 'day')) classes.push('today');
        if (date.weekday >= 6) classes.push('weekend');
        if (date < DateTime.now().startOf('day')) classes.push('past-day');

        return classes.join(' ');
    }

    // === Helpers para layout extendido ===
    getDayHeaderClassFromDate(isoDate) {
        const date = DateTime.fromISO(isoDate);
        const classes = [];
        if (date.hasSame(DateTime.now(), 'day')) classes.push('today');
        if (date.weekday >= 6) classes.push('weekend');
        if (date < DateTime.now().startOf('day')) classes.push('past-day');
        return classes.join(' ');
    }

    isDayOccupiedExtended(roomId, dayObj) {
        // Solo marcamos ocupación para el mes actual
        if (!dayObj?.isCurrentMonth) return false;
        return this.isDayOccupied(roomId, dayObj.day);
    }

    onDayCellMouseDown(ev, roomId, dayObj) {
        if (!dayObj?.isCurrentMonth) return; // no iniciar selección fuera del mes actual
        this.cellSelector.start(ev, roomId, dayObj.day);
    }

    onDayCellMouseEnter(ev, roomId, dayObj) {
        if (!dayObj?.isCurrentMonth) return;
        this.cellSelector.updateHover(roomId, dayObj.day);
    }

    onDayCellClick(ev, roomId, dayObj) {
        if (!dayObj?.isCurrentMonth) return;
        this.onEmptyCellClick(ev, roomId, dayObj.day);
    }

getReservationDurationLabel(res) {
    try {
        // Si tenemos información de duración del API, usarla (más precisa para reservas de pocas horas)
        if (res.duration_hours !== undefined && res.duration_hours !== null) {
            const hours = res.duration_hours;
            if (hours < 1) {
                // Menos de 1 hora: mostrar en minutos
                const minutes = Math.round(hours * 60);
                return `${minutes}m`;
            } else if (hours < 24) {
                // Menos de 24 horas: mostrar en horas
                return `${Math.round(hours * 10) / 10}h`; // 1 decimal
            } else {
                // 24 horas o más: mostrar en días
                const days = hours / 24;
                return `${Math.round(days * 10) / 10}d`; // 1 decimal
            }
        }
        
        // Fallback: calcular desde fechas
        const resStart = DateTime.fromISO(res.date_start);
        const resEnd = DateTime.fromISO(res.date_end);

        if (!resStart.isValid || !resEnd.isValid) return '0d';

        // Calcular duración en horas para mayor precisión
        const durationHours = resEnd.diff(resStart, 'hours').hours;
        
        if (durationHours < 1) {
            const minutes = Math.round(durationHours * 60);
            return `${minutes}m`;
        } else if (durationHours < 24) {
            return `${Math.round(durationHours * 10) / 10}h`;
        } else {
            const days = durationHours / 24;
            return `${Math.round(days * 10) / 10}d`;
        }
    } catch (error) {
        return '0d';
    }
}

isDayOccupied(roomId, day) {
    // Usar el mapa de disponibilidad en lugar del mapa de visualización
    const availabilityMap = this.availabilityByRoomAndDay.get(roomId);
    if (!availabilityMap) return false;

    const availabilityInfo = availabilityMap.get(day);
    if (!availabilityInfo) return false;
    
    const res = availabilityInfo.reservation;
    
    // Si la reserva está cancelada o en room_ready, el día no está ocupado
    if (res.state === 'cancelled' || res.state === 'room_ready') {
        return false;
    }
    
    // Si el día está completamente ocupado, está ocupado
    if (availabilityInfo.type === 'full_day') {
        return true;
    }
    
    // Si es medio día, considerar ocupado solo si es necesario para evitar solapamientos
    // Para reservas de medio día, el día está parcialmente ocupado
    // Por ahora, consideramos que medio día también bloquea el día completo para evitar conflictos
    // Esto se puede ajustar según las necesidades del negocio
    return true;
}

/**
 * Determina si un día está completamente ocupado o solo parcialmente
 * @param {number} roomId - ID de la habitación
 * @param {number} day - Día del mes
 * @returns {Object|null} - {type: 'full_day'|'half_day_morning'|'half_day_afternoon', reservation: res} o null
 */
getDayAvailability(roomId, day) {
    const availabilityMap = this.availabilityByRoomAndDay.get(roomId);
    if (!availabilityMap) return null;
    
    const availabilityInfo = availabilityMap.get(day);
    if (!availabilityInfo) return null;
    
    const res = availabilityInfo.reservation;
    
    // Si la reserva está cancelada o en room_ready, el día está disponible
    if (res.state === 'cancelled' || res.state === 'room_ready') {
        return null;
    }
    
    return availabilityInfo;
}

isRangeAvailable(roomId, startDay, endDay) {
    for (let day = startDay; day <= endDay; day++) {
        const availabilityInfo = this.getDayAvailability(roomId, day);
        
        // Si hay información de disponibilidad y el día está completamente ocupado, no está disponible
        if (availabilityInfo && availabilityInfo.type === 'full_day') {
            return false;
        }
        
        // Si es medio día, verificar si hay conflicto
        // Si es medio día mañana (checkout antes de las 12 PM), la tarde está disponible
        // Si es medio día tarde (checkin después de las 12 PM), la mañana está disponible
        // Por ahora, consideramos que medio día también bloquea para evitar conflictos
        // Esto se puede ajustar según las necesidades del negocio
        if (availabilityInfo) {
            // Si el día está parcialmente ocupado, consideramos que no está disponible
            // para evitar solapamientos. Esto se puede mejorar en el futuro para permitir
            // reservas en la parte disponible del día
            return false;
        }
    }
    return true;
}

hasCleaningReservationInRange(roomId, startDay, endDay) {
    const roomMap = this.reservationsByRoomAndDay.get(roomId);
    if (!roomMap) return false;

    for (let day = startDay; day <= endDay; day++) {
        const res = roomMap.get(day);
        if (res && res.state === 'cleaning_needed') {
            return true;
        }
    }
    return false;
}

async createNewReservation(roomId, startDay, endDay) {
    // Validar que el rango esté disponible antes de crear la reserva
    const selectionStart = Math.min(startDay, endDay);
    const selectionEnd = Math.max(startDay, endDay);

    // Debug: selección original

    // Verificar si hay una reserva reutilizable en estado 'room_ready'
    const reusableReservation = this.findReusableReservation(roomId, selectionStart, selectionEnd);

    if (reusableReservation) {
        // Reutilizar la reserva existente
        await this.reuseExistingReservation(reusableReservation, startDay, endDay);
        return;
    }

    if (!this.isRangeAvailable(roomId, selectionStart, selectionEnd)) {
        // Verificar si hay reservas en estado 'cleaning_needed' en el rango
        const hasCleaningReservation = this.hasCleaningReservationInRange(roomId, selectionStart, selectionEnd);

        if (hasCleaningReservation) {
            this.notification.add(
                _t('No se puede hacer la reserva: la habitación está en proceso de limpieza. Complete la limpieza primero.'),
                {
                    type: 'warning',
                    title: _t('Habitación en Limpieza')
                }
            );
        } else {
            this.notification.add(
                _t('No se puede hacer la reserva: la habitación está ocupada en el rango seleccionado.'),
                {
                    type: 'warning',
                    title: _t('Reserva no válida')
                }
            );
        }
        return;
    }

    // Usar la hora actual del sistema para check-in y check-out
    const now = DateTime.now();
    const checkInDate = this.getDayDate(selectionStart).set({
        hour: now.hour,
        minute: now.minute,
        second: now.second,
        millisecond: 0
    });

    // Checkout INCLUSIVO: usar el último día seleccionado como checkout
    const checkOutDate = this.getDayDate(selectionEnd).set({
        hour: now.hour,
        minute: now.minute,
        second: now.second,
        millisecond: 0
    });

    // Debug: fechas calculadas

    const room = this.state.rooms.find(r => r.id === roomId);
    if (!room) {
        this.notification.add(_t('Habitación no encontrada'), { type: 'warning' });
        return;
    }

    // Extraer ID del hotel de forma segura (igual que room_panel)

    let hotelId = null;

    if (room.hotel_id) {
        if (Array.isArray(room.hotel_id) && room.hotel_id.length >= 2) {
            // Formato [id, name] de Odoo
            hotelId = room.hotel_id[0];
        } else if (typeof room.hotel_id === 'number' || typeof room.hotel_id === 'string') {
            // Formato directo (ID)
            hotelId = parseInt(room.hotel_id);
        }
    }

    // Si no hay hotel_id en la habitación, usar el hotel seleccionado
    if (!hotelId && this.state.selectedHotel) {
        hotelId = this.state.selectedHotel;
    }

    // Obtener ID del usuario actual de forma segura
    const userId = Utils.extractId(this.user?.uid || this.user?.userId || this.user?.id);

    // Obtener el cliente por defecto
    let defaultPartnerId = null;
    try {
        const response = await this.rpc('/hotel/get_default_partner', {});
        if (response.success && response.default_partner_id) {
            defaultPartnerId = response.default_partner_id;
        }
    } catch (error) {
        // No se pudo obtener cliente por defecto
    }

    // Obtener el product_id correspondiente al template_id
    let productId = null;
    try {
        const productResponse = await this.rpc('/hotel/get_product_from_template', {
            template_id: roomId
        });

        if (productResponse.success && productResponse.product_id) {
            productId = productResponse.product_id;
        } else {
            this.notification.add(
                _t('Error: %s', productResponse.error || 'No se pudo obtener la información de la habitación'),
                { type: 'danger' }
            );
            return;
        }
    } catch (error) {
        this.notification.add(
            _t('Error al obtener información de la habitación'),
            { type: 'danger' }
        );
        return;
    }

    // Crear contexto TEMPORAL que NO cree registros automáticamente
    // Usar 'default_' solo para campos que no creen registros
    const context = {
        // NO usar default_* para campos que creen registros automáticamente
        // Solo pasar información temporal para pre-llenar
        'temp_check_in': checkInDate.toFormat('yyyy-MM-dd HH:mm:ss'),
        'temp_check_out': checkOutDate.toFormat('yyyy-MM-dd HH:mm:ss'),
        'temp_hotel_id': hotelId,
        'temp_user_id': userId,
        'temp_room_id': roomId,
        'temp_partner_id': defaultPartnerId,
    };


    // Abrir el modal de "Nueva Reserva" con campos pre-llenados
    this.action.doAction({
        name: _t('Nueva Reserva'),
        type: 'ir.actions.act_window',
        res_model: 'hotel.booking',
        views: [[false, 'form']],
        target: 'new',
        context: {
            // Campos pre-llenados para la nueva reserva
            'default_check_in': checkInDate.toFormat('yyyy-MM-dd HH:mm:ss'),
            'default_check_out': checkOutDate.toFormat('yyyy-MM-dd HH:mm:ss'),
            'default_hotel_id': hotelId,
            'default_user_id': userId,
            'default_partner_id': defaultPartnerId,
            // Pre-llenar la habitación seleccionada con el product_id correcto
            'default_product_id': productId,
        }
    }, {
        onClose: () => this._loadData(),
    });
}

_getStatusDefinition(state) {
    return STATUS_DEFINITIONS[state] || DEFAULT_STATUS;
}

/**
 * Buscar una reserva reutilizable en estado 'room_ready'
 */
findReusableReservation(roomId, startDay, endDay) {
    const startDate = this.getDayDate(startDay).toISODate();
    // Checkout INCLUSIVO para comparación: usar el último día seleccionado
    const endDate = this.getDayDate(endDay).toISODate();

    return this.state.reservations.find(reservation => {
        const reservationRoomId = Utils.extractId(reservation.room_id);
        return reservationRoomId === roomId &&
            reservation.state === 'room_ready' &&
            reservation.date_start <= startDate &&
            reservation.date_end >= endDate;
    });
}

/**
 * Reutilizar una reserva existente en estado 'room_ready'
 */
async reuseExistingReservation(reusableReservation, startDay, endDay) {
    try {
        // Confirmar con el usuario
        const confirmed = await this.dialog.confirm(
            _t('Crear Nueva Reserva'),
            _t('Se encontró una reserva en estado Habitación Lista para esta habitación. ¿Desea crear una nueva reserva basada en la existente?')
        );

        if (!confirmed) {
            return;
        }

        // Llamar al método del backend para reutilizar la reserva
        const result = await this.rpc('/hotel/reuse_room_ready_booking', {
            booking_id: reusableReservation.booking_id
        });

        if (result.success) {
            this.notification.add(
                _t('Nueva reserva creada exitosamente'),
                { type: 'success' }
            );

            // Recargar datos
            await this._loadData();

            // Abrir la nueva reserva creada para edición
            this.action.doAction({
                name: _t('New Reservation'),
                type: 'ir.actions.act_window',
                res_model: 'hotel.booking',
                res_id: result.new_booking_id,
                views: [[false, 'form']],
                target: 'new',
            });
        } else {
            this.notification.add(
                result.error || _t('Error al reutilizar la reserva'),
                { type: 'danger' }
            );
        }
    } catch (error) {
        this.notification.add(
            _t('Error al reutilizar la reserva'),
            { type: 'danger' }
        );
    }
}



isCheckoutSoon(res) {
    if ((res.state || res.status_bar) === 'checkout') return false;

    try {
        const checkoutDate = DateTime.fromISO(res.date_end);
        const today = DateTime.now().startOf('day');

        return checkoutDate.hasSame(today, 'day') ||
            checkoutDate.diff(today, 'days').days === 1;
    } catch (error) {
        return false;
    }
}

// [Removed duplicate, corrupted block of state transition methods]

    /**
     * Cambiar el estado de una reserva con validación
     * @param {number} reservationId - ID de la reserva
     * @param {string} newState - Nuevo estado
     */
    async changeReservationState(reservationId, newState) {
        try {
            const reservation = this.state.reservations.find(r => r.id === reservationId);
            if (!reservation) {
                this.notification.add(_t('Reserva no encontrada'), { type: 'warning' });
                return;
            }

            const currentState = reservation.state || reservation.status_bar;

            // Validar la transición
            if (!isValidStateTransition(currentState, newState)) {
                const availableTransitions = getAvailableTransitions(currentState);
                this.notification.add(
                    _t('Transición de estado no válida. Desde %s solo puedes cambiar a: %s')
                        .replace('%s', currentState)
                        .replace('%s', availableTransitions.join(', ')),
                    { type: 'warning', title: _t('Transición no válida') }
                );
                return;
            }

            // VALIDACIÓN DE FECHAS PARA CHECK-IN
            if (newState === 'checkin') {
                const today = DateTime.now().startOf('day');
                const checkInDate = DateTime.fromISO(reservation.date_start);
                
                if (checkInDate > today) {
                    this.notification.add(
                        _t('No se puede realizar check-in antes de la fecha programada. Fecha de check-in: %s')
                            .replace('%s', checkInDate.toFormat('dd/MM/yyyy')),
                        { type: 'error', title: _t('Check-in no permitido') }
                    );
                    return;
                }
            }

            // Llamar al método del servidor según el estado
            let methodName = '';
            switch (newState) {
                case 'checkin':
                    methodName = 'action_check_in';
                    break;
                case 'checkout':
                    methodName = 'action_check_out';
                    break;
                case 'cleaning_needed':
                    methodName = 'action_mark_cleaning_needed';
                    break;
                case 'room_ready':
                    methodName = 'action_mark_room_ready';
                    break;
                case 'cancelled':
                    methodName = 'action_cancel_booking';
                    break;
                case 'no_show':
                    methodName = 'action_mark_no_show';
                    break;
                default:
                    // Para otros estados, usar el método genérico
                    methodName = '_change_state';
                    break;
            }
            
            await this.orm.call(
                'hotel.booking',
                methodName,
                [reservationId]
            );

            // Recargar datos
            await this._loadData();

            this.notification.add(
                _t('Estado de la reserva cambiado exitosamente'),
                { type: 'success' }
            );

        } catch (error) {
            this.notification.add(
                _t('Error al cambiar el estado de la reserva'),
                { type: 'danger' }
            );
        }
    }

    /**
     * Obtener las transiciones disponibles para una reserva
     * @param {Object} reservation - Objeto de reserva
     * @returns {Array} - Array de estados permitidos
     */
    getAvailableTransitionsForReservation(reservation) {
        const currentState = reservation.state || reservation.status_bar;
        return getAvailableTransitions(currentState);
    }

    /**
     * Verificar si una transición está permitida
     * @param {Object} reservation - Objeto de reserva
     * @param {string} newState - Nuevo estado
     * @returns {boolean} - True si la transición es válida
     */
    isTransitionAllowed(reservation, newState) {
        const currentState = reservation.state || reservation.status_bar;
        return isValidStateTransition(currentState, newState);
    }

    /**
     * Obtener el siguiente estado lógico para una reserva
     * @param {Object} reservation - Objeto de reserva
     * @returns {string|null} - Siguiente estado o null
     */
    getNextLogicalStateForReservation(reservation) {
        const currentState = reservation.state || reservation.status_bar;
        return getNextLogicalState(currentState);
    }

    /**
     * Aplicar el siguiente estado lógico a una reserva
     * @param {number} reservationId - ID de la reserva
     */
    async applyNextLogicalState(reservationId) {
        const reservation = this.state.reservations.find(r => r.id === reservationId);
        if (!reservation) {
            this.notification.add(_t('Reserva no encontrada'), { type: 'warning' });
            return;
        }

        const nextState = this.getNextLogicalStateForReservation(reservation);
        if (nextState) {
            await this.changeReservationState(reservationId, nextState);
        } else {
            this.notification.add(
                _t('No hay ningún siguiente estado lógico disponible para esta reserva.'),
                { type: 'warning' }
            );
        }
    }


    /**
     * Confirmar reserva
     */
    async confirmReservation(reservationId) {
        await this.changeReservationState(reservationId, 'confirmed');
    }

    /**
     * Asignar habitación
     */
    async assignRoom(reservationId) {
        await this.changeReservationState(reservationId, 'room_assigned');
    }

    /**
     * Realizar check-in
     */
    async checkInReservation(reservationId) {
        await this.changeReservationState(reservationId, 'checkin');
    }

    /**
     * Realizar check-out
     */
    async checkOutReservation(reservationId) {
        await this.changeReservationState(reservationId, 'checkout');
    }

    /**
     * Marcar para limpieza
     */
    async markForCleaning(reservationId) {
        await this.changeReservationState(reservationId, 'cleaning_needed');
    }

    /**
     * Marcar habitación como lista
     */
    async markRoomReady(reservationId) {
        await this.changeReservationState(reservationId, 'room_ready');
    }

    /**
     * Cancelar reserva
     */
    async cancelReservation(reservationId) {
        await this.changeReservationState(reservationId, 'cancelled');
    }

    /**
     * Marcar como no show
     */
    async markNoShow(reservationId) {
        await this.changeReservationState(reservationId, 'no_show');
    }

    /**
     * Marcar como pendiente
     */
    async markPending(reservationId) {
        await this.changeReservationState(reservationId, 'pending');
    }

    onRowMouseEnter(roomId) {
        this.state.hoveredRowId = roomId;
    }

    onRowMouseLeave(roomId) {
        if (this.state.hoveredRowId === roomId) {
            this.state.hoveredRowId = null;
        }
    }

    // ===============================
    // Exportaciones de Utilidades del Template
    // ===============================
    // Hacer disponibles las funciones de utilidad al template
    Utils = Utils;
    _t = _t;


}

registry.category("actions").add("hotel.reservation_gantt_action", ReservationGantt);
