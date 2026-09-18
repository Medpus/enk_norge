frappe.pages["enk-norge"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Oversikt"),
		single_column: true,
	});

	frappe.require("/assets/enk_norge/css/enk_norge.css", () => {
		wrapper.enk_norge = new EnkNorgePage(wrapper);
	});
};

class EnkNorgePage {
	constructor(wrapper) {
		this.wrapper = $(wrapper);
		this.page = wrapper.page;
		this.body = this.page.body.addClass("enk-norge-page");
		this.companies = [];
		this.load_companies();
	}

	load_companies() {
		this.render_loading();
		frappe.call({
			method: "enk_norge.setup.list_companies",
			callback: (response) => {
				this.companies = response.message || [];
				this.render();
			},
			error: () => this.render_load_error(),
		});
	}

	render() {
		if (!this.companies.length) {
			this.render_onboarding();
			return;
		}

		this.render_dashboard();
	}

	render_loading() {
		this.body.html(`
			<div class="enk-loading" aria-live="polite">
				<div class="skeleton enk-loading-title"></div>
				<div class="skeleton enk-loading-line"></div>
				<div class="skeleton enk-loading-line short"></div>
			</div>
		`);
	}

	render_load_error() {
		this.body.html(`
			<section class="enk-state" aria-live="assertive">
				<h2>${__("Kunne ikke hente foretak")}</h2>
				<p>${__("Prøv på nytt. Hvis feilen fortsetter, sjekk at ENK Norge-oppsettet er migrert.")}</p>
				<button class="btn btn-default btn-sm" type="button" data-action="retry">
					${__("Prøv igjen")}
				</button>
			</section>
		`);
		this.body.find('[data-action="retry"]').on("click", () => this.load_companies());
	}

	render_onboarding() {
		this.page.clear_actions();
		const can_create_company = frappe.user.has_role("Accounts Manager") || frappe.user.has_role("System Manager");
		this.body.html(`
			<section class="enk-onboarding" aria-labelledby="enk-welcome-title">
				<div class="enk-onboarding-intro">
					<h2 id="enk-welcome-title">${__("Gjør klart foretaket før første bilag")}</h2>
					<p>${__("Oppsettet kobler foretakets grunnopplysninger til ENK Norge. Du kan bruke ERPNext videre, men norsk bokføring må bygges og kontrolleres før reelle bilag føres.")}</p>
					${can_create_company
						? `<button class="btn btn-primary" type="button" data-action="start-onboarding">${__("Fullfør oppsett")}</button>`
						: `<p class="enk-permission-note">${__("Du trenger rollen Accounts Manager eller System Manager for å opprette foretak.")}</p>`}
				</div>
				<div class="enk-onboarding-details">
					<div>
						<h3>${__("Ha dette klart")}</h3>
						<ul>
							<li>${__("Firmanavn, organisasjonsnummer og forretningsadresse")}</li>
							<li>${__("Norsk bankkonto og første bokføringsdato")}</li>
							<li>${__("MVA-status og datoen registreringen gjelder fra, hvis aktuelt")}</li>
						</ul>
					</div>
					<div class="enk-history-note">
						<h3>${__("Bytter du fra et tidligere regnskap?")}</h3>
						<p>${__("Avklar inngående balanse, åpne poster og første fakturanummer før du begynner. Oppsettet flytter ikke historikk automatisk.")}</p>
					</div>
				</div>
			</section>
		`);

		this.body.find('[data-action="start-onboarding"]').on("click", () => this.start_onboarding());
	}

	start_onboarding() {
		this.wizard_step = 1;
		this.wizard_data = { vat_registered: 0, history_confirmed: 0 };
		this.render_wizard();
	}

	render_wizard() {
		const data = this.wizard_data;
		this.body.html(`
			<section class="enk-wizard" aria-labelledby="enk-wizard-title">
				<header class="enk-wizard-header">
					<div>
						<h2 id="enk-wizard-title">${__("Sett opp foretak")}</h2>
						<p>${__("Du kan gå tilbake og kontrollere opplysningene før foretaket opprettes.")}</p>
					</div>
					<div class="enk-stepper" aria-label="${__("Fremdrift")}">
						${this.step_button(1, __("Foretak"))}
						${this.step_button(2, __("Kontakt og MVA"))}
						${this.step_button(3, __("Kontroller"))}
					</div>
				</header>
				<form class="enk-wizard-form" novalidate>
					${this.wizard_fields(data)}
					<div class="enk-form-error hide" role="alert"></div>
					<footer class="enk-wizard-actions">
						<button class="btn btn-default ${this.wizard_step === 1 ? "hide" : ""}" type="button" data-action="previous">
							${__("Tilbake")}
						</button>
						<button class="btn btn-primary" type="submit">
							${this.wizard_step === 3 ? __("Opprett foretak") : __("Fortsett")}
						</button>
					</footer>
				</form>
			</section>
		`);

		this.body.find('[data-action="previous"]').on("click", () => {
			this.collect_wizard_data();
			this.wizard_step -= 1;
			this.render_wizard();
		});
		this.body.find(".enk-wizard-form").on("submit", (event) => this.advance_wizard(event));
		this.body.find('[name="vat_registered"]').on("change", () => this.toggle_vat_date());
		this.toggle_vat_date();
	}

	step_button(number, label) {
		const current = number === this.wizard_step;
		const complete = number < this.wizard_step;
		return `<span class="enk-step ${current ? "is-current" : ""} ${complete ? "is-complete" : ""}">
			<span class="enk-step-number">${number}</span>
			<span>${label}</span>
		</span>`;
	}

	wizard_fields(data) {
		if (this.wizard_step === 1) {
			return `
				<div class="enk-form-section">
					<h3>${__("Foretaket")}</h3>
					<div class="enk-field-grid">
						${this.field("company_name", __("Firmanavn"), "text", data.company_name, true)}
						${this.field("abbr", __("Forkortelse"), "text", data.abbr, true, __("Brukes i kontonavn. Velg en kort og tydelig forkortelse."))}
						${this.field("organization_number", __("Organisasjonsnummer"), "text", data.organization_number, true, __("Ni siffer, uten personopplysninger."))}
						${this.field("start_date", __("Første bokføringsdato"), "date", data.start_date, true)}
					</div>
				</div>
			`;
		}

		if (this.wizard_step === 2) {
			return `
				<div class="enk-form-section">
					<h3>${__("Kontakt, bank og MVA")}</h3>
					<div class="enk-field-grid">
						${this.field("address_line", __("Forretningsadresse"), "text", data.address_line, true)}
						${this.field("postal_code", __("Postnummer"), "text", data.postal_code, true)}
						${this.field("city", __("Poststed"), "text", data.city, true)}
						${this.field("phone", __("Telefon"), "tel", data.phone, true, __("Bruk et telefonnummer foretaket kan kontaktes på."))}
						${this.field("bank_name", __("Bankens navn"), "text", data.bank_name, true)}
						${this.field("bank_account", __("Norsk bankkonto"), "text", data.bank_account, true, __("Bruk kontonummeret foretaket bruker i regnskapet."))}
					</div>
					<label class="enk-check-field">
						<input name="vat_registered" type="checkbox" ${data.vat_registered ? "checked" : ""}>
						<span>${__("Foretaket er registrert i Merverdiavgiftsregisteret")}</span>
					</label>
					<div class="enk-vat-date">
						${this.field("vat_registration_date", __("MVA gjelder fra"), "date", data.vat_registration_date, false)}
					</div>
				</div>
			`;
		}

		return `
			<div class="enk-form-section">
				<h3>${__("Kontroller før opprettelse")}</h3>
				<div class="enk-review-list">
					${this.review_item(__("Foretak"), data.company_name)}
					${this.review_item(__("Første bokføringsdato"), data.start_date)}
					${this.review_item(__("MVA-status"), data.vat_registered ? __("Registrert") : __("Ikke registrert"))}
				</div>
				<div class="enk-history-note">
					<h4>${__("Tidligere regnskap må være avklart")}</h4>
					<p>${__("Hvis foretaket allerede har bokført aktivitet, må inngående balanse, åpne poster og første fakturanummer være avklart før du fortsetter.")}</p>
				</div>
				<label class="enk-check-field">
					<input name="history_confirmed" type="checkbox" ${data.history_confirmed ? "checked" : ""}>
					<span>${__("Jeg har avklart tidligere regnskap, eller bekrefter at foretaket starter uten historikk.")}</span>
				</label>
			</div>
		`;
	}

