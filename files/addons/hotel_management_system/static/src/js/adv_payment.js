/** @odoo-module **/

/* Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>) */
/* See LICENSE file for full copyright and licensing details. */
/* License URL : <https://store.webkul.com/license.html/> */
import publicWidget from '@web/legacy/js/public/public_widget';
import { jsonrpc } from "@web/core/network/rpc_service";

publicWidget.registry.WebsiteOrderAdvancePayments = publicWidget.Widget.extend({
    selector: '#website_order_advance_payment',

    events: {
        'keydown #advance_pay_amount': '_changeAdvancePayAmount',
        'hidden.bs.modal #advancePaymentModal': '_onClosePaymentModal',
        'shown.bs.modal #advancePaymentModal': '_onOpenPaymentModalExtraEvent', // GitLab Issue #64 (Suggestion)
    },

    init() {
        this._super(...arguments);
        this.ui = this.bindService('ui');
        this.showAdvancePaymentBtn = false;
        this._checkHotelAdvanceConfig()
        this.miniAdvanceAmount = 0;
        this.currencyName = 'USD';
    },

    _onClosePaymentModal: function (ev) {
        window.location.reload();
    },

    _changeAdvancePayAmount: async function (ev) {

        if (ev.type === 'keydown' && ev.keyCode !== 13) {
            return;
        }

        document.querySelector('#payment_iframe')?.remove();
        let amount = parseFloat(ev.currentTarget.value);
        let maxAmount = parseFloat(ev.currentTarget.getAttribute('max'));
        const toShowAmount = this.miniAdvanceAmount.toLocaleString('en-US', { style: 'currency', currency: this.currencyName });
        
        if (amount >= parseFloat(this.miniAdvanceAmount) && amount <= maxAmount) {
            document.querySelector('.info_div')?.remove();
            this.ui.block();
            this.content = await jsonrpc("/order/advance_payment/modal_content", {
                amount: amount
            });
            const iFrameDiv = document.createElement('div');
            iFrameDiv.innerHTML = this.content;
            const advancePaymentModal = document.getElementById('advancePaymentModal');
            advancePaymentModal.querySelector('.modal-body').appendChild(iFrameDiv);
            const iFrame = advancePaymentModal.querySelector('#payment_iframe');
            iFrame.onload = function () {
                if (iFrame.contentDocument.body.querySelector('button[name="o_payment_submit_button"]')) {
                    const div = iFrame.contentDocument.querySelector('.col-lg-7');
                    iFrame.contentDocument.body.innerHTML = div.outerHTML;
                    iFrame.contentDocument.body.style.overflowY = "scroll";
                }
                else {
                    const container = iFrame.contentDocument.body.querySelector('.wrap > .container')
                    if (container) {
                        container.querySelector('.row').remove();
                        container.querySelector('a[href="/my/home"]')?.remove();
                        iFrame.contentDocument.body.innerHTML = container.innerHTML;
                        iFrame.contentDocument.body.classList.add('iframe_body');
                        iFrame.contentDocument.body.style.overflow = "hidden";
                    }
                }

            }
            this.ui.unblock();
        }
        else {
            if (!document.querySelector('.info_div')) {
                let infoDiv = document.createElement('div');
                infoDiv.classList.add('info_div');
                let info = `<p class="text-info fst-italic mb-0"><i class="fa fa-info-circle"></i> The entered amount must be equal or greater than minimum amount ${toShowAmount} and less than  ${maxAmount.toLocaleString('en-US', { style: 'currency', currency: this.currencyName })}.</p><p class="text-info fst-italic mb-0"><i class="fa fa-info-circle"></i> Please press Enter to proceed.</p>`;
                infoDiv.innerHTML = info;
                ev.currentTarget.after(infoDiv);
            }
        }

    },

    _checkHotelAdvanceConfig: async function () {
        const res = await jsonrpc("/order/advance_payment/check_hotel_advance_config");
        this.miniAdvanceAmount = res.minimum_amount
        this.currencyName = res.currency;
        const buttons = document.getElementsByName('o_payment_submit_button');

        if (res && res.need_to_show) {
            document.querySelector('#advance_payment').style.display = 'block';
            if (buttons.length > 0 && res.adv_payment_len == 0) {
                buttons[0].classList.add('disabled');
            }
            if (buttons.length > 0 && res.adv_payment_len > 0){
                buttons[0].classList.remove('disabled');
                buttons[0].classList.remove('d-none');
                document.querySelector('#website_order_advance_payment').classList.add('d-none');
            }

            const noteDiv = document.createElement('div');
            noteDiv.classList.add('advance-payment-note');
            noteDiv.innerHTML = `
            <p><strong>Note:</strong> For this hotel, you are required to pay an advance amount. 
            The amount should be equal to or greater than the minimum amount of 
            <strong>${this.miniAdvanceAmount.toFixed(2)}</strong>.</p>
        `;
            document.querySelector('#advance_payment').insertAdjacentElement('afterend', noteDiv);

            // Adding Minimum Amount in Input field as default value
            document.getElementById('advance_pay_amount').value = Math.ceil(this.miniAdvanceAmount);

        }
    },
    
    // On opening the modal, we are triggering the onChange event of the input field with keydown value 13
    _onOpenPaymentModalExtraEvent: function () {
        const input = document.querySelector('#advance_pay_amount');
        if (input) {
            this._changeAdvancePayAmount({ currentTarget: input, type: 'keydown', keyCode: 13 });
        }
    },
});
