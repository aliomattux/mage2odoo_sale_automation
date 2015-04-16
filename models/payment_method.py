from openerp.osv import osv, fields


class PaymentMethod(osv.osv):
    _inherit = 'payment.method'
    _columns = {
	'automatic_payment': fields.boolean('Automatic Payment Validation'),
    }
