# -*- coding: utf-8 -*-
#################################################################################
#
#    Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#
#################################################################################
import random
import string
import logging

from odoo import models, fields, _, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HotelRestAPI(models.Model):
    _name = "hotel.rest.api"
    _description = "Hotel RESTful Web Services"

    def _default_unique_key(self, size, chars=string.ascii_uppercase + string.digits):
        return "".join(random.choice(chars) for x in range(size))

    @api.model
    def _validate(self, api_key, context=None):
        context = context or {}
        response = {"success": False, "message": "Unknown Error !!!"}
        if not api_key:
            response["responseCode"] = 401
            response["message"] = "Invalid/Missing Api Key !!!"
            return response
        try:
            Obj_exists = self.sudo().search([("api_key", "=", api_key)])
            if not Obj_exists:
                response["responseCode"] = 401
                response["message"] = "API Key is invalid !!!"
            else:
                response["success"] = True
                response["responseCode"] = 200
                response["message"] = "Api Key has been successfully validated!."
        except Exception as e:
            response["responseCode"] = 401
            response["message"] = (
                "Api Key verification has been failed: %r" % e.message or e.name
            )
        return response

    name = fields.Char("Name", required=True)
    description = fields.Text(
        "Extra Information", help="Quick description of the key", translate=True
    )
    api_key = fields.Char(string="API Secret key")
    active = fields.Boolean(default=True)

    def generate_secret_key(self):
        self.api_key = self._default_unique_key(32)

    def copy(self, default=None):
        raise UserError(_("You can't duplicate this Configuration."))

    def unlink(self):
        raise UserError(
            _("You cannot delete this Configuration, but you can disable/In-active it.")
        )

    @api.model_create_multi
    def create(self, vals):
        records = super(HotelRestAPI, self).create(vals)
        for rec in records:
            rec.generate_secret_key()
        return records
