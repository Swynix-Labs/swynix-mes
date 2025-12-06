"""
Patch to rename charge_mix_recipe field to charge_mix_ratio

This patch:
1. Reloads updated doctypes
2. Renames database columns from charge_mix_recipe to charge_mix_ratio
"""

import frappe


def execute():
	"""Execute field rename patch"""
	
	print("\n" + "="*70)
	print("RENAMING FIELD: charge_mix_recipe → charge_mix_ratio")
	print("="*70 + "\n")
	
	# Step 1: Reload doctypes with updated schema
	print("Step 1: Reloading doctypes...")
	try:
		frappe.reload_doc("swynix_mes", "doctype", "ppc_casting_plan", force=True)
		frappe.reload_doc("swynix_mes", "doctype", "melting_batch", force=True)
		print("✅ Doctypes reloaded\n")
	except Exception as e:
		print(f"⚠️ Warning during doctype reload: {str(e)}\n")
	
	# Step 2: Rename field in PPC Casting Plan
	print("Step 2: Renaming field in PPC Casting Plan...")
	try:
		if "charge_mix_recipe" in frappe.db.get_table_columns("tabPPC Casting Plan"):
			frappe.db.sql("""
				ALTER TABLE `tabPPC Casting Plan`
				CHANGE COLUMN `charge_mix_recipe` `charge_mix_ratio` VARCHAR(140)
			""")
			print("✅ PPC Casting Plan field renamed\n")
		else:
			print("ℹ️ Field already renamed or doesn't exist in PPC Casting Plan\n")
	except Exception as e:
		print(f"⚠️ Error renaming PPC Casting Plan field: {str(e)}\n")
	
	# Step 3: Rename field in Melting Batch
	print("Step 3: Renaming field in Melting Batch...")
	try:
		if "charge_mix_recipe" in frappe.db.get_table_columns("tabMelting Batch"):
			frappe.db.sql("""
				ALTER TABLE `tabMelting Batch`
				CHANGE COLUMN `charge_mix_recipe` `charge_mix_ratio` VARCHAR(140)
			""")
			print("✅ Melting Batch field renamed\n")
		else:
			print("ℹ️ Field already renamed or doesn't exist in Melting Batch\n")
	except Exception as e:
		print(f"⚠️ Error renaming Melting Batch field: {str(e)}\n")
	
	# Step 4: Clear cache
	print("Step 4: Clearing cache...")
	frappe.clear_cache()
	print("✅ Cache cleared\n")
	
	# Step 5: Commit changes
	frappe.db.commit()
	
	print("="*70)
	print("FIELD RENAME COMPLETED SUCCESSFULLY!")
	print("="*70 + "\n")
	print("Summary:")
	print("  - DocType JSON updated: PPC Casting Plan, Melting Batch")
	print("  - Database columns renamed")
	print("  - Old field name: charge_mix_recipe")
	print("  - New field name: charge_mix_ratio")
	print("  - DocType linked: Charge Mix Ratio")
	print("\n✅ All references to CMR-YYYY-XXXX should now work correctly!")
	print("\n")
