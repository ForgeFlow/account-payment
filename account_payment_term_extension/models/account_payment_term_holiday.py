from odoo import _, api, exceptions, fields, models
from odoo.exceptions import UserError, ValidationError


class AccountPaymentTermHoliday(models.Model):
    _name = "account.payment.term.holiday"
    _description = "Payment Term Holidays"

    payment_id = fields.Many2one(comodel_name="account.payment.term")
    holiday = fields.Date(required=True)
    date_postponed = fields.Date(string="Postponed date", required=True)

    @api.constrains("holiday", "date_postponed")
    def check_holiday(self):
        for record in self:
            if fields.Date.from_string(
                record.date_postponed
            ) <= fields.Date.from_string(record.holiday):
                raise ValidationError(
                    _("Holiday %s can only be postponed into the future")
                    % record.holiday
                )
            if (
                record.search_count(
                    [
                        ("payment_id", "=", record.payment_id.id),
                        ("holiday", "=", record.holiday),
                    ]
                )
                > 1
            ):
                raise ValidationError(
                    _("Holiday %s is duplicated in current payment term")
                    % record.holiday
                )
            if (
                record.search_count(
                    [
                        ("payment_id", "=", record.payment_id.id),
                        "|",
                        ("date_postponed", "=", record.holiday),
                        ("holiday", "=", record.date_postponed),
                    ]
                )
                >= 1
            ):
                raise ValidationError(
                    _("Date %s cannot is both a holiday and a Postponed date")
                    % record.holiday
                )
