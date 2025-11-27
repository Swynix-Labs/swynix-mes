import frappe

WORKSPACES = (
	"mes_overview",
	"foundry_mes",
	"caster_mes",
	"crm_mes",
	"foil_reel_mes",
	"finishing_circle_mes",
)


def load_workspaces():
	for workspace in WORKSPACES:
		frappe.reload_doc("swynix_mes", "workspace", workspace, force=True)


def after_install():
	load_workspaces()


def after_migrate():
	load_workspaces()

