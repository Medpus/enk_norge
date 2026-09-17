"""Idempotente metadataendringer. Oppretter aldri foretak eller bilag."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def after_migrate():
	from frappe.utils.password import get_encryption_key

	# Samme vedvarende nøkkel som Frappe bruker; må følge med ved gjenoppretting.
	get_encryption_key()
	if not frappe.db.exists("Address Template", "Norway"):
		frappe.get_doc(
			dict(
				doctype="Address Template",
				country="Norway",
				template="{{ address_line1 | e }}<br>{% if address_line2 %}{{ address_line2 | e }}<br>{% endif %}{{ pincode | e }} {{ city | e }}<br>{{ country | e }}",
			)
		).insert(ignore_permissions=True)
	from erpnext.setup.setup_wizard.operations.install_fixtures import get_preset_records

	for record in get_preset_records("Norway"):
		if record["doctype"] not in ("Customer Group", "Supplier Group", "Territory", "Party Type"):
			continue
		key = {
			"Customer Group": "customer_group_name",
			"Supplier Group": "supplier_group_name",
			"Territory": "territory_name",
			"Party Type": "party_type",
		}[record["doctype"]]
		if not frappe.db.exists(record["doctype"], record[key]):
			doc = frappe.get_doc(record)
			doc.flags.ignore_mandatory = bool(record.get("is_group"))
			doc.insert(ignore_permissions=True)
	if not frappe.db.exists("UOM", "Nos"):
		frappe.get_doc(dict(doctype="UOM", uom_name="Nos", must_be_whole_number=0)).insert(
			ignore_permissions=True
		)
	for kind, field in (("Selling", "selling"), ("Buying", "buying")):
		if not frappe.db.exists("Price List", "ENK " + kind):
			frappe.get_doc(
				dict(
					doctype="Price List",
					price_list_name="ENK " + kind,
					enabled=1,
					currency="NOK",
					**{field: 1},
				)
			).insert(ignore_permissions=True)
	fields = {}
	for doctype in ("Sales Invoice", "Purchase Invoice"):
		fields[doctype] = [
			dict(fieldname="enk_exchange_rate_source", label="Kurskilde", fieldtype="Small Text"),
			dict(fieldname="enk_exchange_rate_date", label="Kursdato", fieldtype="Date"),
			dict(
				fieldname="enk_tax_treatment",
				label="Norsk avgiftsbehandling",
				fieldtype="Select",
				options="\nNot registered\nDomestic 25\nDomestic 15\nDomestic 12\nExport services\nExempt\nForeign services\nNo input VAT",
				insert_after="tax_category",
			),
			dict(
				fieldname="enk_external_id",
				label="Ekstern hendelses-ID",
				fieldtype="Data",
				unique=0,
				no_copy=1,
				insert_after="enk_tax_treatment",
			),
			dict(
				fieldname="enk_delivery_date",
				label="Leveringsdato",
				fieldtype="Date",
				insert_after="posting_date",
			),
			dict(
				fieldname="enk_delivery_description",
				label="Leveranse og periode",
				fieldtype="Small Text",
				insert_after="enk_delivery_date",
			),
		]
	fields["Sales Invoice"].append(
		dict(
			fieldname="enk_tax_reason",
			label="Grunnlag for MVA-unntak",
			fieldtype="Small Text",
			depends_on="eval:doc.enk_tax_treatment == 'Exempt'",
			description="Oppgi hvilken regel og leveranse som begrunner unntaket.",
		)
	)
	fields["Sales Invoice"].append(
		dict(
			fieldname="enk_vat_registration_pending",
			label="MVA-registrering følges opp",
			fieldtype="Check",
			no_copy=1,
			description="Salget passerer registreringsgrensen. Følg opp registrering og korrigering av hele salget.",
		)
	)
	fields["Sales Invoice"].extend(
	[
		dict(
			fieldname="enk_subscription_source_file",
			label="Privat abonnementsavtale",
			fieldtype="Link",
			options="File",
			read_only=1,
			no_copy=1,
		),
		dict(
			fieldname="enk_deferral_reversal_journal_entry",
			label="Reverseringsbilag for utsatt inntekt",
			fieldtype="Link",
			options="Journal Entry",
			read_only=1,
			no_copy=1,
		),
	]
	)
	fields["Purchase Invoice"].extend(
		[
			dict(
				fieldname="enk_tax_deductible_fraction",
				label="Skattemessig fradragsandel (0-1)",
				fieldtype="Float",
				precision=6,
				default="1",
			),
			dict(
				fieldname="enk_tax_adjustment_reason",
				label="Begrunnelse for redusert skattefradrag",
				fieldtype="Small Text",
				depends_on="eval:doc.enk_tax_deductible_fraction < 1",
			),
			dict(
				fieldname="enk_tax_reason",
				label="Begrunnelse for kjøp uten MVA",
				fieldtype="Small Text",
				depends_on="eval:doc.enk_tax_treatment == 'No input VAT'",
			),
			dict(
				fieldname="enk_business_fraction",
				label="Virksomhetsandel (0-1)",
				fieldtype="Float",
				precision=6,
				default="1",
			),
			dict(
				fieldname="enk_deductible_fraction",
				label="Fradragsandel MVA (0-1)",
				fieldtype="Float",
				precision=6,
				default="1",
			),
			dict(fieldname="enk_vat_basis", label="MVA-grunnlag i NOK", fieldtype="Currency"),
			dict(fieldname="enk_expected_life_months", label="Forventet brukstid i måneder", fieldtype="Int"),
		]
	)
	fields["Journal Entry"] = [
		dict(fieldname="enk_vat_period", label="ENK MVA-periode", fieldtype="Data", read_only=1, no_copy=1),
		dict(fieldname="enk_deferral_key", label="Periodiseringens nøkkel", fieldtype="Data", read_only=1, hidden=1, no_copy=1),
		dict(
			fieldname="enk_deferral_details",
			label="Periodiseringens kildegrunnlag",
			fieldtype="Long Text",
			read_only=1,
			hidden=1,
			no_copy=1,
		),
	]
	fields["Sales Invoice"].append(
		dict(
			fieldname="enk_invoice_snapshot",
			label="Utsteder ved bokføring",
			fieldtype="Long Text",
			read_only=1,
			hidden=1,
			no_copy=1,
		)
	)
	for name in ("Sales Invoice", "Purchase Invoice"):
		fields[name].append(
			dict(
				fieldname="enk_request_fingerprint",
				label="Hendelsens kontrollsum",
				fieldtype="Data",
				read_only=1,
				no_copy=1,
				hidden=1,
			)
		)
	for name in ("Payment Entry", "Journal Entry"):
		fields.setdefault(name, []).extend(
			[
				dict(
					fieldname="enk_manual_reason",
					label="Grunnlag for manuell føring",
					fieldtype="Small Text",
					description="Regnskapsansvarlig må forklare føringen og legge ved et privat kildebilag.",
				),
				dict(
					fieldname="enk_posting_contract",
					label="Kontroll av bokføringsgrunnlag",
					fieldtype="Long Text",
					read_only=1,
					hidden=1,
					no_copy=1,
				),
				dict(
					fieldname="enk_payment_key",
					label="Betalingens nøkkel",
					fieldtype="Data",
					unique=1,
					read_only=1,
					no_copy=1,
				),
				dict(
					fieldname="enk_payment_fingerprint",
					label="Betalingens kontrollsum",
					fieldtype="Data",
					read_only=1,
					no_copy=1,
				),
			]
		)
	fields["Payment Entry"].append(dict(fieldname="enk_fx_journal_entry", label="Tilhørende valutaføring", fieldtype="Data", read_only=1, no_copy=1))
	fields["Journal Entry"].append(dict(fieldname="enk_fx_payment_entry", label="Tilhørende betaling", fieldtype="Data", read_only=1, no_copy=1))
	fields["Bank Transaction"] = [
		dict(
			fieldname="enk_bank_import",
			label="Kilde for bankimport",
			fieldtype="Link",
			options="ENK Bank Import",
			read_only=1,
			no_copy=1,
		),
		dict(
			fieldname="enk_row_hash",
			label="Banklinjens kontrollsum",
			fieldtype="Data",
			read_only=1,
			no_copy=1,
		),
	]
	fields["Payment Entry"].extend(
		[
			dict(fieldname="enk_exchange_rate_source", label="Kurskilde", fieldtype="Small Text"),
			dict(fieldname="enk_exchange_rate_date", label="Kursdato", fieldtype="Date"),
			dict(
				fieldname="enk_bank_amount_nok",
				label="Faktisk bankbeløp i NOK",
				fieldtype="Currency",
				read_only=1,
			),
			dict(fieldname="enk_fee_amount_nok", label="Bankgebyr i NOK", fieldtype="Currency", read_only=1),
		]
	)
	create_custom_fields(fields, update=True)
	from enk_norge.setup import ensure_currency_accounts

	ensure_currency_accounts()
	for name in ("Sales Invoice", "Purchase Invoice"):
		frappe.db.add_unique(name, ["company", "enk_external_id"], constraint_name="unique_enk_company_event")
	frappe.db.add_unique("Journal Entry", ["enk_deferral_key"], constraint_name="unique_enk_deferral_key")
	html = frappe.read_file(frappe.get_app_path("enk_norge", "templates", "enk_invoice.html"))
	if frappe.db.exists("Print Format", "ENK Faktura"):
		doc = frappe.get_doc("Print Format", "ENK Faktura")
		doc.html = html
		doc.save(ignore_permissions=True)
	else:
		frappe.get_doc(
			dict(
				doctype="Print Format",
				name="ENK Faktura",
				doc_type="Sales Invoice",
				module="ENK Norge",
				custom_format=1,
				print_format_type="Jinja",
				html=html,
			)
		).insert(ignore_permissions=True)
	for doctype in ("Sales Invoice", "Purchase Invoice", "Payment Entry", "Journal Entry"):
		from frappe.custom.doctype.property_setter.property_setter import make_property_setter

		make_property_setter(doctype, None, "track_changes", 1, "Check", for_doctype=True)
