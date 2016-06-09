# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import datetime
from decimal import Decimal

from trytond.model import fields
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Eval

from trytond.modules.product import price_digits

__all__ = ['Work', 'WorkInvoicedProgress']

STATES = {
    'required': Eval('invoice_product_type') == 'goods',
    'invisible': Eval('invoice_product_type') != 'goods',
    }
DEPENDS = ['invoice_product_type', 'type']


class WorkInvoicedProgress:
    __name__ = 'project.work.invoiced_progress'
    __metaclass__ = PoolMeta
    uom = fields.Function(fields.Many2One('product.uom', 'UoM'),
        'get_uom')
    uom_digits = fields.Function(fields.Integer('UoM Digits'),
        'get_uom_digits')
    quantity = fields.Float('Quantity', digits=(16, Eval('uom_digits', 2)),
        depends=['uom_digits'])

    def get_uom(self, name):
        return self.work.uom.id if self.work.uom else None

    @staticmethod
    def default_uom_digits():
        return 2

    @fields.depends('uom')
    def get_uom_digits(self, name):
        if self.work.uom:
            return self.work.uom.digits
        return 2


class Work:
    __name__ = 'project.work'
    __metaclass__ = PoolMeta

    invoice_product_type = fields.Selection([
            ('service', 'Service'),
            ('goods', 'Goods'),
            ], 'Invoice Product Type', required=True, select=True)
    # TODO: we can use project_revenue's product field and change the domain
    product_goods = fields.Many2One('product.product', 'Product for Goods',
        states=STATES, depends=DEPENDS)
    product_goods_uom_category = fields.Function(
        fields.Many2One('product.uom.category', 'Product Uom Category'),
        'on_change_with_product_goods_uom_category')
    uom = fields.Many2One('product.uom', 'UoM', domain=[
            ('category', '=', Eval('product_goods_uom_category', -1)),
            ],
        states=STATES, depends=DEPENDS + ['product_goods_uom_category'])
    uom_digits = fields.Function(fields.Integer('UoM Digits'),
        'on_change_with_uom_digits')
    quantity = fields.Float('Quantity', digits=(16, Eval('uom_digits', 2)),
        states=STATES, depends=DEPENDS + ['uom_digits'])
    progress_quantity = fields.Float('Progress Quantity',
        digits=(16, Eval('uom_digits', 2)), domain=[
            ['OR',
                ('progress_quantity', '=', None),
                [
                    ('progress_quantity', '>=', 0.0),
                    ('progress_quantity', '<=', Eval('quantity', 0.0)),
                    ],
                ]
            ],
        states=STATES, depends=DEPENDS + ['uom_digits', 'quantity'])
    progress_amount = fields.Function(fields.Numeric('Progress Amount',
            digits=price_digits),
        'get_total')
    percent_progress_amount = fields.Function(
        fields.Numeric('Percent Progress Amount', digits=price_digits),
        'get_total')

    @classmethod
    def __setup__(cls):
        super(Work, cls).__setup__()
        for fname in ('product', 'work', 'timesheet_available',
                'timesheet_duration', 'effort_duration', 'total_effort',
                'progress'):
            field_states = getattr(cls, fname).states
            if field_states.get('invisible'):
                field_states['invisible'] = (field_states['invisible']
                    | (Eval('invoice_product_type') == 'goods'))
            else:
                field_states['invisible'] = (
                    Eval('invoice_product_type') == 'goods')

            field_depends = getattr(cls, fname).depends
            if 'invoice_product_type' not in field_depends:
                field_depends.append('invoice_product_type')
        if 'invoice' in cls._buttons:
            cls._buttons['invoice']['readonly'] = False

    @classmethod
    def view_attributes(cls):
        return [
            ('/form/notebook/page[@id="general"]/separator[@id="goods"]',
                'states', {
                    'invisible': Eval('invoice_product_type') != 'goods',
                    }),
            ('/form/notebook/page[@id="general"]/separator[@id="service"]',
                'states', {
                    'invisible': Eval('invoice_product_type') != 'service',
                    }),
            ]

    @staticmethod
    def default_invoice_product_type():
        return 'service'

    @fields.depends('product_goods')
    def on_change_product_goods(self):
        if self.product_goods:
            self.name = self.product_goods.rec_name
            self.uom = self.product_goods.default_uom
            self.uom_digits = self.product_goods.default_uom.digits
            self.list_price = self.product_goods.list_price
        else:
            self.uom = None
            self.uom_digits = None

    @fields.depends('product_goods')
    def on_change_with_product_goods_uom_category(self, name=None):
        if self.product_goods:
            return self.product_goods.default_uom_category.id

    @staticmethod
    def default_uom_digits():
        return 2

    @fields.depends('uom')
    def on_change_with_uom_digits(self, name=None):
        if self.uom:
            return self.uom.digits
        return 2

    # TODO: remove, it isn't necessary
    # @fields.depends('quantity', 'invoice_product_type', 'uom',
    #     'effort_duration')
    # def on_change_with_quantity(self, name=None):
    #     pool = Pool()
    #     ModelData = pool.get('ir.model.data')
    #     quantity = self.quantity or 0.0
    #     if self.invoice_product_type == 'service':
    #         uom = self.uom
    #         effort_duration = self.effort_duration
    #         if (uom and uom.id == ModelData.get_id('product', 'uom_cat_time')
    #                 and effort_duration):
    #             total_seconds = effort_duration.total_seconds()
    #             quantity = total_seconds * uom.rate
    #     return quantity

    @staticmethod
    def default_progress_quantity():
        return 0

    # TODO: remove, it isn't necessary
    # @fields.depends('progress_quantity', 'quantity')
    # def on_change_with_progress(self):
    #     if self.quantity:
    #         return (self.progress_quantity or 0.0) / self.quantity
    #     return 0.0

    @property
    def total_progress_quantity(self):
        # TODO: it's necessary? it's extended in project_certification
        # pool = Pool()
        # Uom = pool.get('product.uom')
        # if self.product_goods and self.uom:
        #     return Uom.compute_qty(
        #             self.uom, self.progress_quantity or 0,
        #             self.product_goods.default_uom)
        return self.progress_quantity

    @classmethod
    def get_total(cls, works, names):
        new_names = names[:]
        if 'percent_progress_amount' in names:
            if 'progress_amount' not in names:
                new_names.append('progress_amount')
            if 'revenue' not in names:
                new_names.append('revenue')
            new_names.remove('percent_progress_amount')

        result = super(Work, cls).get_total(works, new_names)

        if 'percent_progress_amount' in names:
            p_amount = result['progress_amount']
            revenue = result['revenue']
            digits = cls.percent_progress_amount.digits[1]
            pp_amount = {}
            for work in works:
                if revenue[work.id] == Decimal(0):
                    pp_amount[work.id] = Decimal(0)
                else:
                    pp_amount[work.id] = (p_amount[work.id] / revenue[work.id]
                        ).quantize(Decimal(str(10 ** - digits)))
            result['percent_progress_amount'] = pp_amount
        for key in result.keys():
            if key not in names:
                del result[key]
        return result

    @classmethod
    def _get_progress_amount(cls, works):
        digits = cls.progress_amount.digits[1]
        result = {}
        for work in works:
            if work.invoice_product_type == 'service':
                amount = ((work.list_price or Decimal(0))
                    * Decimal(str(work.timesheet_duration_hours)))
            elif work.invoice_product_type == 'goods':
                amount = ((work.list_price or Decimal(0))
                    * Decimal(str(work.total_progress_quantity)))
            else:
                amount = Decimal(0)
            result[work.id] = amount.quantize(Decimal(str(10 ** - digits)))
        return result

    @classmethod
    def _get_invoiced_duration(cls, works):
        res = dict.fromkeys((w.id for w in works), datetime.timedelta())
        d_works = [x for x in works if x.invoice_product_type == 'service']
        res.update(super(Work, cls)._get_invoiced_duration(d_works))
        return res

    @classmethod
    def _get_duration_to_invoice(cls, works):
        res = dict.fromkeys((w.id for w in works), datetime.timedelta())
        d_works = [x for x in works if x.invoice_product_type == 'service']
        res.update(super(Work, cls)._get_duration_to_invoice(d_works))
        return res

    @classmethod
    def _get_invoiced_amount_timesheet(cls, works):
        res = dict.fromkeys((w.id for w in works), Decimal(0))
        d_works = [x for x in works if x.invoice_product_type == 'service']
        res.update(super(Work, cls)._get_invoiced_amount_timesheet(d_works))
        return res

    @classmethod
    def _get_duration_to_invoice_progress(cls, works):
        return cls._get_duration_to_invoice_timesheet(works)

    @classmethod
    def _get_invoiced_amount_effort(cls, works):
        Currency = Pool().get('currency.currency')

        res = dict.fromkeys((w.id for w in works), Decimal(0))
        d_works = [x for x in works if x.invoice_product_type == 'service']
        g_works = [x for x in works if x.invoice_product_type == 'goods']
        res.update(super(Work, cls)._get_invoiced_amount_effort(d_works))

        for work in g_works:
            currency = work.company.currency
            invoice_line = work.invoice_line
            if invoice_line:
                invoice_currency = (invoice_line.invoice.currency
                    if invoice_line.invoice else invoice_line.currency)
                res[work.id] = Currency.compute(invoice_currency,
                    invoice_line.unit_price *
                    Decimal(str(invoice_line.quantity)),
                    currency)
        return res

    @classmethod
    def _get_invoiced_amount_progress(cls, works):
        pool = Pool()
        Currency = pool.get('currency.currency')
        InvoicedProgress = pool.get('project.work.invoiced_progress')

        res = dict.fromkeys((w.id for w in works), Decimal(0))
        d_works = [x for x in works if x.invoice_product_type == 'service']
        g_works = [x for x in works if x.invoice_product_type == 'goods']

        res.update(super(Work, cls)._get_invoiced_amount_progress(d_works))

        for work in g_works:
            currency = work.company.currency
            invoiced_progresses = InvoicedProgress.search([
                ('work', '=', work.id)
                ])
            for invoiced_progress in invoiced_progresses:
                invoice_line = invoiced_progress.invoice_line
                if invoice_line:
                    invoice_currency = (invoice_line.invoice.currency
                        if invoice_line.invoice else invoice_line.currency)
                    res[work.id] += Currency.compute(invoice_currency,
                        invoice_line.unit_price *
                        Decimal(str(invoice_line.quantity)),
                        currency)
        return res

    @classmethod
    def _get_revenue(cls, works):
        result = super(Work, cls)._get_revenue(works)
        for work in works:
            if work.invoice_product_type == 'service':
                result[work.id] = (Decimal(str(work.quantity))
                    * (work.list_price or Decimal(0)))
        return result

    @classmethod
    def _get_cost(cls, works):
        result = super(Work, cls)._get_cost(works)
        for work in works:
            if work.invoice_product_type == 'service':
                if work.product_goods:
                    result[work.id] = (Decimal(str(work.quantity)) *
                            work.product_goods.cost_price)
                else:
                    result[work.id] = Decimal(0)
        return result

    def _get_lines_to_invoice_effort(self):
        pool = Pool()
        Uom = pool.get('product.uom')

        if self.invoice_product_type == 'service':
            return super(Work, self)._get_lines_to_invoice_effort()

        if self.invoice_line or not self.quantity or self.state != 'done':
            return []

        if not self.product_goods:
            self.raise_user_error('missing_product', (self.rec_name,))
        elif self.list_price is None:
            self.raise_user_error('missing_list_price', (self.rec_name,))

        quantity = Uom.compute_qty(
            self.uom, self.quantity, self.product_goods.default_uom)
        return [{
                'product': self.product_goods,
                'quantity': quantity,
                'unit': self.uom,
                'unit_price': self.list_price,
                'description': self.name,
                'origin': self,
                }]

    def _get_lines_to_invoice_progress(self):
        pool = Pool()
        InvoicedProgress = pool.get('project.work.invoiced_progress')

        if self.invoice_product_type == 'service':
            return super(Work, self)._get_lines_to_invoice_progress()

        if self.progress is None or self.state != 'done':
            return []

        invoiced_quantity = sum(x.quantity for x in self.invoiced_progress)

        quantity = self.progress_quantity - invoiced_quantity
        if quantity > 0:
            if not self.product_goods:
                self.raise_user_error('missing_product', (self.rec_name,))
            elif self.list_price is None:
                self.raise_user_error('missing_list_price', (self.rec_name,))
            invoiced_progress = InvoicedProgress(work=self,
                quantity=quantity)
            return [{
                    'product': self.product_goods,
                    'quantity': quantity,
                    'unit': self.uom,
                    'unit_price': self.list_price,
                    'origin': invoiced_progress,
                    'description': self.name,
                    }]

    def _get_lines_to_invoice_timesheet(self):
        if self.invoice_product_type == 'service':
            return super(Work, self)._get_lines_to_invoice_timesheet()
        return self._get_lines_to_invoice_progress()

    def _group_lines_to_invoice_key(self, line):
        pool = Pool()
        ModelData = pool.get('ir.model.data')
        Uom = pool.get('product.uom')

        res = super(Work, self)._group_lines_to_invoice_key(line)
        # use hour as unit for service works
        hour = Uom(ModelData.get_id('product', 'uom_hour'))
        return res + (('unit', line.get('unit', hour)),)

    def _get_invoice_line(self, key, invoice, lines):
        "Return a invoice line for the lines"
        pool = Pool()
        InvoiceLine = pool.get('account.invoice.line')
        ModelData = pool.get('ir.model.data')
        Uom = pool.get('product.uom')

        hour = Uom(ModelData.get_id('product', 'uom_hour'))

        unit = key['unit']
        if unit == hour:
            return super(Work, self)._get_invoice_line(key, invoice, lines)

        quantity = sum(l['quantity'] for l in lines)
        product = key['product']

        invoice_line = InvoiceLine()
        invoice_line.type = 'line'
        invoice_line.quantity = Uom.compute_qty(unit, quantity,
            product.default_uom)
        invoice_line.unit = product.default_uom
        invoice_line.product = product
        invoice_line.description = key['description']
        invoice_line.account = product.account_revenue_used
        invoice_line.unit_price = Uom.compute_price(
            unit, key['unit_price'], product.default_uom)

        taxes = []
        pattern = invoice_line._get_tax_rule_pattern()
        party = invoice.party
        for tax in product.customer_taxes_used:
            if party.customer_tax_rule:
                tax_ids = party.customer_tax_rule.apply(tax, pattern)
                if tax_ids:
                    taxes.extend(tax_ids)
                continue
            taxes.append(tax.id)
        if party.customer_tax_rule:
            tax_ids = party.customer_tax_rule.apply(None, pattern)
            if tax_ids:
                taxes.extend(tax_ids)
        invoice_line.taxes = taxes
        return invoice_line
