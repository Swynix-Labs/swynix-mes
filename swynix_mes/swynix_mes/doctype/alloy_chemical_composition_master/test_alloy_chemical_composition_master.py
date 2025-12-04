# Copyright (c) 2025, Swynix and contributors
# For license information, please see license.txt

# import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase


# On IntegrationTestCase, the weights at the doctype need to be inserted
# to the database before running the tests. Uncomment the following line
# to setup test data explicitly.
# EXTRA_TEST_RECORD_DEPENDENCIES = []


class UnitTestAlloyChemicalCompositionMaster(UnitTestCase):
	"""
	Unit tests for AlloyChemicalCompositionMaster.
	Use this class for testing individual functions and methods.
	"""

	pass


class IntegrationTestAlloyChemicalCompositionMaster(IntegrationTestCase):
	"""
	Integration tests for AlloyChemicalCompositionMaster.
	Use this class for testing interactions between multiple components.
	"""

	pass
