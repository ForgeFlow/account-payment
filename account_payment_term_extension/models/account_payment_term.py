# Copyright 2013-2016 Camptocamp SA (Yannick Vaucher)
# Copyright 2004-2016 Odoo S.A. (www.odoo.com)
# Copyright 2015-2016 Akretion
# (Alexis de Lattre <alexis.delattre@akretion.com>)
# Copyright 2018 Simone Rubino - Agile Business Group
# Copyright 2021 Tecnativa - Víctor Martínez
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import calendar

from dateutil.relativedelta import relativedelta

from odoo import _, api, exceptions, fields, models
from odoo.exceptions import UserError, ValidationError


class AccountPaymentTerm(models.Model):
    _inherit = "account.payment.term"

    sequential_lines = fields.Boolean(
        default=False,
        help="Allows to apply a chronological order on lines.",
    )
    holiday_ids = fields.One2many(
        string="Holidays",
        comodel_name="account.payment.term.holiday",
        inverse_name="payment_id",
    )

    def apply_holidays(self, date):
        holiday = self.holiday_ids.search(
            [("payment_id", "=", self.id), ("holiday", "=", date)]
        )
        if holiday:
            return holiday.date_postponed
        return date

    def apply_payment_days(self, line, date):
        """Calculate the new date with days of payments"""
        if line.payment_days:
            payment_days = line._decode_payment_days(line.payment_days)
            if payment_days:
                new_date = None
                payment_days.sort()
                days_in_month = calendar.monthrange(date.year, date.month)[1]
                for day in payment_days:
                    if date.day <= day:
                        if day > days_in_month:
                            day = days_in_month
                        new_date = date + relativedelta(day=day)
                        break
                if not new_date:
                    day = payment_days[0]
                    if day > days_in_month:
                        day = days_in_month
                    new_date = date + relativedelta(day=day, months=1)
                return new_date
        return date

    @api.depends(
        "example_amount",
        "example_date",
        "line_ids.value",
        "line_ids.value_amount",
        "line_ids.nb_days",
        "line_ids.delay_type",
        "sequential_lines",
        "holiday_ids",
    )
    def _compute_example_preview(self):
        """adding depends for new customized fields"""
        return super()._compute_example_preview()

    def _compute_terms(
        self,
        date_ref,
        currency,
        company,
        tax_amount,
        tax_amount_currency,
        sign,
        untaxed_amount,
        untaxed_amount_currency,
    ):
        """Complete overwrite of compute method for adding extra options."""
        # FIXME: Find an inheritable way of doing this
        self.ensure_one()
        company_currency = company.currency_id
        tax_amount_left = tax_amount
        tax_amount_currency_left = tax_amount_currency
        untaxed_amount_left = untaxed_amount
        untaxed_amount_currency_left = untaxed_amount_currency

        total_amount = remaining_amount = tax_amount + untaxed_amount
        total_amount_currency = remaining_amount_currency = (
            tax_amount_currency + untaxed_amount_currency
        )
        result = []
        precision_digits = currency.decimal_places
        company_precision_digits = company_currency.decimal_places
        next_date = date_ref
        for line in self.line_ids:
            if not self.sequential_lines:
                # For all lines, the beginning date is `date_ref`
                next_date = line._get_due_date(date_ref)
            else:
                next_date = line._get_due_date(next_date)

            next_date = self.apply_payment_days(line, next_date)
            next_date = self.apply_holidays(next_date)

            term_vals = {
                "date": next_date,
                "has_discount": self.discount_percentage,
                "discount_date": None,
                "discount_amount_currency": 0.0,
                "discount_balance": 0.0,
                "discount_percentage": self.discount_percentage,
            }

            if line.value == "fixed":
                line_amount = line.compute_line_amount(
                    total_amount, remaining_amount, precision_digits
                )
                company_line_amount = line.compute_line_amount(
                    total_amount, remaining_amount, company_precision_digits
                )
                term_vals["company_amount"] = sign * company_line_amount
                term_vals["foreign_amount"] = sign * line_amount
                company_proportion = (
                    tax_amount / untaxed_amount if untaxed_amount else 1
                )
                foreign_proportion = (
                    tax_amount_currency / untaxed_amount_currency
                    if untaxed_amount_currency
                    else 1
                )
                line_tax_amount = (
                    company_currency.round(line.value_amount * company_proportion)
                    * sign
                )
                line_tax_amount_currency = (
                    currency.round(line.value_amount * foreign_proportion) * sign
                )
                line_untaxed_amount = term_vals["company_amount"] - line_tax_amount
                line_untaxed_amount_currency = (
                    term_vals["foreign_amount"] - line_tax_amount_currency
                )
            elif line.value == "percent":
                line_amount = line.compute_line_amount(
                    total_amount, remaining_amount, precision_digits
                )
                company_line_amount = line.compute_line_amount(
                    total_amount_currency,
                    remaining_amount_currency,
                    company_precision_digits,
                )
                term_vals["company_amount"] = company_line_amount
                term_vals["foreign_amount"] = line_amount
                line_tax_amount = company_currency.round(
                    tax_amount * (line.value_amount / 100.0)
                )
                line_tax_amount_currency = currency.round(
                    tax_amount_currency * (line.value_amount / 100.0)
                )
                line_untaxed_amount = term_vals["company_amount"] - line_tax_amount
                line_untaxed_amount_currency = (
                    term_vals["foreign_amount"] - line_tax_amount_currency
                )

            elif line.value == "percent_amount_untaxed":
                if company_currency != currency:
                    raise UserError(
                        _(
                            "Percentage of amount untaxed can't be used with foreign "
                            "currencies"
                        )
                    )
                line_amount = line.compute_line_amount(
                    untaxed_amount, untaxed_amount_left, precision_digits
                )
                company_line_amount = line.compute_line_amount(
                    untaxed_amount_currency,
                    untaxed_amount_currency_left,
                    company_precision_digits,
                )
                term_vals["company_amount"] = company_line_amount
                term_vals["foreign_amount"] = line_amount
                line_tax_amount = company_currency.round(
                    tax_amount * (line.value_amount / 100.0)
                )
                line_tax_amount_currency = currency.round(
                    tax_amount_currency * (line.value_amount / 100.0)
                )
                line_untaxed_amount = term_vals["company_amount"] - line_tax_amount
                line_untaxed_amount_currency = (
                    term_vals["foreign_amount"] - line_tax_amount_currency
                )
            else:
                line_tax_amount = (
                    line_tax_amount_currency
                ) = line_untaxed_amount = line_untaxed_amount_currency = 0.0

            tax_amount_left -= line_tax_amount
            tax_amount_currency_left -= line_tax_amount_currency
            untaxed_amount_left -= line_untaxed_amount
            untaxed_amount_currency_left -= line_untaxed_amount_currency
            remaining_amount = tax_amount_left + untaxed_amount_left
            remaining_amount_currency = (
                tax_amount_currency_left + untaxed_amount_currency_left
            )

            if self.discount_percentage:
                if self.early_pay_discount_computation in ("excluded", "mixed"):
                    term_vals["discount_balance"] = company_currency.round(
                        term_vals["company_amount"]
                        - line_untaxed_amount * self.discount_percentage / 100.0
                    )
                    term_vals["discount_amount_currency"] = currency.round(
                        term_vals["foreign_amount"]
                        - line_untaxed_amount_currency
                        * self.discount_percentage
                        / 100.0
                    )
                else:
                    term_vals["discount_balance"] = company_currency.round(
                        term_vals["company_amount"]
                        * (1 - (self.discount_percentage / 100.0))
                    )
                    term_vals["discount_amount_currency"] = currency.round(
                        term_vals["foreign_amount"]
                        * (1 - (self.discount_percentage / 100.0))
                    )
                term_vals["discount_date"] = date_ref + relativedelta(
                    days=self.discount_days
                )

            result.append(term_vals)
        return result
