from frappe import _

APP_ICON = "fa fa-industry"
APP_COLOR = "orange"
MODULE_LABEL = _("Swynix MES")

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


def _get_items():
    return [
        {
            "type": "doctype",
            "name": doctype,
            "label": _(doctype),
        }
        for doctype in DOCTYPES
    ]


def get_data():
    return [
        {
            "label": MODULE_LABEL,
            "color": APP_COLOR,
            "icon": APP_ICON,
            "items": _get_items(),
        }
    ]

