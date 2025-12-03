/** @odoo-module **/
/* Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>) */
/* See LICENSE file for full copyright and licensing details. */
/* License URL : <https://store.webkul.com/license.html/> */
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { OfflineErrorPopup } from "@point_of_sale/app/errors/popups/offline_error_popup";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { RoomInfoPopup } from "@wk_hotel_pos_extension/js/Popups/RoomInfoPopup";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { ConnectionAbortedError, ConnectionLostError } from "@web/core/network/rpc_service";
import { Component, onWillStart } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/store/pos_hook";

export class RoomInfoButton extends Component {
    static template = "wk_hotel_pos_expension.RoomInfoButton";

    setup() {
        this.orm = useService('orm');
        this.popup = useService("popup");
        this.pos = usePos();
        onWillStart(async () => {
            this.rooms = await this.orm.call('hotel.booking', 'fetch_booked_room_data_for_pos');
        });
    }
    get bookingName() {
        const order = this.pos.get_order();
        return order ? order.booking_name : null;
    }
    click() {
        const order = this.pos.get_order();
        var rooms = this.rooms
        if (rooms) {
            try {
                this.popup.add(RoomInfoPopup, { info: { 
                    rooms: rooms,
                    booking_line_id: order.booking_line_id,
                }});
            } catch (error) {
                if (error instanceof ConnectionLostError || error instanceof ConnectionAbortedError) {
                    this.popup.add(OfflineErrorPopup, {
                        title: _t('Network Error'),
                        body: _t('Cannot access product information screen if offline.'),
                    });
                } else {
                    this.popup.add(ErrorPopup, {
                        title: _t('Unknown error'),
                        body: _t('An unknown error prevents us from loading product information.'),
                    });
                }
            }
        }
    }
}
ProductScreen.addControlButton({
    component: RoomInfoButton,
    condition: function () {
        return true;
    },
});
