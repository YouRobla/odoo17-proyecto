/** @odoo-module **/
/* Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>) */
/* See LICENSE file for full copyright and licensing details. */
/* License URL : <https://store.webkul.com/license.html/> */
import { WebsiteSale } from '@website_sale/js/website_sale';

WebsiteSale.include({
    events: Object.assign(WebsiteSale.prototype.events, {
        'click .o-mail-custom-stars i': '_click_starts',
    }),
    init() {
        this._super(...arguments);
        this.orm = this.bindService("orm");
    },

    _click_starts: function(ev) {
        $(ev.currentTarget).addClass('fa-star').removeClass('fa-star-o');
        $(ev.currentTarget).prevAll()?.addClass('fa-star').removeClass('fa-star-o');
        $(ev.currentTarget).nextAll()?.addClass('fa-star-o').removeClass('fa-star');
        $(ev.currentTarget).closest('form').find('input.feedback_count').val($(ev.currentTarget).prevAll().length + 1);
    }
});
