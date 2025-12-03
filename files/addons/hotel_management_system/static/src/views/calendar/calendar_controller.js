/** @odoo-module **/

import { CalendarController } from "@web/views/calendar/calendar_controller";
import { CalendarCommonRenderer } from "@web/views/calendar/calendar_common/calendar_common_renderer";
import { CalendarModel } from '@web/views/calendar/calendar_model';
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { CalendarRenderer } from "@web/views/calendar/calendar_renderer";
import { onMounted, onPatched } from "@odoo/owl";

patch(CalendarCommonRenderer.prototype, {
    onEventRender(info) {
        if (this.env.searchModel.resModel === "hotel.booking") {
            // Update the "title" by concatenating the partner_id and the original display_name
            let eventId = info.event.id;
            this.props.model.records[eventId].title = this.props.model.records[eventId].rawRecord.partner_id[1] + ` (${this.props.model.records[eventId].rawRecord.display_name})`;
            this.props.model.records[eventId].model = this.env.searchModel.resModel;
        }
        return super.onEventRender(...arguments);
    },
});

// We are patching CalendarModel to get required data before render
patch(CalendarModel.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
    },
    /**
    * @override
    */
    // async load(params = {}) {
    //     this.meta.productData = await this.fetchData();
    //     return super.load(...arguments);
    // },
    async load(params = {}) {
        if (this.resModel === "hotel.booking") {
            document.querySelector('.o_web_client').addEventListener('click', function(event) {
                if (document.getElementById('roomInformation') && window.innerWidth < 769) {
                    const roomCustomUI = document.querySelector('.roomCustomUI');
                    if (roomCustomUI && roomCustomUI.contains(event.target)) return;
                    document.getElementById('roomInformation').style.display = 'none';
                }
            });
            
            
            this.meta.productData = await this.fetchData();
        }
        return super.load(...arguments);
    },

    /**
     * calling in setup
     * @return return data that will use to render view for first time
     */
    // fetchData() {
    //     var self = this;
    //     return self.orm.call('hotel.booking', 'fetch_data_for_dashboard', [], {})
    // },
    async fetchData() {
        var self = this;
        return await self.orm.call('hotel.booking', 'fetch_data_for_dashboard', [], {'scale': self.scale})
    },
    fetchRecords(data) {
        const { fieldNames, resModel } = this.meta;
        let domain = this.computeDomain(data);
        if(this.resModel === "hotel.booking" && this.room_id) domain.push(['id', 'in', this.room_book_ids]);
        return this.orm.searchRead(resModel, domain, [
            ...new Set([...fieldNames, ...Object.keys(this.meta.activeFields)]),
        ]);
    },
    normalizeRecord(rawRecord) {
        let res = super.normalizeRecord(...arguments);
        if(this.resModel === "hotel.booking"){
            res['title'] = `${res.title} ${rawRecord.partner_id[1]}`;
        }
        return res;
    }
});

