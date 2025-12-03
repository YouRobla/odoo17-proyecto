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
from odoo import fields, models


class HotelDocument(models.Model):
    """Hotel Image

    Parameters
    ----------
    models : model
    """

    _name = "hotel.document"
    _description = "Hotel Document"

    # -------------------------------------------------------------------------//
    # MODEL FIELDS
    # -------------------------------------------------------------------------//

    name = fields.Char("Name", required=True)
    booking_id = fields.Many2one("hotel.booking", string="Booking")
    file = fields.Binary("Document")
    file_name = fields.Char("File Name", default="Content")
