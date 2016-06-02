# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import datetime

from decimal import Decimal
from trytond.model import fields
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Bool, Eval, If
from trytond.modules.product import price_digits

__all__ = ['Work', 'WorkInvoicedProgress']

STATES = {
    'required': Bool(Eval('invoice_product_type') == 'goods'),
    'invisible': ~Bool(Eval('invoice_product_type') == 'goods'),
    }


class WorkInvoicedProgress:
    __name__ = 'project.work.invoiced_progress'
    __metaclass__ = PoolMeta

    quantity = fields.Float('Quantity')


class Work:
    __name__ = 'project.work'
    __metaclass__ = PoolMeta

    product_goods = fields.Many2One('product.product', 'Product for Goods',
        states=STATES, depends=['product'])
    uom = fields.Many2One('product.uom', 'UoM', states=STATES, domain=[
            If(Bool(Eval('product_uom_category')),
                ('category', '=', Eval('product_uom_category')),
                ('category', '!=', -1)),
            ], depends=['product_uom_category'])
    product_uom_category = fields.Function(
        fields.Many2One('product.uom.category', 'Product Uom Category'),
        'on_change_with_product_uom_category')
    uom_digits = fields.Function(fields.Integer('UoM Digits'),
        'on_change_with_uom_digits')
    quantity = fields.Float('Quantity', digits=(16, Eval('uom_digits', 2)),
        states=STATES, depends=['uom_digits'])
    unit_price = fields.Numeric('Unit Price', digits=price_digits,
        states=STATES)
    progress_quantity = fields.Float('Progress Quantity', digits=(16,
                Eval('uom_digits', 2)),
        states={
            'invisible': Bool(Eval('invoice_product_type') == 'service'),
            },
        depends=['uom_digits'])
    progress_amount = fields.Function(fields.Float('Progress Amount'),
        'get_total')
    percent_progress_amount = fields.Function(fields.Float(
        'Percent Progress Amount'), 'get_total')

    total_progress_quantity = fields.Function(fields.Float(
            'Total Progress Quantity',
            digits=(16, Eval('uom_digits', 2)),
            depends=['uom_digits']),
        '_get_total_progress_quantity')

    invoice_product_type = fields.Selection([('service', 'Service'),
        ('goods', 'Goods')],
        'Invoice Product Type', required=True)

    @classmethod
    def __setup__(cls):
        super(Work, cls).__setup__()
        cls.product.states['invisible'] = Bool(
            Eval('invoice_product_type') == 'goods')
        if 'product_goods' not in cls.product.depends:
            cls.product.depends.append('product_goods')
        cls.work.states['invisible'] = Bool(
            Eval('invoice_product_type') == 'goods')
        if 'product_goods' not in cls.work.depends:
            cls.work.depends.append('product_goods')
        cls.timesheet_available.states['invisible'] = Bool(
            Eval('invoice_product_type') == 'goods')
        if 'product_goods' not in cls.timesheet_available.depends:
            cls.timesheet_available.depends.append('product_goods')

        cls.effort_duration.states['invisible'] = Bool(
            Eval('invoice_product_type') == 'goods')
        if 'product_goods' not in cls.effort_duration.depends:
            cls.effort_duration.depends.append('product_goods')
        if 'invoice' in cls._buttons:
            cls._buttons['invoice']['readonly'] = False

    @staticmethod
    def default_uom_digits():
        return 2

    @fields.depends('quantity', 'effort_duration', 'uom',
        'invoice_product_type')
    def on_change_with_quantity(self, name=None):
        quantity = self.quantity or 0.0
        if self.invoice_product_type == 'service':
            uom = self.uom
            effort_duration = self.effort_duration
            if uom and uom.category.name == 'Time' and effort_duration:
                total_seconds = effort_duration.total_seconds()
                quantity = total_seconds * uom.rate
        return quantity

    @fields.depends('uom')
    def on_change_with_uom_digits(self, name=None):
        if self.uom:
            return self.uom.digits
        return 2

    @fields.depends('product_goods')
    def on_change_with_product_uom_category(self, name=None):
        if self.product_goods:
            return self.product_goods.default_uom_category.id

    @fields.depends('product_goods')
    def on_change_product_goods(self):
        if self.product_goods:
            self.name = self.product_goods.rec_name
            self.uom = self.product_goods.default_uom
            self.uom_digits = self.product_goods.default_uom.digits
            self.unit_price = self.product_goods.list_price
        else:
            self.uom = None
            self.uom_digits = None

    @fields.depends('progress_quantity', 'quantity')
    def on_change_with_progress(self):
        if self.quantity:
            return (self.progress_quantity or 0.0) / self.quantity
        return 0.0

    @classmethod
    def _get_total_progress_quantity(cls, works, name):
        pool = Pool()
        Uom = pool.get('product.uom')
        result = {w.id: 0 for w in works}
        result.update({w.id: Uom.compute_qty(
                    w.uom, w.progress_quantity or 0,
                    w.product_goods.default_uom)
                for w in works if w.product_goods and w.uom})
        return result

    @classmethod
    def get_total(cls, works, names):
        if 'percent_progress_amount' in names:
            if 'progress_amount' not in names:
                names.append('progress_amount')
            if 'revenue' not in names:
                names.append('revenue')

        result = super(Work, cls).get_total(works, names)

        if 'percent_progress_amount' in names:
            p_amount = result['progress_amount']
            revenue = result['revenue']
            pp_amount = result['percent_progress_amount']
            for w in works:
                if revenue[w.id] == 0:
                    pp_amount[w.id] = 0
                else:
                    pp_amount[w.id] = round(p_amount[w.id] /
                        float(revenue[w.id]), 2)
        return result

    @classmethod
    def _get_progress_amount(cls, works):
        result = {w.id: 0 for w in works}
        for w in works:
            amount = float(w.list_price or 0) * w.timesheet_duration_hours
            amount += (w.total_progress_quantity or 0) * \
                float(w.unit_price or 0)
            result[w.id] = amount
        return result

    @classmethod
    def _get_percent_progress_amount(cls, works):
        result = {w.id: 0 for w in works}
        for w in works:
            amount = float(w.list_price or 0) * \
                (w.timesheet_duration_hours or 0)
            amount += (w.total_progress_quantity or 0) * \
                float(w.unit_price or 0)
            if w.revenue == 0:
                result[w.id] = 0
            else:
                result[w.id] = amount / float(w.revenue)
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
        return cls._get_duration_to_invoice_timesheet(works, False)

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
            if work.product_goods:
                result[work.id] = (Decimal(str(work.quantity)) *
                        work.product_goods.list_price)
        return result

    @classmethod
    def _get_cost(cls, works):
        result = super(Work, cls)._get_cost(works)
        for work in works:
            if work.product_goods:
                result[work.id] = (Decimal(str(work.quantity)) *
                        work.product_goods.cost_price)
        return result

    # TODO: diria que no fa falta.
    def _get_lines_to_invoice_timesheet(self):
        parent = self
        while getattr(parent, 'parent', None) and parent.type != 'project':
            parent = self.parent
        if parent.invoice_product_type == 'service':
            return super(Work, self)._get_lines_to_invoice_timesheet()
        return []

    def _get_lines_to_invoice_effort(self):
        if self.invoice_product_type == 'service':
            return super(Work, self)._get_lines_to_invoice_effort()

        res = []
        if (not self.invoice_line and self.unit_price and
                self.state == 'done'):
            pool = Pool()
            Uom = pool.get('product.uom')
            quantity = Uom.compute_qty(self.uom, self.quantity or
                Decimal(0), self.product_goods.default_uom)
            res.append({
                'product': self.product_goods,
                'quantity': quantity,
                'unit': self.product_goods.default_uom,
                'unit_price': self.unit_price,
                'description': self.product_goods.name,
                'origin': self,
                })
        return res

    def _get_lines_to_invoice_progress(self):
        pool = Pool()
        Uom = pool.get('product.uom')
        InvoicedProgress = pool.get('project.work.invoiced_progress')

        if not self.product_goods:
            return super(Work, self)._get_lines_to_invoice_progress()

        res = []
        if self.progress is None:
            return res

        invoiced_quantity = sum(x.quantity for x in self.invoiced_progress)
        progress_quantity = Uom.compute_qty(self.uom,
            self.progress_quantity or Decimal(0),
                self.product_goods.default_uom)

        if progress_quantity == invoiced_quantity:
            return res

        quantity = progress_quantity - invoiced_quantity
        invoiced_progress = InvoicedProgress(work=self,
            quantity=quantity)
        res.append({
                'product': self.product_goods,
                'quantity': quantity,
                'unit': self.product_goods.default_uom,
                'unit_price': self.unit_price,
                'origin': invoiced_progress,
                'description': self.name,
                })

        return res

    def _group_lines_to_invoice_key(self, line):
        res = super(Work, self)._group_lines_to_invoice_key(line)
        if 'unit' in line:
            res += (('unit', line['unit']),)
        return res

    def _get_invoice_line(self, key, invoice, lines):
        "Return a invoice line for the lines"

        pool = Pool()
        InvoiceLine = pool.get('account.invoice.line')
        ModelData = pool.get('ir.model.data')
        Uom = pool.get('product.uom')

        hour = Uom(ModelData.get_id('product', 'uom_hour'))

        product = key['product']
        if product.default_uom == hour:
            return super(Work, self)._get_invoice_line(key, invoice, lines)

        quantity = sum(l['quantity'] for l in lines)
        invoice_line = InvoiceLine()
        invoice_line.type = 'line'
        invoice_line.quantity = Uom.compute_qty(key['unit'], quantity,
            product.default_uom)
        invoice_line.unit = product.default_uom
        invoice_line.product = product
        invoice_line.description = key['description']
        invoice_line.account = product.account_revenue_used
        invoice_line.unit_price = Uom.compute_price(key['unit'],
            key['unit_price'], product.default_uom)

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