	field(name, label, type, value, required, description) {
		const safe_value = frappe.utils.escape_html(value || "");
		return `
			<div class="form-group enk-field">
				<label for="enk-${name}">${label}${required ? ' <span class="text-danger">*</span>' : ""}</label>
				<input id="enk-${name}" class="form-control" name="${name}" type="${type}" value="${safe_value}" ${required ? "required" : ""}>
				${description ? `<p class="help-box small text-muted">${description}</p>` : ""}
			</div>
		`;
	}

	review_item(label, value) {
		return `<div><span>${label}</span><strong>${frappe.utils.escape_html(value || __("Ikke oppgitt"))}</strong></div>`;
	}

	collect_wizard_data() {
		const form = this.body.find(".enk-wizard-form");
		form.serializeArray().forEach(({ name, value }) => {
			this.wizard_data[name] = value.trim();
		});
		this.wizard_data.vat_registered = form.find('[name="vat_registered"]').is(":checked") ? 1 : 0;
		this.wizard_data.history_confirmed = form.find('[name="history_confirmed"]').is(":checked") ? 1 : 0;
	}

	advance_wizard(event) {
		event.preventDefault();
		this.collect_wizard_data();
		const error = this.validate_wizard_step();
		if (error) {
			this.show_wizard_error(error);
			return;
		}

		if (this.wizard_step < 3) {
			this.wizard_step += 1;
			this.render_wizard();
			return;
		}

		this.create_company();
	}

	validate_wizard_step() {
		const required_by_step = {
			1: ["company_name", "abbr", "organization_number", "start_date"],
			2: ["address_line", "postal_code", "city", "phone", "bank_name", "bank_account"],
			3: ["history_confirmed"],
		};
		const missing = required_by_step[this.wizard_step].some((fieldname) => !this.wizard_data[fieldname]);
		if (missing) {
			return __("Fyll ut feltene som er merket med stjerne.");
		}
		if (this.wizard_data.vat_registered && !this.wizard_data.vat_registration_date) {
			return __("Oppgi datoen MVA-registreringen gjelder fra.");
		}
		return null;
	}

	show_wizard_error(message) {
		this.body.find(".enk-form-error").removeClass("hide").text(message);
	}

	toggle_vat_date() {
		const vat_registered = this.body.find('[name="vat_registered"]').is(":checked");
		this.body.find(".enk-vat-date").toggleClass("hide", !vat_registered);
	}

	create_company() {
		const button = this.body.find('.enk-wizard-form button[type="submit"]');
		frappe.call({
			method: "enk_norge.setup.create_company",
			args: { data: this.wizard_data },
			btn: button,
			freeze: true,
			freeze_message: __("Oppretter foretak"),
			callback: (response) => {
				const company = response.message?.company || this.wizard_data.company_name;
				frappe.show_alert({ message: __("{0} er opprettet.", [company]), indicator: "green" });
				this.load_companies();
			},
		});
	}

	render_dashboard() {
		const selected = this.companies.find((company) => company.configured) || this.companies[0];
		this.render_dashboard_content(selected, null);
		if (selected.configured) {
			this.load_dashboard(selected);
		}
	}

	load_dashboard(company) {
		frappe.call({
			method: "enk_norge.api.dashboard",
			args: { company: company.company },
			callback: (response) => this.render_dashboard_content(company, response.message || {}),
			error: () => this.render_dashboard_content(company, { error: true }),
		});
	}

	render_dashboard_content(selected, dashboard) {
		this.page.set_primary_action(__("Ny salgsfaktura"), () => {
			this.open_sale_dialog(selected.company);
		});
		const status = !selected.configured
			? __("Foretaket trenger fortsatt norsk oppsett.")
			: dashboard === null
				? __("Henter kladder og ubetalte fakturaer.")
				: __("Regnskap for {0}", [selected.company]);
		this.body.html(`
			<section class="enk-dashboard" aria-labelledby="enk-dashboard-title">
				<header class="enk-dashboard-header">
					<div>
						<h2 id="enk-dashboard-title">${frappe.utils.escape_html(selected.company)}</h2>
						<p>${status}</p>
					</div>
					<a class="btn btn-default btn-sm" href="#Form/Company/${encodeURIComponent(selected.company)}">
						${__("Åpne foretak")}
					</a>
				</header>
				<div class="enk-dashboard-main">
					${this.dashboard_overview(dashboard)}
					<section class="enk-standard-actions" aria-labelledby="enk-standard-title">
						<h3 id="enk-standard-title">${__("Registrer et nytt bilag")}</h3>
						<p>${__("Salg og kjøp opprettes som kladd. Kontroller vedlegg og innhold, og bokfør dokumentet i ERPNext når det er klart.")}</p>
						<div class="enk-action-row">
							<button class="btn btn-default" type="button" data-action="new-sale">${__("Ny salgsfaktura")}</button>
							<button class="btn btn-default" type="button" data-action="invoice-timesheet">${__("Fakturer timer")}</button>
							<button class="btn btn-default" type="button" data-action="invoice-subscription">${__("Fakturer abonnement")}</button>
							<button class="btn btn-default" type="button" data-action="new-purchase">${__("Nytt kjøp")}</button>
							<a class="btn btn-default" href="#List/Sales Invoice/List">${__("Se fakturaer")}</a>
							<a class="btn btn-default" href="#List/Purchase Invoice/List">${__("Se kjøp")}</a>
						</div>
						<h3 class="enk-actions-heading">${__("Avstemming og rapportering")}</h3>
							<div class="enk-action-row">
								<button class="btn btn-default" type="button" data-action="import-bank">${__("Importer bankutskrift")}</button>
								<button class="btn btn-default" type="button" data-action="new-settlement">${__("Registrer oppgjør fra betalingsformidler")}</button>
								<button class="btn btn-default" type="button" data-action="owner-transfer">${__("Eierinnskudd eller uttak")}</button>
							<a class="btn btn-default" href="#List/ENK VAT Return/List">${__("MVA-rapporter")}</a>
							<button class="btn btn-default" type="button" data-action="build-year-report">${__("Lag årsrapport")}</button>
							<a class="btn btn-default" href="#List/ENK Year Report/List">${__("Årsrapporter")}</a>
							<button class="btn btn-default" type="button" data-action="export-saft">${__("Eksporter SAF-T")}</button>
						</div>
						<h3 class="enk-actions-heading">${__("Utstyr og saldogrupper")}</h3>
						<div class="enk-action-row">
							<button class="btn btn-default" type="button" data-action="tax-pool">${__("Opprett saldogruppe")}</button>
							<button class="btn btn-default" type="button" data-action="open-tax-pools">${__("Åpne saldogrupper")}</button>
							<button class="btn btn-default" type="button" data-action="depreciation-draft">${__("Lag avskrivningsutkast")}</button>
							<button class="btn btn-default" type="button" data-action="asset-disposal">${__("Driftsmiddelavgang")}</button>
						</div>
					</section>
				</div>
			</section>
		`);
		this.body.find('[data-action="new-sale"]').on("click", () => this.open_sale_dialog(selected.company));
		this.body.find('[data-action="invoice-timesheet"]').on("click", () => this.open_timesheet_invoice_dialog(selected.company));
		this.body.find('[data-action="invoice-subscription"]').on("click", () => this.open_subscription_invoice_dialog(selected.company));
		this.body.find('[data-action="new-purchase"]').on("click", () => {
			this.open_purchase_dialog(selected.company);
		});
			this.body.find('[data-action="import-bank"]').on("click", () => this.open_bank_import_dialog(selected.company));
			this.body.find('[data-action="new-settlement"]').on("click", () => this.open_settlement_dialog(selected.company));
			this.body.find('[data-action="owner-transfer"]').on("click", () => this.open_owner_transfer_dialog(selected.company));
		this.body.find('[data-action="build-year-report"]').on("click", () => this.open_year_report_dialog(selected.company));
		this.body.find('[data-action="tax-pool"]').on("click", () => this.open_tax_pool_dialog(selected.company));
		this.body.find('[data-action="open-tax-pools"]').on("click", () => frappe.set_route("List", "ENK Tax Pool", "List", { company: selected.company, income_year: 2026 }));
		this.body.find('[data-action="depreciation-draft"]').on("click", () => this.open_created_draft(null, "enk_norge.year_end.create_depreciation_journal_entry_draft", { company: selected.company, income_year: 2026 }));
		this.body.find('[data-action="asset-disposal"]').on("click", () => this.open_asset_disposal_dialog(selected.company));
		this.body.find('[data-action="export-saft"]').on("click", () => this.open_saft_dialog(selected.company));
	}

