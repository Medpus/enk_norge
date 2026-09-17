frappe.provide("enk_norge");
frappe.provide("enk_norge.first_run");

enk_norge.first_run.slides = [
	{
		name: "system-user",
		title: __("Hvem skal bruke regnskapet?"),
		help: __(
			"Opprett en egen systembruker for den daglige driften. Opplysningene brukes ikke som foretaksdata."
		),
		fields: [
			{
				fieldname: "system_user_full_name",
				label: __("Navn"),
				fieldtype: "Data",
				reqd: 1,
			},
			{
				fieldname: "system_user_email",
				label: __("E-post"),
				fieldtype: "Data",
				options: "Email",
				reqd: 1,
			},
			{
				fieldname: "system_user_password",
				label: __("Passord"),
				fieldtype: "Password",
				reqd: 1,
			},
		],
	},
	{
		name: "company",
		title: __("Foretaket"),
		help: __(
			"Vi bruker opplysningene til å opprette foretaket og det norske grunnoppsettet."
		),
		fields: [
			{
				fieldname: "company_name",
				label: __("Firmanavn"),
				fieldtype: "Data",
				reqd: 1,
			},
			{
				fieldname: "abbr",
				label: __("Forkortelse"),
				fieldtype: "Data",
				description: __("To til fem bokstaver eller tall. Brukes i kontonavn og fakturaserie."),
				reqd: 1,
			},
			{
				fieldname: "organization_number",
				label: __("Organisasjonsnummer"),
				fieldtype: "Data",
				reqd: 1,
			},
			{
				fieldname: "start_date",
				label: __("Første bokføringsdato"),
				fieldtype: "Date",
				reqd: 1,
			},
		],
	},
	{
		name: "contact",
		title: __("Kontakt og bank"),
		help: __(
			"Telefon og adresse er en del av foretaksopplysningene. Bankkontoen brukes for avstemming senere."
		),
		fields: [
			{
				fieldname: "address_line",
				label: __("Forretningsadresse"),
				fieldtype: "Data",
				reqd: 1,
			},
			{
				fieldname: "postal_code",
				label: __("Postnummer"),
				fieldtype: "Data",
				reqd: 1,
			},
			{
				fieldname: "city",
				label: __("Poststed"),
				fieldtype: "Data",
				reqd: 1,
			},
			{
				fieldname: "phone",
				label: __("Telefon"),
				fieldtype: "Data",
				reqd: 1,
			},
			{
				fieldname: "bank_name",
				label: __("Bankens navn"),
				fieldtype: "Data",
				reqd: 1,
			},
			{
				fieldname: "bank_account",
				label: __("Norsk bankkonto"),
				fieldtype: "Data",
				reqd: 1,
			},
		],
	},
	{
		name: "vat-and-history",
		title: __("MVA og tidligere regnskap"),
		help: __(
			"Oppsettet flytter ikke historikk. Ved systembytte må inngående balanse, åpne poster og første fakturanummer være avklart før du fortsetter."
		),
		fields: [
			{
				fieldname: "vat_registered",
				label: __("Foretaket er registrert i Merverdiavgiftsregisteret"),
				fieldtype: "Check",
			},
			{
				fieldname: "vat_registration_date",
				label: __("MVA gjelder fra"),
				fieldtype: "Date",
				depends_on: "eval:doc.vat_registered",
			},
			{
				fieldname: "history_confirmed",
				label: __(
					"Jeg har avklart tidligere regnskap, eller bekrefter at foretaket starter uten historikk."
				),
				fieldtype: "Check",
				reqd: 1,
			},
		],
		validate() {
			if (this.values.vat_registered && !this.values.vat_registration_date) {
				frappe.msgprint(__("Oppgi datoen MVA-registreringen gjelder fra."));
				return false;
			}
			return true;
		},
	},
];

frappe.setup.on("before_load", () => {
	if (frappe.boot.setup_wizard_completed_apps?.includes("erpnext")) {
		return;
	}

	const add_slide = frappe.setup.add_slide;
	frappe.setup.slides = [];
	enk_norge.first_run.slides.forEach((slide) => frappe.setup.slides.push(slide));

	// ERPNexts page-skript kan registreres etter dette oppsettet. Ikke la det
	// legge standard kontoplan-slidene etter vårt norske førstegangsoppsett.
	frappe.setup.add_slide = function (slide) {
		if (enk_norge.first_run.slides.includes(slide)) {
			add_slide.call(this, slide);
		}
	};
});

frappe.setup.on("after_load", () => {
	if (!frappe.wizard || frappe.boot.setup_wizard_completed_apps?.includes("erpnext")) {
		return;
	}

	frappe.wizard.action_on_complete = function () {
		if (!this.current_slide.set_values()) {
			return;
		}
		this.update_values();
		this.show_working_state();
		this.disable_keyboard_nav();

		frappe.call({
			method: "enk_norge.setup.complete_first_run",
			args: { data: this.values },
			freeze: true,
			freeze_message: __("Gjør klart ENK Norge"),
			callback: () => {
				this.set_setup_complete_message(__("Oppsettet er klart"), __("Åpner ENK Norge ..."));
				setTimeout(() => window.location.assign("/app/enk-norge"), 500);
			},
			error: () => this.abort_setup(),
		});
	};
});
