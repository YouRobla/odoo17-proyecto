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
from odoo import fields, models, _


class AttachDoc(models.TransientModel):
    _name = "customer.document"
    _description = "Attached customer document image"

    add_docs_ids = fields.One2many(
        "customer.document.lines", "doc_id", string="Attach Documents"
    )
    booking_id = fields.Many2one("hotel.booking")

    def confirm_doc(self):
        """Confirm document wizard"""
        active_booking_id = self.env["hotel.booking"].browse(
            self._context.get("active_ids")
        )
        data = [[0, 0, {"file": doc.file, "name": doc.name}]
                for doc in self.add_docs_ids]
        template_id = self.env.ref(
            "hotel_management_system.hotel_booking_allot_id"
        )
        active_booking_id.write({"docs_ids": data, "status_bar": "allot"})
        allot_config = self.env["ir.config_parameter"].sudo(
        ).get_param("hotel_management_system.send_on_allot")
        if allot_config:
            template_id.send_mail(active_booking_id.id, force_send=True)


class AttachDocLines(models.TransientModel):
    _name = "customer.document.lines"
    _description = "Attached customer document lines"

    name = fields.Char("Name", required=True)
    file = fields.Binary("File", required=True)
    file_name = fields.Char("File Name", default="Content")
    doc_id = fields.Many2one("customer.document")
