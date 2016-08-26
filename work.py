# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import datetime
from decimal import Decimal

from trytond.model import fields
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Eval

from trytond.modules.product import price_digits

__all__ = ['Work', 'WorkInvoicedProgress', 'get_service_goods_aux']

STATES = {
    'required': Eval('invoice_product_type') == 'goods',
    'invisible': Eval('invoice_product_type') != 'goods',
    }
DEPENDS = ['invoice_product_type']


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


def get_service_goods_aux(works, service_computation, goods_computation):
    """
    service_coputation is a classmethod function, usually a super call
    goods_computation is an static/lambda function that receives single
        work as param

    It's used on most functions used by get_total(), calling the super for
    service works and doing a "work instance based calculation" for goods works
    """
    service_works = []
    result = {}
    for work in works:
        if work.invoice_product_type == 'service':
            service_works.append(work)
        else:
            result[work.id] = goods_computation(work)
    if service_works:
        result.update(service_computation(service_works))
    return result


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
        digits=(16, Eval('uom_digits', 2)),
        domain=[
            ['OR',
                ('progress_quantity', '=', None),
                [
                    ('progress_quantity', '>=', 0.0),
                    ('progress_quantity', '<=', Eval('quantity', 0.0)),
                    ],
                ]
            ],
        states=STATES, depends=DEPENDS + ['uom_digits', 'quantity',
            'progress_quantity'])
    progress_quantity_func = fields.Function(fields.Float('Progress Quantity',
            digits=price_digits, states=STATES, depends=DEPENDS),
        'total_progress_quantity', setter='set_progress_quantity')

    progress_amount = fields.Function(fields.Numeric('Progress Amount',
            digits=price_digits),
        'get_total')
    percent_progress_amount = fields.Function(
        fields.Numeric('Percent Progress Amount', digits=price_digits),
        'get_total')

    invoiced_quantity = fields.Function(fields.Float('Invoiced Quantity',
            digits=(16, Eval('uom_digits', 2)), depends=['uom_digits']),
        'get_invoiced_quantity')

    @classmethod
    def __setup__(cls):
        super(Work, cls).__setup__()
        for fname in ('product', 'work', 'timesheet_available',
                'timesheet_duration', 'effort_duration', 'total_effort',
                'progress', 'invoiced_duration', 'duration_to_invoice'):
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

    @classmethod
    def set_progress_quantity(cls, works, name, value):
        cls.write(works, {
                'progress_quantity': value,
                })

    def total_progress_quantity(self, name=None):
        return self.progress_quantity

    def get_invoiced_quantity(self, name):
        invoiced_quantity = sum(x.quantity for x in self.invoiced_progress)
        return invoiced_quantity

    @classmethod
    def get_total(cls, works, names):
        # Explanation what it does in project, project_invoice, project_revenue
        # =====================================================================
        # get_total multifield getter for:
        # - project: timesheet_duration, total_effort, total_progress
        # - project_invoice: invoiced_duration, duration_to_invoice,
        #   invoiced_amount
        # - project_revenue: revenue, cost
        #
        # get_total(works, field_name) calls _get_<field_name> (project)
        # _get_invoiced_duration/duration_to_invoice/invoiced_amount calls
        #     _get_invoice_values(works, <field_name>) (project_invoice)
        # _get_invoice_values(works, field_name) calls
        #     _get_<field_name>_<invoice_method> setting default values
        #     previously (project_invoice)
        #     List of called methos:
        #     - _get_invoiced_duration_manual/effort/progrees/timesheet
        #     - _get_duration_to_invoice_manual/effort/progrees/timesheet
        #     - _get_invoiced_amount_manual/effort/progrees/timesheet
        #     All these methods computes their values "directly" except:
        #     - _get_<field_name>_manual do nothing (return empty {})
        #     - _get_invoiced_duration_timesheet(works) calls
        #         _get_duration_timesheet(works, True) (project_invoice)
        #     - _get_duration_to_invoice_timesheet(works) calls
        #         _get_duration_timesheet(works, False) (project_invoice)
        #
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
                    * Decimal(str(work.effort_hours * (work.progress or 0))))
            elif work.invoice_product_type == 'goods':
                amount = ((work.list_price or Decimal(0))
                    * Decimal(str(work.total_progress_quantity())))
            else:
                amount = Decimal(0)
            result[work.id] = amount.quantize(Decimal(str(10 ** - digits)))

        import logging
        logger = logging.getLogger(__name__)
        logger.info(result)
        return result

    @classmethod
    def _get_timesheet_duration(cls, works):
        """Return 0 timedelta for goods works"""
        return get_service_goods_aux(
            works,
            super(Work, cls)._get_timesheet_duration,
            lambda work: datetime.timedelta())

    @classmethod
    def _get_total_effort(cls, works):
        """Return 0 timedelta for goods works"""
        return get_service_goods_aux(
            works,
            super(Work, cls)._get_total_effort,
            lambda work: datetime.timedelta())

    @classmethod
    def _get_total_progress(cls, works):
        """Return 0 for goods works"""
        # TODO: it could replace total_progress_quantity?
        return get_service_goods_aux(
            works,
            super(Work, cls)._get_total_progress,
            lambda work: 0)

    @classmethod
    def _get_invoice_values(cls, works, name):
        if name in ('invoiced_duration', 'duration_to_invoice'):
            service_works = []
            res = {}
            default_value = getattr(cls, 'default_%s' % name)()
            for work in works:
                if work.invoice_product_type == 'goods':
                    res[work.id] = default_value
                else:
                    service_works.append(work)
            if service_works:
                res.update(
                    super(Work, cls)._get_invoice_values(service_works, name))
            return res
        # name == invoiced_amount
        # it will call _get_invoiced_amount_{manual,effort,progress,timesheet}
        return super(Work, cls)._get_invoice_values(works, name)

    @classmethod
    def _get_invoiced_amount_effort(cls, works):
        pool = Pool()
        Currency = pool.get('currency.currency')
        Uom = pool.get('product.uom')

        def __get_invoiced_amount_effort(work):
            currency = work.company.currency
            invoice_line = work.invoice_line
            if invoice_line:
                # If get fields from invoice_line has performance problems,
                # construct a dictionary with used fields
                invoice_currency = (invoice_line.invoice.currency
                    if invoice_line.invoice else invoice_line.currency)
                # It doesn't use invoice_line amount because one invoice
                # line could invoice several works
                unit_price = Uom.compute_price(
                    invoice_line.unit, invoice_line.unit_price, work.uom)
                return Currency.compute(
                    invoice_currency,
                    Decimal(str(work.quantity)) * unit_price,
                    currency)
            return Decimal(0)

        return get_service_goods_aux(
            works,
            super(Work, cls)._get_invoiced_amount_effort,
            __get_invoiced_amount_effort)

    @classmethod
    def _get_invoiced_amount_progress(cls, works):
        pool = Pool()
        Currency = pool.get('currency.currency')
        Uom = pool.get('product.uom')

        def __get_invoiced_amount_progress(work):
            currency = work.company.currency
            amount = Decimal(0)
            for invoiced_progress in work.invoiced_progress:
                invoice_line = invoiced_progress.invoice_line
                if invoice_line:
                    invoice_currency = (invoice_line.invoice.currency
                        if invoice_line.invoice else invoice_line.currency)
                    # It doesn't use invoice_line amount because one
                    # invoice line could invoice several works
                    unit_price = Uom.compute_price(
                        invoice_line.unit, invoice_line.unit_price,
                        work.uom)
                    amount += Currency.compute(
                        invoice_currency,
                        Decimal(str(invoiced_progress.quantity))
                        * unit_price,
                        currency)
            return currency.round(amount)

        return get_service_goods_aux(
            works,
            super(Work, cls)._get_invoiced_amount_progress,
            __get_invoiced_amount_progress)

    @classmethod
    def _get_invoiced_amount_timesheet(cls, works):
        service_works, goods_works = [], []
        for work in works:
            if work.invoice_product_type == 'service':
                service_works.append(work)
            else:
                goods_works.append(work)

        amounts = cls._get_invoiced_amount_progress(goods_works)
        amounts.update(
            super(Work, cls)._get_invoiced_amount_timesheet(service_works))
        return amounts

    @classmethod
    def _get_revenue(cls, works):
        """Return the quantity * list_price for goods works"""
        return get_service_goods_aux(
            works,
            super(Work, cls)._get_revenue,
            lambda work: (Decimal(str(work.quantity))
                * (work.list_price or Decimal(0))))

    @classmethod
    def _get_cost(cls, works):
        """Return the quantity * product's cost price for goods works"""

        works_c = works
        costs = {}
        if hasattr(cls, 'purchase_lines'):
            work_p = [x for x in works if x.purchase_lines]
            costs = super(Work, cls)._get_cost(work_p)
            works_c = [x for x in works if not x.purchase_lines]

        costs.update(get_service_goods_aux(
            works_c,
            super(Work, cls)._get_cost,
            lambda work: (Decimal(str(work.quantity)) *
                work.product_goods.cost_price)))
        return costs

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

        if self.progress_quantity is None:
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
        return []

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
        # TODO: why don't use key['unit'] and avoid conversion here and in lot
        # of places? it's also applicable on project_invoice module
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