	dashboard_overview(dashboard) {
		if (dashboard === null) {
			return `<section class="enk-state enk-overview-loading" aria-live="polite">
				<h3>${__("Daglig oversikt")}</h3>
				<div class="skeleton enk-loading-line"></div>
				<div class="skeleton enk-loading-line short"></div>
			</section>`;
		}
		if (dashboard?.error) {
			return `<section class="enk-state" aria-live="polite">
				<h3>${__("Daglig oversikt er ikke tilgjengelig")}</h3>
				<p>${__("Kladder og ubetalte fakturaer kunne ikke hentes nå. Du kan fortsatt åpne standardlistene i ERPNext.")}</p>
			</section>`;
		}
		if (!dashboard) {
			return `<section class="enk-state">
				<h3>${__("Fullfør norsk oppsett")}</h3>
				<p>${__("Dette foretaket mangler ENK-innstillinger. Åpne foretaket for videre oppsett.")}</p>
			</section>`;
		}

		return `<section class="enk-overview" aria-labelledby="enk-overview-title">
			<h3 id="enk-overview-title">${__("Daglig oversikt")}</h3>
			${this.vat_threshold_notice(dashboard)}
			<div class="enk-overview-counts enk-overview-amounts">
				${this.overview_amount(__("Inntekter hittil"), dashboard.income)}
				${this.overview_amount(__("Kostnader hittil"), dashboard.expenses)}
				${this.overview_amount(__("Resultat hittil"), dashboard.result)}
				${this.overview_amount(__("Bankbeholdning"), dashboard.bank_balance)}
			</div>
			${dashboard.bank_account_record ? `<a class="enk-bank-link" href="#Form/Bank Account/${encodeURIComponent(dashboard.bank_account_record)}">${__("Åpne bankkonto for avstemming")}</a>` : ""}
			<div class="enk-overview-counts">
				${this.overview_count(__("Kladder for salg"), dashboard.draft_sales?.length || 0)}
				${this.overview_count(__("Kladder for kjøp"), dashboard.draft_purchases?.length || 0)}
				${this.overview_count(__("Ubetalte fakturaer"), dashboard.unpaid_sales?.length || 0)}
			</div>
			${this.document_list(__("Salgskladder"), dashboard.draft_sales, "customer", "grand_total", "Sales Invoice")}
			${this.document_list(__("Kjøpskladder"), dashboard.draft_purchases, "supplier", "grand_total", "Purchase Invoice")}
			${this.document_list(__("Ubetalte fakturaer"), dashboard.unpaid_sales, "customer", "outstanding_amount", "Sales Invoice")}
			${this.document_list(__("Fakturaer som må følges opp ved MVA-registrering"), dashboard.vat_followup, "customer", "grand_total", "Sales Invoice")}
		</section>`;
	}

	vat_threshold_notice(dashboard) {
		const crossing = dashboard.vat_first_crossing;
		if (dashboard.vat_registered || !crossing?.date || crossing.basis === undefined) {
			return "";
		}
		const date = frappe.datetime.str_to_user(crossing.date);
		const basis = frappe.utils.escape_html(format_nok(crossing.basis));
		return `<section class="enk-vat-threshold-notice" aria-label="${__("MVA-avklaring")}">
			<h4>${__("MVA-registrering må avklares")}</h4>
			<p>${__("Omsetningen passerte {0} {1}. Avklar alle berørte salg fra denne datoen før videre bokføring.", [date, basis])}</p>
		</section>`;
	}

	overview_count(label, value) {
		return `<div><strong>${value}</strong><span>${label}</span></div>`;
	}

	overview_amount(label, value) {
		return `<div><strong>${frappe.utils.escape_html(format_nok(value))}</strong><span>${label}</span></div>`;
	}

	document_list(title, documents = [], party_field, amount_field, doctype) {
		if (!documents.length) {
			return "";
		}
		const rows = documents
			.map((document) => {
				const name = frappe.utils.escape_html(document.name);
				const party = frappe.utils.escape_html(document[party_field] || "");
				const amount = frappe.utils.escape_html(format_nok(document[amount_field]));
				return `<li><a href="#Form/${doctype}/${encodeURIComponent(document.name)}"><span>${name}</span><span>${party}</span><strong>${amount}</strong></a></li>`;
			})
			.join("");
		return `<div class="enk-document-list"><h4>${title}</h4><ul>${rows}</ul></div>`;
	}

