===============================
Project Product Effort Scenario
===============================

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

Create project product user::

    >>> project_product_user = User()
    >>> project_product_user.name = 'Project Product'
    >>> project_product_user.login = 'project_product'
    >>> project_product_user.main_company = company
    >>> project_product_group, = Group.find([('name', '=', 'Project Invoice')])
    >>> project_group, = Group.find([('name', '=', 'Project Administration')])
    >>> project_product_user.groups.extend(
    ...     [project_product_group, project_group])
    >>> project_product_user.save()

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

    >>> product_good = Product()
    >>> template = ProductTemplate()
    >>> template.name = 'Good'
    >>> template.default_uom = unit
    >>> template.type = 'goods'
    >>> template.list_price = Decimal('100')
    >>> template.cost_price = Decimal('50')
    >>> template.account_revenue = revenue
    >>> template.save()
    >>> product_good.template = template
    >>> product_good.save()

    >>> product_service = Product()
    >>> template = ProductTemplate()
    >>> template.name = 'Service'
    >>> template.default_uom = hour
    >>> template.type = 'service'
    >>> template.list_price = Decimal('100')
    >>> template.cost_price = Decimal('50')
    >>> template.account_revenue = revenue
    >>> template.save()
    >>> product_service.template = template
    >>> product_service.save()

Create a Project::

    >>> config.user = project_user.id
    >>> ProjectWork = Model.get('project.work')
    >>> TimesheetWork = Model.get('timesheet.work')
    >>> project = ProjectWork()
    >>> project.name = 'Test effort'
    >>> project.type = 'project'
    >>> project.party = customer
    >>> project.project_invoice_method = 'effort'
    >>> project.invoice_product_type = 'service'
    >>> work = TimesheetWork()
    >>> work.name = 'Task 1'
    >>> work.save()
    >>> project.work = work
    >>> project.effort_duration = datetime.timedelta(days=5)
    >>> project.product = product_service

    >>> task = ProjectWork()
    >>> task.name = 'Task 1'
    >>> task.type = 'task'
    >>> task.invoice_product_type = 'goods'
    >>> task.product_goods = product_good
    >>> task.quantity = 5
    >>> task.progress_quantity = 3
    >>> project.children.append(task)
    >>> project.save()
    >>> project.reload()

Check task progress::

    >>> task, = project.children
    >>> task.progress
    0.6

Check project invoiced amount::
    >>> project.invoiced_amount
    Decimal('0')

Invoice project::

    >>> config.user = project_product_user.id
    >>> project.click('invoice')
    >>> project.invoiced_amount
    Decimal('0')

Do project::

    >>> config.user = project_user.id
    >>> task.progress_quantity = 5.0
    >>> task.state = 'done'
    >>> task.save()
    >>> project.reload()

Check task progress::

    >>> task, = project.children
    >>> task.progress
    1.0

Invoice again project::

    >>> config.user = project_product_user.id
    >>> project.click('invoice')
    >>> project.invoiced_amount
    Decimal('500.00')
