# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Caster(Document):
    def validate(self):
        # Ensure caster_id is alphanumeric
        if self.caster_id and not self.caster_id.replace(" ", "").replace("-", "").replace("_", "").isalnum():
            frappe.throw("Caster ID should be alphanumeric")







