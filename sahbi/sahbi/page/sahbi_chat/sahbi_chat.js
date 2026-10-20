frappe.pages["sahbi-chat"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "صاحبي",
		single_column: true,
	});

	page.main.html(`
		<div class="sahbi-chat" dir="rtl">
			<div class="sahbi-chat-log"></div>
			<form class="sahbi-chat-form">
				<input class="sahbi-chat-input" type="text" autocomplete="off" placeholder="اكتب هنا..." />
				<button class="btn btn-primary sahbi-chat-send" type="submit">إرسال</button>
			</form>
		</div>
	`);

	const $log = page.main.find(".sahbi-chat-log");
	const $input = page.main.find(".sahbi-chat-input");
	let conversation = null;

	function addBubble(role, content) {
		const who = role === "User" ? "أنت" : "صاحبي";
		const safe = frappe.utils.escape_html(content || "").replace(/\n/g, "<br>");
		$log.append(
			`<div class="sahbi-bubble sahbi-bubble-${role.toLowerCase()}">
				<strong>${who}</strong>
				<div class="sahbi-bubble-text">${safe}</div>
			</div>`
		);
		$log.scrollTop($log.prop("scrollHeight"));
	}

	function loadHistory() {
		frappe.call({
			method: "sahbi.chat.api.get_history",
			callback(r) {
				conversation = r.message.conversation;
				$log.empty();
				(r.message.messages || []).forEach((row) => addBubble(row.role, row.content));
			},
		});
	}

	page.main.find(".sahbi-chat-form").on("submit", function (event) {
		event.preventDefault();
		const text = ($input.val() || "").trim();
		if (!text) {
			return;
		}
		addBubble("User", text);
		$input.val("");
		frappe.call({
			method: "sahbi.chat.api.send_message",
			args: { text, conversation },
			callback(r) {
				conversation = r.message.conversation;
				addBubble("Sahbi", r.message.reply);
			},
			error() {
				addBubble("Sahbi", "حصلت مشكلة. العملية متنفذتش.");
			},
		});
	});

	loadHistory();
	$input.trigger("focus");
};
