"""
Migration script to transition from Caster master to Workstation

This script:
1. Creates Workstation custom fields (workstation_type, caster_no)
2. Migrates existing Caster records to Workstation
3. Updates all references in Casting Plans, Casting Runs, Mother Coils
4. Archives the old Caster doctype (not delete to preserve data)
"""

import frappe
from frappe import _


def execute():
	"""Execute migration from Caster to Workstation"""
	
	print("\n" + "="*70)
	print("CASTING MES MIGRATION: Caster → Workstation")
	print("="*70 + "\n")
	
	# Step 1: Create custom fields for Workstation
	print("Step 1: Creating Workstation custom fields...")
	create_workstation_custom_fields()
	print("✅ Custom fields created\n")
	
	# Step 2: Migrate existing Caster records
	print("Step 2: Migrating Caster records to Workstation...")
	migrate_casters_to_workstations()
	print("✅ Caster records migrated\n")
	
	# Step 3: Update references in PPC Casting Plan
	print("Step 3: Updating PPC Casting Plan references...")
	update_casting_plan_references()
	print("✅ Casting Plan references updated\n")
	
	# Step 4: Update references in Casting Run
	print("Step 4: Updating Casting Run references...")
	update_casting_run_references()
	print("✅ Casting Run references updated\n")
	
	# Step 5: Update references in Mother Coil
	print("Step 5: Updating Mother Coil references...")
	update_mother_coil_references()
	print("✅ Mother Coil references updated\n")
	
	# Step 6: Archive old Caster doctype
	print("Step 6: Archiving old Caster doctype...")
	archive_caster_doctype()
	print("✅ Caster doctype archived\n")
	
	print("="*70)
	print("MIGRATION COMPLETED SUCCESSFULLY!")
	print("="*70 + "\n")
	
	print("📝 Summary:")
	print("   - Workstation custom fields created")
	print("   - Caster data migrated to Workstation")
	print("   - All references updated")
	print("   - Old Caster doctype archived")
	print("\n✅ Your Casting MES is now using ERPNext Workstation!")
	print("\n")


def create_workstation_custom_fields():
	"""Create custom fields for Workstation if they don't exist"""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
	
	custom_fields = {
		"Workstation": [
			{
				"fieldname": "workstation_type",
				"label": "Workstation Type",
				"fieldtype": "Select",
				"options": "\nFurnace\nCaster\nMill\nSlitter",
				"insert_after": "workstation_name",
				"in_list_view": 1,
				"in_standard_filter": 1,
				"reqd": 0,
			},
			{
				"fieldname": "caster_no",
				"label": "Caster No",
				"fieldtype": "Int",
				"insert_after": "workstation_type",
				"depends_on": "eval:doc.workstation_type=='Caster'",
				"mandatory_depends_on": "eval:doc.workstation_type=='Caster'",
			}
		]
	}
	
	create_custom_fields(custom_fields, update=True)


def migrate_casters_to_workstations():
	"""Migrate existing Caster records to Workstation"""
	casters = frappe.get_all("Caster", fields=["name", "caster_id", "caster_name", "no_of_strands", "is_active"])
	
	migration_map = {}
	
	for caster in casters:
		# Check if workstation already exists
		existing_ws = frappe.db.exists("Workstation", caster.caster_id)
		
		if existing_ws:
			# Update existing workstation
			ws = frappe.get_doc("Workstation", caster.caster_id)
			ws.workstation_type = "Caster"
			ws.caster_no = int(caster.caster_id.split("-")[-1]) if "-" in caster.caster_id else 1
			ws.save(ignore_permissions=True)
			migration_map[caster.name] = ws.name
			print(f"   Updated existing Workstation: {ws.name}")
		else:
			# Create new workstation
			ws = frappe.new_doc("Workstation")
			ws.workstation_name = caster.caster_name or caster.caster_id
			ws.workstation_type = "Caster"
			ws.caster_no = int(caster.caster_id.split("-")[-1]) if "-" in caster.caster_id else 1
			ws.insert(ignore_permissions=True)
			migration_map[caster.name] = ws.name
			print(f"   Created new Workstation: {ws.name}")
	
	# Store migration map for reference updates
	frappe.cache().set_value("caster_migration_map", migration_map)
	
	print(f"   Migrated {len(casters)} Caster records to Workstation")


def update_casting_plan_references():
	"""Update Caster references in PPC Casting Plan to Workstation"""
	migration_map = frappe.cache().get_value("caster_migration_map") or {}
	
	# Note: PPC Casting Plan already uses Workstation, so no migration needed
	# This function is here for completeness
	print("   PPC Casting Plan already uses Workstation - no update needed")


def update_casting_run_references():
	"""Update Caster references in Casting Run to Workstation"""
	migration_map = frappe.cache().get_value("caster_migration_map") or {}
	
	if not migration_map:
		print("   No migration map found - skipping")
		return
	
	count = 0
	for old_caster, new_workstation in migration_map.items():
		updated = frappe.db.sql("""
			UPDATE `tabCasting Run`
			SET caster = %s
			WHERE caster = %s
		""", (new_workstation, old_caster))
		count += updated
	
	frappe.db.commit()
	print(f"   Updated {count} Casting Run records")


def update_mother_coil_references():
	"""Update Caster references in Mother Coil to Workstation"""
	migration_map = frappe.cache().get_value("caster_migration_map") or {}
	
	if not migration_map:
		print("   No migration map found - skipping")
		return
	
	count = 0
	for old_caster, new_workstation in migration_map.items():
		updated = frappe.db.sql("""
			UPDATE `tabMother Coil`
			SET caster = %s
			WHERE caster = %s
		""", (new_workstation, old_caster))
		count += updated
	
	frappe.db.commit()
	print(f"   Updated {count} Mother Coil records")


def archive_caster_doctype():
	"""
	Archive the old Caster doctype
	
	We don't delete it to preserve historical data.
	Instead, we hide it from the UI.
	"""
	try:
		# Check if Caster doctype exists
		if frappe.db.exists("DocType", "Caster"):
			caster_dt = frappe.get_doc("DocType", "Caster")
			caster_dt.hide_toolbar = 1
			caster_dt.issingle = 0
			caster_dt.description = "⚠️ DEPRECATED: This doctype is no longer used. Please use Workstation with workstation_type='Caster' instead."
			caster_dt.save(ignore_permissions=True)
			print("   Caster doctype marked as deprecated")
			
			# You could optionally disable all permissions
			frappe.db.sql("""
				UPDATE `tabCustom DocPerm`
				SET `read` = 0, `write` = 0, `create` = 0, `delete` = 0
				WHERE parent = 'Caster'
			""")
			frappe.db.commit()
			print("   Caster doctype permissions disabled")
	except Exception as e:
		print(f"   Warning: Could not archive Caster doctype: {str(e)}")


if __name__ == "__main__":
	execute()
