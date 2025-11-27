import frappe

WORKSPACES = (
	"swynix_mes",
	"planning",
	"operations",
	"logs",
	"quality",
)


def load_workspaces():
	for workspace in WORKSPACES:
		frappe.reload_doc("swynix_mes", "workspace", workspace, force=True)


def after_install():
	load_workspaces()


def after_migrate():
	load_workspaces()

