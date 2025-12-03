# -*- coding: utf-8 -*-
##############################################################################
# Copyright (c) 2015-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
# See LICENSE file for full copyright and licensing details.
# License URL : <https://store.webkul.com/license.html/>
##############################################################################

from odoo import api, fields, models, _
import logging
_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    """Populate factory part for account.payment."""
    _inherit = "account.payment"

    sale_order_id = fields.Many2one('sale.order', string='Order')

    def register_payment(self):
        self.action_post()
        email_values = {
            'email_to': self.sale_order_id.user_id.email
        }
        template = self.env.ref(
            'hotel_management_system.payment_confirmation_email_template')
        template.send_mail(self.id, force_send=True,
                           email_values=email_values)

        return {
            "type": "ir.actions.act_window",
            'name': 'Payment',
            'res_model': 'account.payment',
            'view_mode': 'form',
            'res_id': self.id,
            "target": "self",
        }

    @api.model_create_multi
    def create(self, vals_list):
        skip_account_move_synchronization = False
        if self.env.context.get('is_advance_payment_sale', False):
            skip_account_move_synchronization = True
        res = super(AccountPayment, self.with_context(
            skip_account_move_synchronization=skip_account_move_synchronization)).create(vals_list)
        return res

    def _prepare_move_line_default_vals(self, write_off_line_vals=None, force_balance=None):
        res = super()._prepare_move_line_default_vals(
            write_off_line_vals, force_balance)
        default = self.env['res.config.settings'].sudo().get_values()
        if self.env.context.get('is_advance_payment_sale', False) and default.get('account_receivable'):
            res[1]['account_id'] = default.get('account_receivable')
        return res


class AccountPaymentRegister(models.TransientModel):
    """Populate factory part for account.payment."""
    _inherit = "account.payment.register"

    def _create_payments(self):

        payments = super(AccountPaymentRegister, self)._create_payments()
        if not payments:
            return payments

        # Get all selected invoices
        invoice_ids = self._context.get("active_ids", [])
        if not invoice_ids:
            return payments

        invoices = self.env['account.move'].browse(invoice_ids).exists()
        if not invoices:
            return payments

        # Process each payment
        for payment in payments:
            # Find the related invoice(s) for this payment
            payment_moves = payment.move_id.line_ids.mapped('move_id')
            related_invoices = invoices.filtered(
                lambda inv: inv in payment_moves)

            if related_invoices:
                # Get sale orders from the related invoice lines
                source_orders = related_invoices.line_ids.sale_line_ids.order_id
                if source_orders:
                    payment.sale_order_id = source_orders[0].id

                # Send email notification
                email_values = {
                    'email_to': related_invoices[0].invoice_user_id.email
                }
                template = self.env.ref(
                    'hotel_management_system.payment_confirmation_template')
                if template:
                    template.send_mail(
                        payment.id, force_send=True, email_values=email_values)

        return payments


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _create_payment(self, **extra_create_values):
        res = super()._create_payment()
        if self.sale_order_ids:
            res.sale_order_id = self.sale_order_ids[0]
        return res
