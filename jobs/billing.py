from openerp.osv import osv, fields
from pprint import pprint as pp

class MageIntegrator(osv.osv):
    _inherit = 'mage.integrator'

    def prepare_billing_search_domain(self):
	#TODO Check to make sure invoiced doesnt mean just invoiced, not paid
	#Do not process any order that is invoiced from picking
	#This is handled in the core mage2odoo module. See sale vals payment defaults
        return [('mage_invoice_complete', '=', True),
                ('invoiced', '=', False),
		('state', '!=', 'cancel'),
		('order_policy', '!=', 'picking'),
		('payment_method.journal', '!=', False),
        ]


    def autopay_sale_orders(self, cr, uid, ids, context=None):
	context = {}
	sale_obj = self.pool.get('sale.order')
	search_domain = self.prepare_billing_search_domain()
	sale_ids = sale_obj.search(cr, uid, search_domain, limit=6000)
	if not sale_ids:
	    return True

	return self.process_sale_orders(cr, uid, sale_ids, False)


    def process_sale_orders(self, cr, uid, sale_ids, back_date, context=None):
	sale_obj = self.pool.get('sale.order')
	invoice_obj = self.pool.get('account.invoice')
	picking_obj = self.pool.get('stock.picking')
	voucher_obj = self.pool.get('account.voucher')
	for sale in sale_obj.browse(cr, uid, sale_ids):
	    #We can't process a payment without a payment journal
	    if not sale.payment_method.journal:
		continue

	    backdate = sale.date_order

	    if sale.state == 'draft':
	        sale.action_button_confirm()

	    #If the invoice must be manually created
	    if sale.order_policy == 'manual' and not sale.invoice_ids:
		sale_obj.action_invoice_create(cr, uid, [sale.id], date_invoice=backdate)

	    #TODO: This could cause performance problems
	    for invoice in sale.invoice_ids:

		#TODO: Implement state filter
		if invoice.state != 'draft':
		    'Skipping'
		    continue

		invoice.date_invoice = backdate
		invoice.due_date = backdate
		invoice.signal_workflow('invoice_open')

		voucher = self.prepare_voucher_vals(cr, uid, invoice, backdate, sale.payment_method, context=context)
		voucher_obj.button_proforma_voucher(cr, uid, [voucher.id])
		#This is called by passing variables into context automatically. Left here as reference
#		invoice.signal_workflow('reconciled')
	    cr.commit()

	return True


    def prepare_voucher_vals(self, cr, uid, invoice, backdate, payment_method, context=None):
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

	if backdate:
	    vals.update({
		'date': backdate,
		'create_date': backdate,
	    })

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

                if k == 'line_dr_ids':
                    dr_values = []
                    for each in v:
                        dr_values.append([0, False, each])
                    vals[k] = dr_values
                else:
                    vals[k] = v

	#solves bug where onchange returns out_invoice
	vals['type'] = 'receipt'
	#TODO: See if this is necessary
        if backdate:
            vals.update({
                'date': backdate,
                'create_date': backdate,
            })

        for k, v in vals.items():
            if k == 'line_cr_ids':
                values = []
                for each in v:
                    values.append([0, False, each])
                vals[k] = values
		continue
            else:
                vals[k] = v
		continue
            if k == 'line_dr_ids':
                dr_values = []
                for each in v:
                    dr_values.append([0, False, each])
                vals[k] = dr_values
		continue
            else:
                vals[k] = v
		continue
	pp(vals)

	voucher_id = voucher_obj.create(cr, uid, vals, context=context)
	voucher = voucher_obj.browse(cr, uid, voucher_id)

	return voucher
