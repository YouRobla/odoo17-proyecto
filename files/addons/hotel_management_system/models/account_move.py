# -*- coding: utf-8 -*-
##########################################################################
# Author : Webkul Software Pvt. Ltd. (<https://webkul.com/>;)
# Copyright(c): 2017-Present Webkul Software Pvt. Ltd.
# All Rights Reserved.
#
#
#
# This program is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#
# You should have received a copy of the License along with this program.
# If not, see <https://store.webkul.com/license.html/>;
##########################################################################

# Odoo Module
from odoo import fields, models, _


class AccountMove(models.Model):
    _inherit = "account.move"

    # -------------------------------------------------------------------------//
    # MODEL FIELDS
    # -------------------------------------------------------------------------//
    booking_count = fields.Integer("Booking count", copy=False)
    hotel_booking_id = fields.Many2one("hotel.booking")

    # -------------------------------------------------------------------------
    # OPEN VIEWS
    # -------------------------------------------------------------------------
    def action_view_source_booking(self):
        self.ensure_one()
        source_orders = self.line_ids.sale_line_ids.order_id
        if self.sale_order_count == 1:
            return source_orders.action_view_booking()

    # Advance Payment Integration
    def _compute_payments_widget_to_reconcile_info(self):
        super()._compute_payments_widget_to_reconcile_info()
        for move in self:
            if move.move_type == "out_invoice":
                move.invoice_outstanding_credits_debits_widget = False
                move.invoice_has_outstanding = False

                if (
                    move.state != "posted"
                    or move.payment_state not in ("not_paid", "partial")
                    or not move.is_invoice(include_receipts=True)
                ):
                    continue

                pay_term_lines = move.line_ids.filtered(
                    lambda line: line.account_id.account_type
                    in ("asset_receivable", "liability_payable")
                )
                source_orders = move.line_ids.sale_line_ids.order_id
                default = self.env["res.config.settings"].sudo().get_values()
                outstanding_credit = {
                    payment.move_id.line_ids[-1].account_id.id
                    for sale_order in source_orders
                    for payment in sale_order.payment_ids
                    if payment.state == "in_process"
                    and payment.move_id.line_ids.filtered(
                        lambda x: x.account_id.id == default.get(
                            "account_receivable")
                    )
                }
                outstanding_credit = list(outstanding_credit)
                domain = [
                    (
                        "account_id",
                        "in",
                        pay_term_lines.account_id.ids + outstanding_credit,
                    ),
                    ("parent_state", "=", "posted"),
                    ("partner_id", "=", move.commercial_partner_id.id),
                    ("reconciled", "=", False),
                    "|",
                    ("amount_residual", "!=", 0.0),
                    ("amount_residual_currency", "!=", 0.0),
                ]
                payments_widget_vals = {
                    "outstanding": True,
                    "content": [],
                    "move_id": move.id,
                }
                if move.is_inbound():
                    domain.append(("balance", "<", 0.0))
                    payments_widget_vals["title"] = _("Outstanding credits")
                else:
                    domain.append(("balance", ">", 0.0))
                    payments_widget_vals["title"] = _("Outstanding debits")
                for line in self.env["account.move.line"].search(domain):
                    if line.currency_id == move.currency_id:
                        amount = abs(line.amount_residual_currency)
                    else:
                        amount = line.company_currency_id._convert(
                            abs(line.amount_residual),
                            move.currency_id,
                            move.company_id,
                            line.date,
                        )

                    if move.currency_id.is_zero(amount):
                        continue

                    payments_widget_vals["content"].append(
                        {
                            "journal_name": line.ref or line.move_id.name,
                            "amount": amount,
                            "currency_id": move.currency_id.id,
                            "id": line.id,
                            "move_id": line.move_id.id,
                            "date": fields.Date.to_string(line.date),
                            "account_payment_id": line.payment_id.id,
                        }
                    )

                if not payments_widget_vals["content"]:
                    continue

                move.invoice_outstanding_credits_debits_widget = payments_widget_vals
                move.invoice_has_outstanding = True

    def js_assign_outstanding_line(self, line_id):
        original_lines = self.env["account.move.line"].browse(line_id)
        journal_item = self.line_ids.filtered(
            lambda x: x.account_id.account_type == "asset_receivable"
        )
        default = self.env["res.config.settings"].sudo().get_values()
        if self.move_type == "out_invoice" and default.get("account_receivable"):
            original_lines.account_id = journal_item.account_id
        return super().js_assign_outstanding_line(line_id)
