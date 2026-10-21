app_name = "sahbi"
app_title = "Sahbi"
app_publisher = "Beshoy Atef"
app_description = "Build a personal financial assistant for everyday Egyptian users"
app_email = "beshoyatef31@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "sahbi",
# 		"logo": "/assets/sahbi/logo.png",
# 		"title": "Sahbi",
# 		"route": "/sahbi",
# 		"has_permission": "sahbi.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/sahbi/css/sahbi.css"
# app_include_js = "/assets/sahbi/js/sahbi.js"

# include js, css files in header of web template
# web_include_css = "/assets/sahbi/css/sahbi.css"
# web_include_js = "/assets/sahbi/js/sahbi.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "sahbi/public/scss/website"

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
# app_include_icons = "sahbi/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

website_route_rules = [
	{"from_route": "/terms", "to_route": "terms-of-service"},
	{"from_route": "/policy", "to_route": "privacy-policy"},
]

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "sahbi.utils.jinja_methods",
# 	"filters": "sahbi.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "sahbi.install.before_install"
after_install = "sahbi.workspace.after_migrate"
after_migrate = "sahbi.workspace.after_migrate"

# Uninstallation
# ------------

# before_uninstall = "sahbi.uninstall.before_uninstall"
# after_uninstall = "sahbi.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "sahbi.utils.before_app_install"
# after_app_install = "sahbi.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "sahbi.utils.before_app_uninstall"
# after_app_uninstall = "sahbi.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "sahbi.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

permission_query_conditions = {
	"Sahbi Workspace": "sahbi.permissions.workspace_query",
	"Sahbi Person": "sahbi.permissions.person_query",
	"Sahbi Entry": "sahbi.permissions.entry_query",
	"Sahbi Payment": "sahbi.permissions.payment_query",
	"Sahbi Payment Allocation": "sahbi.permissions.allocation_query",
	"Sahbi Conversation": "sahbi.permissions.conversation_query",
	"Sahbi Chat Message": "sahbi.permissions.chat_message_query",
	"Sahbi Human Handoff": "sahbi.permissions.handoff_query",
}

has_permission = {
	"Sahbi Workspace": "sahbi.permissions.has_workspace_permission",
	"Sahbi Person": "sahbi.permissions.has_person_permission",
	"Sahbi Entry": "sahbi.permissions.has_entry_permission",
	"Sahbi Payment": "sahbi.permissions.has_payment_permission",
	"Sahbi Payment Allocation": "sahbi.permissions.has_allocation_permission",
	"Sahbi Conversation": "sahbi.permissions.has_conversation_permission",
	"Sahbi Chat Message": "sahbi.permissions.has_chat_message_permission",
	"Sahbi Human Handoff": "sahbi.permissions.has_handoff_permission",
}

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"User": {
		"after_insert": "sahbi.workspace.ensure_workspace_for_user",
	},
	"Sahbi Entry": {
		"validate": "sahbi.permissions.validate_workspace_on_doc",
	},
	"Sahbi Payment": {
		"validate": "sahbi.permissions.validate_workspace_on_doc",
	},
	"Sahbi Payment Allocation": {
		"validate": "sahbi.permissions.validate_workspace_on_doc",
	},
	"Sahbi Person": {
		"validate": "sahbi.permissions.validate_workspace_on_doc",
	},
	"Sahbi Conversation": {
		"validate": "sahbi.permissions.validate_workspace_on_doc",
	},
	"Sahbi Chat Message": {
		"validate": "sahbi.permissions.validate_workspace_on_doc",
	},
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"sahbi.tasks.all"
# 	],
# 	"daily": [
# 		"sahbi.tasks.daily"
# 	],
# 	"hourly": [
# 		"sahbi.tasks.hourly"
# 	],
# 	"weekly": [
# 		"sahbi.tasks.weekly"
# 	],
# 	"monthly": [
# 		"sahbi.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "sahbi.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "sahbi.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "sahbi.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["sahbi.utils.before_request"]
# after_request = ["sahbi.utils.after_request"]

# Job Events
# ----------
# before_job = ["sahbi.utils.before_job"]
# after_job = ["sahbi.utils.after_job"]

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
# 	"sahbi.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

default_log_clearing_doctypes = {
	"Sahbi Webhook Request": 30,
	"Sahbi Webhook Event Log": 30,
	"Sahbi Integration Log": 30,
}

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

