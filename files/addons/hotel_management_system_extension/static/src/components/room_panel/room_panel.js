/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useState, onWillStart, onMounted, onWillUnmount, Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";


// =============================================================================
// DEFINICIONES DE ESTADO Y UTILIDADES - IDÉNTICAS AL GANTT
// =============================================================================

const STATUS_DEFINITIONS = Object.freeze({
    // Estados principales - IDÉNTICOS AL MODELO PADRE
    initial: {
        key: 'initial',
        label: _t('BORRADOR'),
        description: _t('Reserva en estado borrador, no activa.'),
        isBlocking: false,
        color: '#A9A9A9',
        legendClass: 'draft',
        emoji: '⚫'
    },
    confirm: {
        key: 'confirm',
        label: _t('CONFIRMADA'),
        description: _t('Reserva confirmada y garantizada.'),
        isBlocking: true,
        color: '#00BFA5',
        legendClass: 'confirmed',
        emoji: '🟢'
    },
    allot: {
        key: 'allot',
        label: _t('HABITACIÓN ASIGNADA'),
        description: _t('Habitación asignada al huésped.'),
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
    cancel: {
        key: 'cancel',
        label: _t('CANCELADA'),
        description: _t('Reserva cancelada.'),
        isBlocking: false,
        color: '#D32F2F',
        legendClass: 'cancelled',
        emoji: '🔴'
    },

    // Estados adicionales para compatibilidad con el panel
    room_ready: {
        key: 'room_ready',
        label: _t('HABITACION LISTA'),
        description: _t('Habitación limpia y lista para nuevos huéspedes.'),
        isBlocking: false,
        color: '#4CAF50',
        legendClass: 'room_ready',
        emoji: '🟢'
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
    check_in: {
        key: 'check_in',
        label: _t('CHECK-IN'),
        description: _t('Huésped en habitación (estado legacy).'),
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
    }
});

// =============================================================================
// COMPONENTE RoomPanel - FUNCIONALIDAD COMPLETA RESTAURADA (SIN LUXON)
// =============================================================================

export class RoomPanel extends Component {
    static template = "room_panel";

    static props = {
        action: { type: Object, optional: true },
        actionId: { type: [String, Number], optional: true },
        breadcrumbs: { type: Object, optional: true },
        className: { type: String, optional: true },
        globalState: { type: Object, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.rpc = useService("rpc");
        this.notification = useService("notification");
        this.action = useService("action");
        this.user = useService("user");
        this.dialog = useService("dialog");
        this._t = _t;

        this.STATUS_DEFINITIONS = STATUS_DEFINITIONS;

        this.state = useState({
            rooms: [],
            reservations: [],
            reservationsByRoom: {},
            stats: {
                room_ready: 0,
                checkin: 0,
                cleaning_needed: 0,
                revenue: 0
            },
            filterData: {
                hotels: [],
                room_types: [],
                available_states: []
            },
            isLoading: true,
            error: null,
            product_tag_ids: [],
            expandedImages: {},
            filters: {
                hotel_id: "",
                room_type_id: "",
                status: "",
            },
        });

        this.filterTimeout = null;
        this.refreshInterval = null;

        onWillStart(async () => {
            await this.loadInitialData();
        });

        onMounted(() => {
            this.setupAutoRefresh();
        });

        onWillUnmount(() => {
            this.cleanup();
        });
    }

    //==========================================================================
    // Computed Properties
    //==========================================================================

    get filteredRooms() {
        const { hotel_id, room_type_id, status } = this.state.filters;

        return this.state.rooms.filter(room => {
            const hotelMatch = !hotel_id || (room.hotel_id && room.hotel_id[0] == hotel_id);
            const roomTypeMatch = !room_type_id || (room.categ_id && room.categ_id[0] == room_type_id);

            let statusMatch = true;
            if (status) {
                if (room.status === status) {
                    statusMatch = true;
                } else {
                    const currentReservation = room.current_reservation;
                    if (currentReservation && currentReservation.status === status) {
                        statusMatch = true;
                    } else {
                        statusMatch = false;
                    }
                }
            }

            return hotelMatch && roomTypeMatch && statusMatch;
        });
    }

    //==========================================================================
    // Lifecycle and Data Fetching
    //==========================================================================

    async loadInitialData() {
        this.state.isLoading = true;
        this.state.error = null;

        try {
            await this.loadFilterData();
            await this.fetchData();
        } catch (error) {
            console.error('Error loading room panel data:', error);

            let errorMessage = 'Error desconocido';
            if (error.message) {
                if (error.message.includes('transacción abortada')) {
                    errorMessage = 'Error de base de datos. Por favor, recarga la página.';
                } else if (error.message.data?.message) {
                    errorMessage = error.message.data.message;
                } else {
                    errorMessage = error.message;
                }
            }

            this.state.error = `Error al cargar los datos: ${errorMessage}`;
            this.notification.add(this.state.error, { type: 'danger' });

            try {
                this.state.rooms = [];
                this.state.reservations = [];
                this.state.reservationsByRoom = {};
            } catch (fallbackError) {
                console.error('Error en respaldo:', fallbackError);
            }
        } finally {
            this.state.isLoading = false;
        }
    }

    async loadFilterData() {
        try {
            const data = await this.rpc("/hotel/room_panel_filters", {});
            if (data && data.success) {
                this.state.filterData = {
                    hotels: data.hotels || [],
                    room_types: data.room_types || [],
                    available_states: data.available_states || [],
                };
            } else {
                throw new Error(data?.error || 'Error desconocido al cargar filtros');
            }
        } catch (error) {
            console.error('Error fetching filter data:', error);
            throw error;
        }
    }

    async fetchData() {
        try {
            this.state.rooms = [];
            this.state.reservations = [];

            const result = await this.rpc('/hotel/room_panel_data', {
                hotel_id: this.state.filters.hotel_id || false,
            });

            if (result && result.success) {
                this.state.rooms = result.rooms || [];
                this.state.reservations = result.reservations || [];

                if (result.warning) {
                    this.notification.add(result.warning, { type: 'warning' });
                }

                this._processReservations();
            } else {
                const errorMsg = result?.error || this._t('No se pudieron cargar los datos de las habitaciones.');
                throw new Error(errorMsg);
            }
        } catch (error) {
            console.error('Error fetching data:', error);
            this.state.rooms = [];
            this.state.reservations = [];
            this.state.reservationsByRoom = {};
            throw error;
        }
    }

    _processReservations() {
        const reservationsByRoom = {};
        this.state.reservations.forEach(reservation => {
            const roomId = reservation.room_id[0];
            if (!reservationsByRoom[roomId]) {
                reservationsByRoom[roomId] = reservation;
            }
        });
        this.state.reservationsByRoom = reservationsByRoom;
        this._updateStats();
    }

    _updateStats() {
        const stats = {
            room_ready: 0,
            checkin: 0,
            cleaning_needed: 0,
            revenue: 0
        };

        // CÁLCULO DE INGRESOS: Solo habitaciones actualmente ocupadas (en check-in)
        let dailyRevenue = 0;


        this.state.rooms.forEach(room => {
            const status = room.status || 'available';

            // Contar estados de habitación
            switch (status) {
                // Estados disponibles
                case 'available':
                case 'room_ready':
                    stats.room_ready++;
                    break;

                // Estados ocupados - SOLO ESTOS GENERAN INGRESOS
                case 'occupied':
                case 'checkin':
                case 'check_in':
                case 'allot':
                    stats.checkin++;
                    // Solo contar ingresos de habitaciones actualmente ocupadas
                    const roomRevenue = room.list_price || 0;
                    dailyRevenue += roomRevenue;
                    break;

                // Estados de limpieza
                case 'cleaning':
                case 'cleaning_needed':
                case 'checkout':
                case 'checkout_pending':
                    stats.cleaning_needed++;
                    break;

                // Estados reservados (confirmados pero no ocupados aún)
                case 'reserved':
                case 'confirmed':
                    // No contar como ocupados ni generar ingresos hasta el check-in
                    break;

                // Estados terminales
                case 'initial':
                case 'cancelled':
                case 'no_show':
                    break;

                default:
                    // Estados desconocidos se consideran disponibles
                    stats.room_ready++;
                    break;
            }
        });

        // Asignar los ingresos calculados
        stats.revenue = dailyRevenue;
        this.state.stats = stats;
    }

    async refreshData(showNotification = true) {
        this.state.isLoading = true;
        await this.loadInitialData();
        if (showNotification && !this.state.error) {
            this.notification.add(_t('Datos actualizados correctamente'), { type: 'success' });
        }
        this.state.isLoading = false;
    }

    //==========================================================================
    // Event Handlers
    //==========================================================================

    onFilterChange() {
        clearTimeout(this.filterTimeout);
        this.filterTimeout = setTimeout(() => {
            this.refreshData(false);
        }, 300);
    }

    clearFilters() {
        this.state.filters = {
            hotel_id: '',
            room_type_id: '',
            status: ''
        };
        this.refreshData(false);
    }

    setStatusFilter(statusKey) {
        if (this.state.filters.status === statusKey) {
            this.state.filters.status = "";
        } else {
            this.state.filters.status = statusKey;
        }
        this.refreshData(false);
    }

    toggleImageExpansion(roomId) {
        if (!roomId) {
            return;
        }

        const newExpandedImages = { ...this.state.expandedImages };
        newExpandedImages[roomId] = !newExpandedImages[roomId];
        this.state.expandedImages = newExpandedImages;

    }

    isImageExpanded(roomId) {
        if (!roomId) {
            return false;
        }
        return Boolean(this.state.expandedImages[roomId]);
    }

    openReservationModal(room) {

        let modalTitle;
        if (room.status === 'available' || room.status === 'room_ready') {
            modalTitle = this._t('Nueva Reserva - %s', room.name || 'Habitación');
        } else {
            modalTitle = this._t('Detalles y Reserva - %s', room.name || 'Habitación');
        }

        if (room.status === 'room_ready') {
            this._createNewReservationWithDefaults(room, modalTitle);
            return;
        }

        if (room.current_reservation && room.current_reservation.id && room.status !== 'room_ready') {
            this.action.doAction({
                name: this._t('Reserva: %s', room.current_reservation.guest_name || 'Cliente'),
                type: 'ir.actions.act_window',
                res_model: 'hotel.booking',
                res_id: room.current_reservation.id,
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
                onClose: () => this.fetchData(),
            });
            return;
        }

        this._createNewReservationWithDefaults(room, modalTitle);
    }

    async _createNewReservationWithDefaults(room, modalTitle) {
        try {
            let defaultPartnerId = null;
            try {
                const response = await this.rpc('/hotel/get_default_partner', {});
                if (response.success && response.default_partner_id) {
                    defaultPartnerId = response.default_partner_id;
                }
            } catch (error) {
                console.warn('No se pudo obtener cliente por defecto:', error);
            }

            let productId = null;
            try {
                const productResponse = await this.rpc('/hotel/get_product_from_template', {
                    template_id: room.id
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
                console.error('Error en llamada RPC para obtener producto:', error);
                this.notification.add(
                    _t('Error al obtener información de la habitación'),
                    { type: 'danger' }
                );
                return;
            }

            // Calcular fechas automáticamente respetando la zona horaria local
            const now = new Date();
            const formatLocalDateTime = (date) => {
                const pad = (value) => String(value).padStart(2, '0');
                return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
                    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
            };

            const checkInDate = formatLocalDateTime(now);
            // Check-out: mismo instante (mismo día) para evitar desfase
            const checkOutDateStr = formatLocalDateTime(new Date(now.getTime()));

            // Crear contexto con campos auto-completados
            const context = {
                'default_product_id': productId,
                'default_hotel_id': room.hotel_id ? room.hotel_id[0] : null,
                'default_check_in': checkInDate,
                'default_check_out': checkOutDateStr,
                'default_partner_id': defaultPartnerId,
                'default_status_bar': 'initial',
                'room_status': room.status || 'room_ready',
                'room_capacity': ((room.max_adult || 0) + (room.max_child || 0)),
            };


            this.action.doAction({
                name: modalTitle,
                type: 'ir.actions.act_window',
                res_model: 'hotel.booking',
                views: [[false, 'form']],
                target: 'new',
                context: context,
            }, {
                onClose: () => this.fetchData(),
            });
        } catch (error) {
            console.error('Error creando nueva reserva:', error);
            this.notification.add(
                this._t('Error al crear nueva reserva: %s', error.message || error),
                { type: 'danger' }
            );
        }
    }

    viewReservations(room) {
        this.action.doAction({
            name: this._t('Reservas - %s', room.name || 'Habitación'),
            type: 'ir.actions.act_window',
            res_model: 'hotel.booking',
            views: [[false, 'list'], [false, 'form']],
            target: 'current',
            domain: [['room_id', '=', room.id]],
            context: {
                default_room_id: room.id,
                default_hotel_id: room.hotel_id && Array.isArray(room.hotel_id) ? room.hotel_id[0] : room.hotel_id,
            },
        });
    }

    //==========================================================================
    // Utilities & Helpers
    //==========================================================================

    setupAutoRefresh() {
        this.refreshInterval = setInterval(() => {
            this.refreshData(false);
        }, 30000);
    }

    cleanup() {
        if (this.refreshInterval) clearInterval(this.refreshInterval);
        if (this.filterTimeout) clearTimeout(this.filterTimeout);
    }

    getHotels() { return this.state.filterData?.hotels || []; }
    getRoomTypes() { return this.state.filterData?.room_types || []; }

    getStatusLabel(status) {
        const statusDef = STATUS_DEFINITIONS[status];
        if (statusDef) {
            return statusDef.label;
        }
        return status || this._t('Desconocido');
    }

    getStatusVariant(status) {
        const statusDef = STATUS_DEFINITIONS[status];
        if (statusDef) {
            return statusDef.legendClass || 'light';
        }
        return 'light';
    }

    getStatusColor(status) {
        const statusDef = STATUS_DEFINITIONS[status];
        if (statusDef) {
            return statusDef.color;
        }
        return '#6B7280';
    }

    getStatusEmoji(status) {
        const statusDef = STATUS_DEFINITIONS[status];
        if (statusDef) {
            return statusDef.emoji;
        }
        return '❓';
    }

    formatPrice(price) {
        return new Intl.NumberFormat(this.user.lang.replace('_', '-'), {
            style: 'currency',
            currency: 'PEN'
        }).format(price);
    }

    formatDate(dateString) {
        if (!dateString) return _t("N/A");
        const safeDateString = dateString.slice(0, 10).replace(/-/g, '/');
        const date = new Date(safeDateString);
        if (isNaN(date.getTime())) return _t("Fecha inválida");
        return date.toLocaleDateString(this.user.lang.replace('_', '-'), { month: "short", day: "numeric" });
    }

    formatDateTime(dateTimeString) {
        if (!dateTimeString) return _t("N/A");
        try {
            const date = new Date(dateTimeString);
            if (isNaN(date.getTime())) return _t("Fecha inválida");

            const options = {
                month: "short",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit",
                hour12: false
            };

            return date.toLocaleDateString(this.user.lang.replace('_', '-'), options);
        } catch (error) {
            return _t("Fecha inválida");
        }
    }

    getTimeAgo(dateString) {
        if (!dateString) return this._t('Nunca');
        const date = new Date(dateString.includes(' ') ? dateString : dateString + 'Z');
        const diffMins = Math.floor((new Date() - date) / 60000);
        if (diffMins < 1) return this._t('Ahora');
        if (diffMins < 60) return `${diffMins}m`;
        const diffHours = Math.floor(diffMins / 60);
        if (diffHours < 24) return `${diffHours}h`;
        return `${Math.floor(diffHours / 24)}d`;
    }
}


try {
    registry.category("actions").add("hotel_management_system_extension.room_panel_action", RoomPanel);

    // Verificar que se registró correctamente
    const registeredAction = registry.category("actions").get("hotel_management_system_extension.room_panel_action");

} catch (error) {
    console.error('DEBUG - Error registrando room_panel_action:', error);
    console.error('DEBUG - Stack trace:', error.stack);
}