patch(CalendarController.prototype, {
    async setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");

        // onWillStart(async () => {
        //     await loadJS("/web/static/lib/jquery/jquery.js");
        // });
        await super.setup(...arguments);
    },


    /**
     * Open view on based click.
     *
     * @param {ev} x passing current clicked event.
     * @output open booking view or product variant view.
     */

    openViewonClick(ev) {
        if ($(ev.target).hasClass('total_available')) {
            let roomTypeDomain = [["is_room_type", "=", true], ['active', '=', true]];
            let group = [];

            // @class {total_available_room} adding a domain to filter unbooked room.
            // @class {total_booked} adding a domain to filter booked room.

            if ($(ev.target).hasClass('total_available_room')) {
                roomTypeDomain.push(["id", "not in", this.model.meta.productData.booked_room_ids]);
                if (this.model.meta.productData.available_rooms) group.push('product_tmpl_id');
            }
            else if ($(ev.target).hasClass('total_booked')) {
                roomTypeDomain.push(["id", "in", this.model.meta.productData.booked_room_ids]);
                if (this.model.meta.productData.booked_room_ids.length) group.push('product_tmpl_id');
            }
            this.actionService.doAction({
                type: "ir.actions.act_window",
                res_model: 'product.product',
                name: 'Rooms',
                views: [[false, 'tree'], [false, 'form']],
                domain: roomTypeDomain,
                res_id: false,
                context: {
                    group_by: group,
                    create: true,
                },
            }, {
                additionalContext: this.props.context,
            });
        }
        else {
            let bookingTypeDomain = [];
            if ($(ev.target).hasClass('selected-date-checkin')) {
                bookingTypeDomain.push(["id", "in", this.model.meta.productData.check_in_booking]);
            }
            else {
                bookingTypeDomain.push(["id", "in", this.model.meta.productData.check_out_booking]);
            }
            this.actionService.doAction({
                type: "ir.actions.act_window",
                res_model: 'hotel.booking',
                name: 'Booking',
                views: [[false, 'tree'], [false, 'form']],
                domain: bookingTypeDomain,
                context: {
                    create: true,
                },
            }, {
                additionalContext: this.props.context,
            });
        }
    },

    /**
     * Update Availavle room data based on selected date
     *
     * @param {booking_count} booking_count passing data of booking that contain details of available rooms.
     * @output updating html of available rooms data if room selected already.
     */

    update_available_rooms_data(booking_count) {
        let selected_room = this.selected_room;
        let available_rooms_name_copy = [...booking_count.available_rooms_name]
        if (!($.isEmptyObject(available_rooms_name_copy)) && selected_room) {
            $.each(available_rooms_name_copy, function (key, val) {
                if (val && val.product_tmpl_id[0] !== selected_room) {
                    available_rooms_name_copy.splice(key, 1)
                }
            });
        }
        $('#availableRoomsTable').html(this.record_html([{ 'room_variant_data': available_rooms_name_copy }], true));
    },

    /**
     * Update booking count based on selected date.
     *
     * @param {calendar_data} x passing model date data like: year,month,day etc...
     * @param {scale} x scale is value of calander scale like year, month, week, and day...
     * @output update value of view count and update value of booking ids.
     */

    async update_bookingCount(calendar_data, scale) {
        var booking_count = await this.orm.call('hotel.booking', 'fetch_booking_count_for_dashboard', [,], { calendar_data: calendar_data, scale: scale, dayInMonth: this.model.date.daysInMonth, weekDay: this.model.date.weekday });
        this.model.meta.productData.check_in_booking = booking_count.check_in_booking; //bookings ids for checkin date
        this.model.meta.productData.check_out_booking = booking_count.check_out_booking;//bookings ids for checkout date
        this.model.meta.productData.booked_room_ids = booking_count.booked_room_ids;
        $('#current_date_check_in').text(booking_count.current_month_check_in);
        $('#current_date_check_out').text(booking_count.current_month_check_out);
        $('#total_available_room').text(booking_count.available_rooms);
        $('#total_booked_room').text(booking_count.booked_room_ids.length);
        this.update_available_rooms_data(booking_count); //update Available Room if Room already selected
    },

    //here we are updating our view data based on calander changes
    get rendererProps() {
        if (this.model.resModel === "hotel.booking") {
            this.update_bookingCount(this.model.date.c, this.model.scale);
        }
        return super.rendererProps;
    },

    bookingModel() {
        return this.props.resModel === 'hotel.booking';
    },

    fetchBookingData() {
        var self = this;
        return this.orm.searchRead('hotel.booking', [], ["display_name", "status_bar"]);
    },


    //*****************************************************
    // when click on any room template, we are adding html
    //  with data of room as well as adding available room
    //  details
    //**********************************************

    record_html(room_detail, variant = false) {
        var data = '<tbody>';
        if (variant) {
            $.each(room_detail[0].room_variant_data, function (key, val) {
                data += `<tr><td>${key + 1}</td>  <td>${val.display_name}</td><td><input class="form-check-input d-none" type="checkbox" id="checkbox${key}" value=""/></td></tr><div></div>`
            })
            return data;
        }
        $.each(room_detail[0], function (key, val) {
            if (!(['id', 'room_variant_data'].includes(key))) {
                if (key == 'Price') {
                    data += `<tr><td>${key}</td>  <td>${val.join(' ')}</td></tr>`
                }
                else {
                    data += `<tr><td>${key.replace(/[_]/gi, ' ').toUpperCase()}</td>  <td>${val}</td></tr>`
                }
            }
        })
        data = data + '</tbody>';
        return data;
    },

    // async fetchRoomTypeData(ev) {
    //     var self = this;
    //     var room_id = $(ev.target).data('id');
    //     var room_detail;
    //     if (room_id) {
    //         this.selected_room = room_id;
    //         room_detail = await this.orm.call('product.template', 'fetch_data_for_room', [[room_id]], { selected_date: this.model.date.c });
    //         $('#roomInformation').fadeOut().html('');
    //         $('#roomInformation').fadeIn('slow').html(`
    //         <div class="selected_room_container p-2" data-prod-tmplt=${room_id}>
    //         <h3>${room_detail[0].name}</h3>
    //         <table>
    //         ${self.record_html(room_detail)}</table>
    //         <h3 class="pt-2">Available Rooms</h3>
    //         <table id="availableRoomsTable">
    //         ${self.record_html(room_detail, true)}</table></div>`
    //         );
    //         $('.allBookingRoom').find('.o_calendar_filter_item').each(function () {
    //             if ($(this).attr('data-value') === room_id.toString()) {
    //                 $(this).find('input').prop('checked', true).prop('disabled', false)
    //             }
    //             else {
    //                 $(this).find('input').prop('checked', false).prop('disabled', true)
    //             }
    //         })
    //     }
    //     else {
    //         $('.allBookingRoom').find('.o_calendar_filter_item').each(function () {
    //             $(this).find('input').prop('checked', true).prop('disabled', false)
    //         })
    //         $('#roomInformation').fadeOut().html('')
    //     }
    // },


    async fetchRoomTypeData(ev=null) {
        var self = this;
        var room_id;
        let d;
        if (ev) {
            room_id = $(ev.target).data('id');
        } else {
            room_id = this.model.meta.productData.room_data[0]?.id; 
        }

        var room_detail;
        this.model.room_id = room_id;
        if (room_id) {
            this.selected_room = room_id;
            d = await this.orm.call('product.template', 'fetch_data_for_room', [[room_id]], { selected_date: this.model.date.c });
            this.model.room_book_ids = d['b_ids'];
            room_detail = d['room_record'];
            $('#roomInformation').html('');
            $('#roomInformation').html(`
                <div class="selected_room_container p-2" data-prod-tmplt=${room_id}>
                <h3>${room_detail[0].name}</h3>
                <table>
                ${self.record_html(room_detail)}</table>
                <h3 class="pt-2">Available Rooms</h3>
                <table id="availableRoomsTable">
                ${self.record_html(room_detail, true)}</table></div>`
            ).show();
            $('.allBookingRoom').find('.o_calendar_filter_item').each(function () {
                if ($(this).attr('data-value') === room_id.toString()) {
                    $(this).find('input').prop('checked', true).prop('disabled', false)
                }
                else {
                    $(this).find('input').prop('checked', false).prop('disabled', true)
                }
            });
            this.model.load();
        } else {
            $('.allBookingRoom').find('.o_calendar_filter_item').each(function () {
                $(this).find('input').prop('checked', true).prop('disabled', false)
            });
            $('#roomInformation').html('').hide();
            this.model.room_book_ids = [];
            this.model.load();
        }
    }
});

