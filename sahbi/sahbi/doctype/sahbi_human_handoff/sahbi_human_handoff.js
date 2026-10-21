// Copyright (c) 2026, Beshoy Atef and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sahbi Human Handoff", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.status === "Resolved") {
			return;
		}
		frm.add_custom_button(__("Resolve & Resume AI"), () => {
			frappe.prompt(
				[
					{
						fieldname: "notes",
						fieldtype: "Small Text",
						label: __("Resolution Notes"),
					},
				],
				(values) => {
					frappe.call({
						method: "sahbi.api.conversations.resolve_handoff",
						args: {
							handoff: frm.doc.name,
							notes: values.notes,
							resume_ai: 1,
						},
						freeze: true,
						callback() {
							frm.reload_doc();
							frappe.show_alert({
								message: __("Handoff resolved; AI resumed"),
								indicator: "green",
							});
						},
					});
				},
				__("Resolve Handoff"),
				__("Resolve")
			);
		});
	},
});
