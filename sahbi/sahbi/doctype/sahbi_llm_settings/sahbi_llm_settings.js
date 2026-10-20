// Copyright (c) 2026, Beshoy Atef and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sahbi LLM Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Test Connection"), () => {
			frappe.call({
				method: "sahbi.sahbi.doctype.sahbi_llm_settings.sahbi_llm_settings.test_llm_connection",
				freeze: true,
				callback(r) {
					const status = r.message || {};
					const models = (status.models || []).join(", ");
					if (status.available) {
						frappe.msgprint({
							title: __("Ollama"),
							indicator: status.configured_model_present ? "green" : "orange",
							message: __(
								"Connected to {0}. Configured model: {1}. Installed: {2}",
								[status.url, status.configured_model, models || __("none")]
							),
						});
					} else {
						frappe.msgprint({
							title: __("Ollama"),
							indicator: "red",
							message: status.error || __("Ollama is unavailable"),
						});
					}
				},
			});
		});
	},
});
