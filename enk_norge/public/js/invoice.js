for (const doctype of ["Sales Invoice", "Purchase Invoice"]) {
	frappe.ui.form.on(doctype, {
		async refresh(frm) {
			if (!frm.doc.company || frm.is_new()) return;
			if (!(await frappe.db.exists("ENK Settings", frm.doc.company))) return;
			const actions = window.enk_norge_actions;
			const doc = {
				doctype,
				name: frm.doc.name,
				company: frm.doc.company,
				currency: frm.doc.currency,
				outstanding_amount: frm.doc.outstanding_amount,
				deferred: doctype === "Sales Invoice" && frm.doc.items.some((item) => item.enable_deferred_revenue),
			};
			const open_created = (created) => frappe.set_route("Form", created.doctype, created.name);
			frm.add_custom_button(__("Vis i ENK Norge"), () => frappe.set_route("enk-norge", "bilag", doctype, frm.doc.name));
			if (doctype === "Sales Invoice") {
				frm.add_custom_button(__("Norsk faktura / PDF"), () => {
					const params = new URLSearchParams({
						doctype, name: frm.doc.name, format: "ENK Faktura", no_letterhead: "1",
					});
					window.open(`/printview?${params}`, "_blank", "noopener");
				});
			}
			if (frm.doc.docstatus === 1 && !frm.doc.is_return) {
				frm.add_custom_button(__("Lag kreditnota"), () => actions.credit_note(doc, open_created));
				if (doc.deferred) {
					frm.add_custom_button(__("Lag inntektsføringsutkast"), () => actions.recognize_revenue(doc, open_created));
				}
			}
			if (frm.doc.docstatus === 1 && frm.doc.outstanding_amount > 0 && !frm.doc.is_return) {
				frm.add_custom_button(__("Registrer bankbetaling"), () => actions.bank_payment(doc, open_created));
				if (doctype === "Purchase Invoice" && (frm.doc.currency || "NOK").toUpperCase() === "NOK") {
					frm.add_custom_button(__("Betalt privat"), () => actions.pay_privately(doc, open_created));
				}
			}
		},
	});
}
