/** @odoo-module **/
/* Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>) */
/* See LICENSE file for full copyright and licensing details. */
/* License URL : <https://store.webkul.com/license.html/> */
import PaymentForm from "@payment/js/payment_form";

PaymentForm.include({
    _prepareTransactionRouteParams() {
        const transactionRouteParams = this._super(...arguments);
        const searchParams = new URLSearchParams(window.location.search);
        let order_id = searchParams.has('order_id') ? searchParams.get('order_id') : 0

        return {
            ...transactionRouteParams,
            'advance_payment_order_id': order_id,
        }
    },
});