from frappe import _

MODULE_NAME = "Swynix MES"
MODULE_ICON = "octicon octicon-gear"
MODULE_IMAGE = "/assets/swynix_mes/manufacture.png"

DOCTYPES = [
	"Annealing Log",
	"Breakdown Log",
	"Caster QC Inspection",
	"Casting Operation",
	"Circle Packing Log",
	"Circle Production Log",
	"Coil",
	"Coil Operation",
	"Cutting Operation Log",
	"Dross Log",
	"Energy Log",
	"Finishing Production Log",
	"Foil Operation",
	"Melting Batch",
	"Melting Batch Material",
	"Packing Batch",
	"Packing Batch Item",
	"Parameter Log",
	"QC Log",
	"Reason Code",
	"Recipe Detail",
	"Recipe Master",
	"Reel",
	"Rolling Plan",
	"Rolling Plan Pass",
	"Scrap Log",
	"Slitting Operation Log",
	"WIP Movement Log",
]


def get_data():
	return [
		{
			"module_name": MODULE_NAME,
			"type": "module",
			"label": _(MODULE_NAME),
			"color": "orange",
			"icon": MODULE_ICON,
			"image": MODULE_IMAGE,
			"items": [
				{
					"type": "doctype",
					"name": doctype,
					"label": _(doctype),
				}
				for doctype in DOCTYPES
			],
		}
	]

