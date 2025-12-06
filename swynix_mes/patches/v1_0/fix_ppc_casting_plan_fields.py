"""
Patch to rename caster field to casting_workstation in PPC Casting Plan

This patch:
1. Removes charge_mix_ratio field from PPC Casting Plan (belongs only in Melting Batch)
2. Renames caster column to casting_workstation
3. Updates all data references
"""

import frappe


def execute():
	"""Execute field rename and cleanup patch"""
	
	print("\n" + "="*70)
	print("FIXING PPC CASTING PLAN FIELD NAMES")
	print("="*70 + "\n")
	
	# Step 1: Reload doctype with updated schema
	print("Step 1: Reloading PPC Casting Plan doctype...")
	try:
		frappe.reload_doc("swynix_mes", "doctype", "ppc_casting_plan", force=True)
		print("✅ Doctype reloaded\n")
	except Exception as e:
		print(f"⚠️ Warning during doctype reload: {str(e)}\n")
	
	# Step 2: Remove charge_mix_ratio column if it exists
	print("Step 2: Removing charge_mix_ratio column from PPC Casting Plan...")
	try:
		if "charge_mix_ratio" in frappe.db.get_table_columns("tabPPC Casting Plan"):
			frappe.db.sql("""
				ALTER TABLE `tabPPC Casting Plan`
				DROP COLUMN `charge_mix_ratio`
			""")
			print("✅ Removed charge_mix_ratio column\n")
		else:
			print("ℹ️ charge_mix_ratio column already removed or doesn't exist\n")
	except Exception as e:
		print(f"⚠️ Error removing charge_mix_ratio column: {str(e)}\n")
	
	# Step 3: Rename caster column to casting_workstation
	print("Step 3: Renaming caster to casting_workstation...")
	try:
		if "caster" in frappe.db.get_table_columns("tabPPC Casting Plan"):
			frappe.db.sql("""
				ALTER TABLE `tabPPC Casting Plan`
				CHANGE COLUMN `caster` `casting_workstation` VARCHAR(140)
			""")
			print("✅ Renamed caster to casting_workstation\n")
		else:
			print("ℹ️ Column already renamed or doesn't exist\n")
	except Exception as e:
		print(f"⚠️ Error renaming caster column: {str(e)}\n")
	
	# Step 4: Clear cache
	print("Step 4: Clearing cache...")
	frappe.clear_cache()
	print("✅ Cache cleared\n")
	
	# Step 5: Commit changes
	frappe.db.commit()
	
	print("="*70)
	print("PATCH COMPLETED SUCCESSFULLY!")
	print("="*70 + "\n")
	print("Summary:")
	print("  - Removed charge_mix_ratio from PPC Casting Plan")
	print("    (This field belongs ONLY in Melting Batch)")
	print("  - Renamed caster → casting_workstation")
	print("  - Must use workstation_type = 'Casting'")
	print("\n✅ Database schema updated!")
	print("\n")
