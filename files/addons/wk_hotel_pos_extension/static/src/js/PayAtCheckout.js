/** @odoo-module **/
/* Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>) */
/* See LICENSE file for full copyright and licensing details. */
/* License URL : <https://store.webkul.com/license.html/> */
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { ConfirmPopup } from "@point_of_sale/app/utils/confirm_popup/confirm_popup";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { sprintf } from "@web/core/utils/strings";

patch(PaymentScreen.prototype, {
    setup() {
        super.setup();
        this.popup = useService("popup");
    },
    async _confirmationPayAtCheckout() {
        this._is_pay_at_checkout = true;
        if (!(this.currentOrder.is_to_invoice())) {
            const { confirmed } = await this.popup.add(ConfirmPopup, {
                title: _t('Please select the Invoice'),
                body: _t(
                    'You need to select the invoice before using Pay at checkout, Proceed?'
                ),
            });
            if (confirmed) {
                this.currentOrder.set_to_invoice(!this.currentOrder.is_to_invoice());
                this.validateOrder(true);
            }
            return false;
        }
        else {
            this.validateOrder(true);
        }
    },
    async _isOrderValid(isForceValidate) {
        if (this.currentOrder.booking_id) {
            if (this.currentOrder.get_orderlines().length === 0 && this.currentOrder.is_to_invoice()) {
                this.popup.add(ErrorPopup, {
                    title: _t('Empty Order'),
                    body: _t('There must be at least one product in your order before it can be validated and invoiced.'),
                });
                return false;
            }

            const splitPayments = this.paymentLines.filter(payment => payment.payment_method.split_transactions)
            if (splitPayments.length && !this.currentOrder.get_partner()) {
                const paymentMethod = splitPayments[0].payment_method
                const { confirmed } = await this.popup.add(ConfirmPopup, {
                    title: _t('Customer Required'),
                    body: sprintf(_t('Customer is required for %s payment method.'), paymentMethod.name),
                });
                if (confirmed) {
                    this.selectPartner();
                }
                return false;
            }

            if ((this.currentOrder.is_to_invoice() || this.currentOrder.getShippingDate()) && !this.currentOrder.get_partner()) {
                const { confirmed } = await this.popup.add(ConfirmPopup, {
                    title: _t('Please select the Customer'),
                    body: _t('You need to select the customer before you can invoice or ship an order.'),
                });
                if (confirmed) {
                    this.selectPartner();
                }
                return false;
            }

            let partner = this.currentOrder.get_partner()
            if (this.currentOrder.getShippingDate() && !(partner.name && partner.street && partner.city && partner.country_id)) {
                this.popup.add(ErrorPopup, {
                    title: _t('Incorrect address for shipping'),
                    body: _t('The selected customer needs an address.'),
                });
                return false;
            }
            if (!this.currentOrder.is_paid() || this.invoicing) {
                return false;
            }
            if (this.currentOrder.has_not_valid_rounding()) {
                var line = this.currentOrder.has_not_valid_rounding();
                this.popup.add(ErrorPopup, {
                    title: _t('Incorrect rounding'),
                    body: _t('You have to round your payments lines.' + line.amount + ' is not rounded.'),
                });
                return false;
            }
            if (!this.currentOrder._isValidEmptyOrder()) return false;
            return true;
        }
        else {
            return super._isOrderValid(...arguments);
        }


    },

    async validateOrder(isForceValidate) {
        var self = this;
        var order = self.pos.get_order();
        if (order.booking_id && this._is_pay_at_checkout) {
            if (this.pos.config.cash_rounding) {
                if (!this.pos.get_order().check_paymentlines_rounding()) {
                    this.popup.add(ErrorPopup, {
                        title: _t('Rounding error in payment lines'),
                        body: _t("The amount of your payment lines must be rounded to validate the transaction."),
                    });
                    return;
                }
            }
            if (order.get_orderlines().length === 0) {

                this.popup.add(ErrorPopup, {
                    title: _t('Empty Order'),
                    body: _t('There must be at least one product in your order before it can be validated'),
                });
                return false;
            }
            else if (!await self._isOrderValid(isForceValidate)) {

                await this._finalizeValidation();
            } else {

                await this._finalizeValidation();
            }
        }
        else {
            order.booking_id = false;
            return super.validateOrder(...arguments);
        }

    },
    addNewPaymentLine(paymentMethod) {
        // original function: click_paymentmethods
        if (this.currentOrder.booking_id) {
            return false;
        }
        else {
            return super.addNewPaymentLine(paymentMethod);
        }
    }
});
