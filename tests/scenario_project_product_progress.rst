=================================
Project Product Progress Scenario
=================================

Imports::

    >>> import datetime
    >>> from dateutil.relativedelta import relativedelta
    >>> from decimal import Decimal
    >>> from proteus import config, Model, Wizard
    >>> from trytond.modules.company.tests.tools import create_company, \
    ...     get_company
    >>> from trytond.modules.account.tests.tools import create_chart, \
    ...     get_accounts
    >>> from trytond.modules.account_invoice.tests.tools import \
    ...     create_payment_term
    >>> today = datetime.date.today()

Create database::

    >>> config = config.set_trytond()
    >>> config.pool.test = True

Install project_product::

    >>> Module = Model.get('ir.module')
    >>> module, = Module.find([
    ...         ('name', '=', 'project_product'),
    ...     ])
    >>> module.click('install')
    >>> Wizard('ir.module.install_upgrade').execute('upgrade')

Create company::

    >>> _ = create_company()
    >>> company = get_company()

Create chart of accounts::

    >>> _ = create_chart(company)
    >>> accounts = get_accounts(company)
    >>> revenue = accounts['revenue']

Reload the context::

    >>> User = Model.get('res.user')
    >>> Group = Model.get('res.group')
    >>> config._context = User.get_preferences(True, config.context)

Create project user::

    >>> project_user = User()
    >>> project_user.name = 'Project'
    >>> project_user.login = 'project'
    >>> project_user.main_company = company
    >>> project_group, = Group.find([('name', '=', 'Project Administration')])
    >>> timesheet_group, = Group.find([('name', '=', 'Timesheet Administration')])
    >>> project_user.groups.extend([project_group, timesheet_group])
    >>> project_user.save()

Create project invoice user::

    >>> project_invoice_user = User()
    >>> project_invoice_user.name = 'Project Invoice'
    >>> project_invoice_user.login = 'project_invoice'
    >>> project_invoice_user.main_company = company
    >>> project_invoice_group, = Group.find([('name', '=', 'Project Invoice')])
    >>> project_group, = Group.find([('name', '=', 'Project Administration')])
    >>> project_invoice_user.groups.extend(
    ...     [project_invoice_group, project_group])
    >>> project_invoice_user.save()

Create payment term::

    >>> payment_term = create_payment_term()
    >>> payment_term.save()

Create customer::

    >>> Party = Model.get('party.party')
    >>> customer = Party(name='Customer')
    >>> customer.customer_payment_term = payment_term
    >>> customer.save()

Create employee::

    >>> Employee = Model.get('company.employee')
    >>> employee = Employee()
    >>> party = Party(name='Employee')
    >>> party.save()
    >>> employee.party = party
    >>> employee.company = company
    >>> employee.save()

Create products::

    >>> ProductUom = Model.get('product.uom')
    >>> unit, = ProductUom.find([('name', '=', 'Unit')])
    >>> hour, = ProductUom.find([('name', '=', 'Hour')])
    >>> Product = Model.get('product.product')
    >>> ProductTemplate = Model.get('product.template')
    >>> service = Product()
    >>> template = ProductTemplate()
    >>> template.name = 'Service'
    >>> template.default_uom = hour
    >>> template.type = 'service'
    >>> template.list_price = Decimal('20')
    >>> template.cost_price = Decimal('5')
    >>> template.account_revenue = revenue
    >>> template.save()
    >>> service.template = template
    >>> service.save()
    >>> good = Product()
    >>> template = ProductTemplate()
    >>> template.name = 'Good'
    >>> template.default_uom = unit
    >>> template.type = 'goods'
    >>> template.list_price = Decimal('100')
    >>> template.cost_price = Decimal('50')
    >>> template.account_revenue = revenue
    >>> template.save()
    >>> good.template = template
    >>> good.save()

Create a Project::

    >>> config.user = project_user.id
    >>> ProjectWork = Model.get('project.work')
    >>> TimesheetWork = Model.get('timesheet.work')
    >>> project = ProjectWork()
    >>> project.name = 'Test progress'
    >>> project.type = 'project'
    >>> project.party = customer
    >>> project.project_invoice_method = 'progress'
    >>> project.invoice_product_type = 'goods'
    >>> project.product_goods = good
    >>> project.quantity = 10.0
    >>> project.unit_price = Decimal('100.0')
    >>> project.progress_quantity = 5.0
    >>> task = ProjectWork()
    >>> task.name = 'Service Task'
    >>> work = TimesheetWork()
    >>> work.name = 'Test progress work'
    >>> work.save()
    >>> task.work = work
    >>> task.type = 'task'
    >>> task.invoice_product_type = 'goods'
    >>> task.product_goods = good
    >>> task.quantity = 10.0
    >>> task.unit_price = Decimal('20.0')
    >>> task.progress_quantity = 5.0
    >>> project.children.append(task)
    >>> project.save()

Check project progress::

    >>> project.reload()
    >>> project.progress_quantity
    5.0
    >>> project.progress_amount
    600.0
    >>> project.invoiced_amount
    Decimal('0')

Invoice project::

    >>> config.user = project_invoice_user.id
    >>> project.click('invoice')

Check project progress::

    >>> project.reload()
    >>> project.invoiced_amount
    Decimal('600.00')

Do 100% of task and start another one::

    >>> config.user = project_user.id
    >>> task, = project.children
    >>> task.progress_amount = 10
    >>> task.save()
    >>> task = ProjectWork()
    >>> task.name = 'Good Task'
    >>> task.type = 'task'
    >>> task.invoice_product_type = 'goods'
    >>> task.product_goods = good
    >>> task.quantity = 5.0
    >>> task.unit_price = Decimal('100.0')
    >>> task.progress_quantity = 3.0
    >>> project.children.append(task)
    >>> project.save()
    >>> task.reload()

Check project progress::

    >>> project.reload()
    >>> project.progress_quantity
    5.0
    >>> project.progress_amount
    900.0
    >>> project.invoiced_amount
    Decimal('600.00')

Invoice project::

    >>> config.user = project_invoice_user.id
    >>> project.click('invoice')

Check project progress::

    >>> project.reload()
    >>> project.invoiced_amount
    Decimal('900.00')