	open_sale_dialog(company) {
		const dialog = new frappe.ui.Dialog({
			title: __("Ny salgsfaktura"),
			fields: [
				{ fieldname: "customer", label: __("Kunde"), fieldtype: "Link", options: "Customer", reqd: 1 },
				{ fieldname: "customer_address", label: __("Fakturaadresse"), fieldtype: "Link", options: "Address", reqd: 1 },
				{ fieldname: "description", label: __("Hva er levert?"), fieldtype: "Small Text", reqd: 1 },
				{ fieldname: "delivery_date", label: __("Leveringsdato"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
				{ fieldname: "unit_price", label: __("Beløp ekskl. MVA"), fieldtype: "Currency", reqd: 1 },
				{
					fieldname: "currency",
					label: __("Valuta"),
					fieldtype: "Link",
					options: "Currency",
					default: "NOK",
					reqd: 1,
					description: __("Valutasalg støttes bare for fjernleverbare tjenester til utenlandsk bedrift."),
				},
				{
					fieldname: "conversion_rate",
					label: __("Kurs til NOK"),
					fieldtype: "Float",
					precision: 6,
					depends_on: "eval:doc.currency!='NOK'",
					description: __("NOK per enhet i dokumentvalutaen."),
				},
				{
					fieldname: "exchange_rate_source",
					label: __("Kurskilde"),
					fieldtype: "Data",
					depends_on: "eval:doc.currency!='NOK'",
					description: __("For eksempel bankens kursnotering eller betalingsformidlerens oppgjør."),
				},
				{
					fieldname: "exchange_rate_date",
					label: __("Kursdato"),
					fieldtype: "Date",
					depends_on: "eval:doc.currency!='NOK'",
				},
				{ fieldname: "due_date", label: __("Forfallsdato"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
				{
					fieldname: "tax_treatment",
					label: __("Avgiftsbehandling"),
					fieldtype: "Select",
					options: ["", "Domestic 25", "Domestic 15", "Domestic 12", "Not registered", "Export services", "Exempt"].join("\n"),
					description: __("La feltet stå tomt for standardbehandling. Velg eksplisitt for eksport eller unntatt omsetning."),
				},
				{
					fieldname: "tax_reason",
					label: __("Regel og begrunnelse for unntatt omsetning"),
					fieldtype: "Small Text",
					depends_on: "eval:doc.tax_treatment=='Exempt'",
				},
				{ fieldname: "defer_revenue", label: __("Periodiser forskuddsbetalt SaaS-abonnement"), fieldtype: "Check", change: () => this.toggle_subscription_fields(dialog) },
				{ fieldname: "service_start_date", label: __("Tjenestestart"), fieldtype: "Date", depends_on: "eval:doc.defer_revenue" },
				{ fieldname: "service_end_date", label: __("Tjenesteslutt"), fieldtype: "Date", depends_on: "eval:doc.defer_revenue" },
				{
					fieldname: "subscription_source_file",
					label: __("Privat avtaledokument"),
					fieldtype: "Attach",
					options: { make_attachments_public: false },
					depends_on: "eval:doc.defer_revenue",
					description: __("Periodisering krever en privat avtale. Fakturaen må være før eller på tjenestestart."),
				},
			],
			primary_action_label: __("Opprett kladd"),
			primary_action: async (values) => {
				if (!this.validate_currency_values(values, values.delivery_date, values.tax_treatment === "Export services", __("Valutasalg"))) {
					return;
				}
				if (values.tax_treatment === "Exempt" && !values.tax_reason?.trim()) {
					frappe.msgprint(__("Oppgi den konkrete regelen og begrunnelsen for unntatt omsetning."));
					return;
				}
				if (values.defer_revenue) {
					if (!values.service_start_date || !values.service_end_date || !values.subscription_source_file) {
						frappe.msgprint(__("Periodisering krever tjenestestart, tjenesteslutt og privat avtaledokument."));
						return;
					}
					if (values.delivery_date > values.service_start_date || values.service_end_date < values.service_start_date) {
						frappe.msgprint(__("Fakturaen må være før eller på tjenestestart, og tjenesteslutt kan ikke være før start."));
						return;
					}
					const file = await frappe.db.get_value("File", { file_url: values.subscription_source_file }, ["name", "is_private"]);
					if (!file.message?.name || !file.message.is_private) {
						frappe.msgprint(__("Last opp avtaledokumentet på nytt som privat fil."));
						return;
					}
					values.subscription_source_file = file.message.name;
				}
				delete values.defer_revenue;
				this.create_draft(dialog, "enk_norge.api.create_sale", { ...values, company, quantity: 1 });
			},
		});
		dialog.show();
		this.toggle_subscription_fields(dialog);
	}

	toggle_subscription_fields(dialog) {
		const enabled = Boolean(dialog.get_value("defer_revenue"));
		for (const fieldname of ["service_start_date", "service_end_date", "subscription_source_file"]) {
			dialog.get_field(fieldname).toggle(enabled);
		}
	}

	open_timesheet_invoice_dialog(company) {
		const dialog = new frappe.ui.Dialog({
			title: __("Fakturer godkjente timer"),
			fields: [
				{ fieldtype: "HTML", options: `<p class="text-muted small">${__("Velg en innsendt Timesheet i dette foretaket. Utkastet bruker Timesheet-satsen; endre Timesheet først hvis prisen har endret seg.")}</p>` },
				{ fieldname: "timesheet", label: __("Timesheet"), fieldtype: "Link", options: "Timesheet", reqd: 1 },
				{ fieldname: "customer", label: __("Kunde"), fieldtype: "Link", options: "Customer", reqd: 1 },
				{ fieldname: "customer_address", label: __("Fakturaadresse"), fieldtype: "Link", options: "Address", reqd: 1 },
				{ fieldname: "item_code", label: __("Vare"), fieldtype: "Link", options: "Item", reqd: 1 },
				{ fieldname: "posting_date", label: __("Fakturadato"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
				{ fieldname: "delivery_date", label: __("Leveringsdato"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
				{ fieldname: "delivery_description", label: __("Hva er levert?"), fieldtype: "Small Text", reqd: 1 },
				{ fieldname: "due_date", label: __("Forfallsdato"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
				{ fieldname: "unit_price", label: __("Timesheet-sats (valgfri kontroll)"), fieldtype: "Currency", options: "NOK", description: __("Må være lik Timesheet-satsen. La feltet stå tomt for å bruke satsen derfra.") },
				...this.sale_tax_fields(),
			],
			primary_action_label: __("Opprett kladd"),
			primary_action: (values) => {
				if (!this.validate_tax_reason(values)) return;
				this.create_draft(dialog, "enk_norge.billing.create_timesheet_invoice_draft", { company, ...values });
			},
		});
		dialog.show();
	}

	open_subscription_invoice_dialog(company) {
		const dialog = new frappe.ui.Dialog({
			title: __("Fakturer abonnement"),
			fields: [
				{ fieldtype: "HTML", options: `<p class="text-muted small">${__("Bruk abonnementets aktive periode, eller neste direkte sammenhengende periode når den forrige er bokført. Slå av «Submit Generated Invoices». Flyten lager bare kladd, hopper aldri over en periode og avviser overlappende faktura.")}</p>` },
				{ fieldname: "subscription", label: __("Abonnement"), fieldtype: "Link", options: "Subscription", reqd: 1 },
				{ fieldname: "customer", label: __("Kunde"), fieldtype: "Link", options: "Customer", reqd: 1 },
				{ fieldname: "customer_address", label: __("Fakturaadresse"), fieldtype: "Link", options: "Address", reqd: 1 },
				{ fieldname: "posting_date", label: __("Fakturadato"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
				{ fieldname: "delivery_date", label: __("Leveringsdato"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
				{ fieldname: "delivery_description", label: __("Hva er levert?"), fieldtype: "Small Text", reqd: 1 },
				{ fieldname: "due_date", label: __("Forfallsdato"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
				{ fieldname: "service_start_date", label: __("Tjenestestart"), fieldtype: "Date", reqd: 1 },
				{ fieldname: "service_end_date", label: __("Tjenesteslutt"), fieldtype: "Date", reqd: 1 },
				{
					fieldname: "subscription_source_file",
					label: __("Privat avtaledokument"),
					fieldtype: "Attach",
					options: { make_attachments_public: false },
					reqd: 1,
					description: __("Avtalen må ligge som privat fil og dokumentere perioden."),
				},
				...this.sale_tax_fields(),
			],
			primary_action_label: __("Opprett kladd"),
			primary_action: async (values) => {
				if (!this.validate_tax_reason(values)) return;
				if (values.service_end_date < values.service_start_date || values.posting_date > values.service_start_date) {
					frappe.msgprint(__("Tjenesteperioden må være sammenhengende, og fakturaen må være før eller på tjenestestart."));
					return;
				}
				const file = await this.private_file_name(values.subscription_source_file, __("avtaledokumentet"));
				if (!file) return;
				values.subscription_source_file = file;
				this.create_draft(dialog, "enk_norge.billing.create_subscription_invoice_draft", { company, ...values });
			},
		});
		dialog.show();
	}

	sale_tax_fields() {
		return [
			{
				fieldname: "tax_treatment",
				label: __("Avgiftsbehandling"),
				fieldtype: "Select",
				options: ["", "Domestic 25", "Domestic 15", "Domestic 12", "Not registered", "Export services", "Exempt"].join("\n"),
			},
			{ fieldname: "tax_reason", label: __("Regel og begrunnelse for unntatt omsetning"), fieldtype: "Small Text", depends_on: "eval:doc.tax_treatment=='Exempt'" },
		];
	}

	validate_tax_reason(values) {
		if (values.tax_treatment === "Exempt" && !values.tax_reason?.trim()) {
			frappe.msgprint(__("Oppgi den konkrete regelen og begrunnelsen for unntatt omsetning."));
			return false;
		}
		return true;
	}

	async private_file_name(file_url, label) {
		const file = await frappe.db.get_value("File", { file_url }, ["name", "is_private"]);
		if (!file.message?.name || !file.message.is_private) {
			frappe.msgprint(__("Last opp {0} på nytt som privat fil.", [label]));
			return "";
		}
		return file.message.name;
	}

	open_purchase_dialog(company) {
		const dialog = new frappe.ui.Dialog({
			title: __("Nytt kjøp"),
			fields: [
				{ fieldname: "supplier", label: __("Leverandør"), fieldtype: "Link", options: "Supplier", reqd: 1 },
				{ fieldname: "bill_no", label: __("Leverandørens bilagsnummer"), fieldtype: "Data", reqd: 1 },
				{ fieldname: "bill_date", label: __("Bilagsdato"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
				{ fieldname: "description", label: __("Formål"), fieldtype: "Small Text", reqd: 1 },
				{ fieldname: "gross_amount", label: __("Beløp inkl. MVA"), fieldtype: "Currency", reqd: 1 },
				{
					fieldname: "currency",
					label: __("Valuta"),
					fieldtype: "Link",
					options: "Currency",
					default: "NOK",
					reqd: 1,
					description: __("Valutakjøp støttes bare for utenlandske tjenester med omvendt MVA."),
				},
				{
					fieldname: "conversion_rate",
					label: __("Kurs til NOK"),
					fieldtype: "Float",
					precision: 6,
					depends_on: "eval:doc.currency!='NOK'",
					description: __("NOK per enhet i dokumentvalutaen."),
				},
				{
					fieldname: "exchange_rate_source",
					label: __("Kurskilde"),
					fieldtype: "Data",
					depends_on: "eval:doc.currency!='NOK'",
				},
				{
					fieldname: "exchange_rate_date",
					label: __("Kursdato"),
					fieldtype: "Date",
					depends_on: "eval:doc.currency!='NOK'",
				},
				{ fieldname: "vat_rate", label: __("MVA-sats"), fieldtype: "Select", options: "0\n12\n15\n25", default: "0", reqd: 1 },
				{ fieldname: "foreign_service", label: __("Kjøp av utenlandsk tjeneste"), fieldtype: "Check" },
				{
					fieldname: "tax_reason",
					label: __("Regel og begrunnelse uten inngående MVA"),
					fieldtype: "Small Text",
					depends_on: "eval:doc.vat_rate=='0' && !doc.foreign_service",
					description: __("Oppgi dette når foretaket er MVA-registrert og kjøpet ikke gir inngående MVA."),
				},
				{
					fieldname: "category",
					label: __("Kostnadskategori"),
					fieldtype: "Select",
					options: [
						{ label: __("Annen driftskostnad"), value: "expense" },
						{ label: __("Programvare og nettjenester"), value: "software" },
						{ label: __("Utstyr kostnadsført ved kjøp"), value: "equipment" },
						{ label: __("Bank- og betalingsgebyr"), value: "fees" },
						{ label: __("Utstyr med varig verdi"), value: "asset" },
					],
					default: "expense",
					reqd: 1,
				},
				{
					fieldname: "expected_life_months",
					label: __("Forventet brukstid i måneder"),
					fieldtype: "Int",
					depends_on: "eval:doc.category=='equipment'||doc.category=='asset'",
				},
				{
					fieldname: "business_fraction_percent",
					label: __("Næringsandel av kjøpet (%)"),
					fieldtype: "Float",
					default: 100,
					description: __("Hvor stor del av hele kjøpet som brukes i næringen."),
					reqd: 1,
				},
				{
					fieldname: "deductible_fraction_percent",
					label: __("Fradragsberettiget MVA (%)"),
					fieldtype: "Float",
					default: 100,
					description: __("Kan ikke være høyere enn næringsandelen."),
					reqd: 1,
				},
				{
					fieldname: "tax_deductible_fraction_percent",
					label: __("Skattemessig fradragsandel av næringskostnaden (%)"),
					fieldtype: "Float",
					default: 100,
					description: __("Gjelder den bokførte næringskostnaden etter privat andel. Dette er ikke MVA-andelen."),
					reqd: 1,
				},
				{
					fieldname: "tax_adjustment_reason",
					label: __("Begrunnelse for redusert skattemessig fradrag"),
					fieldtype: "Small Text",
					depends_on: "eval:doc.tax_deductible_fraction_percent<100",
				},
			],
			primary_action_label: __("Opprett kladd"),
			primary_action: (values) => {
				if (!this.validate_currency_values(values, values.bill_date, Boolean(values.foreign_service), __("Valutakjøp"))) {
					return;
				}
				const business_fraction = Number(values.business_fraction_percent) / 100;
				const deductible_fraction = Number(values.deductible_fraction_percent) / 100;
				const tax_deductible_fraction = Number(values.tax_deductible_fraction_percent) / 100;
				if (!Number.isFinite(business_fraction) || !Number.isFinite(deductible_fraction) || business_fraction < 0 || business_fraction > 1 || deductible_fraction < 0 || deductible_fraction > business_fraction) {
					frappe.msgprint(__("Oppgi andeler fra 0 til 100 prosent. MVA-andelen kan ikke være høyere enn næringsandelen."));
					return;
		}

				if (!Number.isFinite(tax_deductible_fraction) || tax_deductible_fraction < 0 || tax_deductible_fraction > 1) {
					frappe.msgprint(__("Den skattemessige fradragsandelen må være fra 0 til 100 prosent."));
					return;
				}
				if (tax_deductible_fraction < 1 && !values.tax_adjustment_reason?.trim()) {
					frappe.msgprint(__("Forklar hvorfor den skattemessige fradragsandelen er redusert."));
					return;
				}
				if (tax_deductible_fraction < 1 && (values.foreign_service || values.category === "asset")) {
					frappe.msgprint(__("Redusert skattemessig fradrag for utenlandske tjenester eller utstyr må avklares før bokføring."));
					return;
				}
				if (["equipment", "asset"].includes(values.category) && !values.expected_life_months) {
					frappe.msgprint(__("Oppgi forventet brukstid for utstyr eller eiendel."));
					return;
				}
				this.create_draft(dialog, "enk_norge.api.create_purchase", {
					...values,
					company,
					business_fraction,
					deductible_fraction,
					tax_deductible_fraction,
				});
			},
		});
		dialog.show();
	}

	validate_currency_values(values, document_date, allowed_foreign_currency, label) {
		const currency = (values.currency || "NOK").trim().toUpperCase();
		if (!/^[A-Z]{3}$/.test(currency)) {
			frappe.msgprint(__("Velg en ISO-valutakode med tre bokstaver."));
			return false;
		}
		if (currency === "NOK") {
			if (values.conversion_rate && Number(values.conversion_rate) !== 1) {
				frappe.msgprint(__("NOK-bilag skal ha kurs 1."));
				return false;
			}
			if (values.exchange_rate_source || values.exchange_rate_date) {
				frappe.msgprint(__("Fjern kurskilde og kursdato for et NOK-bilag."));
				return false;
			}
			values.currency = "NOK";
			return true;
		}
		if (!allowed_foreign_currency) {
			frappe.msgprint(__(`${label} støttes bare i den angitte utenlandsflyten. Velg riktig avgiftsbehandling før du fortsetter.`));
			return false;
		}
		const rate = Number(values.conversion_rate);
		if (!Number.isFinite(rate) || rate <= 0 || !values.exchange_rate_source?.trim() || !values.exchange_rate_date) {
			frappe.msgprint(__("Oppgi positiv kurs, kurskilde og kursdato for valutabilaget."));
			return false;
		}
		if (values.exchange_rate_date > document_date) {
			frappe.msgprint(__("Kursdato kan ikke være etter bilagsdatoen."));
			return false;
		}
		values.currency = currency;
		return true;
	}

	open_bank_import_dialog(company) {
		const dialog = new frappe.ui.Dialog({
			title: __("Importer bankutskrift"),
			fields: [
				{ fieldname: "file_url", label: __("Privat CSV-fil fra banken"), fieldtype: "Attach", reqd: 1 },
				{ fieldtype: "HTML", options: `<p class="text-muted small">${__("Filen må være UTF-8 CSV med transaction_id, date, amount, currency og description. Importen oppretter eller gjenbruker bankhendelser, men bokfører ikke automatisk.")}</p>` },
			],
			primary_action_label: __("Importer"),
			primary_action: (values) => this.open_created_draft(dialog, "enk_norge.banking.import_bank_csv", { company, file_url: values.file_url }),
		});
		dialog.show();
	}

	open_owner_transfer_dialog(company) {
		const dialog = new frappe.ui.Dialog({
			title: __("Eierinnskudd eller uttak"),
			fields: [
				{ fieldname: "direction", label: __("Type"), fieldtype: "Select", options: [{ label: __("Eierinnskudd"), value: "Deposit" }, { label: __("Eieruttak"), value: "Withdrawal" }, { label: __("Tilbakebetaling"), value: "Refund" }], default: "Deposit", reqd: 1 },
				{ fieldname: "amount", label: __("Beløp"), fieldtype: "Currency", reqd: 1 },
				{ fieldname: "posting_date", label: __("Dato"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
				{ fieldname: "description", label: __("Forklaring"), fieldtype: "Small Text", reqd: 1 },
				{ fieldname: "reference", label: __("Referanse fra banken"), fieldtype: "Data", reqd: 1 },
			],
			primary_action_label: __("Opprett utkast"),
			primary_action: (values) => this.open_created_draft(dialog, "enk_norge.banking.owner_transfer", { company, ...values }),
		});
		dialog.show();
	}

	open_settlement_dialog(company) {
		const invoices = [];
		const credit_notes = [];
		const dialog = new frappe.ui.Dialog({
			title: __("Oppgjør fra betalingsformidler"),
			fields: [
				{ fieldtype: "HTML", fieldname: "settlement_intro", options: `<p class="text-muted small">${__("Bruk denne flyten når foretaket er direkte selger. Oppgjøret er bare i NOK og lager et signert journalutkast for kontroll før bokføring.")}</p>` },
				{ fieldname: "external_settlement_id", label: __("Oppgjørs-ID fra betalingsformidleren"), fieldtype: "Data", reqd: 1 },
				{ fieldname: "posting_date", label: __("Bokføringsdato"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
				{
					fieldname: "source_file",
					label: __("Privat oppgjørsfil"),
					fieldtype: "Attach",
					options: { make_attachments_public: false },
					reqd: 1,
					description: __("Last opp kildefilen privat. Den knyttes til journalutkastet og må bevares uendret."),
				},
				{ fieldname: "merchant_of_record_confirmed", label: __("Jeg bekrefter at foretaket er direkte selger"), fieldtype: "Check", reqd: 1 },
				{ fieldtype: "Section Break", label: __("Fakturaer i oppgjøret") },
				{ fieldname: "invoice", label: __("Bokført salgsfaktura"), fieldtype: "Link", options: "Sales Invoice" },
				{ fieldname: "invoice_amount", label: __("Beløp i oppgjøret (NOK)"), fieldtype: "Currency", options: "NOK" },
				{ fieldname: "add_invoice", label: __("Legg til faktura"), fieldtype: "Button", click: () => this.add_settlement_reference(dialog, invoices, "invoice", "invoice_amount", false) },
				{ fieldname: "invoice_list", fieldtype: "HTML" },
				{ fieldtype: "Section Break", label: __("Kreditnotaer i oppgjøret") },
				{ fieldname: "credit_note", label: __("Bokført kreditnota"), fieldtype: "Link", options: "Sales Invoice" },
				{ fieldname: "credit_note_amount", label: __("Refusjon i oppgjøret (NOK)"), fieldtype: "Currency", options: "NOK" },
				{ fieldname: "add_credit_note", label: __("Legg til kreditnota"), fieldtype: "Button", click: () => this.add_settlement_reference(dialog, credit_notes, "credit_note", "credit_note_amount", true) },
				{ fieldname: "credit_note_list", fieldtype: "HTML" },
				{ fieldtype: "Section Break", label: __("Avstemming") },
				{
					fieldname: "fee",
					label: __("Bank- eller betalingsgebyr (NOK)"),
					fieldtype: "Currency",
					options: "NOK",
					default: 0,
					description: __("Bare gebyr uten MVA. Avgiftspliktige formidlertjenester føres som eget dokumentert kjøp."),
				},
				{ fieldname: "net_amount", label: __("Netto utbetaling på oppgjørsfilen (NOK)"), fieldtype: "Currency", options: "NOK", reqd: 1 },
			],
			primary_action_label: __("Lag signert journalutkast"),
			primary_action: async (values) => {
				const gross = this.settlement_total(invoices);
				const refunds = this.settlement_total(credit_notes);
				const fee = Number(values.fee || 0);
				const net = Number(values.net_amount);
				if (!invoices.length) {
					frappe.msgprint(__("Legg til minst én bokført salgsfaktura."));
					return;
				}
				if (!values.merchant_of_record_confirmed) {
					frappe.msgprint(__("Bekreft at foretaket er direkte selger før du lager oppgjøret."));
					return;
				}
				if (!Number.isFinite(fee) || fee < 0 || !Number.isFinite(net) || net <= 0 || Math.abs(gross - refunds - fee - net) > 0.004) {
					frappe.msgprint(__("Brutto salg minus refusjoner og gebyr må være lik netto utbetaling på oppgjørsfilen."));
					return;
				}
				const file = await frappe.db.get_value("File", { file_url: values.source_file }, "name");
				if (!file.message?.name) {
					frappe.msgprint(__("Oppgjørsfilen ble ikke funnet. Last den opp på nytt som privat fil."));
					return;
				}
				frappe.call({
					method: "enk_norge.settlement.create_settlement",
					args: { data: { company, ...values, source_file: file.message.name, currency: "NOK", merchant_of_record: "Direct seller", invoices, credit_notes } },
					btn: dialog?.get_primary_btn(),
					freeze: true,
					freeze_message: __("Lager signert journalutkast"),
					callback: (response) => {
						dialog.hide();
						frappe.show_alert({ message: __("Signert journalutkast er klart. Kontroller oppgjør, kildefil og kontering før du bokfører."), indicator: "blue" });
						frappe.set_route("Form", response.message.doctype, response.message.name);
					},
				});
			},
		});
		dialog.show();
		dialog.enk_invoices = invoices;
		dialog.enk_credit_notes = credit_notes;
		dialog.$wrapper.addClass("enk-settlement-dialog");
		this.render_settlement_references(dialog, invoices, credit_notes);
	}

	add_settlement_reference(dialog, rows, name_field, amount_field, credit_note) {
		const name = (dialog.get_value(name_field) || "").trim();
		const amount = Number(dialog.get_value(amount_field));
		const other_rows = credit_note ? dialog.enk_invoices : dialog.enk_credit_notes;
		const duplicate = rows.some((row) => row.name === name) || other_rows.some((row) => row.name === name);
		if (!name || !Number.isFinite(amount) || amount <= 0) {
			frappe.msgprint(__("Velg dokumentet og oppgi et positivt NOK-beløp."));
			return;
		}
		if (duplicate) {
			frappe.msgprint(__("Dokumentet er allerede lagt til i oppgjøret og kan ikke være både faktura og kreditnota."));
			return;
		}
		rows.push({ name, amount: amount.toFixed(2) });
		dialog.set_value(name_field, "");
		dialog.set_value(amount_field, "");
		this.render_settlement_references(dialog, dialog.enk_invoices, dialog.enk_credit_notes);
	}

	render_settlement_references(dialog, invoices, credit_notes) {
		const render = (rows, empty) => rows.length
			? `<ul class="enk-settlement-reference-list">${rows.map((row) => `<li><span>${frappe.utils.escape_html(row.name)}</span><strong>${frappe.utils.escape_html(format_nok(row.amount))}</strong></li>`).join("")}</ul>`
			: `<p class="text-muted small mb-0">${empty}</p>`;
		dialog.get_field("invoice_list").$wrapper.html(render(invoices, __("Ingen fakturaer lagt til ennå.")));
		dialog.get_field("credit_note_list").$wrapper.html(render(credit_notes, __("Ingen kreditnotaer lagt til.")));
	}

	settlement_total(rows) {
		return rows.reduce((total, row) => total + Number(row.amount), 0);
	}

	open_tax_pool_dialog(company) {
		const acquisitions = [];
		const disposals = [];
		const dialog = new frappe.ui.Dialog({
			title: __("Saldogruppe for driftsmidler"),
			fields: [
				{ fieldtype: "HTML", options: `<p class="text-muted small">${__("Bruk dette for dokumenterte skattesaldoer i gruppe a eller d. Kjøp med kategorien «Utstyr med varig verdi» aktiveres først som utstyr; fordel bare dokumenterte kildebilag i riktig saldogruppe.")}</p>` },
				{ fieldname: "saldo_group", label: __("Saldogruppe"), fieldtype: "Select", options: "a\nd", reqd: 1 },
				{ fieldname: "opening_balance", label: __("Inngående skattesaldo"), fieldtype: "Currency", options: "NOK", default: 0, reqd: 1, description: __("Ikke-null saldo krever privat vedlegg fra tidligere saldooppgjør.") },
				{ fieldname: "opening_source_file", label: __("Privat vedlegg for inngående saldo"), fieldtype: "Attach", options: { make_attachments_public: false } },
				{ fieldname: "acquisitions", label: __("Anskaffelser i året"), fieldtype: "Currency", options: "NOK", default: 0, reqd: 1 },
				{ fieldtype: "Section Break", label: __("Kildebilag for anskaffelser") },
				{ fieldname: "acquisition_doctype", label: __("Dokumenttype"), fieldtype: "Select", options: "Purchase Invoice\nJournal Entry" },
				{ fieldname: "acquisition_name", label: __("Bilagsnummer"), fieldtype: "Data" },
				{ fieldname: "acquisition_amount", label: __("Beløp fra bilaget"), fieldtype: "Currency", options: "NOK" },
				{ fieldname: "add_acquisition", label: __("Legg til kildebilag"), fieldtype: "Button", click: () => this.add_pool_reference(dialog, acquisitions, "acquisition") },
				{ fieldname: "acquisition_list", fieldtype: "HTML" },
				{ fieldtype: "Section Break", label: __("Avgang og kildebilag") },
				{ fieldname: "disposal_proceeds", label: __("Realisasjonsvederlag"), fieldtype: "Currency", options: "NOK", default: 0, reqd: 1 },
				{ fieldname: "disposal_proceeds_taken_to_income", label: __("Vederlag tatt direkte til inntekt"), fieldtype: "Currency", options: "NOK", default: 0, reqd: 1 },
				{ fieldname: "disposal_doctype", label: __("Dokumenttype"), fieldtype: "Select", options: "Journal Entry" },
				{ fieldname: "disposal_name", label: __("Bilagsnummer"), fieldtype: "Data" },
				{ fieldname: "disposal_amount", label: __("Beløp fra bilaget"), fieldtype: "Currency", options: "NOK" },
				{ fieldname: "add_disposal", label: __("Legg til kildebilag"), fieldtype: "Button", click: () => this.add_pool_reference(dialog, disposals, "disposal") },
				{ fieldname: "disposal_list", fieldtype: "HTML" },
			],
			primary_action_label: __("Lagre saldogruppe"),
			primary_action: async (values) => {
				const opening = Number(values.opening_balance || 0);
				if (!Number.isFinite(opening)) { frappe.msgprint(__("Inngående saldo må være et gyldig beløp.")); return; }
				let opening_source_file = "";
				if (opening !== 0) {
					opening_source_file = await this.private_file_name(values.opening_source_file, __("dokumentasjonen av inngående saldo"));
					if (!opening_source_file) return;
				}
				if (!this.validate_pool_reference_total(acquisitions, values.acquisitions, __("anskaffelser")) || !this.validate_pool_reference_total(disposals, values.disposal_proceeds, __("realisasjonsvederlag"))) return;
				const doc = { doctype: "ENK Tax Pool", company, income_year: 2026, ...values, opening_source_file, acquisition_sources_json: JSON.stringify(acquisitions), disposal_sources_json: JSON.stringify(disposals) };
				delete doc.acquisition_doctype; delete doc.acquisition_name; delete doc.acquisition_amount; delete doc.add_acquisition; delete doc.acquisition_list;
				delete doc.disposal_doctype; delete doc.disposal_name; delete doc.disposal_amount; delete doc.add_disposal; delete doc.disposal_list;
				delete doc.opening_source_file; doc.opening_source_file = opening_source_file;
				const response = await frappe.call({ method: "frappe.client.insert", args: { doc }, btn: dialog.get_primary_btn(), freeze: true, freeze_message: __("Lagrer saldogruppe") });
				dialog.hide();
				frappe.set_route("Form", "ENK Tax Pool", response.message.name);
			},
		});
		dialog.show();
		dialog.enk_acquisitions = acquisitions; dialog.enk_disposals = disposals;
		this.render_pool_references(dialog, acquisitions, disposals);
	}

	add_pool_reference(dialog, rows, prefix) {
		const doctype = dialog.get_value(`${prefix}_doctype`);
		const name = (dialog.get_value(`${prefix}_name`) || "").trim();
		const amount = Number(dialog.get_value(`${prefix}_amount`));
		if (!doctype || !name || !Number.isFinite(amount) || amount <= 0) { frappe.msgprint(__("Velg dokumenttype, bilagsnummer og positivt beløp.")); return; }
		if (rows.some((row) => row.doctype === doctype && row.name === name)) { frappe.msgprint(__("Kildebilaget er allerede lagt til.")); return; }
		rows.push({ doctype, name, amount: amount.toFixed(2) });
		for (const suffix of ["doctype", "name", "amount"]) dialog.set_value(`${prefix}_${suffix}`, "");
		this.render_pool_references(dialog, dialog.enk_acquisitions, dialog.enk_disposals);
	}

	render_pool_references(dialog, acquisitions, disposals) {
		const render = (rows, empty) => rows.length ? `<ul class="enk-settlement-reference-list">${rows.map((row) => `<li><span>${frappe.utils.escape_html(`${row.doctype} ${row.name}`)}</span><strong>${frappe.utils.escape_html(format_nok(row.amount))}</strong></li>`).join("")}</ul>` : `<p class="text-muted small mb-0">${empty}</p>`;
		dialog.get_field("acquisition_list").$wrapper.html(render(acquisitions, __("Ingen kildebilag lagt til.")));
		dialog.get_field("disposal_list").$wrapper.html(render(disposals, __("Ingen kildebilag lagt til.")));
	}

	validate_pool_reference_total(rows, total, label) {
		const expected = Number(total || 0); const sum = rows.reduce((value, row) => value + Number(row.amount), 0);
		if (!Number.isFinite(expected) || expected < 0 || Math.abs(sum - expected) > 0.004) { frappe.msgprint(__("Kildebilagene for {0} må summere til beløpet i saldogruppen.", [label])); return false; }
		return true;
	}

	open_asset_disposal_dialog(company) {
		const dialog = new frappe.ui.Dialog({
			title: __("Driftsmiddelavgang"),
			fields: [
				{ fieldtype: "HTML", options: `<p class="text-muted small">${__("Avgrenset til allerede betalt, dokumentert salg eller uttak før MVA-registrering. Dette er ikke fakturering eller utsendelse. Salg krever komplett eksternt salgsbilag; uttak krever dokumentert markedsverdi.")}</p>` },
				{ fieldname: "disposition", label: __("Type"), fieldtype: "Select", options: "Sale\nWithdrawal", default: "Sale", reqd: 1 },
				{ fieldname: "posting_date", label: __("Dato"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
				{ fieldname: "proceeds", label: __("Vederlag eller markedsverdi (NOK)"), fieldtype: "Currency", options: "NOK", reqd: 1 },
				{ fieldname: "carrying_amount", label: __("Dokumentert bokført verdi (NOK)"), fieldtype: "Currency", options: "NOK", reqd: 1 },
				{ fieldname: "direct_income", label: __("Vederlag tatt direkte til inntekt (NOK)"), fieldtype: "Currency", options: "NOK", default: 0, reqd: 1 },
				{ fieldname: "description", label: __("Beskrivelse"), fieldtype: "Small Text", reqd: 1 },
				{ fieldname: "private_source_file", label: __("Privat kildebilag"), fieldtype: "Attach", options: { make_attachments_public: false }, reqd: 1 },
			],
			primary_action_label: __("Lag journalutkast"),
			primary_action: async (values) => {
				const file = await this.private_file_name(values.private_source_file, __("kildebilaget")); if (!file) return;
				const proceeds = Number(values.proceeds), carrying = Number(values.carrying_amount), direct = Number(values.direct_income || 0);
				if (!Number.isFinite(proceeds) || proceeds <= 0 || !Number.isFinite(carrying) || carrying < 0 || !Number.isFinite(direct) || direct < 0 || direct > proceeds) { frappe.msgprint(__("Kontroller vederlag, bokført verdi og direkte inntekt.")); return; }
				this.open_created_draft(dialog, "enk_norge.year_end.create_asset_disposal_journal_entry_draft", { company, ...values, private_source_file: file });
			},
		});
		dialog.show();
	}

	open_year_report_dialog(company) {
		const money_fields = [
			["capital_return_base", __("Kapitalavkastningsgrunnlag"), __("Oppgi dokumentert grunnlag. Null er tillatt når dokumentasjonen viser null.")],
			["documented_shielding", __("Dokumentert skjermingsbeløp"), __("La stå tomt hvis du i stedet oppgir dokumentert skjermingsrente.")],
			["capital_income", __("Kapitalinntekt"), ""],
			["financial_gains", __("Finansgevinst"), ""],
			["capital_costs", __("Kapitalkostnader"), ""],
			["financial_losses", __("Finanstap"), ""],
			["private_debt_interest", __("Privat gjeldsrente"), ""],
			["qualifying_business_debt", __("Kvalifiserende foretaks­gjeld"), ""],
			["qualifying_business_debt_interest", __("Rente på kvalifiserende foretaks­gjeld"), ""],
			["special_deductions", __("Særskilt fradrag"), ""],
			["carried_forward_negative", __("Fremførbar negativ personinntekt"), ""],
		];
		const fields = [
			{ fieldtype: "HTML", fieldname: "year_intro", options: `<p class="text-muted small">${__("Bygger et kontrollgrunnlag fra hovedbok og dokumenterte opplysninger. Det er ikke en direkte innsending til Skatteetaten.")}</p>` },
			{ fieldname: "income_year", label: __("Inntektsår"), fieldtype: "Int", default: 2026, read_only: 1 },
			{ fieldtype: "Section Break", label: __("Personinntekt og skjerming") },
			...money_fields.slice(0, 2).map(([fieldname, label, description]) => ({ fieldname, label, fieldtype: "Currency", options: "NOK", default: fieldname === "capital_return_base" ? 0 : undefined, description })),
			{ fieldname: "shielding_rate", label: __("Dokumentert skjermingsrente"), fieldtype: "Float", precision: 6, description: __("Oppgi som desimaltall, for eksempel 0,015. Appen antar aldri en rente.") },
			{ fieldtype: "Section Break", label: __("Kapitalposter og korreksjoner") },
			...money_fields.slice(2).map(([fieldname, label, description]) => ({ fieldname, label, fieldtype: "Currency", options: "NOK", default: 0, description })),
			{ fieldtype: "Section Break", label: __("Kontroller") },
			{ fieldname: "person_income_reviewed", label: __("Jeg har vurdert personinntekt på grunnlag av dokumenterte opplysninger"), fieldtype: "Check", reqd: 1 },
			{ fieldname: "shielding_reviewed", label: __("Jeg har vurdert skjerming og eventuelt dokumentert beløp eller rente"), fieldtype: "Check", reqd: 1 },
			{ fieldname: "private_corrections_reviewed", label: __("Jeg har kontrollert private uttak og skattemessige korreksjoner"), fieldtype: "Check", reqd: 1 },
		];
		const dialog = new frappe.ui.Dialog({
			title: __("Bygg årsrapport 2026"),
			fields,
			primary_action_label: __("Bygg kontrollgrunnlag"),
			primary_action: async (values) => {
				const personal_income_inputs = this.year_income_inputs(values, money_fields);
				if (!personal_income_inputs) return;
				if (!values.person_income_reviewed || !values.shielding_reviewed || !values.private_corrections_reviewed) {
					frappe.msgprint(__("Bekreft kontrollpunktene etter at du har gjort de faktiske vurderingene."));
					return;
				}
				const response = await frappe.call({
					method: "enk_norge.year_end.build_year_report",
					args: {
						company,
						income_year: values.income_year,
						personal_income_inputs,
						controls: {
							person_income_reviewed: true,
							shielding_reviewed: true,
							private_corrections_reviewed: true,
						},
					},
					btn: dialog?.get_primary_btn(),
					freeze: true,
					freeze_message: __("Bygger årsrapport"),
				});
				this.render_year_report_result(dialog, response.message);
			},
		});
		dialog.show();
	}

	year_income_inputs(values, money_fields) {
		const result = {};
		for (const [fieldname, label] of money_fields) {
			const amount = Number(values[fieldname] || 0);
			if (!Number.isFinite(amount) || amount < 0) {
				frappe.msgprint(__("{0} må være null eller et positivt beløp.", [label]));
				return null;
			}
			result[fieldname] = amount.toFixed(2);
		}
		const rate = values.shielding_rate;
		if (rate !== undefined && rate !== null && rate !== "") {
			const parsed = Number(rate);
			if (!Number.isFinite(parsed) || parsed < 0 || parsed > 1) {
				frappe.msgprint(__("Skjermingsrente må være mellom 0 og 1."));
				return null;
			}
			if (Number(values.documented_shielding || 0) > 0) {
				frappe.msgprint(__("Oppgi enten dokumentert skjermingsbeløp eller skjermingsrente, ikke begge."));
				return null;
			}
			result.shielding_rate = parsed.toFixed(6);
		}
		return result;
	}

	render_year_report_result(dialog, report) {
		const safe = (value) => frappe.utils.escape_html(value === undefined || value === null ? "" : String(value));
		const amount = (value) => frappe.utils.escape_html(format_nok(value));
		const return_rows = (report.return_basis || []).map((row) => `<tr><td>${safe(row.category)}</td><td>${safe(row.code)}</td><td class="text-right">${amount(row.amount)}</td><td>${safe((row.accounts || []).join(", "))}</td></tr>`).join("") || `<tr><td colspan="4" class="text-muted">${__("Ingen hovedboksummer er tilgjengelige ennå.")}</td></tr>`;
		const bridge_labels = [
			["accounting_profit", __("Regnskapsmessig resultat")],
			["book_depreciation", __("Bokført avskrivning")],
			["tax_depreciation", __("Skattemessig avskrivning")],
			["book_disposal_result", __("Bokført gevinst eller tap ved avgang")],
			["direct_disposal_income", __("Direkte skattemessig inntekt ved avgang")],
			["negative_balance_income", __("Inntektsføring av negativ saldo")],
			["manual_tax_adjustments", __("Manuelle skattekorrigeringer")],
			["taxable_business_profit", __("Skattemessig næringsresultat")],
		];
		const bridge_rows = bridge_labels.map(([fieldname, label]) => `<tr><td>${label}</td><td class="text-right">${amount(report.tax_bridge?.[fieldname])}</td></tr>`).join("");
		const clarifications = (report.open_clarifications || []).length
			? `<ul class="enk-year-clarifications">${report.open_clarifications.map((item) => `<li>${safe(item)}</li>`).join("")}</ul>`
			: `<p class="text-muted mb-0">${__("Ingen åpne avklaringer i dette kontrollgrunnlaget.")}</p>`;
		const personal = report.personal_income
			? `<p><strong>${__("Beregnet personinntekt")}</strong><span class="enk-year-result-value">${amount(report.personal_income.person_income)}</span></p>`
			: `<p class="text-muted">${__("Personinntekt er ikke beregnet.")}</p>`;
		const pools = (report.tax_pools || []).length
			? `<details><summary>${__("Saldogrupper")}</summary><div class="enk-year-table-wrap"><table class="table table-bordered"><thead><tr><th>${__("Saldogruppe")}</th><th class="text-right">${__("Skattemessig avskrivning")}</th><th class="text-right">${__("Negativ saldo")}</th><th class="text-right">${__("Vederlag ved avgang")}</th></tr></thead><tbody>${report.tax_pools.map((pool) => `<tr><td>${safe(pool.name)}</td><td class="text-right">${amount(pool.depreciation_deduction)}</td><td class="text-right">${amount(pool.negative_balance_income)}</td><td class="text-right">${amount(pool.disposal_proceeds)}</td></tr>`).join("")}</tbody></table></div></details>`
			: "";
		dialog.$wrapper.addClass("enk-year-report-dialog");
		dialog.$body.html(`<div class="enk-year-report-result">
			<p class="text-muted">${__("Hovedbok er fordelt på rapportkoder. Skattemessige korreksjoner vises separat. Kontroller grunnlaget før eventuell manuell levering; det kan ikke sendes blindt til Skatteetaten.")}</p>
			<div class="enk-year-status"><span>${__("Status")}</span><strong>${safe(report.status)}</strong><span>${__("Revisjon")}</span><strong>${safe(report.revision)}</strong></div>
			<h4>${__("Hovedbok fordelt på rapportkoder")}</h4>
			<div class="enk-year-table-wrap"><table class="table table-bordered"><thead><tr><th>${__("Kategori")}</th><th>${__("Rapportkode")}</th><th class="text-right">${__("Beløp")}</th><th>${__("Kontoer")}</th></tr></thead><tbody>${return_rows}</tbody></table></div>
			<h4>${__("Skatteavstemming")}</h4>
			<div class="enk-year-table-wrap"><table class="table table-bordered"><tbody>${bridge_rows}</tbody></table></div>
			<h4>${__("Personinntekt og avklaringer")}</h4>${personal}${clarifications}${pools}
		</div>`);
		dialog.get_primary_btn().html(__("Åpne årsrapport")).off("click").on("click", () => {
			frappe.set_route("Form", "ENK Year Report", report.name);
			dialog.hide();
		});
	}

	open_saft_dialog(company) {
		const dialog = new frappe.ui.Dialog({
			title: __("Eksporter SAF-T"),
			fields: [
				{ fieldname: "from_date", label: __("Fra dato"), fieldtype: "Date", reqd: 1, default: "2026-01-01" },
				{ fieldname: "to_date", label: __("Til dato"), fieldtype: "Date", reqd: 1, default: "2026-12-31" },
			],
			primary_action_label: __("Last ned SAF-T"),
			primary_action: (values) => {
				const query = new URLSearchParams({ company, from_date: values.from_date, to_date: values.to_date });
				window.open(`/api/method/enk_norge.saft.export_saf_t?${query.toString()}`, "_blank", "noopener");
				dialog.hide();
			},
		});
		dialog.show();
	}

	open_created_draft(dialog, method, args) {
		frappe.call({
			method,
			args,
			btn: dialog?.get_primary_btn(),
			freeze: true,
			freeze_message: __("Oppretter utkast"),
			callback: (response) => {
				dialog?.hide();
				if (response.message?.doctype && response.message?.name) {
					frappe.set_route("Form", response.message.doctype, response.message.name);
				} else {
					this.load_dashboard({ company: args.company });
				}
			},
		});
	}

	create_draft(dialog, method, data) {
		frappe.call({
			method,
			args: { data },
			btn: dialog?.get_primary_btn(),
			freeze: true,
			freeze_message: __("Oppretter kladd"),
			callback: (response) => {
				dialog.hide();
				frappe.set_route("Form", response.message.doctype, response.message.name);
			},
		});
	}
}

function format_nok(value) {
	const number = typeof value === "number" ? value : Number(value);
	return format_currency(Number.isFinite(number) ? number : 0, "NOK");
}
