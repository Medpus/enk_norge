for (const doctype of ["Sales Invoice", "Purchase Invoice"]) {
	frappe.ui.form.on(doctype, {
		async refresh(frm) {
			if (!frm.doc.company || frm.is_new()) return;
			if (!(await frappe.db.exists("ENK Settings", frm.doc.company))) return;
			if (doctype === "Sales Invoice") {
				frm.add_custom_button(__("Norsk faktura / PDF"), () => {
					const params = new URLSearchParams({
						doctype, name: frm.doc.name, format: "ENK Faktura", no_letterhead: "1",
					});
					window.open(`/printview?${params}`, "_blank", "noopener");
				});
			}
			if (frm.doc.docstatus === 1 && !frm.doc.is_return) {
				const is_deferred_subscription = doctype === "Sales Invoice" && frm.doc.items.some((item) => item.enable_deferred_revenue);
				frm.add_custom_button(__("Lag kreditnota"), () => {
					const fields = [
						{ fieldname: "posting_date", label: __("Kreditnotadato"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
						...(is_deferred_subscription ? [{
							fieldname: "subscription_refund_source_file",
							label: __("Privat refusjonsgrunnlag"),
							fieldtype: "Attach",
							options: { make_attachments_public: false },
							reqd: 1,
							description: __("Last opp avtalt refusjon eller annet grunnlag. Det kreves for kreditnota av periodisert abonnement."),
						}] : []),
					];
					frappe.prompt(fields, async (values) => {
						let private_source_file = "";
						if (is_deferred_subscription) {
							private_source_file = await private_file_name(values.subscription_refund_source_file, __("refusjonsgrunnlaget"));
							if (!private_source_file) return;
						}
						const response = await frappe.call({
							method: "enk_norge.api.create_credit_note",
							args: { doctype, name: frm.doc.name, posting_date: values.posting_date, private_source_file },
							freeze: true,
						});
						frappe.set_route("Form", response.message.doctype, response.message.name);
					}, __("Korriger fakturaen"), __("Lag kreditnotautkast"));
				});
				if (is_deferred_subscription) {
					frm.add_custom_button(__("Lag inntektsføringsutkast"), () => open_revenue_recognition_dialog(frm));
				}
			}
			if (frm.doc.docstatus === 1 && frm.doc.outstanding_amount > 0 && !frm.doc.is_return) {
				frm.add_custom_button(__("Registrer bankbetaling"), () => open_payment_dialog(frm, doctype));
				if (doctype === "Purchase Invoice" && (frm.doc.currency || "NOK").toUpperCase() === "NOK") {
					frm.add_custom_button(__("Betalt privat"), () => {
						frappe.prompt([{ fieldname: "posting_date", label: __("Betalingsdato"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 }], async (values) => {
							const response = await frappe.call({ method: "enk_norge.api.pay_purchase_privately", args: { invoice: frm.doc.name, ...values }, freeze: true });
							frappe.set_route("Form", response.message.doctype, response.message.name);
						}, __("Kjøp betalt med egne penger"), __("Lag betalingsutkast"));
					});
				}
			}
		},
	});
}

function open_payment_dialog(frm, doctype) {
	const currency = (frm.doc.currency || "NOK").toUpperCase();
	const is_foreign_currency = currency !== "NOK";
	const dialog = new frappe.ui.Dialog({
		title: __("Betaling til kontroll"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<p class="text-muted small">${is_foreign_currency
					? __("Beløpet er i {0}. Oppgi bankens faktiske NOK-bevegelse og dokumenter betalingskursen.", [frappe.utils.escape_html(currency)])
					: __("Kontroller bankreferanse og beløp før du lager betalingsutkastet.")}</p>`,
			},
			{ fieldname: "amount", label: __("Betalt beløp på fakturaen ({0})", [currency]), fieldtype: "Currency", options: currency, default: frm.doc.outstanding_amount, reqd: 1 },
			{ fieldname: "posting_date", label: __("Betalingsdato"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
			{ fieldname: "reference", label: __("Referanse fra banken"), fieldtype: "Data", reqd: 1 },
			{
				fieldname: "fee",
				label: __("Bank- eller betalingsgebyr (NOK)"),
				fieldtype: "Currency",
				options: "NOK",
				default: 0,
				description: __("Bare gebyr uten MVA. Avgiftspliktige formidlertjenester føres som eget dokumentert kjøp."),
			},
			...(is_foreign_currency ? [
				{ fieldtype: "Section Break", label: __("Faktisk bankbevegelse") },
				{ fieldname: "bank_amount_nok", label: __("Faktisk bankbeløp (NOK)"), fieldtype: "Currency", options: "NOK", reqd: 1 },
				{ fieldname: "exchange_rate_source", label: __("Kurskilde for betalingen"), fieldtype: "Data", reqd: 1 },
				{ fieldname: "exchange_rate_date", label: __("Kursdato"), fieldtype: "Date", reqd: 1 },
			] : []),
		],
		primary_action_label: __("Lag betalingsutkast"),
		primary_action: async (values) => {
			const amount = Number(values.amount);
			const fee = Number(values.fee || 0);
			if (!Number.isFinite(amount) || amount <= 0 || !Number.isFinite(fee) || fee < 0) {
				frappe.msgprint(__("Oppgi et positivt betalingsbeløp og et gebyr på null eller mer."));
				return;
			}
			if (is_foreign_currency) {
				const bank_amount_nok = Number(values.bank_amount_nok);
				if (!Number.isFinite(bank_amount_nok) || bank_amount_nok <= 0 || !values.exchange_rate_source?.trim() || !values.exchange_rate_date) {
					frappe.msgprint(__("Oppgi faktisk bankbeløp i NOK, kurskilde og kursdato for valutabetalingen."));
					return;
				}
				if (values.exchange_rate_date > values.posting_date) {
					frappe.msgprint(__("Kursdato kan ikke være etter betalingsdatoen."));
					return;
				}
			}
			const response = await frappe.call({
				method: "enk_norge.banking.create_payment",
				args: { doctype, name: frm.doc.name, ...values },
				btn: dialog.get_primary_btn(),
				freeze: true,
				freeze_message: __("Lager betalingsutkast"),
			});
			dialog.hide();
			if (is_foreign_currency && response.message.adjustment_journal_entry) {
				frappe.show_alert({ message: __("Gebyr og valutadifferanse følger betalingsutkastet og bokføres når du bokfører betalingen."), indicator: "blue" });
			}
			frappe.set_route("Form", response.message.doctype, response.message.name);
		},
	});
	dialog.show();
}


async function private_file_name(file_url, label) {
	const file = await frappe.db.get_value("File", { file_url }, ["name", "is_private"]);
	if (!file.message?.name || !file.message.is_private) {
		frappe.msgprint(__("Last opp {0} på nytt som privat fil.", [label]));
		return "";
	}
	return file.message.name;
}

function open_revenue_recognition_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Periodiser abonnementsinntekt"),
		fields: [
			{ fieldtype: "HTML", options: `<p class="text-muted small">${__("Flytten lager et signert journalutkast for opptjent del av abonnementet. Kontroller avtalen og beløpet før du bokfører.")}</p>` },
			{ fieldname: "through_date", label: __("Opptjent til og med"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		],
		primary_action_label: __("Lag journalutkast"),
		primary_action: async (values) => {
			const response = await frappe.call({
				method: "enk_norge.deferrals.create_revenue_recognition_draft",
				args: { company: frm.doc.company, invoice_name: frm.doc.name, through_date: values.through_date },
				btn: dialog.get_primary_btn(),
				freeze: true,
				freeze_message: __("Lager periodiseringsutkast"),
			});
			dialog.hide();
			frappe.set_route("Form", response.message.doctype, response.message.name);
		},
	});
	dialog.show();
}
