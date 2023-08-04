# -*- coding: utf-8 -*-
from odoo import api, models, fields, tools, _
from odoo.tools.xml_utils import _check_with_xsd
from odoo.tools.float_utils import float_round, float_is_zero

import logging
import re
import base64
import json
import requests
import random
import string

from lxml import etree
from lxml.objectify import fromstring
from datetime import datetime
from io import BytesIO
from zeep import Client
from zeep.transports import Transport
from json.decoder import JSONDecodeError

_logger = logging.getLogger(__name__)


class AccountEdiFormat(models.Model):
    _inherit = 'account.edi.format'

    def _check_move_configuration(self, move):
        if self.code != 'cfdi_4_0':
            return super()._check_move_configuration(move)
        return self._l10n_mx_edi_check_configuration(move)

    def _get_invoice_edi_content(self, move):
        #OVERRIDE
        if self.code != 'cfdi_4_0':
            return super()._get_invoice_edi_content(move)
        return self._l10n_mx_edi_export_invoice_cfdi(move).get('cfdi_str')

    def _get_payment_edi_content(self, move):
        #OVERRIDE
        if self.code != 'cfdi_4_0':
            return super()._get_payment_edi_content(move)
        return self._l10n_mx_edi_export_payment_cfdi(move).get('cfdi_str')

    def _needs_web_services(self):
        # OVERRIDE
        return self.code == 'cfdi_4_0' or super()._needs_web_services()

    def _is_compatible_with_journal(self, journal):
        # OVERRIDE
        self.ensure_one()
        if self.code != 'cfdi_4_0':
            return super()._is_compatible_with_journal(journal)
        return journal.type == 'sale' and journal.country_code == 'MX' and \
            journal.company_id.currency_id.name == 'MXN'


    # def _is_required_for_invoice(self, invoice):
    #     # OVERRIDE
    #     self.ensure_one()
    #     if self.code != 'cfdi_4_0':
    #         return super()._is_required_for_invoice(invoice)

    def _is_required_for_payment(self, move):
        # OVERRIDE
        self.ensure_one()
        if self.code != 'cfdi_4_0':
            return super()._is_required_for_payment(move)

        # Determine on which invoices the Mexican CFDI must be generated.
        if move.country_code != 'MX':
            return False

        if (move.payment_id or move.statement_line_id).l10n_mx_edi_force_generate_cfdi:
            return True

        reconciled_invoices = move._get_reconciled_invoices()
        return 'PPD' in reconciled_invoices.mapped('l10n_mx_edi_payment_policy')


    def _post_invoice_edi(self, invoices):
        # OVERRIDE
        edi_result = super()._post_invoice_edi(invoices)
        if self.code != 'cfdi_4_0':
            return edi_result

        print("invoices",invoices)
        for invoice in invoices:

            # == Check the configuration ==
            errors = self._l10n_mx_edi_check_configuration(invoice)
            if errors:
                edi_result[invoice] = {
                    'error': self._l10n_mx_edi_format_error_message(_("Invalid configuration:"), errors),
                }
                continue

            # == Generate the CFDI ==
            res = self._l10n_mx_edi_export_invoice_cfdi(invoice)
            if res.get('errors'):
                edi_result[invoice] = {
                    'error': self._l10n_mx_edi_format_error_message(_("Failure during the generation of the CFDI:"), res['errors']),
                }
                continue

            # == Call the web-service ==
            res = self._l10n_mx_edi_post_invoice_pac(invoice, res)
            if res.get('error'):
                edi_result[invoice] = res
                continue

            addenda = invoice.partner_id.l10n_mx_edi_addenda or invoice.partner_id.commercial_partner_id.l10n_mx_edi_addenda
            if addenda:
                if res['cfdi_encoding'] == 'base64':
                    res.update({
                        'cfdi_signed': base64.decodebytes(res['cfdi_signed']),
                        'cfdi_encoding': 'str',
                    })
                res['cfdi_signed'] = self._l10n_mx_edi_cfdi_append_addenda(invoice, res['cfdi_signed'], addenda)

            if res['cfdi_encoding'] == 'str':
                res.update({
                    'cfdi_signed': base64.encodebytes(res['cfdi_signed']),
                    'cfdi_encoding': 'base64',
                })

            # == Create the attachment ==
            cfdi_filename = ('%s-%s-MX-Invoice-4.0.xml' % (invoice.journal_id.code, invoice.payment_reference)).replace('/', '')
            cfdi_attachment = self.env['ir.attachment'].create({
                'name': cfdi_filename,
                'res_id': invoice.id,
                'res_model': invoice._name,
                'type': 'binary',
                'datas': res['cfdi_signed'],
                'mimetype': 'application/xml',
                'description': _('Mexican invoice CFDI generated for the %s document.') % invoice.name,
            })
            edi_result[invoice] = {'success': True, 'attachment': cfdi_attachment}

            # == Chatter ==
            invoice.with_context(no_new_invoice=True).message_post(
                body=_("The CFDI document was successfully created and signed by the government."),
                attachment_ids=cfdi_attachment.ids,
            )
        return edi_result

    def _cancel_invoice_edi(self, invoices):
        # OVERRIDE
        edi_result = super()._cancel_invoice_edi(invoices)
        if self.code != 'cfdi_4_0':
            return edi_result

        for invoice in invoices:

            # == Check the configuration ==
            errors = self._l10n_mx_edi_check_configuration(invoice)
            if errors:
                edi_result[invoice] = {'error': self._l10n_mx_edi_format_error_message(_("Invalid configuration:"), errors)}
                continue

            # == Call the web-service ==
            pac_name = invoice.company_id.l10n_mx_edi_pac

            credentials = getattr(self, '_l10n_mx_edi_get_%s_credentials' % pac_name)(invoice)
            if credentials.get('errors'):
                edi_result[invoice] = {'error': self._l10n_mx_edi_format_error_message(_("PAC authentification error:"), credentials['errors'])}
                continue

            signed_edi = invoice._get_l10n_mx_edi_signed_edi_document()
            if signed_edi:
                cfdi_data = base64.decodebytes(signed_edi.attachment_id.with_context(bin_size=False).datas)
            res = getattr(self, '_l10n_mx_edi_%s_cancel_invoice' % pac_name)(invoice, credentials, cfdi_data)
            if res.get('errors'):
                edi_result[invoice] = {'error': self._l10n_mx_edi_format_error_message(_("PAC failed to cancel the CFDI:"), res['errors'])}
                continue

            edi_result[invoice] = res

            # == Chatter ==
            invoice.with_context(no_new_invoice=True).message_post(
                body=_("The CFDI document has been successfully cancelled."),
                subtype_xmlid='account.mt_invoice_validated',
            )

        return edi_result

    def _post_payment_edi(self, payments):
        # OVERRIDE
        edi_result = super()._post_payment_edi(payments)
        if self.code != 'cfdi_4_0':
            return edi_result

        for move in payments:

            # == Check the configuration ==
            errors = self._l10n_mx_edi_check_configuration(move)
            if errors:
                edi_result[move] = {
                    'error': self._l10n_mx_edi_format_error_message(_("Invalid configuration:"), errors),
                }
                continue

            # == Generate the CFDI ==
            res = self._l10n_mx_edi_export_payment_cfdi(move)
            if res.get('errors'):
                edi_result[move] = {
                    'error': self._l10n_mx_edi_format_error_message(_("Failure during the generation of the CFDI:"), res['errors']),
                }
                continue

            # == Call the web-service ==
            res = self._l10n_mx_edi_post_payment_pac(move, res)
            if res.get('error'):
                edi_result[move] = res
                continue

            # == Create the attachment ==
            cfdi_signed = res['cfdi_signed'] if res['cfdi_encoding'] == 'base64' else base64.encodebytes(res['cfdi_signed'])
            cfdi_filename = ('%s-%s-MX-Payment-20.xml' % (move.journal_id.code, move.name)).replace('/', '')
            cfdi_attachment = self.env['ir.attachment'].create({
                'name': cfdi_filename,
                'res_id': move.id,
                'res_model': move._name,
                'type': 'binary',
                'datas': cfdi_signed,
                'mimetype': 'application/xml',
                'description': _('Mexican payment CFDI generated for the %s document.') % move.name,
            })
            edi_result[move] = {'success': True, 'attachment': cfdi_attachment}

            # == Chatter ==
            message = _("The CFDI document has been successfully signed.")
            move.message_post(body=message, attachment_ids=cfdi_attachment.ids)
            if move.payment_id:
                move.payment_id.message_post(body=message, attachment_ids=cfdi_attachment.ids)

        return edi_result

    def _cancel_payment_edi(self, moves):
        # OVERRIDE
        edi_result = super()._cancel_payment_edi(moves)
        if self.code != 'cfdi_4_0':
            return edi_result

        for move in moves:

            # == Check the configuration ==
            errors = self._l10n_mx_edi_check_configuration(move)
            if errors:
                edi_result[move] = {'error': self._l10n_mx_edi_format_error_message(_("Invalid configuration:"), errors)}
                continue

            # == Call the web-service ==
            pac_name = move.company_id.l10n_mx_edi_pac

            credentials = getattr(self, '_l10n_mx_edi_get_%s_credentials' % pac_name)(move)
            if credentials.get('errors'):
                edi_result[move] = {'error': self._l10n_mx_edi_format_error_message(_("PAC authentification error:"), credentials['errors'])}
                continue

            signed_edi = move._get_l10n_mx_edi_signed_edi_document()
            if signed_edi:
                cfdi_data = base64.decodebytes(signed_edi.attachment_id.with_context(bin_size=False).datas)
            res = getattr(self, '_l10n_mx_edi_%s_cancel_payment' % pac_name)(move, credentials, cfdi_data)
            if res.get('errors'):
                edi_result[move] = {'error': self._l10n_mx_edi_format_error_message(_("PAC failed to cancel the CFDI:"), res['errors'])}
                continue

            edi_result[move] = res

            # == Chatter ==
            message = _("The CFDI document has been successfully cancelled.")
            move.message_post(body=message)
            if move.payment_id:
                move.payment_id.message_post(body=message)

        return edi_result

    def _l10n_mx_edi_export_invoice_cfdi(self, invoice):
        ''' Create the CFDI attachment for the invoice passed as parameter.

        :param move:    An account.move record.
        :return:        A dictionary with one of the following key:
        * cfdi_str:     A string of the unsigned cfdi of the invoice.
        * error:        An error if the cfdi was not successfuly generated.
        '''

        # == CFDI values ==
        cfdi_values = self._l10n_mx_edi_get_invoice_cfdi_values(invoice)
        print("xxxx",cfdi_values)
        # == Generate the CFDI ==
        cfdi = self.env.ref('cfdi4_enterprise.cfdiv40')._render(cfdi_values)
        decoded_cfdi_values = invoice._l10n_mx_edi_decode_cfdi(cfdi_data=cfdi)
        cfdi_cadena_crypted = cfdi_values['certificate'].sudo().get_encrypted_cadena(decoded_cfdi_values['cadena'])
        decoded_cfdi_values['cfdi_node'].attrib['Sello'] = cfdi_cadena_crypted

        # == Optional check using the XSD ==
        xsd_attachment = self.sudo().env.ref('l10n_mx_edi.xsd_cached_cfdv33_xsd', False)
        xsd_datas = base64.b64decode(xsd_attachment.datas) if xsd_attachment else None

        res = {
            'cfdi_str': etree.tostring(decoded_cfdi_values['cfdi_node'], pretty_print=True, xml_declaration=True, encoding='UTF-8'),
        }

        if xsd_datas:
            try:
                with BytesIO(xsd_datas) as xsd:
                    _check_with_xsd(decoded_cfdi_values['cfdi_node'], xsd)
            except (IOError, ValueError):
                _logger.info(_('The xsd file to validate the XML structure was not found'))
            except Exception as e:
                res['errors'] = str(e).split('\\n')

        return res

    def _l10n_mx_edi_export_payment_cfdi(self, move):
        ''' Create the CFDI attachment for the journal entry passed as parameter being a payment used to pay some
        invoices.

        :param move:    An account.move record.
        :return:        A dictionary with one of the following key:
        * cfdi_str:     A string of the unsigned cfdi of the invoice.
        * error:        An error if the cfdi was not successfully generated.
        '''
        if move.payment_id:
            currency = move.payment_id.currency_id
            total_amount = move.payment_id.amount
        else:
            if move.statement_line_id.foreign_currency_id:
                total_amount = move.statement_line_id.amount_currency
                currency = move.statement_line_id.foreign_currency_id
            else:
                total_amount = move.statement_line_id.amount
                currency = move.statement_line_id.currency_id

        # Process reconciled invoices.
        invoice_vals_list = []
        pay_rec_lines = move.line_ids.filtered(lambda line: line.account_internal_type in ('receivable', 'payable'))
        paid_amount = abs(sum(pay_rec_lines.mapped('amount_currency')))

        mxn_currency = self.env["res.currency"].search([('name', '=', 'MXN')], limit=1)
        if move.currency_id == mxn_currency:
            rate_payment_curr_mxn = None
            paid_amount_comp_curr = paid_amount
        else:
            rate_payment_curr_mxn = move.currency_id._convert(1.0, mxn_currency, move.company_id, move.date, round=False)
            paid_amount_comp_curr = move.company_currency_id.round(paid_amount * rate_payment_curr_mxn)

        for field1, field2 in (('debit', 'credit'), ('credit', 'debit')):
            for partial in pay_rec_lines[f'matched_{field1}_ids']:
                payment_line = partial[f'{field2}_move_id']
                invoice_line = partial[f'{field1}_move_id']
                invoice_amount = partial[f'{field1}_amount_currency']
                exchange_move = invoice_line.full_reconcile_id.exchange_move_id
                invoice = invoice_line.move_id

                if not invoice.l10n_mx_edi_cfdi_request:
                    continue

                if exchange_move:
                    exchange_partial = invoice_line[f'matched_{field2}_ids']\
                        .filtered(lambda x: x[f'{field2}_move_id'].move_id == exchange_move)
                    if exchange_partial:
                        invoice_amount += exchange_partial[f'{field2}_amount_currency']

                if invoice_line.currency_id == payment_line.currency_id:
                    # Same currency
                    amount_paid_invoice_curr = invoice_amount
                    exchange_rate = None
                else:
                    # It needs to be how much invoice currency you pay for one payment currency
                    amount_paid_invoice_comp_curr = payment_line.company_currency_id.round(
                        total_amount * (partial.amount / paid_amount_comp_curr))
                    invoice_rate = abs(invoice_line.amount_currency) / abs(invoice_line.balance)
                    amount_paid_invoice_curr = invoice_line.currency_id.round(partial.amount * invoice_rate)
                    exchange_rate = amount_paid_invoice_curr / amount_paid_invoice_comp_curr
                    exchange_rate = float_round(exchange_rate, precision_digits=6, rounding_method='UP')

                invoice_vals_list.append({
                    'invoice': invoice,
                    'exchange_rate': exchange_rate,
                    'payment_policy': invoice.l10n_mx_edi_payment_policy,
                    'number_of_payments': len(invoice._get_reconciled_payments()) + len(invoice._get_reconciled_statement_lines()),
                    'amount_paid': amount_paid_invoice_curr,
                    'amount_before_paid': min(invoice.amount_residual + amount_paid_invoice_curr, invoice.amount_total),
                    **self._l10n_mx_edi_get_serie_and_folio(invoice),
                })

        payment_method_code = move.l10n_mx_edi_payment_method_id.code
        is_payment_code_emitter_ok = payment_method_code in ('02', '03', '04', '05', '06', '28', '29', '99')
        is_payment_code_receiver_ok = payment_method_code in ('02', '03', '04', '05', '28', '29', '99')
        is_payment_code_bank_ok = payment_method_code in ('02', '03', '04', '28', '29', '99')

        bank_accounts = move.partner_id.commercial_partner_id.bank_ids.filtered(lambda x: x.company_id.id in (False, move.company_id.id))

        partner_bank = bank_accounts[:1].bank_id
        if partner_bank.country and partner_bank.country.code != 'MX':
            partner_bank_vat = 'XEXX010101000'
        else:  # if no partner_bank (e.g. cash payment), partner_bank_vat is not set.
            partner_bank_vat = partner_bank.l10n_mx_edi_vat

        payment_account_ord = re.sub(r'\s+', '', bank_accounts[:1].acc_number or '') or None
        payment_account_receiver = re.sub(r'\s+', '', move.journal_id.bank_account_id.acc_number or '') or None

        cfdi_values = {
            **self._l10n_mx_edi_get_common_cfdi_values(move),
            'invoice_vals_list': invoice_vals_list,
            'currency': currency,
            'amount': total_amount,
            'rate_payment_curr_mxn': rate_payment_curr_mxn,
            'emitter_vat_ord': is_payment_code_emitter_ok and partner_bank_vat,
            'bank_vat_ord': is_payment_code_bank_ok and partner_bank.name,
            'payment_account_ord': is_payment_code_emitter_ok and payment_account_ord,
            'receiver_vat_ord': is_payment_code_receiver_ok and move.journal_id.bank_account_id.bank_id.l10n_mx_edi_vat,
            'payment_account_receiver': is_payment_code_receiver_ok and payment_account_receiver,
            'cfdi_date': move.l10n_mx_edi_post_time.strftime('%Y-%m-%dT%H:%M:%S'),
        }

        cfdi_payment_datetime = datetime.combine(fields.Datetime.from_string(move.date), datetime.strptime('12:00:00', '%H:%M:%S').time())
        cfdi_values['cfdi_payment_date'] = cfdi_payment_datetime.strftime('%Y-%m-%dT%H:%M:%S')

        if cfdi_values['customer'].country_id.l10n_mx_edi_code != 'MEX':
            cfdi_values['customer_fiscal_residence'] = cfdi_values['customer'].country_id.l10n_mx_edi_code
        else:
            cfdi_values['customer_fiscal_residence'] = None

        cfdi = self.env.ref('cfdi4_enterprise.payment20')._render(cfdi_values)
        decoded_cfdi_values = move._l10n_mx_edi_decode_cfdi(cfdi_data=cfdi)
        cfdi_cadena_crypted = cfdi_values['certificate'].sudo().get_encrypted_cadena(decoded_cfdi_values['cadena'])
        decoded_cfdi_values['cfdi_node'].attrib['Sello'] = cfdi_cadena_crypted

        return {
            'cfdi_str': etree.tostring(decoded_cfdi_values['cfdi_node'], pretty_print=True, xml_declaration=True, encoding='UTF-8'),
        }

    






