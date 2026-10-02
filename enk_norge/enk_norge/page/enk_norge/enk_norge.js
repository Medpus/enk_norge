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

frappe.pages["enk-norge"].on_page_show = function (wrapper) {
	use_enk_sidebar(wrapper);
	wrapper.enk_norge?.route();
};

function use_enk_sidebar(wrapper) {
	// Startsiden har tom rute, og da velger Frappe en vilkårlig modulmeny etter at siden vises.
	// Vi setter ENK-menyen etter Frappes eget valg, så lenge ENK-siden er den aktive siden.
	const apply = () => {
		const sidebar = frappe.app?.sidebar;
		if (frappe.container?.page !== wrapper || !sidebar || !frappe.boot.workspace_sidebar_item?.["enk norge"]) return;
		if (sidebar.sidebar_title !== "ENK Norge") sidebar.setup("ENK Norge");
		// Begge menypunktene peker på samme side, så Frappe kan ikke se hvilket som er aktivt.
		const active = frappe.get_route()[1] === "mva" ? "MVA" : "Oversikt";
		$(".body-sidebar .standard-sidebar-item").each((_, item) => {
			$(item).toggleClass("active-sidebar", $(item).text().trim() === active);
		});
	};
	if (!wrapper.enk_sidebar_bound) {
		wrapper.enk_sidebar_bound = true;
		frappe.router.on("change", () => setTimeout(apply, 0));
	}
	setTimeout(apply, 0);
}

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
				this.loaded = true;
				this.route();
			},
			error: () => this.render_load_error(),
		});
	}

	route() {
		if (!this.loaded) return;
		// Sidemenyen kan bare lenke til selve siden, så MVA-lenken sender vis=mva som parameter.
		const target = frappe.route_options?.vis || frappe.utils.get_query_params().vis;
		if (target === "mva") {
			// Erstatt historikken, ellers sender Tilbake-knappen brukeren hit igjen.
			frappe.route_options = null;
			window.history.replaceState(null, "", "/desk/enk-norge/mva");
			frappe.router.route();
			return;
		}
		const [, view, doctype, name] = frappe.get_route();
		if (!this.companies.length) {
			this.render_onboarding();
		} else if (view === "bilag" && doctype && name) {
			this.render_document(doctype, name);
		} else if (view === "mva") {
			this.render_vat(doctype);
		} else {
			this.render_dashboard();
		}
	}

	selected_company() {
		return this.companies.find((company) => company.configured) || this.companies[0];
	}

	open_document(doctype, name) {
		const [, view, current_doctype, current_name] = frappe.get_route();
		if (view === "bilag" && current_doctype === doctype && current_name === name) {
			this.render_document(doctype, name);
		} else {
			frappe.set_route("enk-norge", "bilag", doctype, name);
		}
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
		const selected = this.selected_company();
		this.list_state = this.list_state || { kind: "all", status: "", search: "" };
		this.render_dashboard_content(selected, null);
		if (selected.configured) {
			this.load_dashboard(selected);
		}
	}

	load_dashboard(company) {
		frappe.call({
			method: "enk_norge.api.dashboard",
			args: { company: company.company },
			callback: (response) => {
				this.dashboard_data = response.message || {};
				this.render_dashboard_content(company, this.dashboard_data);
			},
			error: () => this.render_dashboard_content(company, { error: true }),
		});
	}

	render_dashboard_content(selected, dashboard) {
		const company = selected.company;
		this.page.clear_actions();
		this.page.set_title(__("Oversikt"));
		this.body.html(`
			<section class="enk-dashboard" aria-labelledby="enk-dashboard-title">
				<header class="enk-dashboard-header">
					<div>
						<h2 id="enk-dashboard-title">${frappe.utils.escape_html(company)}</h2>
						<p>${this.company_status(selected, dashboard)}</p>
					</div>
					${selected.configured ? `<button class="btn btn-default btn-sm" type="button" data-action="company-profile">${__("Foretak og MVA")}</button>` : ""}
				</header>
				${selected.configured ? `
					<div class="enk-dashboard-main">
						${this.dashboard_overview(dashboard)}
						<section class="enk-standard-actions" aria-labelledby="enk-standard-title">
							<h3 id="enk-standard-title">${__("Ny registrering")}</h3>
							<div class="enk-action-row enk-primary-actions">
								<button class="btn btn-primary" type="button" data-action="new-sale">${__("Ny faktura")}</button>
								<button class="btn btn-primary" type="button" data-action="new-purchase">${__("Nytt kjøp eller utgift")}</button>
								<button class="btn btn-default" type="button" data-action="log-hours">${__("Før timer")}</button>
							</div>
							<div class="enk-action-row">
								<button class="btn btn-default btn-sm" type="button" data-action="invoice-hours">${__("Fakturer timer")}</button>
								<button class="btn btn-default btn-sm" type="button" data-action="new-customer">${__("Ny kunde")}</button>
								<button class="btn btn-default btn-sm" type="button" data-action="new-supplier">${__("Ny leverandør")}</button>
							</div>
						</section>
					</div>
					${this.document_section()}
					${this.more_section()}
				` : `<div class="enk-dashboard-main">${this.dashboard_overview(undefined)}</div>`}
			</section>
		`);
		this.bind_dashboard(company);
		if (selected.configured) {
			this.load_documents(company);
		}
	}

	company_status(selected, dashboard) {
		if (!selected.configured) return __("Foretaket trenger fortsatt norsk oppsett.");
		if (dashboard === null) return __("Henter oversikten.");
		if (!dashboard || dashboard.error) return "";
		return dashboard.vat_registered ? __("MVA-registrert") : __("Ikke MVA-registrert");
	}

	bind_dashboard(company) {
		const on = (action, handler) => this.body.find(`[data-action="${action}"]`).on("click", handler);
		on("company-profile", () => this.open_company_profile_dialog(company));
		on("new-sale", () => this.open_sale_dialog(company));
		on("new-purchase", () => this.open_purchase_dialog(company));
		on("log-hours", () => this.open_log_hours_dialog(company));
		on("invoice-hours", () => this.open_invoice_hours_dialog(company));
		on("new-customer", () => this.open_customer_dialog(() => this.load_dashboard({ company, configured: true })));
		on("new-supplier", () => this.open_supplier_dialog(() => {}));
		on("vat", () => frappe.set_route("enk-norge", "mva"));
		on("import-bank", () => this.open_bank_import_dialog(company));
		on("new-settlement", () => this.open_settlement_dialog(company));
		on("owner-transfer", () => this.open_owner_transfer_dialog(company));
		on("build-year-report", () => this.open_year_report_dialog(company));
		on("tax-pool", () => this.open_tax_pool_dialog(company));
		on("open-tax-pools", () => frappe.set_route("List", "ENK Tax Pool", "List", { company, income_year: 2026 }));
		on("depreciation-draft", () => this.open_created_draft(null, "enk_norge.year_end.create_depreciation_journal_entry_draft", { company, income_year: 2026 }));
		on("asset-disposal", () => this.open_asset_disposal_dialog(company));
		on("export-saft", () => this.open_saft_dialog(company));
		this.body.find("[data-open-doctype]").on("click", (event) => {
			event.preventDefault();
			const target = $(event.currentTarget);
			this.open_document(target.attr("data-open-doctype"), target.attr("data-open-name"));
		});
		this.body.find("[data-list-kind]").on("click", (event) => {
			this.list_state.kind = $(event.currentTarget).attr("data-list-kind");
			this.load_documents(company);
		});
		this.body.find("[data-list-status]").on("click", (event) => {
			const status = $(event.currentTarget).attr("data-list-status");
			this.list_state.status = this.list_state.status === status ? "" : status;
			this.load_documents(company);
		});
		let timer;
		this.body.find(".enk-document-search").on("input", (event) => {
			clearTimeout(timer);
			timer = setTimeout(() => {
				this.list_state.search = event.target.value;
				this.load_documents(company);
			}, 250);
		});
	}

	document_section() {
		const kinds = [["all", __("Alle")], ["sales", __("Salg")], ["purchases", __("Kjøp")], ["other", __("Betalinger og posteringer")]];
		const statuses = [["draft", __("Kladder")], ["unpaid", __("Ubetalt")]];
		const state = this.list_state;
		return `<section class="enk-documents" aria-labelledby="enk-documents-title">
			<header class="enk-documents-header">
				<h3 id="enk-documents-title">${__("Bilag")}</h3>
				<input class="form-control enk-document-search" type="search" value="${frappe.utils.escape_html(state.search)}"
					placeholder="${__("Søk på nummer, kunde eller leverandør")}" aria-label="${__("Søk i bilag")}">
			</header>
			<div class="enk-document-filters" role="toolbar" aria-label="${__("Filtrer bilag")}">
				${kinds.map(([value, label]) => `<button type="button" class="btn btn-xs ${state.kind === value ? "btn-primary" : "btn-default"}" data-list-kind="${value}" aria-pressed="${state.kind === value}">${label}</button>`).join("")}
				<span class="enk-filter-divider" aria-hidden="true"></span>
				${statuses.map(([value, label]) => `<button type="button" class="btn btn-xs ${state.status === value ? "btn-primary" : "btn-default"}" data-list-status="${value}" aria-pressed="${state.status === value}">${label}</button>`).join("")}
			</div>
			<div class="enk-document-table" aria-live="polite">
				<div class="skeleton enk-loading-line"></div>
			</div>
		</section>`;
	}

	load_documents(company) {
		const table = this.body.find(".enk-document-table");
		const state = this.list_state;
		this.body.find("[data-list-kind]").each((_, el) => {
			const active = $(el).attr("data-list-kind") === state.kind;
			$(el).toggleClass("btn-primary", active).toggleClass("btn-default", !active).attr("aria-pressed", active);
		});
		this.body.find("[data-list-status]").each((_, el) => {
			const active = $(el).attr("data-list-status") === state.status;
			$(el).toggleClass("btn-primary", active).toggleClass("btn-default", !active).attr("aria-pressed", active);
		});
		frappe.call({
			method: "enk_norge.documents.list_documents",
			args: { company, kind: state.kind, search: state.search, limit: 100 },
			callback: (response) => {
				const rows = (response.message || []).filter((row) => !state.status || row.status === state.status);
				table.html(this.document_rows(rows));
				table.find("[data-open-doctype]").on("click", (event) => {
					event.preventDefault();
					const target = $(event.currentTarget);
					this.open_document(target.attr("data-open-doctype"), target.attr("data-open-name"));
				});
			},
			error: () => table.html(`<p class="text-muted">${__("Kunne ikke hente bilagene. Last siden på nytt.")}</p>`),
		});
	}

	document_rows(rows) {
		if (!rows.length) {
			const filtered = this.list_state.search || this.list_state.status || this.list_state.kind !== "all";
			return `<div class="enk-empty">
				<p>${filtered ? __("Ingen bilag passer med filteret.") : __("Ingen bilag ennå. Start med en faktura eller et kjøp.")}</p>
			</div>`;
		}
		return `<ul class="enk-document-rows">${rows.map((row) => {
			const amount = row.status === "unpaid" ? row.outstanding_amount : row.total;
			return `<li><a href="/desk/enk-norge/bilag/${encodeURIComponent(row.doctype)}/${encodeURIComponent(row.name)}" data-open-doctype="${frappe.utils.escape_html(row.doctype)}" data-open-name="${frappe.utils.escape_html(row.name)}">
				<span class="enk-row-main">
					<span class="enk-row-party">${frappe.utils.escape_html(row.party || row.description || enk_doctype_label(row.doctype, row))}</span>
					<span class="enk-row-meta">${enk_doctype_label(row.doctype, row)} · ${frappe.utils.escape_html(row.name)} · ${row.posting_date ? frappe.datetime.str_to_user(row.posting_date) : ""}</span>
				</span>
				<span class="enk-row-side">
					<strong>${frappe.utils.escape_html(format_money(amount, row.currency))}</strong>
					${enk_status_pill(row.status)}
				</span>
			</a></li>`;
		}).join("")}</ul>`;
	}

	more_section() {
		return `<section class="enk-more" aria-labelledby="enk-more-title">
			<h3 id="enk-more-title">${__("Bank, rapporter og årsoppgjør")}</h3>
			<div class="enk-more-groups">
				<div>
					<h4>${__("Bank og oppgjør")}</h4>
					<div class="enk-action-row">
						<button class="btn btn-default btn-sm" type="button" data-action="import-bank">${__("Importer bankutskrift")}</button>
						<button class="btn btn-default btn-sm" type="button" data-action="new-settlement">${__("Utbetaling fra Stripe e.l.")}</button>
						<button class="btn btn-default btn-sm" type="button" data-action="owner-transfer">${__("Innskudd eller uttak")}</button>
					</div>
				</div>
				<div>
					<h4>${__("Rapportering")}</h4>
					<div class="enk-action-row">
						<button class="btn btn-default btn-sm" type="button" data-action="vat">${__("MVA")}</button>
						<button class="btn btn-default btn-sm" type="button" data-action="build-year-report">${__("Lag årsrapport")}</button>
						<a class="btn btn-default btn-sm" href="/desk/enk-year-report">${__("Årsrapporter")}</a>
						<button class="btn btn-default btn-sm" type="button" data-action="export-saft">${__("Eksporter SAF-T")}</button>
					</div>
				</div>
				<div>
					<h4>${__("Utstyr og avskrivning")}</h4>
					<div class="enk-action-row">
						<button class="btn btn-default btn-sm" type="button" data-action="tax-pool">${__("Opprett saldogruppe")}</button>
						<button class="btn btn-default btn-sm" type="button" data-action="open-tax-pools">${__("Saldogrupper")}</button>
						<button class="btn btn-default btn-sm" type="button" data-action="depreciation-draft">${__("Lag avskrivning")}</button>
						<button class="btn btn-default btn-sm" type="button" data-action="asset-disposal">${__("Salg eller uttak av utstyr")}</button>
					</div>
				</div>
			</div>
		</section>`;
	}

	dashboard_overview(dashboard) {
		if (dashboard === null) {
			return `<section class="enk-state enk-overview-loading" aria-live="polite">
				<h3>${__("Status")}</h3>
				<div class="skeleton enk-loading-line"></div>
				<div class="skeleton enk-loading-line short"></div>
			</section>`;
		}
		if (dashboard?.error) {
			return `<section class="enk-state" aria-live="polite">
				<h3>${__("Oversikten er ikke tilgjengelig")}</h3>
				<p>${__("Tallene kunne ikke hentes nå. Last siden på nytt.")}</p>
			</section>`;
		}
		if (!dashboard) {
			return `<section class="enk-state">
				<h3>${__("Fullfør norsk oppsett")}</h3>
				<p>${__("Dette foretaket mangler ENK-innstillinger.")}</p>
			</section>`;
		}
		const drafts = (dashboard.draft_sales?.length || 0) + (dashboard.draft_purchases?.length || 0);
		const unpaid = dashboard.unpaid_sales?.length || 0;
		const todo = [
			drafts ? `<li><button type="button" class="btn btn-link" data-list-status="draft">${drafts === 1 ? __("1 kladd venter på bokføring") : __("{0} kladder venter på bokføring", [drafts])}</button></li>` : "",
			unpaid ? `<li><button type="button" class="btn btn-link" data-list-status="unpaid">${unpaid === 1 ? __("1 faktura er ikke betalt") : __("{0} fakturaer er ikke betalt", [unpaid])}</button></li>` : "",
		].join("");
		return `<section class="enk-overview" aria-labelledby="enk-overview-title">
			<h3 id="enk-overview-title">${__("Status i år")}</h3>
			${this.vat_threshold_notice(dashboard)}
			<dl class="enk-overview-amounts">
				${this.overview_amount(__("Inntekter"), dashboard.income)}
				${this.overview_amount(__("Kostnader"), dashboard.expenses)}
				${this.overview_amount(__("Resultat"), dashboard.result)}
				${this.overview_amount(__("Bankkonto i regnskapet"), dashboard.bank_balance)}
			</dl>
			${todo ? `<ul class="enk-todo">${todo}</ul>` : `<p class="enk-todo-clear">${__("Ingen kladder eller ubetalte fakturaer.")}</p>`}
			${this.document_list(__("Følg opp ved MVA-registrering"), dashboard.vat_followup, "customer", "grand_total", "Sales Invoice")}
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
			<h4>${__("Du har passert MVA-grensen")}</h4>
			<p>${__("Omsetningen passerte {0} {1}. Meld foretaket inn i Merverdiavgiftsregisteret, og registrer datoen under «Foretak og MVA».", [date, basis])}</p>
		</section>`;
	}

	overview_amount(label, value) {
		return `<div><dt>${label}</dt><dd>${frappe.utils.escape_html(format_nok(value))}</dd></div>`;
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
				return `<li><a href="/desk/enk-norge/bilag/${encodeURIComponent(doctype)}/${encodeURIComponent(document.name)}" data-open-doctype="${doctype}" data-open-name="${name}"><span>${name}</span><span>${party}</span><strong>${amount}</strong></a></li>`;
			})
			.join("");
		return `<div class="enk-document-list"><h4>${title}</h4><ul>${rows}</ul></div>`;
	}

	vat_periods(profile) {
		// Ordinær melding gjelder tomånedsterminer etter registrering. Uregistrerte rapporterer
		// omvendt avgiftsplikt per kvartal. Serveren kontrollerer termin og regler uansett.
		const today = frappe.datetime.get_today();
		const ordinary = profile.vat_registered && profile.vat_registration_date;
		const months = ordinary ? [2, 4, 6, 8, 10, 12] : [3, 6, 9, 12];
		const names = ordinary
			? [__("januar–februar"), __("mars–april"), __("mai–juni"), __("juli–august"), __("september–oktober"), __("november–desember")]
			: [__("1. kvartal"), __("2. kvartal"), __("3. kvartal"), __("4. kvartal")];
		return months.map((month, index) => {
			const end = frappe.datetime.obj_to_str(new Date(2026, month, 0));
			const start = frappe.datetime.obj_to_str(new Date(2026, month - (ordinary ? 2 : 3), 1));
			return { end, start, label: `${names[index]} 2026`, report_type: ordinary ? "Ordinary" : "Reverse charge unregistered" };
		}).filter((period) => period.start <= today && (!ordinary || period.end >= profile.vat_registration_date));
	}

	async render_vat(period_end) {
		const company = this.selected_company().company;
		this.page.clear_actions();
		this.page.set_title(__("MVA"));
		const escape = frappe.utils.escape_html;
		const profile = (await frappe.call({ method: "enk_norge.setup.company_profile", args: { company } })).message;
		const periods = this.vat_periods(profile);
		const ordinary = periods[0]?.report_type === "Ordinary";
		const selected = periods.find((period) => period.end === period_end) || periods[periods.length - 1];
		this.body.html(`
			<section class="enk-bilag enk-vat" aria-labelledby="enk-vat-title">
				<button class="btn btn-link enk-back" type="button" data-action="back">${frappe.utils.icon("arrow-left", "sm")} ${__("Oversikt")}</button>
				<header class="enk-bilag-header"><div>
					<h2 id="enk-vat-title">${ordinary ? __("MVA-melding") : __("Omvendt avgiftsplikt for kjøp fra utlandet")}</h2>
					<p>${ordinary
						? __("Melding for hver tomånedstermin etter at foretaket ble MVA-registrert.")
						: __("Foretaket er ikke MVA-registrert. Kjøper du tjenester fra utlandet for mer enn 2 000 kr i et kvartal, skal du likevel levere melding og betale MVA av dem.")}</p>
				</div></header>
				${periods.length ? `
					<div class="enk-vat-period">
						<label for="enk-vat-period">${ordinary ? __("Termin") : __("Kvartal")}</label>
						<select id="enk-vat-period" class="form-control">${periods.map((period) => `<option value="${period.end}" ${period.end === selected.end ? "selected" : ""}>${escape(period.label)}</option>`).join("")}</select>
						<button class="btn btn-primary btn-sm" type="button" data-action="build-vat">${__("Beregn")}</button>
					</div>
					<div class="enk-vat-result" aria-live="polite"></div>
				` : `<p class="enk-guidance">${__("Ingen termin i 2026 er startet ennå.")}</p>`}
			</section>
		`);
		this.body.find('[data-action="back"]').on("click", () => frappe.set_route("enk-norge"));
		this.body.find("#enk-vat-period").on("change", (event) => frappe.set_route("enk-norge", "mva", event.target.value));
		this.body.find('[data-action="build-vat"]').on("click", () => this.build_vat(company, selected));
		if (selected) this.show_existing_vat(company, selected);
	}

	async show_existing_vat(company, period) {
		const existing = await frappe.call({
			method: "frappe.client.get_list",
			args: { doctype: "ENK VAT Return", filters: { company, period_end: period.end, report_type: period.report_type }, fields: ["name"], order_by: "revision desc", limit_page_length: 1 },
		});
		const name = existing.message?.[0]?.name;
		if (name) this.render_vat_result(company, period, name);
	}

	build_vat(company, period) {
		frappe.call({
			method: "enk_norge.vat.build_vat_return",
			args: { company, period_end: period.end, report_type: period.report_type },
			freeze: true,
			freeze_message: __("Beregner"),
			callback: (response) => this.render_vat_result(company, period, response.message.name),
		});
	}

	async render_vat_result(company, period, name) {
		const escape = frappe.utils.escape_html;
		const doc = (await frappe.db.get_doc("ENK VAT Return", name));
		const checks = JSON.parse(doc.reconciliation_json || "[]");
		const ordinary = period.report_type === "Ordinary";
		const rows = ordinary
			? [
				[__("Omsetning med 25 % MVA"), doc.sales_25_basis],
				[__("Omsetning med 15 % MVA"), doc.sales_15_basis],
				[__("Omsetning med 12 % MVA"), doc.sales_12_basis],
				[__("Utgående MVA"), doc.output_vat],
				[__("Tjenester solgt til utlandet"), doc.export_turnover],
				[__("Omsetning unntatt MVA"), doc.exempt_turnover],
				[__("Kjøp fra utlandet, grunnlag"), doc.reverse_charge_basis],
				[__("MVA av kjøp fra utlandet"), doc.reverse_charge_output_vat],
				[__("Fradrag for inngående MVA"), Number(doc.purchase_input_vat) + Number(doc.reverse_charge_input_vat)],
			]
			: [
				[__("Kjøp av tjenester fra utlandet, grunnlag"), doc.reverse_charge_basis],
				[__("MVA å betale (25 %)"), doc.reverse_charge_output_vat],
			];
		const missing_reverse = checks.some((check) => check.includes("Omvendt MVA"));
		const filed = doc.status === "Manually filed";
		const nothing = !ordinary && !Number(doc.reverse_charge_basis);
		const status = filed
			? `<span class="indicator-pill green">${__("Levert")}</span>`
			: checks.length ? `<span class="indicator-pill orange">${__("Må rettes")}</span>` : `<span class="indicator-pill blue">${__("Klar til levering")}</span>`;
		this.body.find(".enk-vat-result").html(`
			<div class="enk-vat-status">${status}<span class="text-muted small">${__("Beregnet {0}", [frappe.datetime.str_to_user(doc.prepared_at)])}</span></div>
			${nothing ? `<p class="enk-guidance">${__("Kjøpene fra utlandet i kvartalet er ikke over 2 000 kr. Du trenger ikke levere melding for dette kvartalet.")}</p>` : ""}
			<dl class="enk-totals enk-vat-totals">${rows.map(([label, value]) => `<div><dt>${label}</dt><dd>${escape(format_nok(value))}</dd></div>`).join("")}
				<div><dt>${ordinary ? __("Å betale (negativt er til gode)") : __("Å betale")}</dt><dd>${escape(format_nok(doc.net_vat_payable))}</dd></div></dl>
			${checks.length ? `<div class="enk-vat-threshold-notice"><h4>${__("Dette må rettes før levering")}</h4><ul>${checks.map((check) => `<li>${escape(check)}</li>`).join("")}</ul>
				${missing_reverse ? `<p>${__("Lag posteringen for MVA av kjøp fra utlandet, bokfør den og beregn på nytt.")}</p><button class="btn btn-primary btn-sm" type="button" data-action="reverse-draft">${__("Lag postering")}</button>` : ""}</div>` : ""}
			${!checks.length && !filed && !nothing ? `<section class="enk-attachments">
				<h3>${__("Lever meldingen")}</h3>
				<p class="enk-guidance">${__("Logg inn hos Skatteetaten og fyll inn beløpene over i MVA-meldingen. Appen sender ikke meldingen selv. Last deretter opp kvitteringen du får, så markeres meldingen som levert her.")}</p>
				<a class="btn btn-default btn-sm" href="https://www.skatteetaten.no/bedrift-og-organisasjon/avgifter/mva/" target="_blank" rel="noopener">${__("Til Skatteetaten")}</a>
				<label class="btn btn-primary btn-sm enk-upload">${__("Last opp kvittering og marker levert")}<input type="file" accept="image/*,application/pdf" class="enk-vat-receipt"></label>
				<p class="enk-upload-status text-muted small" role="status"></p>
			</section>` : ""}
			${filed ? `<p class="enk-guidance">${__("Levert {0}. Kvitteringen ligger ved rapporten.", [frappe.datetime.str_to_user(doc.manually_filed_at)])}</p>` : ""}
		`);
		this.body.find('[data-action="reverse-draft"]').on("click", () => this.open_created_draft(null, "enk_norge.vat.create_reverse_charge_draft", { company, period_end: period.end, report_type: period.report_type }));
		this.body.find(".enk-vat-receipt").on("change", async (event) => {
			const file = event.target.files?.[0];
			if (!file) return;
			const status = this.body.find(".enk-upload-status");
			status.text(__("Laster opp {0}", [file.name]));
			const form = new FormData();
			form.append("file", file, file.name);
			form.append("is_private", "1");
			form.append("doctype", "ENK VAT Return");
			form.append("docname", doc.name);
			try {
				const response = await fetch("/api/method/upload_file", { method: "POST", headers: { "X-Frappe-CSRF-Token": frappe.csrf_token, Accept: "application/json" }, body: form });
				if (!response.ok) throw new Error(response.statusText);
				const uploaded = (await response.json()).message;
				frappe.call({
					method: "enk_norge.vat.mark_vat_return_manually_filed",
					args: { company, period_end: period.end, report_type: period.report_type, private_receipt_file: uploaded.name },
					freeze: true,
					callback: () => {
						frappe.show_alert({ message: __("Meldingen er markert som levert."), indicator: "green" });
						this.render_vat_result(company, period, doc.name);
					},
				});
			} catch (error) {
				status.text(__("Opplastingen feilet. Prøv igjen."));
			}
		});
	}

	render_document(doctype, name) {
		this.page.clear_actions();
		this.page.set_title(__("Bilag"));
		this.body.html(`<section class="enk-bilag" aria-live="polite"><div class="enk-loading">
			<div class="skeleton enk-loading-title"></div><div class="skeleton enk-loading-line"></div></div></section>`);
		frappe.call({
			method: "enk_norge.documents.get_document",
			args: { doctype, name },
			callback: (response) => this.render_document_content(response.message),
			error: () => {
				this.body.html(`<section class="enk-state">
					<h2>${__("Fant ikke bilaget")}</h2>
					<p>${__("Det kan være slettet, eller du mangler tilgang.")}</p>
					<button class="btn btn-default btn-sm" type="button" data-action="back">${__("Tilbake til oversikten")}</button>
				</section>`);
				this.body.find('[data-action="back"]').on("click", () => frappe.set_route("enk-norge"));
			},
		});
	}

	render_document_content(doc) {
		const escape = frappe.utils.escape_html;
		const money = (value) => escape(format_money(value, doc.currency));
		const is_invoice = ["Sales Invoice", "Purchase Invoice"].includes(doc.doctype);
		const needs_receipt = doc.doctype === "Purchase Invoice" && doc.docstatus === 0 && !doc.attachments.some((file) => file.is_private);
		this.page.set_title(`${enk_doctype_label(doc.doctype, doc)} ${doc.name}`);
		const facts = [
			doc.party && [doc.doctype === "Purchase Invoice" ? __("Leverandør") : doc.doctype === "Sales Invoice" ? __("Kunde") : __("Motpart"), doc.party],
			doc.bill_no && [__("Leverandørens bilagsnr."), doc.bill_no],
			doc.posting_date && [__("Dato"), frappe.datetime.str_to_user(doc.posting_date)],
			doc.due_date && doc.doctype === "Sales Invoice" && [__("Forfall"), frappe.datetime.str_to_user(doc.due_date)],
			doc.return_against && [__("Korrigerer"), doc.return_against],
			doc.reference_no && [__("Bankreferanse"), doc.reference_no],
			doc.description && [__("Forklaring"), doc.description],
		].filter(Boolean);
		const lines = doc.doctype === "Journal Entry"
			? `<table class="enk-lines"><thead><tr><th>${__("Konto")}</th><th class="text-right">${__("Debet")}</th><th class="text-right">${__("Kredit")}</th></tr></thead>
				<tbody>${doc.lines.map((line) => `<tr><td>${escape(line.description)}</td><td class="text-right" data-label="${__("Debet")}">${Number(line.debit) ? money(line.debit) : ""}</td><td class="text-right" data-label="${__("Kredit")}">${Number(line.credit) ? money(line.credit) : ""}</td></tr>`).join("")}</tbody></table>`
			: doc.lines.length
				? `<table class="enk-lines"><thead><tr><th>${__("Beskrivelse")}</th>${is_invoice ? `<th class="text-right">${__("Antall")}</th><th class="text-right">${__("Pris")}</th>` : ""}<th class="text-right">${__("Beløp")}</th></tr></thead>
					<tbody>${doc.lines.map((line) => `<tr><td>${escape(line.description || "")}</td>${is_invoice ? `<td class="text-right" data-label="${__("Antall")}">${escape(format_hours(line.qty))}</td><td class="text-right" data-label="${__("Pris")}">${money(line.rate)}</td>` : ""}<td class="text-right" data-label="${__("Beløp")}">${money(line.amount)}</td></tr>`).join("")}</tbody></table>`
				: "";
		const totals = is_invoice
			? [[__("Ekskl. MVA"), doc.net_total], [__("MVA"), doc.tax_total], [__("Totalt"), doc.grand_total], ...(doc.docstatus === 1 && !doc.is_return ? [[__("Gjenstår å betale"), doc.outstanding_amount]] : [])]
			: [[__("Beløp"), doc.grand_total]];
		this.body.html(`
			<section class="enk-bilag" aria-labelledby="enk-bilag-title">
				<button class="btn btn-link enk-back" type="button" data-action="back">${frappe.utils.icon("arrow-left", "sm")} ${__("Oversikt")}</button>
				<header class="enk-bilag-header">
					<div>
						<h2 id="enk-bilag-title">${escape(doc.party || doc.description || enk_doctype_label(doc.doctype, doc))}</h2>
						<p>${enk_doctype_label(doc.doctype, doc)} · ${escape(doc.name)}</p>
					</div>
					${enk_status_pill(doc.status)}
				</header>
				${this.document_guidance(doc, needs_receipt)}
				<div class="enk-bilag-actions">${this.document_actions(doc, needs_receipt)}</div>
				<dl class="enk-facts">${facts.map(([label, value]) => `<div><dt>${label}</dt><dd>${escape(String(value))}</dd></div>`).join("")}</dl>
				${lines}
				<dl class="enk-totals">${totals.map(([label, value]) => `<div><dt>${label}</dt><dd>${money(value)}</dd></div>`).join("")}</dl>
				<section class="enk-attachments" aria-labelledby="enk-attachments-title">
					<h3 id="enk-attachments-title">${__("Vedlegg")}</h3>
					${doc.attachments.length
						? `<ul>${doc.attachments.map((file) => `<li><a href="${encodeURI(file.file_url)}" target="_blank" rel="noopener">${escape(file.file_name || file.file_url)}</a>${file.is_private ? "" : ` <span class="text-muted small">${__("(offentlig fil)")}</span>`}</li>`).join("")}</ul>`
						: `<p class="text-muted">${doc.doctype === "Purchase Invoice" ? __("Legg ved kvitteringen eller fakturaen fra leverandøren.") : __("Ingen vedlegg.")}</p>`}
					${needs_receipt ? "" : `<label class="btn btn-default btn-sm enk-upload">
						${doc.doctype === "Purchase Invoice" ? __("Legg ved flere filer") : __("Legg ved fil")}
						<input type="file" accept="image/*,application/pdf" class="enk-upload-input">
					</label>`}
					<p class="enk-upload-status text-muted small" role="status"></p>
				</section>
				<footer class="enk-bilag-footer">
					${doc.can_delete ? `<button class="btn btn-default btn-sm text-danger" type="button" data-action="delete">${__("Slett kladden")}</button>` : ""}
					<a class="enk-erpnext-link" href="/desk/${frappe.router.slug(doc.doctype)}/${encodeURIComponent(doc.name)}">${__("Åpne i ERPNext")}</a>
				</footer>
			</section>
		`);
		this.bind_document(doc);
	}

	document_guidance(doc, needs_receipt) {
		let text = "";
		if (doc.docstatus === 0) {
			text = needs_receipt
				? __("Legg ved bilde eller PDF av kvitteringen. Deretter kan du bokføre.")
				: __("Dette er en kladd. Kontroller opplysningene og bokfør når alt stemmer.");
			if (doc.doctype === "Sales Invoice") {
				text += " " + __("Kladden er ikke sendt til kunden. Last ned PDF-en og send den selv etter bokføring.");
			}
		} else if (doc.status === "unpaid") {
			text = doc.doctype === "Sales Invoice"
				? __("Fakturaen er bokført. Registrer betalingen når pengene kommer inn.")
				: __("Kjøpet er bokført. Registrer hvordan det ble betalt.");
		}
		return text ? `<p class="enk-guidance">${text}</p>` : "";
	}

	document_actions(doc, needs_receipt) {
		const buttons = [];
		const add = (action, label, primary = false, disabled = false) => buttons.push(
			`<button class="btn ${primary ? "btn-primary" : "btn-default"} btn-sm" type="button" data-action="${action}" ${disabled ? "disabled" : ""}>${label}</button>`
		);
		if (doc.edit) {
			buttons.push(`<button class="btn btn-default btn-sm" type="button" data-action="edit">${__("Rediger kladd")}</button>`);
		}
		if (needs_receipt) {
			buttons.push(`<label class="btn btn-primary btn-sm enk-upload">${__("Legg ved kvittering")}
				<input type="file" accept="image/*,application/pdf" class="enk-upload-input" aria-label="${__("Velg bilde eller PDF av kvitteringen")}"></label>`);
		} else if (doc.docstatus === 0 && doc.can_submit) {
			add("submit", __("Bokfør"), true);
		}
		if (doc.doctype === "Sales Invoice") {
			add("pdf", doc.docstatus === 0 ? __("Forhåndsvis PDF") : __("Last ned PDF"));
		}
		if (doc.docstatus === 1 && doc.status === "unpaid") {
			add("bank-payment", doc.doctype === "Sales Invoice" ? __("Registrer innbetaling") : __("Betalt fra bankkontoen"), true);
			if (doc.doctype === "Purchase Invoice" && (doc.currency || "NOK") === "NOK") {
				add("private-payment", __("Betalt med egne penger"));
			}
		}
		if (doc.docstatus === 1 && Number(doc.tax_pool_remaining) > 0) {
			add("tax-pool", __("Legg i saldogruppe"), doc.status !== "unpaid");
		}
		if (doc.docstatus === 1 && ["Sales Invoice", "Purchase Invoice"].includes(doc.doctype) && !doc.is_return) {
			if (doc.deferred && doc.doctype === "Sales Invoice") {
				add("next-period", __("Lag faktura for neste periode"));
				add("recognize", __("Inntektsfør opptjent del"));
			}
			add("credit-note", __("Lag kreditnota"));
		}
		return buttons.join("");
	}

	bind_document(doc) {
		const actions = window.enk_norge_actions;
		const reload = () => this.render_document(doc.doctype, doc.name);
		const open_created = (created) => {
			if (created?.doctype && created?.name) {
				frappe.show_alert({ message: __("Kladden er laget. Kontroller og bokfør den."), indicator: "blue" });
				this.open_document(created.doctype, created.name);
			} else {
				reload();
			}
		};
		const on = (action, handler) => this.body.find(`[data-action="${action}"]`).on("click", handler);
		on("back", () => frappe.set_route("enk-norge"));
		on("submit", () => frappe.confirm(
			__("Når bilaget er bokført, kan det ikke endres eller slettes. Feil rettes med kreditnota. Vil du bokføre nå?"),
			() => frappe.call({
				method: "enk_norge.documents.submit_document",
				args: { doctype: doc.doctype, name: doc.name },
				freeze: true,
				freeze_message: __("Bokfører"),
				callback: () => {
					frappe.show_alert({ message: __("Bokført."), indicator: "green" });
					reload();
				},
			}),
		));
		on("delete", () => frappe.confirm(__("Vil du slette kladden? Den er ikke bokført, så ingenting i regnskapet endres."), () => frappe.call({
			method: "enk_norge.documents.delete_draft",
			args: { doctype: doc.doctype, name: doc.name },
			freeze: true,
			callback: () => {
				frappe.show_alert({ message: __("Kladden er slettet."), indicator: "green" });
				frappe.set_route("enk-norge");
			},
		})));
		on("pdf", () => {
			const params = new URLSearchParams({ doctype: doc.doctype, name: doc.name, format: "ENK Faktura", no_letterhead: "1" });
			window.open(`/api/method/frappe.utils.print_format.download_pdf?${params}`, "_blank", "noopener");
		});
		on("bank-payment", () => actions.bank_payment(doc, open_created));
		on("private-payment", () => actions.pay_privately(doc, open_created));
		on("credit-note", () => actions.credit_note(doc, open_created));
		on("recognize", () => actions.recognize_revenue(doc, open_created));
		on("tax-pool", () => this.open_add_to_tax_pool_dialog(doc, reload));
		on("edit", async () => {
			// Skjemaet trenger MVA-statusen. Den er ikke hentet når siden åpnes rett på et bilag.
			if (!this.dashboard_data) {
				this.dashboard_data = (await frappe.call({ method: "enk_norge.api.dashboard", args: { company: doc.company } })).message || {};
			}
			if (doc.doctype === "Sales Invoice") this.open_sale_dialog(doc.company, doc.edit, doc.name);
			else this.open_purchase_dialog(doc.company, doc.edit, doc.name);
		});
		on("next-period", () => frappe.call({
			method: "enk_norge.documents.create_next_period",
			args: { name: doc.name },
			freeze: true,
			callback: (response) => open_created(response.message),
		}));
		this.body.find(".enk-upload-input").on("change", (event) => this.upload_attachment(doc, event.target, reload));
	}

	open_add_to_tax_pool_dialog(doc, done) {
		const dialog = new frappe.ui.Dialog({
			title: __("Legg i saldogruppe"),
			fields: [
				{ fieldtype: "HTML", options: `<p class="text-muted small">${__("Utstyret er aktivert og skal avskrives over flere år. Velg gruppen det hører til. {0} legges i gruppen.", [frappe.utils.escape_html(format_nok(doc.tax_pool_remaining))])}</p>` },
				{
					fieldname: "saldo_group",
					label: __("Saldogruppe"),
					fieldtype: "Select",
					options: [
						{ label: __("a: kontormaskiner, PC, Mac og telefon (30 % i året)"), value: "a" },
						{ label: __("d: maskiner, inventar og verktøy (20 % i året)"), value: "d" },
					],
					default: "a",
					reqd: 1,
				},
			],
			primary_action_label: __("Legg i gruppen"),
			primary_action: (values) => frappe.call({
				method: "enk_norge.documents.add_to_tax_pool",
				args: { name: doc.name, saldo_group: values.saldo_group },
				btn: dialog.get_primary_btn(),
				callback: (response) => {
					dialog.hide();
					frappe.msgprint({
						title: __("Lagt i saldogruppe {0}", [response.message.saldo_group]),
						message: __("Skattemessig avskrivning i år blir {0}. Saldoen som avskrives videre neste år er {1}.", [
							frappe.utils.escape_html(format_nok(response.message.depreciation_deduction)),
							frappe.utils.escape_html(format_nok(response.message.closing_balance)),
						]),
						indicator: "green",
					});
					done();
				},
			}),
		});
		dialog.show();
	}

	async upload_attachment(doc, input, done) {
		const file = input.files?.[0];
		if (!file) return;
		const status = this.body.find(".enk-upload-status");
		if (file.size > 10 * 1024 * 1024) {
			status.text(__("Filen er større enn 10 MB. Ta et nytt bilde eller lagre som mindre PDF."));
			return;
		}
		status.text(__("Laster opp {0}", [file.name]));
		const form = new FormData();
		form.append("file", file, file.name);
		form.append("is_private", "1");
		form.append("doctype", doc.doctype);
		form.append("docname", doc.name);
		form.append("folder", "Home/Attachments");
		try {
			const response = await fetch("/api/method/upload_file", {
				method: "POST",
				headers: { "X-Frappe-CSRF-Token": frappe.csrf_token, Accept: "application/json" },
				body: form,
			});
			if (!response.ok) throw new Error(response.statusText);
			frappe.show_alert({ message: __("Vedlegget er lagret."), indicator: "green" });
			done();
		} catch (error) {
			status.text(__("Opplastingen feilet. Prøv igjen, eller velg en annen fil."));
		}
	}

	async open_company_profile_dialog(company) {
		const response = await frappe.call({ method: "enk_norge.setup.company_profile", args: { company } });
		const profile = response.message;
		const escape = frappe.utils.escape_html;
		const locked = profile.vat_registered && profile.has_postings;
		const facts = [
			[__("Organisasjonsnummer"), profile.organization_number],
			[__("Adresse"), `${profile.address_line}, ${profile.postal_code} ${profile.city}`],
			[__("Telefon"), profile.phone],
			[__("Bank"), `${profile.bank_name}, ${profile.bank_account}`],
			[__("Regnskapet starter"), frappe.datetime.str_to_user(profile.start_date)],
		];
		const dialog = new frappe.ui.Dialog({
			title: __("Foretak og MVA"),
			fields: [
				{ fieldtype: "HTML", options: `<dl class="enk-facts">${facts.map(([label, value]) => `<div><dt>${label}</dt><dd>${escape(value || "")}</dd></div>`).join("")}</dl>` },
				{ fieldtype: "Section Break", label: __("MVA-registrering") },
				{
					fieldtype: "HTML",
					options: `<p class="text-muted small">${locked
						? __("Foretaket er registrert fra {0}, og det er bokført bilag. Registreringen kan ikke endres her.", [frappe.datetime.str_to_user(profile.vat_registration_date)])
						: __("Når Skatteetaten har registrert foretaket i Merverdiavgiftsregisteret, oppgir du datoen registreringen gjelder fra. Fakturaer fra og med den datoen får MVA.")}</p>`,
				},
				{ fieldname: "vat_registered", label: __("Foretaket er MVA-registrert"), fieldtype: "Check", default: profile.vat_registered ? 1 : 0, read_only: locked ? 1 : 0 },
				{ fieldname: "vat_registration_date", label: __("Registrert fra"), fieldtype: "Date", default: profile.vat_registration_date, depends_on: "eval:doc.vat_registered", read_only: locked ? 1 : 0 },
			],
			primary_action_label: locked ? __("Lukk") : __("Lagre"),
			primary_action: (values) => {
				if (locked) {
					dialog.hide();
					return;
				}
				if (values.vat_registered && !values.vat_registration_date) {
					frappe.msgprint(__("Oppgi datoen registreringen gjelder fra."));
					return;
				}
				frappe.call({
					method: "enk_norge.setup.update_vat_registration",
					args: { company, vat_registered: values.vat_registered ? 1 : 0, vat_registration_date: values.vat_registration_date || null },
					btn: dialog.get_primary_btn(),
					callback: () => {
						dialog.hide();
						frappe.show_alert({ message: __("MVA-status er lagret."), indicator: "green" });
						this.render_dashboard();
					},
				});
			},
		});
		dialog.show();
	}

	open_sale_dialog(company, edit = null, draft = null) {
		const dialog = new frappe.ui.Dialog({
			title: draft ? __("Rediger faktura {0}", [draft]) : __("Ny faktura"),
			fields: this.with_defaults(edit, [
				...this.customer_fields(() => dialog),
				{ fieldname: "lines", fieldtype: "HTML" },
				{ fieldtype: "Section Break" },
				{ fieldname: "delivery_date", label: __("Leveringsdato"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
				{ fieldtype: "Column Break" },
				{ fieldname: "due_date", label: __("Forfallsdato"), fieldtype: "Date", reqd: 1, default: frappe.datetime.add_days(frappe.datetime.get_today(), 14) },
				{ fieldtype: "Section Break", label: __("Utenlandsk kunde, unntak eller abonnement"), collapsible: 1 },
				...this.sale_tax_fields(),
				{
					fieldname: "currency",
					label: __("Valuta"),
					fieldtype: "Link",
					options: "Currency",
					default: "NOK",
					description: __("Annen valuta enn NOK gjelder bare tjenester til utenlandske bedrifter."),
				},
				{ fieldname: "conversion_rate", label: __("Kurs til NOK"), fieldtype: "Float", precision: 6, depends_on: "eval:doc.currency!='NOK'", description: __("NOK per enhet i valutaen.") },
				{ fieldname: "exchange_rate_source", label: __("Kurskilde"), fieldtype: "Data", depends_on: "eval:doc.currency!='NOK'", description: __("For eksempel Norges Bank eller bankens kurs.") },
				{ fieldname: "exchange_rate_date", label: __("Kursdato"), fieldtype: "Date", depends_on: "eval:doc.currency!='NOK'" },
				{ fieldname: "defer_revenue", label: __("Abonnement eller forskudd for en periode"), fieldtype: "Check", change: () => this.toggle_subscription_fields(dialog), description: __("Inntekten fordeles over perioden. Etter bokføring kan du lage neste periode med ett klikk.") },
				{ fieldname: "service_start_date", label: __("Tjenestestart"), fieldtype: "Date", depends_on: "eval:doc.defer_revenue" },
				{ fieldname: "service_end_date", label: __("Tjenesteslutt"), fieldtype: "Date", depends_on: "eval:doc.defer_revenue" },
				{
					fieldname: "subscription_source_file",
					label: __("Avtale eller ordrebekreftelse"),
					fieldtype: "Attach",
					options: { make_attachments_public: false },
					depends_on: "eval:doc.defer_revenue",
					description: __("Dokumenterer perioden. Fakturadatoen må være før eller på tjenestestart."),
				},
			]),
			primary_action_label: draft ? __("Lagre endringer") : __("Lag kladd"),
			primary_action: async (values) => {
				if (!values.customer_address) {
					frappe.msgprint(__("Kunden mangler fakturaadresse. Opprett kunden med «Ny kunde», eller legg til adressen på kunden."));
					return;
				}
				const items = lines.values();
				if (!items) return;
				if (!this.validate_currency_values(values, values.delivery_date, values.tax_treatment === "Export services", __("Valutasalg"))) {
					return;
				}
				if (!this.validate_tax_reason(values)) return;
				if (values.defer_revenue) {
					if (!values.service_start_date || !values.service_end_date || !values.subscription_source_file) {
						frappe.msgprint(__("Abonnement som inntektsføres over perioden krever tjenestestart, tjenesteslutt og avtaledokument."));
						return;
					}
					if (values.delivery_date > values.service_start_date || values.service_end_date < values.service_start_date) {
						frappe.msgprint(__("Fakturaen må være før eller på tjenestestart, og tjenesteslutt kan ikke være før start."));
						return;
					}
					const file = await this.private_file_name(values.subscription_source_file, __("avtaledokumentet"));
					if (!file) return;
					values.subscription_source_file = file;
				}
				delete values.defer_revenue;
				delete values.address_display;
				delete values.lines;
				this.create_draft(dialog, "enk_norge.api.create_sale", { ...values, items, company, ...(draft ? { draft } : {}) });
			},
		});
		dialog.show();
		this.use_native_dates(dialog);
		const lines = new EnkInvoiceLines(dialog.get_field("lines").$wrapper, () => this.dashboard_data?.vat_registered);
		if (edit) {
			lines.fill(edit.items);
			this.fill_billing_address(dialog).then(() => dialog.set_value("customer_address", edit.customer_address));
		}
		this.toggle_subscription_fields(dialog);
	}

	with_defaults(edit, fields) {
		// Frappes datovelger kan låse hele siden i en løkke mellom velgeren og feltet. Disse
		// skjemaene bruker derfor nettleserens egen datovelger, og en kladds verdier gis som
		// startverdier i stedet for å settes etter at skjemaet er åpnet.
		return fields.map((field) => {
			const value = edit?.[field.fieldname];
			const next = field.fieldname && value !== null && value !== undefined ? { ...field, default: value } : { ...field };
			if (next.fieldtype === "Date") {
				next.fieldtype = "Data";
				next.enk_native_date = 1;
			}
			return next;
		});
	}

	use_native_dates(dialog) {
		for (const field of dialog.fields_list) {
			if (!field.df.enk_native_date || !field.$input) continue;
			const value = field.get_value();
			field.$input.attr("type", "date");
			field.$input.val(value || "");
		}
	}

	customer_fields(get_dialog) {
		return [
			{
				fieldname: "new_customer",
				label: __("Ny kunde"),
				fieldtype: "Button",
				click: () => this.open_customer_dialog((created) => {
					const dialog = get_dialog();
					dialog.set_value("customer", created.customer);
				}),
			},
			{
				fieldname: "customer",
				label: __("Kunde"),
				fieldtype: "Link",
				options: "Customer",
				only_select: 1,
				reqd: 1,
				change: () => this.fill_billing_address(get_dialog()),
			},
			{ fieldname: "customer_address", fieldtype: "Data", hidden: 1 },
			{ fieldname: "address_display", fieldtype: "HTML" },
		];
	}

	async fill_billing_address(dialog) {
		const customer = dialog.get_value("customer");
		const display = dialog.get_field("address_display");
		if (!display) return;
		dialog.set_value("customer_address", "");
		display.$wrapper.html("");
		if (!customer) return;
		const response = await frappe.call({ method: "enk_norge.parties.billing_address", args: { customer } });
		const address = response.message;
		if (dialog.get_value("customer") !== customer) return;
		if (!address) {
			display.$wrapper.html(`<p class="text-danger small">${__("Kunden mangler fakturaadresse.")}</p>`);
			return;
		}
		dialog.set_value("customer_address", address.name);
		const lines = [address.address_line1, [address.pincode, address.city].filter(Boolean).join(" "), address.country !== "Norway" ? address.country : ""].filter(Boolean);
		display.$wrapper.html(`<p class="text-muted small enk-address">${lines.map(frappe.utils.escape_html).join(", ")}</p>`);
	}

	open_customer_dialog(on_created) {
		const dialog = new frappe.ui.Dialog({
			title: __("Ny kunde"),
			fields: [
				{ fieldname: "customer_name", label: __("Navn"), fieldtype: "Data", reqd: 1 },
				{ fieldname: "customer_type", label: __("Type"), fieldtype: "Select", options: [{ label: __("Bedrift"), value: "Company" }, { label: __("Privatperson"), value: "Individual" }], default: "Company", reqd: 1 },
				{ fieldname: "organization_number", label: __("Organisasjonsnummer"), fieldtype: "Data", depends_on: "eval:doc.customer_type=='Company'" },
				{ fieldname: "email", label: __("E-post for faktura"), fieldtype: "Data", options: "Email" },
				{ fieldtype: "Section Break", label: __("Fakturaadresse") },
				{ fieldname: "address_line", label: __("Adresse"), fieldtype: "Data", reqd: 1 },
				{ fieldname: "postal_code", label: __("Postnummer"), fieldtype: "Data" },
				{ fieldname: "city", label: __("Poststed"), fieldtype: "Data", reqd: 1 },
				{ fieldname: "country", label: __("Land"), fieldtype: "Link", options: "Country", default: "Norway", reqd: 1 },
			],
			primary_action_label: __("Opprett kunde"),
			primary_action: (values) => frappe.call({
				method: "enk_norge.parties.create_customer",
				args: { data: values },
				btn: dialog.get_primary_btn(),
				callback: (response) => {
					dialog.hide();
					frappe.show_alert({ message: __("{0} er opprettet.", [response.message.customer_name]), indicator: "green" });
					on_created?.(response.message);
				},
			}),
		});
		dialog.show();
	}

	supplier_fields(get_dialog) {
		return [
			{
				fieldname: "new_supplier",
				label: __("Ny leverandør"),
				fieldtype: "Button",
				click: () => this.open_supplier_dialog((created) => get_dialog().set_value("supplier", created.supplier)),
			},
			{
				fieldname: "supplier",
				label: __("Leverandør"),
				fieldtype: "Link",
				options: "Supplier",
				only_select: 1,
				reqd: 1,
				change: () => this.fill_supplier_country(get_dialog()),
			},
			{ fieldname: "foreign_service", label: __("Tjeneste fra utlandet"), fieldtype: "Check", hidden: 1 },
			{ fieldname: "supplier_display", fieldtype: "HTML" },
		];
	}

	async fill_supplier_country(dialog) {
		const supplier = dialog.get_value("supplier");
		const display = dialog.get_field("supplier_display");
		display.$wrapper.html("");
		if (!supplier) return;
		const response = await frappe.db.get_value("Supplier", supplier, "country");
		if (dialog.get_value("supplier") !== supplier) return;
		const country = response.message?.country;
		const foreign = Boolean(country && country !== "Norway");
		dialog.set_value("foreign_service", foreign ? 1 : 0);
		if (foreign) {
			display.$wrapper.html(`<p class="text-muted small">${__("Leverandøren holder til i {0}. Kjøpet føres som tjeneste fra utlandet, og beløpet oppgis uten norsk MVA.", [frappe.utils.escape_html(__(country))])}</p>`);
		}
	}

	open_supplier_dialog(on_created) {
		const dialog = new frappe.ui.Dialog({
			title: __("Ny leverandør"),
			fields: [
				{ fieldname: "supplier_name", label: __("Navn"), fieldtype: "Data", reqd: 1, description: __("For eksempel OpenAI, Apple eller Telenor.") },
				{ fieldname: "country", label: __("Land"), fieldtype: "Link", options: "Country", default: "Norway", reqd: 1, description: __("Landet leverandøren fakturerer fra. Avgjør om MVA skal beregnes som kjøp fra utlandet.") },
				{ fieldname: "organization_number", label: __("Organisasjonsnummer"), fieldtype: "Data", depends_on: "eval:doc.country=='Norway'" },
			],
			primary_action_label: __("Opprett leverandør"),
			primary_action: (values) => frappe.call({
				method: "enk_norge.parties.create_supplier",
				args: { data: { ...values, supplier_type: "Company" } },
				btn: dialog.get_primary_btn(),
				callback: (response) => {
					dialog.hide();
					frappe.show_alert({ message: __("{0} er opprettet.", [response.message.supplier_name]), indicator: "green" });
					on_created?.(response.message);
				},
			}),
		});
		dialog.show();
	}

	toggle_subscription_fields(dialog) {
		const enabled = Boolean(dialog.get_value("defer_revenue"));
		for (const fieldname of ["service_start_date", "service_end_date", "subscription_source_file"]) {
			dialog.get_field(fieldname).toggle(enabled);
		}
	}

	open_log_hours_dialog(company) {
		const dialog = new frappe.ui.Dialog({
			title: __("Før timer"),
			fields: [
				...this.customer_fields(() => dialog).filter((field) => !["customer_address", "address_display"].includes(field.fieldname)),
				{ fieldname: "date", label: __("Dato"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
				{ fieldtype: "Section Break" },
				{ fieldname: "hours", label: __("Timer"), fieldtype: "Float", precision: 2, reqd: 1, description: __("For eksempel 1,5 for halvannen time.") },
				{ fieldtype: "Column Break" },
				{ fieldname: "rate", label: __("Timepris"), fieldtype: "Currency", options: "NOK", reqd: 1, description: __("Uten MVA.") },
				{ fieldtype: "Section Break" },
				{ fieldname: "description", label: __("Hva jobbet du med?"), fieldtype: "Small Text", reqd: 1 },
			],
			primary_action_label: __("Lagre timer"),
			primary_action: (values) => frappe.call({
				method: "enk_norge.hours.log_hours",
				args: { data: { ...values, company } },
				btn: dialog.get_primary_btn(),
				callback: (response) => {
					const summary = response.message;
					frappe.show_alert({
						message: __("Lagret. {0} timer venter på fakturering hos {1}.", [format_hours(summary.hours), frappe.utils.escape_html(summary.customer_name)]),
						indicator: "green",
					});
					dialog.set_value("hours", "");
					dialog.set_value("description", "");
				},
			}),
			secondary_action_label: __("Lukk"),
			secondary_action: () => dialog.hide(),
		});
		dialog.show();
	}

	async open_invoice_hours_dialog(company) {
		const response = await frappe.call({ method: "enk_norge.hours.open_hours", args: { company } });
		const groups = response.message || [];
		if (!groups.length) {
			frappe.msgprint({
				title: __("Ingen timer å fakturere"),
				message: __("Før timer først. Timene samles per kunde til du fakturerer dem."),
			});
			return;
		}
		const escape = frappe.utils.escape_html;
		const options = groups.map((group) => ({ label: `${group.customer_name}: ${format_hours(group.hours)} t, ${format_nok(group.amount)}`, value: group.timesheet }));
		const render_logs = (dialog) => {
			const group = groups.find((item) => item.timesheet === dialog.get_value("timesheet"));
			if (!group) return;
			dialog.get_field("logs").$wrapper.html(`<table class="enk-lines"><thead><tr><th>${__("Dato")}</th><th>${__("Arbeid")}</th><th class="text-right">${__("Timer")}</th><th class="text-right">${__("Beløp")}</th><th></th></tr></thead><tbody>
				${group.logs.map((log) => `<tr><td>${frappe.datetime.str_to_user(log.date)}</td><td>${escape(log.description || "")}</td><td class="text-right">${format_hours(log.hours)}</td><td class="text-right">${escape(format_nok(log.amount))}</td>
					<td class="text-right">${group.docstatus === 0 ? `<button type="button" class="btn btn-xs btn-default" data-remove-row="${escape(log.row)}" aria-label="${__("Fjern")}">${__("Fjern")}</button>` : ""}</td></tr>`).join("")}
			</tbody></table>`);
			dialog.get_field("logs").$wrapper.find("[data-remove-row]").on("click", (event) => {
				frappe.call({
					method: "enk_norge.hours.remove_hours",
					args: { timesheet: group.timesheet, row: $(event.currentTarget).attr("data-remove-row") },
					callback: () => {
						dialog.hide();
						this.open_invoice_hours_dialog(company);
					},
				});
			});
		};
		const dialog = new frappe.ui.Dialog({
			title: __("Fakturer timer"),
			fields: [
				{ fieldname: "timesheet", label: __("Kunde"), fieldtype: "Select", options, default: options[0].value, reqd: 1, change: () => render_logs(dialog) },
				{ fieldname: "logs", fieldtype: "HTML" },
				{ fieldname: "delivery_description", label: __("Tekst på fakturaen"), fieldtype: "Small Text", reqd: 1, default: __("Konsulenttimer") },
				{ fieldtype: "Section Break" },
				{ fieldname: "posting_date", label: __("Fakturadato"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
				{ fieldtype: "Column Break" },
				{ fieldname: "due_date", label: __("Forfallsdato"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), 14), reqd: 1 },
				{ fieldtype: "Section Break", label: __("Utenlandsk kunde eller unntak"), collapsible: 1 },
				...this.sale_tax_fields(),
			],
			primary_action_label: __("Lag fakturakladd"),
			primary_action: (values) => {
				if (!this.validate_tax_reason(values)) return;
				this.open_created_draft(dialog, "enk_norge.hours.invoice_hours", { data: { ...values, company } });
			},
		});
		dialog.show();
		render_logs(dialog);
	}

	sale_tax_fields() {
		return [
			{
				fieldname: "tax_treatment",
				label: __("Avgiftsbehandling"),
				fieldtype: "Select",
				options: [
					{ label: __("Vanlig (velges ut fra MVA-status)"), value: "" },
					{ label: __("25 % MVA"), value: "Domestic 25" },
					{ label: __("15 % MVA (næringsmidler)"), value: "Domestic 15" },
					{ label: __("12 % MVA (persontransport, kultur m.m.)"), value: "Domestic 12" },
					{ label: __("Ikke MVA-registrert"), value: "Not registered" },
					{ label: __("Tjeneste til utenlandsk bedrift"), value: "Export services" },
					{ label: __("Unntatt fra MVA"), value: "Exempt" },
				],
				description: __("La stå på «Vanlig» med mindre kunden er i utlandet eller leveransen er unntatt."),
			},
			{ fieldname: "tax_reason", label: __("Regel og begrunnelse for unntaket"), fieldtype: "Small Text", depends_on: "eval:doc.tax_treatment=='Exempt'" },
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

	open_purchase_dialog(company, edit = null, draft = null) {
		const registered = Boolean(this.dashboard_data?.vat_registered);
		const dialog = new frappe.ui.Dialog({
			title: draft ? __("Rediger kjøp") : __("Nytt kjøp eller utgift"),
			fields: this.with_defaults(edit, [
				...this.supplier_fields(() => dialog),
				{ fieldname: "description", label: __("Hva er kjøpt, og hva skal det brukes til?"), fieldtype: "Small Text", reqd: 1, description: __("For eksempel «ChatGPT-abonnement til kundearbeid».") },
				{
					fieldname: "category",
					label: __("Type kjøp"),
					fieldtype: "Select",
					options: [
						{ label: __("Programvare og abonnementer"), value: "software" },
						{ label: __("Utstyr, for eksempel PC, Mac eller telefon"), value: "equipment" },
						{ label: __("Annen driftskostnad"), value: "expense" },
						{ label: __("Bank- og betalingsgebyr"), value: "fees" },
					],
					default: "software",
					reqd: 1,
				},
				{
					fieldname: "expected_life_months",
					label: __("Hvor mange måneder regner du med å bruke det?"),
					fieldtype: "Int",
					default: 36,
					depends_on: "eval:doc.category=='equipment'",
					description: __("Utstyr til 30 000 kr eller mer som varer minst tre år, aktiveres og avskrives automatisk."),
				},
				{ fieldtype: "Section Break" },
				{ fieldname: "gross_amount", label: __("Totalbeløp på kvitteringen"), fieldtype: "Currency", reqd: 1, description: __("Det du faktisk betalte, med eventuell MVA.") },
				{ fieldtype: "Column Break" },
				{ fieldname: "bill_date", label: __("Dato på kvitteringen"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
				{ fieldtype: "Section Break" },
				{ fieldname: "bill_no", label: __("Kvitterings- eller fakturanummer"), fieldtype: "Data", reqd: 1, description: __("Står på kvitteringen. Brukes til å stoppe dobbeltregistrering.") },
				{
					fieldname: "vat_rate",
					label: __("MVA-sats på kvitteringen"),
					fieldtype: "Select",
					options: [{ label: "25 %", value: "25" }, { label: "15 %", value: "15" }, { label: "12 %", value: "12" }, { label: __("Ingen MVA"), value: "0" }],
					default: registered ? "25" : "0",
					hidden: registered ? 0 : 1,
					depends_on: "eval:!doc.foreign_service",
				},
				{
					fieldname: "tax_reason",
					label: __("Hvorfor er det ingen MVA?"),
					fieldtype: "Small Text",
					hidden: registered ? 0 : 1,
					depends_on: registered ? "eval:doc.vat_rate=='0' && !doc.foreign_service" : "eval:false",
					description: __("For eksempel unntatt ytelse eller leverandør som ikke er MVA-registrert."),
				},
				{ fieldtype: "Section Break", label: __("Betalt i utenlandsk valuta"), depends_on: "eval:doc.foreign_service" },
				{ fieldname: "currency", label: __("Valuta"), fieldtype: "Link", options: "Currency", default: "NOK" },
				{ fieldname: "conversion_rate", label: __("Kurs til NOK"), fieldtype: "Float", precision: 6, depends_on: "eval:doc.currency!='NOK'", description: __("NOK per enhet. Bruk kursen fra kontoutskriften eller Norges Bank.") },
				{ fieldname: "exchange_rate_source", label: __("Kurskilde"), fieldtype: "Data", depends_on: "eval:doc.currency!='NOK'" },
				{ fieldname: "exchange_rate_date", label: __("Kursdato"), fieldtype: "Date", depends_on: "eval:doc.currency!='NOK'" },
				{ fieldtype: "Section Break", label: __("Brukes også privat"), collapsible: 1 },
				{ fieldname: "business_fraction_percent", label: __("Hvor mye brukes i næringen (%)"), fieldtype: "Float", default: 100, description: __("Resten føres som privat uttak.") },
				{
					fieldname: "deductible_fraction_percent",
					label: __("Fradragsberettiget MVA (%)"),
					fieldtype: "Float",
					default: 100,
					hidden: registered ? 0 : 1,
					description: __("Kan ikke være høyere enn næringsandelen."),
				},
				{ fieldname: "tax_deductible_fraction_percent", label: __("Skattemessig fradrag av næringsdelen (%)"), fieldtype: "Float", default: 100, description: __("Normalt 100. Lavere bare når deler av kostnaden ikke gir fradrag, for eksempel representasjon.") },
				{ fieldname: "tax_adjustment_reason", label: __("Begrunnelse for redusert fradrag"), fieldtype: "Small Text", depends_on: "eval:doc.tax_deductible_fraction_percent<100" },
			]),
			primary_action_label: draft ? __("Lagre endringer") : __("Lag kladd"),
			primary_action: (values) => {
				delete values.supplier_display;
				if (!registered) {
					values.vat_rate = "0";
					values.deductible_fraction_percent = values.business_fraction_percent;
				}
				if (values.foreign_service) values.vat_rate = "0";
				if (!this.validate_currency_values(values, values.bill_date, Boolean(values.foreign_service), __("Valutakjøp"))) {
					return;
				}
				const percent = (value) => (value === undefined || value === null || value === "" ? 100 : Number(value)) / 100;
				const business_fraction = percent(values.business_fraction_percent);
				const deductible_fraction = percent(values.deductible_fraction_percent);
				const tax_deductible_fraction = percent(values.tax_deductible_fraction_percent);
				if (!Number.isFinite(business_fraction) || !Number.isFinite(deductible_fraction) || business_fraction <= 0 || business_fraction > 1 || deductible_fraction < 0 || deductible_fraction > business_fraction) {
					frappe.msgprint(__("Oppgi næringsandel fra 1 til 100 prosent. MVA-andelen kan ikke være høyere enn næringsandelen."));
					return;
				}
				if (!Number.isFinite(tax_deductible_fraction) || tax_deductible_fraction < 0 || tax_deductible_fraction > 1) {
					frappe.msgprint(__("Den skattemessige fradragsandelen må være fra 0 til 100 prosent."));
					return;
				}
				if (tax_deductible_fraction < 1 && !values.tax_adjustment_reason?.trim()) {
					frappe.msgprint(__("Forklar hvorfor fradraget er redusert."));
					return;
				}
				if (values.category === "equipment" && !values.expected_life_months) {
					frappe.msgprint(__("Oppgi hvor lenge du regner med å bruke utstyret."));
					return;
				}
				this.create_draft(dialog, "enk_norge.api.create_purchase", {
					...values,
					company,
					business_fraction,
					deductible_fraction,
					tax_deductible_fraction,
					...(draft ? { draft } : {}),
				});
			},
		});
		dialog.show();
		this.use_native_dates(dialog);
		if (edit) this.fill_supplier_country(dialog);
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
			title: __("Utbetaling fra Stripe e.l."),
			fields: [
				{ fieldtype: "HTML", fieldname: "settlement_intro", options: `<p class="text-muted small">${__("Bruk dette når Stripe, Vipps eller en lignende tjeneste har betalt ut penger for fakturaer du har bokført. Utbetalingen må være i NOK.")}</p>` },
				{ fieldname: "external_settlement_id", label: __("Utbetalings-ID"), fieldtype: "Data", reqd: 1, description: __("Står i oversikten fra Stripe, for eksempel «po_...».") },
				{ fieldname: "posting_date", label: __("Bokføringsdato"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
				{
					fieldname: "source_file",
					label: __("Rapport for utbetalingen"),
					fieldtype: "Attach",
					options: { make_attachments_public: false },
					reqd: 1,
					description: __("CSV eller PDF fra Stripe. Den lagres som bilag og skal ikke endres."),
				},
				{ fieldname: "merchant_of_record_confirmed", label: __("Foretaket selger selv til kundene, og Stripe er bare betalingstjeneste"), fieldtype: "Check", reqd: 1 },
				{ fieldtype: "Section Break", label: __("Fakturaer i oppgjøret") },
				{ fieldname: "invoice", label: __("Bokført salgsfaktura"), fieldtype: "Link", options: "Sales Invoice", only_select: 1 },
				{ fieldname: "invoice_amount", label: __("Beløp i oppgjøret (NOK)"), fieldtype: "Currency", options: "NOK" },
				{ fieldname: "add_invoice", label: __("Legg til faktura"), fieldtype: "Button", click: () => this.add_settlement_reference(dialog, invoices, "invoice", "invoice_amount", false) },
				{ fieldname: "invoice_list", fieldtype: "HTML" },
				{ fieldtype: "Section Break", label: __("Kreditnotaer i oppgjøret") },
				{ fieldname: "credit_note", label: __("Bokført kreditnota"), fieldtype: "Link", options: "Sales Invoice", only_select: 1 },
				{ fieldname: "credit_note_amount", label: __("Refusjon i oppgjøret (NOK)"), fieldtype: "Currency", options: "NOK" },
				{ fieldname: "add_credit_note", label: __("Legg til kreditnota"), fieldtype: "Button", click: () => this.add_settlement_reference(dialog, credit_notes, "credit_note", "credit_note_amount", true) },
				{ fieldname: "credit_note_list", fieldtype: "HTML" },
				{ fieldtype: "Section Break", label: __("Avstemming") },
				{
					fieldname: "fee",
					label: __("Gebyr trukket av Stripe (NOK)"),
					fieldtype: "Currency",
					options: "NOK",
					default: 0,
					description: __("Bare gebyr uten MVA. Får du faktura med MVA for tjenesten, føres den som eget kjøp."),
				},
				{ fieldname: "net_amount", label: __("Beløp utbetalt til banken (NOK)"), fieldtype: "Currency", options: "NOK", reqd: 1 },
			],
			primary_action_label: __("Lag kladd"),
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
					frappe.msgprint(__("Fakturaene minus refusjoner og gebyr må bli det samme som beløpet som ble utbetalt."));
					return;
				}
				const file = await frappe.db.get_value("File", { file_url: values.source_file }, "name");
				if (!file.message?.name) {
					frappe.msgprint(__("Rapporten for utbetalingen ble ikke funnet. Last den opp på nytt."));
					return;
				}
				frappe.call({
					method: "enk_norge.settlement.create_settlement",
					args: { data: { company, ...values, source_file: file.message.name, currency: "NOK", merchant_of_record: "Direct seller", invoices, credit_notes } },
					btn: dialog?.get_primary_btn(),
					freeze: true,
					freeze_message: __("Lager kladd"),
					callback: (response) => {
						dialog.hide();
						frappe.show_alert({ message: __("Oppgjøret er laget som kladd. Kontroller det og bokfør."), indicator: "blue" });
						this.open_document(response.message.doctype, response.message.name);
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
			<div class="enk-year-status"><span>${__("Status")}</span><strong>${safe({ "Draft": __("Utkast"), "Ready for review": __("Klar til levering"), "Manually filed": __("Levert") }[report.status] || report.status)}</strong><span>${__("Revisjon")}</span><strong>${safe(report.revision)}</strong></div>
			<h4>${__("Hovedbok fordelt på rapportkoder")}</h4>
			<div class="enk-year-table-wrap"><table class="table table-bordered"><thead><tr><th>${__("Kategori")}</th><th>${__("Rapportkode")}</th><th class="text-right">${__("Beløp")}</th><th>${__("Kontoer")}</th></tr></thead><tbody>${return_rows}</tbody></table></div>
			<h4>${__("Skatteavstemming")}</h4>
			<div class="enk-year-table-wrap"><table class="table table-bordered"><tbody>${bridge_rows}</tbody></table></div>
			<h4>${__("Personinntekt og avklaringer")}</h4>${personal}${clarifications}${pools}
		</div>`);
		const ready = report.status === "Ready for review";
		dialog.$body.find(".enk-year-report-result").append(ready
			? `<section class="enk-attachments">
				<h4>${__("Lever skattemeldingen")}</h4>
				<p class="text-muted">${__("Før tallene inn i skattemeldingen og næringsspesifikasjonen hos Skatteetaten. Last deretter opp kvitteringen, så markeres årsoppgjøret som levert.")}</p>
				<label class="btn btn-default btn-sm enk-upload">${__("Last opp kvittering og marker levert")}<input type="file" accept="image/*,application/pdf" class="enk-year-receipt"></label>
				<p class="enk-upload-status text-muted small" role="status"></p>
			</section>`
			: report.status === "Manually filed" ? `<p class="text-muted">${__("Årsoppgjøret er markert som levert.")}</p>` : "");
		dialog.$body.find(".enk-year-receipt").on("change", async (event) => {
			const file = event.target.files?.[0];
			if (!file) return;
			const status = dialog.$body.find(".enk-upload-status");
			status.text(__("Laster opp {0}", [file.name]));
			const form = new FormData();
			form.append("file", file, file.name);
			form.append("is_private", "1");
			form.append("doctype", "ENK Year Report");
			form.append("docname", report.name);
			try {
				const response = await fetch("/api/method/upload_file", { method: "POST", headers: { "X-Frappe-CSRF-Token": frappe.csrf_token, Accept: "application/json" }, body: form });
				if (!response.ok) throw new Error(response.statusText);
				const uploaded = (await response.json()).message;
				const filed = await frappe.call({
					method: "enk_norge.year_end.mark_year_report_manually_filed",
					args: { company: report.company, income_year: report.income_year, private_receipt_file: uploaded.name },
					freeze: true,
				});
				frappe.show_alert({ message: __("Årsoppgjøret er markert som levert."), indicator: "green" });
				this.render_year_report_result(dialog, { ...report, ...filed.message });
			} catch (error) {
				status.text(__("Opplastingen feilet. Prøv igjen."));
			}
		});
		dialog.get_primary_btn().html(__("Lukk")).off("click").on("click", () => dialog.hide());
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
				if (["Sales Invoice", "Purchase Invoice", "Payment Entry", "Journal Entry"].includes(response.message?.doctype) && response.message?.name) {
					this.open_document(response.message.doctype, response.message.name);
				} else if (response.message?.doctype && response.message?.name) {
					frappe.set_route("Form", response.message.doctype, response.message.name);
				} else {
					frappe.show_alert({ message: __("Ferdig."), indicator: "green" });
					this.route();
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
				if (response.message.reused) {
					frappe.show_alert({ message: __("Bilaget fantes allerede. Viser det eksisterende."), indicator: "blue" });
				}
				this.open_document(response.message.doctype, response.message.name);
			},
		});
	}
}

function format_plain(value) {
	// Tall fra API-et vises med komma, slik man skriver dem selv.
	return Number(value || 0).toLocaleString("nb-NO", { maximumFractionDigits: 2, useGrouping: false });
}

function two_decimals(value) {
	return Math.abs(Math.round(value * 100) - value * 100) < 1e-6;
}

// Fakturalinjer i fakturaskjemaet. Frappes tabellfelt blir for trangt på mobil.
class EnkInvoiceLines {
	constructor(wrapper, registered) {
		this.wrapper = wrapper;
		this.registered = registered;
		this.wrapper.html(`<div class="enk-lines-editor">
			<div class="enk-lines-head" aria-hidden="true"><span>${__("Beskrivelse")}</span><span>${__("Antall")}</span><span>${__("Pris")}</span><span>${__("Beløp")}</span><span></span></div>
			<div class="enk-lines-rows"></div>
			<button type="button" class="btn btn-default btn-sm enk-lines-add">${__("Legg til linje")}</button>
			<div class="enk-lines-total"></div>
		</div>`);
		this.rows = this.wrapper.find(".enk-lines-rows");
		this.wrapper.find(".enk-lines-add").on("click", () => this.add(true));
		this.add(false);
	}

	add(focus) {
		const row = $(`<div class="enk-line">
			<textarea class="form-control enk-line-desc" rows="1" placeholder="${__("Hva er levert?")}" aria-label="${__("Beskrivelse")}"></textarea>
			<input class="form-control enk-line-qty" inputmode="decimal" value="1" aria-label="${__("Antall")}">
			<input class="form-control enk-line-rate" inputmode="decimal" placeholder="0" aria-label="${__("Pris per enhet")}">
			<span class="enk-line-sum" aria-label="${__("Beløp")}"></span>
			<button type="button" class="btn btn-xs btn-default enk-line-remove" aria-label="${__("Fjern linjen")}">${frappe.utils.icon("close", "xs")}</button>
		</div>`);
		row.find("input, textarea").on("input", () => this.update());
		row.find(".enk-line-desc").on("input", (event) => {
			event.target.style.height = "auto";
			event.target.style.height = `${event.target.scrollHeight}px`;
		});
		row.find(".enk-line-remove").on("click", () => {
			if (this.rows.children().length > 1) row.remove();
			else row.find("textarea, .enk-line-rate").val("");
			this.update();
		});
		this.rows.append(row);
		this.update();
		if (focus) row.find(".enk-line-desc").trigger("focus");
	}

	parse(value) {
		// Godta både 1 200,50 og 1200.50.
		const text = String(value || "").replace(/\s/g, "");
		if (!text) return NaN;
		const normalized = text.includes(",") ? text.replace(/\./g, "").replace(",", ".") : text;
		return Number(normalized);
	}

	update() {
		let total = 0;
		this.rows.children().each((_, el) => {
			const row = $(el);
			const amount = this.parse(row.find(".enk-line-qty").val()) * this.parse(row.find(".enk-line-rate").val());
			row.find(".enk-line-sum").text(Number.isFinite(amount) ? format_nok(amount) : "");
			if (Number.isFinite(amount)) total += amount;
		});
		const vat = this.registered() ? total * 0.25 : 0;
		this.wrapper.find(".enk-lines-total").html(this.registered()
			? `<span>${__("Sum eks. MVA")}</span><strong>${format_nok(total)}</strong><span>${__("Med 25 % MVA")}</span><strong>${format_nok(total + vat)}</strong>`
			: `<span>${__("Å betale")}</span><strong>${format_nok(total)}</strong>`);
	}

	fill(items = []) {
		this.rows.empty();
		for (const item of items) {
			this.add(false);
			const row = this.rows.children().last();
			row.find(".enk-line-desc").val(item.description || "");
			row.find(".enk-line-qty").val(format_plain(item.quantity));
			row.find(".enk-line-rate").val(format_plain(item.unit_price));
		}
		if (!items.length) this.add(false);
		this.update();
	}

	values() {
		const items = [];
		let error = "";
		this.rows.children().each((_, el) => {
			const row = $(el);
			const description = row.find(".enk-line-desc").val().trim();
			const quantity = this.parse(row.find(".enk-line-qty").val());
			const rate = this.parse(row.find(".enk-line-rate").val());
			if (!description && !row.find(".enk-line-rate").val()) return;
			if (!description) error = __("Hver linje må ha en beskrivelse.");
			else if (!(quantity > 0) || !(rate > 0)) error = __("Oppgi antall og pris større enn null på linjen «{0}».", [frappe.utils.escape_html(description)]);
			else if (!two_decimals(quantity) || !two_decimals(rate)) error = __("Antall og pris kan ha høyst to desimaler.");
			items.push({ description, quantity: quantity.toFixed(2), unit_price: rate.toFixed(2) });
		});
		if (!error && !items.length) error = __("Legg inn minst én linje.");
		if (error) {
			frappe.msgprint(error);
			return null;
		}
		return items;
	}
}

function format_hours(value) {
	return Number(value || 0).toLocaleString("nb-NO", { maximumFractionDigits: 2 });
}

function format_money(value, currency = "NOK") {
	const number = typeof value === "number" ? value : Number(value);
	return format_currency(Number.isFinite(number) ? number : 0, currency || "NOK");
}

function enk_doctype_label(doctype, doc = {}) {
	if (doc.is_return) return __("Kreditnota");
	return {
		"Sales Invoice": __("Faktura"),
		"Purchase Invoice": __("Kjøp"),
		"Payment Entry": __("Betaling"),
		"Journal Entry": __("Postering"),
	}[doctype] || doctype;
}

function enk_status_pill(status) {
	const [label, color] = {
		draft: [__("Kladd"), "orange"],
		unpaid: [__("Ikke betalt"), "red"],
		paid: [__("Betalt"), "green"],
		credit_note: [__("Kreditnota"), "gray"],
		posted: [__("Bokført"), "green"],
		cancelled: [__("Annullert"), "gray"],
	}[status] || [status, "gray"];
	return `<span class="indicator-pill ${color} enk-status">${label}</span>`;
}

function format_nok(value) {
	const number = typeof value === "number" ? value : Number(value);
	return format_currency(Number.isFinite(number) ? number : 0, "NOK");
}
