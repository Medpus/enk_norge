"""PDF-ressurser for ENK-fakturaer bak ekstern tilgangskontroll."""

import unittest
from unittest.mock import patch
from uuid import uuid4

import frappe

from enk_norge.printing import _pdf_asset_origin, rewrite_pdf_asset_urls
from enk_norge.tests.test_workflows import WorkflowsTest


class PrintingCoreTest(unittest.TestCase):
	def test_core_download_endpoint_is_overridden(self):
		self.assertIn(
			"enk_norge.printing.download_pdf",
			frappe.get_hooks("override_whitelisted_methods")["frappe.utils.print_format.download_pdf"],
		)

	def test_only_relative_static_assets_use_internal_origin(self):
		html = """
		<link rel="stylesheet" href="/assets/enk_norge/css/invoice.css">
		<img src="/assets/enk_norge/logo.svg?x=1">
		<a href="/assets/enk_norge/manual.pdf">Vanlig lenke</a>
		<img src="https://example.invalid/logo.svg">
		<img src="/assets/../api/method/private">
		<div style="background:url('/assets/enk_norge/bg.png')"></div>
		<style>.logo { background: url(/assets/enk_norge/mark.svg); }</style>
		"""
		out = rewrite_pdf_asset_urls(html, "http://erpnext-frontend:8080")
		self.assertIn('href="http://erpnext-frontend:8080/assets/enk_norge/css/invoice.css"', out)
		self.assertIn('src="http://erpnext-frontend:8080/assets/enk_norge/logo.svg?x=1"', out)
		self.assertIn('href="/assets/enk_norge/manual.pdf"', out)
		self.assertIn('src="https://example.invalid/logo.svg"', out)
		self.assertIn('src="/assets/../api/method/private"', out)
		self.assertIn("http://erpnext-frontend:8080/assets/enk_norge/bg.png", out)
		self.assertIn("http://erpnext-frontend:8080/assets/enk_norge/mark.svg", out)

	def test_origin_requires_a_plain_server_configured_http_origin(self):
		old = frappe.conf.get("enk_pdf_asset_origin")
		self.addCleanup(frappe.conf.__setitem__, "enk_pdf_asset_origin", old)
		frappe.conf.enk_pdf_asset_origin = "http://erpnext-frontend:8080"
		self.assertEqual(_pdf_asset_origin(), "http://erpnext-frontend:8080")
		frappe.conf.enk_pdf_asset_origin = "https://user:pass@example.invalid/"
		with self.assertRaises(frappe.ValidationError):
			_pdf_asset_origin()


class PrintingWorkflowTest(unittest.TestCase):
	setUp = WorkflowsTest.setUp
	tearDown = WorkflowsTest.tearDown
	sale = WorkflowsTest.sale

	def set_origin(self, origin):
		had_origin = "enk_pdf_asset_origin" in frappe.conf
		old_origin = frappe.conf.get("enk_pdf_asset_origin")
		if origin is None:
			frappe.conf.pop("enk_pdf_asset_origin", None)
		else:
			frappe.conf.enk_pdf_asset_origin = origin

		def restore():
			if had_origin:
				frappe.conf.enk_pdf_asset_origin = old_origin
			else:
				frappe.conf.pop("enk_pdf_asset_origin", None)

		self.addCleanup(restore)

	def test_enk_invoice_returns_a_real_pdf_from_rewritten_html(self):
		from enk_norge.printing import download_pdf

		invoice = self.sale()
		self.set_origin("http://erpnext-frontend:8080")
		frappe.local.response.clear()
		with patch(
			"enk_norge.printing.frappe.get_print",
			return_value="<html><body><h1>Fiktiv ENK-faktura</h1></body></html>",
		):
			download_pdf("Sales Invoice", invoice.name)
		self.assertEqual(frappe.local.response.type, "pdf")
		self.assertEqual(frappe.local.response.filename, invoice.name + ".pdf")
		self.assertTrue(frappe.local.response.filecontent.startswith(b"%PDF"))

	def test_target_path_checks_document_permission_before_rendering(self):
		from enk_norge.printing import download_pdf

		invoice = self.sale()
		self.set_origin("http://erpnext-frontend:8080")
		user = frappe.get_doc(
			dict(
				doctype="User",
				email=f"enk-print-{uuid4().hex}@example.invalid",
				first_name="Uautorisert",
				send_welcome_email=0,
			)
		).insert()
		frappe.set_user(user.name)
		with self.assertRaises(frappe.PermissionError):
			download_pdf("Sales Invoice", invoice.name)

	def test_unset_origin_uses_core_download_method(self):
		from enk_norge.printing import download_pdf

		invoice = self.sale()
		self.set_origin(None)
		with patch("enk_norge.printing._native_download_pdf") as native:
			download_pdf("Sales Invoice", invoice.name)
		native.assert_called_once()


def run():
	if frappe.local.site != "test.localhost":
		raise RuntimeError("Kun test.localhost kan kjøre PDF-testen.")
	result = unittest.TextTestRunner(verbosity=2).run(
		unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__, fromlist=["*"]))
	)
	frappe.db.rollback()
	if not result.wasSuccessful():
		raise RuntimeError("PDF-testene feilet.")
	return {"tests": result.testsRun, "successful": True}
