# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from . import configuration
from . import work


def register():
    Pool.register(
        configuration.Configuration,
        work.Work,
        work.WorkInvoicedProgress,
        module='project_product', type_='model')
