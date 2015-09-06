#This module, although written from scrach and is a different implementation than sale_automatic_workflow,
#was inspired by it

from openerp.osv import osv, fields
#from pprint import pprint as pp


class MageIntegrator(osv.osv):
    _inherit = 'mage.integrator'

    def prepare_shipping_search_domain(self):
	#Check orders that are marked shipped in Magento
	#Not shipped in Odoo (Calculated field so be careful)
        return [('mage_shipment_complete', '=', True),
                ('shipped', '=', False),
		('state', 'not in', ['done', 'cancel'])
        ]


    def autodeliver_sale_orders(self, cr, uid, ids, context=None):
	#This feature is useful for initial imports into an instance
	#It is NOT recommended to use this as a long term solution
	#You could have inaccurate stock and problems with fulfillment
        context = {}

        sale_obj = self.pool.get('sale.order')
        picking_obj = self.pool.get('stock.picking')
        move_obj = self.pool.get('stock_move')
        search_domain = self.prepare_shipping_search_domain()
	#Limit the amount of records to process in case of performance
        sale_ids = sale_obj.search(cr, uid, search_domain)
        if not sale_ids:
            return True

        return self.ship_sale_orders(cr, uid, sale_ids)


    def ship_sale_orders(self, cr, uid, sale_ids):
        sale_obj = self.pool.get('sale.order')
        picking_obj = self.pool.get('stock.picking')
        move_obj = self.pool.get('stock_move')
	for sale in sale_obj.browse(cr, uid, sale_ids):
	    backdate = sale.date_order
	    #If the order is not confirmed and requires pre-payment we cant process it
	    if sale.state == 'draft' and sale.order_policy != 'prepaid':
		sale.action_button_confirm()

	    #If the order requires pre-payment and it is not paid, we can't deliver
	    #TODO, this could cause performance problems
	    if sale.state == 'prepaid' and not sale.invoiced:
		continue

	    if not sale.picking_ids:
		pass
		#TODO: Add functionality to create picking if necessary

	    #Search for pickings not done as there many be many
	    #TODO: Possible to do this without a search
	    picking_ids = picking_obj.search(cr, uid, [('sale', '=', sale.id), \
		('state', 'not in', ['done', 'cancel'])])

	    self.process_pickings(cr, uid, picking_ids, backdate=backdate)


    def automate_only_pickings(self, cr, uid, ids, context=None):
	picking_obj = self.pool.get('stock.picking')
	picking_ids = picking_obj.search(cr, uid, [\
		('state', 'in', ['waiting', 'confirmed', 'partially_available', 'assigned']),
		('picking_type_id.code', '=', 'outgoing'),
	])
	return self.process_pickings(cr, uid, picking_ids)

    def process_pickings(self, cr, uid, picking_ids, backdate=False):
	picking_obj = self.pool.get('stock.picking')
	for picking in picking_obj.browse(cr, uid, picking_ids):
	    if picking.state in ['confirmed', 'waiting']:
		picking_obj.force_assign(cr, uid, [picking.id])

	    picking.do_transfer()
#	    backdate = picking.sale.date_order

	    if backdate:
		picking.date = backdate
	        picking.create_date = backdate
		picking.date_done = backdate
		cr.execute("UPDATE stock_move SET create_date = '%s', date = '%s' \
			WHERE picking_id = %s"%(backdate, backdate, picking.id
		))
	return True
