// Felles handlinger på bokførte fakturaer. Brukes både av ENK-siden og ERPNext-skjemaet.
// `doc` trenger doctype, name, company, currency, outstanding_amount og deferred.
// Beløp fra API-et er tekst med punktum. Gjør dem til tall før de blir standardverdier,
// ellers leser det norske tallformatet punktum som tusenskille.
window.enk_norge_actions = {
	async private_file_name(file_url, label) {
		const file = await frappe.db.get_value("File", { file_url }, ["name", "is_private"]);
		if (!file.message?.name || !file.message.is_private) {
			frappe.msgprint(__("Last opp {0} på nytt som privat fil.", [label]));
			return "";
		}
		return file.message.name;
	},

	credit_note(doc, on_created) {
		const fields = [
			{ fieldname: "posting_date", label: __("Kreditnotadato"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
			...(doc.deferred ? [{
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
			if (doc.deferred) {
				private_source_file = await this.private_file_name(values.subscription_refund_source_file, __("refusjonsgrunnlaget"));
				if (!private_source_file) return;
			}
			const response = await frappe.call({
				method: "enk_norge.api.create_credit_note",
				args: { doctype: doc.doctype, name: doc.name, posting_date: values.posting_date, private_source_file },
				freeze: true,
			});
			on_created(response.message);
		}, __("Korriger fakturaen"), __("Lag kreditnota"));
	},

	pay_privately(doc, on_created) {
		frappe.prompt([
			{ fieldtype: "HTML", options: `<p class="text-muted small">${__("Bruk dette når du betalte med egne penger. Beløpet føres som ditt innskudd i foretaket, og kostnaden gir fradrag som vanlig.")}</p>` },
			{ fieldname: "posting_date", label: __("Betalingsdato"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		], async (values) => {
			const response = await frappe.call({ method: "enk_norge.api.pay_purchase_privately", args: { invoice: doc.name, posting_date: values.posting_date }, freeze: true });
			on_created(response.message);
		}, __("Betalt med egne penger"), __("Registrer betaling"));
	},

	bank_payment(doc, on_created) {
		const currency = (doc.currency || "NOK").toUpperCase();
		const is_foreign_currency = currency !== "NOK";
		const incoming = doc.doctype === "Sales Invoice";
		const dialog = new frappe.ui.Dialog({
			title: incoming ? __("Betaling mottatt") : __("Betalt fra bankkontoen"),
			fields: [
				...(is_foreign_currency ? [{
					fieldtype: "HTML",
					options: `<p class="text-muted small">${__("Beløpet er i {0}. Oppgi bankens faktiske NOK-bevegelse og dokumenter kursen.", [frappe.utils.escape_html(currency)])}</p>`,
				}] : []),
				{ fieldname: "amount", label: __("Beløp ({0})", [currency]), fieldtype: "Currency", options: currency, default: Number(doc.outstanding_amount), reqd: 1 },
				{ fieldname: "posting_date", label: __("Betalingsdato"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
				{ fieldname: "reference", label: __("Referanse fra kontoutskriften"), fieldtype: "Data", reqd: 1, description: __("For eksempel arkivreferanse eller tekst fra banklinjen.") },
				{
					fieldname: "fee",
					label: __("Bankgebyr (NOK)"),
					fieldtype: "Currency",
					options: "NOK",
					default: 0,
					description: __("Bare gebyr uten MVA."),
				},
				...(is_foreign_currency ? [
					{ fieldtype: "Section Break", label: __("Faktisk bankbevegelse") },
					{ fieldname: "bank_amount_nok", label: __("Beløp på kontoen (NOK)"), fieldtype: "Currency", options: "NOK", reqd: 1 },
					{ fieldname: "exchange_rate_source", label: __("Kurskilde"), fieldtype: "Data", reqd: 1 },
					{ fieldname: "exchange_rate_date", label: __("Kursdato"), fieldtype: "Date", reqd: 1 },
				] : []),
			],
			primary_action_label: __("Registrer betaling"),
			primary_action: async (values) => {
				const amount = Number(values.amount);
				const fee = Number(values.fee || 0);
				if (!Number.isFinite(amount) || amount <= 0 || !Number.isFinite(fee) || fee < 0) {
					frappe.msgprint(__("Oppgi et positivt beløp og et gebyr på null eller mer."));
					return;
				}
				if (is_foreign_currency) {
					const bank_amount_nok = Number(values.bank_amount_nok);
					if (!Number.isFinite(bank_amount_nok) || bank_amount_nok <= 0 || !values.exchange_rate_source?.trim() || !values.exchange_rate_date) {
						frappe.msgprint(__("Oppgi beløpet på kontoen i NOK, kurskilde og kursdato."));
						return;
					}
					if (values.exchange_rate_date > values.posting_date) {
						frappe.msgprint(__("Kursdato kan ikke være etter betalingsdatoen."));
						return;
					}
				}
				const response = await frappe.call({
					method: "enk_norge.banking.create_payment",
					args: { doctype: doc.doctype, name: doc.name, ...values },
					btn: dialog.get_primary_btn(),
					freeze: true,
					freeze_message: __("Lager betaling"),
				});
				dialog.hide();
				on_created(response.message);
			},
		});
		dialog.show();
	},

	recognize_revenue(doc, on_created) {
		const dialog = new frappe.ui.Dialog({
			title: __("Inntektsfør opptjent abonnement"),
			fields: [
				{ fieldtype: "HTML", options: `<p class="text-muted small">${__("Fører den delen av forskuddsbetalingen som er opptjent fram til datoen, som inntekt.")}</p>` },
				{ fieldname: "through_date", label: __("Opptjent til og med"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
			],
			primary_action_label: __("Lag inntektsføring"),
			primary_action: async (values) => {
				const response = await frappe.call({
					method: "enk_norge.deferrals.create_revenue_recognition_draft",
					args: { company: doc.company, invoice_name: doc.name, through_date: values.through_date },
					btn: dialog.get_primary_btn(),
					freeze: true,
				});
				dialog.hide();
				on_created(response.message);
			},
		});
		dialog.show();
	},
};
