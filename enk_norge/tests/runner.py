"""Samlet, lokal testkjøring. Kan ikke brukes på et produksjonssite."""

import importlib
import inspect
import unittest

import frappe


def run(modules=None):
	if frappe.local.site != "test.localhost":
		raise RuntimeError("Regnskapstestene er begrenset til test.localhost.")
	modules = modules or [
		"test_norway_rules",
		"test_saft",
		"test_posting_contract",
		"test_workflows",
		"test_access",
		"test_banking",
		"test_billing",
		"test_currency",
		"test_deferrals",
		"test_settlement",
		"test_tax_pool",
		"test_saft_integration",
		"test_vat",
		"test_year_end",
	]
	suite = unittest.TestSuite()
	for name in modules:
		if not name.startswith("test_") or not name.replace("_", "").isalnum():
			raise ValueError("Ugyldig testmodul.")
		module = importlib.import_module("enk_norge.tests." + name)
		for _, case in inspect.getmembers(module, inspect.isclass):
			if issubclass(case, unittest.TestCase) and case.__module__ == module.__name__:
				suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
	try:
		result = unittest.TextTestRunner(verbosity=2).run(suite)
	finally:
		frappe.db.rollback()
	if not result.wasSuccessful():
		raise RuntimeError("Regnskapstestene feilet. Se feilene over.")
	return {"tests": result.testsRun, "skipped": len(result.skipped), "successful": True}
