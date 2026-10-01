app_name = "enk_norge"
app_title = "ENK Norge"
app_publisher = "Haakon Fornes"
app_description = "Norsk ENK-tilpasning for ERPNext"
app_email = "85625055+Medpus@users.noreply.github.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "enk_norge",
# 		"logo": "/assets/enk_norge/logo.png",
# 		"title": "ENK Norge",
# 		"route": "/enk_norge",
# 		"has_permission": "enk_norge.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/enk_norge/css/enk_norge.css"
# app_include_js = "/assets/enk_norge/js/enk_norge.js"

# include js, css files in header of web template
# web_include_css = "/assets/enk_norge/css/enk_norge.css"
# web_include_js = "/assets/enk_norge/js/enk_norge.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "enk_norge/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "enk_norge/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "enk_norge.utils.jinja_methods",
# 	"filters": "enk_norge.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "enk_norge.install.before_install"
# after_install = "enk_norge.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "enk_norge.uninstall.before_uninstall"
# after_uninstall = "enk_norge.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "enk_norge.utils.before_app_install"
# after_app_install = "enk_norge.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "enk_norge.utils.before_app_uninstall"
# after_app_uninstall = "enk_norge.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "enk_norge.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "enk_norge.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["enk_norge.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"enk_norge.tasks.all"
# 	],
# 	"daily": [
# 		"enk_norge.tasks.daily"
# 	],
# 	"hourly": [
# 		"enk_norge.tasks.hourly"
# 	],
# 	"weekly": [
# 		"enk_norge.tasks.weekly"
# 	],
# 	"monthly": [
# 		"enk_norge.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "enk_norge.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "enk_norge.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
override_whitelisted_methods = {
	"frappe.utils.print_format.download_pdf": "enk_norge.printing.download_pdf"
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "enk_norge.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["enk_norge.utils.before_request"]
# after_request = ["enk_norge.utils.after_request"]

# Job Events
# ----------
# before_job = ["enk_norge.utils.before_job"]
# after_job = ["enk_norge.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"enk_norge.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []


required_apps = ['erpnext']
after_install = 'enk_norge.install.after_migrate'
after_migrate = 'enk_norge.install.after_migrate'
override_doctype_class = {'Subscription': 'enk_norge.subscription.ENKSubscription'}
doc_events = {
	name: {
		'before_submit': 'enk_norge.validation.validate_transaction',
		'before_cancel': 'enk_norge.validation.validate_transaction',
		'on_trash': 'enk_norge.validation.protect_delete',
		'before_rename': 'enk_norge.validation.protect_rename',
	}
	for name in ('Sales Invoice', 'Purchase Invoice', 'Payment Entry', 'Journal Entry')
}

doc_events['File'] = {'on_trash': 'enk_norge.validation.protect_file', 'before_save': 'enk_norge.validation.protect_file_update'}
for report in ('ENK Year Report', 'ENK VAT Return'):
	doc_events[report] = {'on_trash': 'enk_norge.validation.protect_delete'}

setup_wizard_requires = 'assets/enk_norge/js/enk_setup.js'

jinja = {'methods': ['enk_norge.printing.enk_invoice_issuer']}

app_include_js = ['/assets/enk_norge/js/enk_actions.js']

doctype_js = {
	'Sales Invoice': 'public/js/invoice.js',
	'Purchase Invoice': 'public/js/invoice.js',
}


doc_events['Payment Entry']['on_submit'] = 'enk_norge.banking.sync_currency_adjustment'
doc_events['Payment Entry']['before_cancel'] = [
	'enk_norge.validation.validate_transaction',
	'enk_norge.banking.sync_currency_adjustment',
]


doc_events['Process Deferred Accounting'] = {
	'before_insert': 'enk_norge.deferrals.block_native_deferred_accounting',
	'before_submit': 'enk_norge.deferrals.block_native_deferred_accounting',
}


doc_events['Sales Invoice']['on_submit'] = 'enk_norge.deferrals.sync_credit_reversal'
doc_events['Sales Invoice']['before_cancel'] = [
	'enk_norge.validation.validate_transaction',
	'enk_norge.deferrals.sync_credit_reversal',
]
doc_events['Sales Invoice']['before_update_after_submit'] = 'enk_norge.deferrals.validate_deferred_revenue_update'
doc_events['Sales Invoice']['before_insert'] = 'enk_norge.validation.validate_subscription_invoice_creation'

for doctype in ('Stock Entry', 'POS Invoice', 'Delivery Note', 'Purchase Receipt'):
	doc_events[doctype] = {
		'before_submit': 'enk_norge.validation.validate_unsupported_native_accounting',
		'before_cancel': 'enk_norge.validation.validate_unsupported_native_accounting',
	}

doc_events['Company'] = {'before_save': 'enk_norge.validation.validate_company_perpetual_inventory'}
doc_events['Subscription'] = {
	'before_insert': 'enk_norge.validation.validate_subscription',
	'before_save': 'enk_norge.validation.validate_subscription',
}