patch(CalendarRenderer.prototype, {
    setup() {
        let self = this;
        onPatched(() => {
            self.renderEvents();            
        });
        onMounted(() => {
            document.addEventListener('click', function (event) {
                const roomInfo = document.getElementById('roomInformation');
                if (roomInfo && !roomInfo.contains(event.target)) {
                    roomInfo.style.display = 'none';
                }
            });

            self.renderEvents();         
            if (self.props.model.resModel === 'hotel.booking') {
                const calendarContainer = document.querySelector('.o_calendar_container');
                if (calendarContainer) calendarContainer.classList.add('wk_hotel_container');
            }
        });
    },
    getColorFromIndex(index) {
        const colorMap = {
            'inital': '#0180a5',
            'checkout': '#ff0000',
            'allot': '#f1cd6a',
            'cancel': '#808080',
            'confirm': '#008000'
        };
        return colorMap[index] || '#0180a5';
    },
    lightenColor(color, percent) {
        let colorHex = color.replace(/^#/, '');
        let r = parseInt(colorHex.substring(0, 2), 16);
        let g = parseInt(colorHex.substring(2, 4), 16);
        let b = parseInt(colorHex.substring(4, 6), 16);

        r = Math.round(r + (255 - r) * percent);
        g = Math.round(g + (255 - g) * percent);
        b = Math.round(b + (255 - b) * percent);

        return `rgb(${r}, ${g}, ${b})`;
    },
    renderEvents(){
        let self = this;
        if(self.props.model.resModel === 'hotel.booking'){
            if(self.props.model.scale !== 'year'){
                document.querySelectorAll('.fc-day-grid-event, .fc-daygrid-event-harness.fc-daygrid-event-harness-abs a').forEach(function(aTag) {
                    const eventId = aTag.getAttribute('data-event-id');
                    if (eventId) {
                        let rec = self.props.model.data.records[eventId];
                        const parentDiv = aTag;
                        
                        if (rec && rec.colorIndex) {
                            const color = self.getColorFromIndex(rec.colorIndex);
                            parentDiv.style.border = `1px solid ${color}`;
                            parentDiv.style.borderLeft = `4px solid ${color}`;
                            parentDiv.style.borderRadius = '10px';
                            aTag.style.border = '0';
                            parentDiv.style.backgroundColor = self.lightenColor(color, 0.8);
                            aTag.style.backgroundColor = self.lightenColor(color, 0.8);

                            const divs = aTag.querySelectorAll('div');
                            const isMobileView = window.innerWidth <= 768;

                            divs.forEach((div) => {
                                div.style.color = color;
                                div.style.backgroundColor = self.lightenColor(color, 0.8);
                                if (!isMobileView) {
                                    div.style.alignItems = 'center';
                                }
                            });


                        }
                    }
                });
            }else{
                document.querySelectorAll('.fc-event').forEach(function (event) {
                    const eventId = event.getAttribute('data-event-id');
                    if (eventId) {
                        let rec = self.props.model.data.records[eventId];
                        if (rec && rec.colorIndex) {
                            const color = self.getColorFromIndex(rec.colorIndex);
                            event.style.backgroundColor = color;
                        }
                    }
                });
            }
        }
    },
});