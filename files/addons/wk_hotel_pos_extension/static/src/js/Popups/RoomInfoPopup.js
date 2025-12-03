/** @odoo-module **/
/* Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>) */
/* See LICENSE file for full copyright and licensing details. */
/* License URL : <https://store.webkul.com/license.html/> */
import { onMounted } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { AbstractAwaitablePopup } from "@point_of_sale/app/popup/abstract_awaitable_popup";

/**
 * Props:
 *  {
 *      info: {object of data}
 *  }
 */

export class RoomInfoPopup extends AbstractAwaitablePopup {
    static template = "wk_hotel_pos_expension.RoomInfoPopup";
    static defaultProps = { confirmKey: false };

    setup() {
        let self = this;
        super.setup();
        this.pos = usePos();
        Object.assign(this, this.props.info);
        onMounted(() => {
            self._onChangeSelection();
        });

    }
    //--------------------------------------------------------------------------
    // Handler
    //--------------------------------------------------------------------------
    /**
     * @private
     */
    _onChangeSelection(ev) {
    let selected_option = $(ev?.currentTarget).find(":selected").length ? $(ev?.currentTarget).find(":selected"): $('#room_no_selection').find(':selected');
        if(selected_option){
            let booking_name = selected_option.data('booking_name');
            let booking_customer = selected_option.data('customer');
            $('#booking_name').val(booking_name);
            $('#booking_customer').val(booking_customer);
        }
    }
    confirm_booking(ev) {
        const selected_option = $("#room_no_selection").find(":selected");
        let current_order = this.pos.get_order();
        let customer = this.pos.db.get_partner_by_id(parseInt(selected_option.data('customer_id')));
        current_order['booking_id'] = selected_option.data('booking_id');
        current_order['booking_line_id'] = selected_option.data('line_id');
        current_order['booking_name'] = selected_option.text();
        current_order.set_partner(customer);
        current_order.updatePricelistAndFiscalPosition(customer);
        this.confirm();
    }
    remove_booking(ev) {
        let current_order = this.pos.get_order();
        current_order['booking_id'] = null;
        current_order['booking_line_id'] = null;
        current_order['booking_name'] = '';
        current_order.set_partner(false);
        current_order.updatePricelistAndFiscalPosition(false);
        this.confirm();
    }
}
