# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields
from trytond.pool import PoolMeta
from trytond.pyson import Bool, Eval

__all__ = ['Configuration']


class Configuration:
    __metaclass__ = PoolMeta
    __name__ = 'work.configuration'
    invoice_product_type = fields.Property(fields.Selection([
            ('service', 'Service'),
            ('goods', 'Goods'),
        ], 'Invoice Product Type', states={
            'required': Bool(Eval('context', {}).get('company')),
        }))
    product_goods = fields.Property(fields.Many2One(
        'product.product', 'Product Goods', domain=[
            ('type', '!=', 'service'),
        ], states={
            'invisible': Eval('invoice_product_type') == 'service',
        }, depends=['invoice_product_type']))
