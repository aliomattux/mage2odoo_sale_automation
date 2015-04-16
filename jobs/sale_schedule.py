#This module, although written from scrach and is a different implementation than sale_automatic_workflow,
#was inspired by it

from openerp.osv import osv, fields
#from pprint import pprint as pp


class MageIntegrator(osv.osv):
    _inherit = 'mage.integrator'

    def prepare_search_domain(self):
	return [('state', '=', 'draft'),
		('payment_method.automatic_payment', '=', True)
	]


    def autopay_sale_orders(self, cr, uid, ids, context=None):
	context = {}

	sale_obj = self.pool.get('sale.order')
	invoice_obj = self.pool.get('account.invoice')
	voucher_obj = self.pool.get('account.voucher')
	search_domain = self.prepare_search_domain()
	sale_ids = sale_obj.search(cr, uid, search_domain, limit=100)
	if not sale_ids:
	    return True

	for sale in sale_obj.browse(cr, uid, sale_ids):
	    sale.action_button_confirm()

	    for invoice in sale.invoice_ids:
		if invoice.state not in ['confirm', 'draft']:
		    continue

		if invoice.state == 'draft':
		    invoice.signal_workflow('invoice_open')

		voucher = self.prepare_voucher_vals(cr, uid, invoice, sale.payment_method, context=context)
		voucher_obj.button_proforma_voucher(cr, uid, [voucher.id])
		#This is called by passing variables into context automatically. Left here as reference
#		invoice.signal_workflow('reconciled')

	return True


    def prepare_voucher_vals(self, cr, uid, invoice, payment_method, context=None):
	voucher_obj = self.pool.get('account.voucher')
	journal_id = payment_method.journal.id

	if not context:
	    context = {}

	context.update({
		'close_after_process': True,
		'invoice_id': invoice.id,
		'invoice_type': invoice.type,
		'payment_expected_currency': invoice.currency_id.id,
	})

	vals = {
                'partner_id': self.pool.get('res.partner')._find_accounting_partner(invoice.partner_id).id,
                'amount': invoice.type in ('out_refund', 'in_refund') and -invoice.residual or invoice.residual,
                'reference': invoice.name,
		'type': 'receipt',
		'journal_id': journal_id,
		'company_id': invoice.company_id.id,

	}

	#In the UI all vals are loaded into context. Add them into context in case they are retrieved from functions
	context.update(vals)

	#This is set as default
	payment_rate = 1.0
	payment_currency_rate = voucher_obj._get_payment_rate_currency(cr, uid, context=context)

	#In the UI when you initialize a new voucher (pay customer form) all of these events are called
	#Simulate these events happing with scripting so all of the prepared vals/calculations are run

	partner_vals = voucher_obj.onchange_partner_id(cr, uid, False, invoice.partner_id.id, \
		journal_id, vals['amount'], invoice.currency_id.id, vals['type'], invoice.date_invoice
	)
	updated_vals = voucher_obj.onchange_journal_voucher(cr, uid, False, \
		False, False, vals['amount'], invoice.partner_id.id, \
		journal_id, invoice.type
	)

	amount_vals = voucher_obj.onchange_amount(cr, uid, [], vals['amount'], \
		payment_rate, vals['partner_id'], vals['journal_id'], invoice.currency_id.id, vals['type'], \
		invoice.date_invoice, payment_currency_rate, invoice.company_id.id, context=context \
	)

	#Combine all of the onchange event vals into a prepared dict
	onchange_vals = [partner_vals, updated_vals, amount_vals]
	for change_vals in onchange_vals:
            for k, v in change_vals['value'].items():
                if k == 'line_cr_ids':
                    values = []
                    for each in v:
                        values.append([0, False, each])
                    vals[k] = values
                else:
                    vals[k] = v

	#solves bug where onchange returns out_invoice
	vals['type'] = 'receipt'

	voucher_id = voucher_obj.create(cr, uid, vals)
	voucher = voucher_obj.browse(cr, uid, voucher_id)

	return voucher

