from dateutil.relativedelta import relativedelta

from odoo import _, api, exceptions, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_round


class AccountPaymentTermLine(models.Model):
    _inherit = "account.payment.term.line"

    amount_round = fields.Float(
        string="Amount Rounding",
        digits="Account",
        help="Sets the amount so that it is a multiple of this value.",
    )
    weeks = fields.Integer("Weeks", help="Number of weeks to add to the due date.")
    value = fields.Selection(
        selection_add=[
            ("percent_amount_untaxed", "Percent (Untaxed amount)"),
            ("fixed",),
        ],
        ondelete={"percent_amount_untaxed": lambda r: r.write({"value": "percent"})},
    )
    payment_days = fields.Char(
        string="Payment day(s)",
        help="Put here the day or days when the partner makes the payment. "
             "Separate each possible payment day with dashes (-), commas (,) "
             "or spaces ( ).",
    )

    def _get_due_date(self, date_ref):
        self.ensure_one()
        due_date = fields.Date.from_string(date_ref)
        if self.delay_type == 'days_after_end_of_month':
            due_date = due_date + relativedelta(day=31)
        elif self.delay_type == 'days_after_end_of_next_month':
            due_date = due_date + relativedelta(months=1, day=31)
        due_date += relativedelta(weeks=self.weeks)
        due_date += relativedelta(days=self.nb_days)

        return due_date

    @api.constrains("value", "value_amount")
    def _check_value_amount_untaxed(self):
        for term_line in self:
            if (
                term_line.value == "percent_amount_untaxed"
                and not 0 <= term_line.value_amount <= 100
            ):
                raise ValidationError(
                    _(
                        "Percentages on the Payment Terms lines "
                        "must be between 0 and 100."
                    )
                )

    def compute_line_amount(self, total_amount, remaining_amount, precision_digits):
        """Compute the amount for a payment term line.
        In case of procent computation, use the payment
        term line rounding if defined

            :param total_amount: total balance to pay
            :param remaining_amount: total amount minus sum of previous lines
                computed amount
            :returns: computed amount for this line
        """
        self.ensure_one()
        if self.value == "fixed":
            return float_round(self.value_amount, precision_digits=precision_digits)
        elif self.value in ("percent", "percent_amount_untaxed"):
            amt = total_amount * self.value_amount / 100.0
            if self.amount_round:
                amt = float_round(amt, precision_rounding=self.amount_round)
            return float_round(amt, precision_digits=precision_digits)
        elif self.value == "balance":
            return float_round(remaining_amount, precision_digits=precision_digits)
        return None

    def _decode_payment_days(self, days_char):
        # Admit space, dash and comma as separators
        days_char = days_char.replace(" ", "-").replace(",", "-")
        days_char = [x.strip() for x in days_char.split("-") if x]
        days = [int(x) for x in days_char]
        days.sort()
        return days

    @api.constrains("payment_days")
    def _check_payment_days(self):
        for record in self:
            if not record.payment_days:
                continue
            try:
                payment_days = record._decode_payment_days(record.payment_days)
                error = any(day <= 0 or day > 31 for day in payment_days)
            except Exception:
                error = True
            if error:
                raise exceptions.Warning(_("Payment days field format is not valid."))


