// Copyright (c) 2026, Beshoy Atef and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sahbi Conversation", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}
		frm.add_custom_button(__("Refresh Messages"), () => load_transcript(frm));
		if (is_staff()) {
			frm.add_custom_button(__("Pause AI"), () => {
				frappe.call({
					method: "sahbi.api.conversations.pause_ai",
					args: { conversation: frm.doc.name },
					freeze: true,
					callback() {
						frm.reload_doc();
						frappe.show_alert({ message: __("AI paused"), indicator: "orange" });
					},
				});
			});
			frm.add_custom_button(__("Resume AI"), () => {
				frappe.call({
					method: "sahbi.api.conversations.resume_ai",
					args: { conversation: frm.doc.name },
					freeze: true,
					callback() {
						frm.reload_doc();
						frappe.show_alert({ message: __("AI resumed"), indicator: "green" });
					},
				});
			});
			frm.add_custom_button(__("Send Reply"), () => send_staff_reply(frm), __("Reply"));
			frm.add_custom_button(
				__("Staff Reply (dialog)"),
				() => {
					frappe.prompt(
						[{ fieldname: "text", fieldtype: "Small Text", label: __("Message"), reqd: 1 }],
						(values) => {
							frappe.call({
								method: "sahbi.api.conversations.staff_reply",
								args: { conversation: frm.doc.name, text: values.text },
								freeze: true,
								callback(r) {
									frm.set_value("staff_reply_text", "");
									load_transcript(frm);
									const tag = r.message && r.message.human_agent_tag;
									frappe.show_alert({
										message: tag ? __("Sent with Human Agent tag") : __("Reply sent"),
										indicator: "green",
									});
								},
							});
						},
						__("Staff Reply"),
						__("Send")
					);
				},
				__("Reply")
			);
			frm.add_custom_button(__("Create Handoff"), () => {
				frappe.prompt(
					[
						{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
						{
							fieldname: "priority",
							fieldtype: "Select",
							label: __("Priority"),
							options: "Low\nNormal\nHigh\nUrgent",
							default: "Normal",
						},
					],
					(values) => {
						frappe.call({
							method: "sahbi.api.conversations.create_handoff",
							args: {
								conversation: frm.doc.name,
								reason: values.reason,
								priority: values.priority,
							},
							callback() {
								frm.reload_doc();
							},
						});
					},
					__("Create Handoff"),
					__("Create")
				);
			});
		}
		load_transcript(frm);
	},
});

function is_staff() {
	return (
		frappe.user.name === "Administrator" ||
		frappe.user.has_role("System Manager") ||
		frappe.user.has_role("Sahbi Support")
	);
}

function send_staff_reply(frm) {
	const text = (frm.doc.staff_reply_text || "").trim();
	if (!text) {
		frappe.msgprint(__("Type a reply, then click Send Reply."));
		return;
	}
	frappe.call({
		method: "sahbi.api.conversations.staff_reply",
		args: { conversation: frm.doc.name, text },
		freeze: true,
		freeze_message: __("Sending…"),
		callback(r) {
			frm.set_value("staff_reply_text", "");
			load_transcript(frm);
			const tag = r.message && r.message.human_agent_tag;
			frappe.show_alert({
				message: tag ? __("Sent with Human Agent tag") : __("Reply sent"),
				indicator: "green",
			});
		},
	});
}

function load_transcript(frm) {
	const $wrap = frm.fields_dict.chat_transcript_html.$wrapper;
	$wrap.html(`<div class="text-muted" style="padding:12px;">${__("Loading messages…")}</div>`);
	frappe.call({
		method: "sahbi.api.conversations.get_transcript",
		args: { conversation: frm.doc.name, limit: 300 },
		callback(r) {
			const rows = r.message || [];
			$wrap.html(render_transcript(rows));
			const el = $wrap.find(".sahbi-chat-scroll").get(0);
			if (el) {
				el.scrollTop = 0;
			}
		},
		error() {
			$wrap.html(
				`<div class="text-danger" style="padding:12px;">${__("Could not load messages.")}</div>`
			);
		},
	});
}

function render_transcript(rows) {
	if (!rows.length) {
		return `<div class="sahbi-chat-empty" style="padding:16px;color:var(--text-muted);">
			${__("No messages yet.")}
		</div>`;
	}
	const bubbles = rows
		.map((m) => {
			const inbound = m.role === "User";
			const who = inbound ? __("User") : staff_label(m);
			const when = frappe.datetime.str_to_user(m.creation) || m.creation || "";
			const body = frappe.utils.escape_html(m.content || "").replace(/\n/g, "<br>");
			const meta = [when, m.role || "", m.status || ""].filter(Boolean).join(" · ");
			const align = inbound ? "flex-start" : "flex-end";
			const bg = inbound ? "var(--control-bg)" : "var(--bg-blue-light, #e8f1ff)";
			const border = inbound ? "var(--border-color)" : "var(--blue-200, #c5d9f5)";
			return `<div style="display:flex;justify-content:${align};margin:8px 0;">
				<div style="max-width:78%;background:${bg};border:1px solid ${border};border-radius:12px;padding:10px 12px;">
					<div style="font-size:11px;color:var(--text-muted);margin-bottom:4px;">
						<strong>${frappe.utils.escape_html(who)}</strong> · ${frappe.utils.escape_html(meta)}
					</div>
					<div style="white-space:pre-wrap;word-break:break-word;line-height:1.45;font-size:13px;">${body}</div>
				</div>
			</div>`;
		})
		.join("");

	return `<div class="sahbi-chat-scroll" style="max-height:480px;overflow:auto;padding:8px 4px 16px;background:var(--bg-color);border:1px solid var(--border-color);border-radius:8px;">
		${bubbles}
	</div>`;
}

function staff_label(m) {
	const corr = m.correlation_id || "";
	if (String(corr).startsWith("staff:")) {
		return __("Staff") + " (" + String(corr).slice(6) + ")";
	}
	if (m.role === "Staff") {
		return __("Staff");
	}
	return __("صاحبي");
}
