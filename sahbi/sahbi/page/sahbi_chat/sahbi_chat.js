frappe.pages["sahbi-chat"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("صاحبي"),
		single_column: true,
	});

	frappe.sahbi_chat = new SahbiChat(page);
};

frappe.pages["sahbi-chat"].on_page_show = function () {
	if (frappe.sahbi_chat) {
		frappe.sahbi_chat.load_history();
		frappe.sahbi_chat.focus_input();
	}
};

class SahbiChat {
	constructor(page) {
		this.page = page;
		this.$body = $(page.body);
		this.busy = false;
		this.conversation = null;
		this.build();
		this.bind();
		this.add_toolbar();
		this.load_history();
	}

	build() {
		this.$body.html(`
			<div class="sahbi-chat" dir="rtl">
				<div class="sahbi-chat__hero">
					<div class="sahbi-chat__brand">صاحبي</div>
					<p class="sahbi-chat__sub">
						صاحبك في الفلوس. اكتب زي ما بتتكلم، وهو يسجّل ويوريك الحساب.
					</p>
				</div>
				<div class="sahbi-chat__suggestions"></div>
				<div class="sahbi-chat__thread" role="log" aria-live="polite"></div>
				<div class="sahbi-chat__composer">
					<textarea class="sahbi-chat__input form-control" rows="2"
						placeholder="اكتب هنا... مثلاً: دخلت 500 أو وريني حسابات الناس"></textarea>
					<button class="btn btn-primary sahbi-chat__send" type="button">إرسال</button>
				</div>
				<div class="sahbi-chat__hint text-muted">
					جرّب: ازيك، دخلت 500، دفعت 200 لمحمد، مين ليه فلوس عندي.
				</div>
			</div>
		`);
		this.$thread = this.$body.find(".sahbi-chat__thread");
		this.$input = this.$body.find(".sahbi-chat__input");
		this.$send = this.$body.find(".sahbi-chat__send");
		this.$suggestions = this.$body.find(".sahbi-chat__suggestions");

		const chips = [
			{ label: "ازيك", text: "ازيك" },
			{ label: "دخلت 500", text: "دخلت 500" },
			{ label: "دفعت 200 لمحمد", text: "دفعت 200 لمحمد" },
			{ label: "حسابات الناس", text: "وريني حسابات الناس" },
			{ label: "مين ليه فلوس", text: "مين ليه فلوس عندي" },
		];
		chips.forEach((chip) => {
			const $b = $(`<button type="button" class="btn btn-sm btn-default sahbi-chat__chip"></button>`)
				.text(chip.label)
				.attr("data-text", chip.text);
			this.$suggestions.append($b);
		});
	}

	add_toolbar() {
		this.page.set_primary_action("إرسال", () => this.send());
		this.page.add_inner_button("تحديث المحادثة", () => this.load_history());
	}

	bind() {
		this.$send.on("click", () => this.send());
		this.$input.on("keydown", (e) => {
			if (e.key === "Enter" && !e.shiftKey) {
				e.preventDefault();
				this.send();
			}
		});
		this.$suggestions.on("click", ".sahbi-chat__chip", (e) => {
			const text = $(e.currentTarget).attr("data-text");
			this.$input.val(text);
			this.send();
		});
	}

	focus_input() {
		this.$input.trigger("focus");
	}

	append_system(text) {
		this.$thread.append(
			`<div class="sahbi-chat__msg sahbi-chat__msg--system"><div class="sahbi-chat__bubble">${frappe.utils.escape_html(
				text
			)}</div></div>`
		);
		this.scroll();
	}

	append_user(text) {
		this.$thread.append(
			`<div class="sahbi-chat__msg sahbi-chat__msg--user"><div class="sahbi-chat__bubble">${frappe.utils.escape_html(
				text
			)}</div></div>`
		);
		this.scroll();
	}

	append_sahbi(text) {
		const safe = frappe.utils.escape_html(text || "").replace(/\n/g, "<br>");
		this.$thread.append(
			`<div class="sahbi-chat__msg sahbi-chat__msg--ai">
				<div class="sahbi-chat__avatar">ص</div>
				<div>
					<div class="sahbi-chat__bubble">${safe}</div>
				</div>
			</div>`
		);
		this.scroll();
	}

	scroll() {
		const el = this.$thread.get(0);
		if (el) {
			el.scrollTop = el.scrollHeight;
		}
	}

	set_busy(flag) {
		this.busy = flag;
		this.$send.prop("disabled", flag);
		this.$input.prop("disabled", flag);
	}

	load_history() {
		frappe.call({
			method: "sahbi.chat.api.get_history",
			args: { conversation: this.conversation, limit: 0 },
			callback: (r) => {
				const msg = r.message || {};
				this.conversation = msg.conversation;
				this.$thread.empty();
				const rows = msg.messages || [];
				if (!rows.length) {
					this.append_system("اكتب أول رسالة، صاحبي هيرد عليك.");
					return;
				}
				rows.forEach((row) => {
					if (row.role === "User") {
						this.append_user(row.content);
					} else {
						this.append_sahbi(row.content);
					}
				});
			},
			error: () => {
				this.append_system("مقدرش أحمّل المحادثة.");
			},
		});
	}

	send() {
		if (this.busy) {
			return;
		}
		const text = (this.$input.val() || "").trim();
		if (!text) {
			return;
		}
		this.$input.val("");
		this.append_user(text);
		this.set_busy(true);
		frappe.call({
			method: "sahbi.chat.api.send_message",
			args: { text, conversation: this.conversation },
			freeze: false,
			callback: (r) => {
				const msg = r.message || {};
				this.conversation = msg.conversation;
				this.append_sahbi(msg.reply || "حصلت مشكلة. العملية متنفذتش.");
			},
			error: () => {
				this.append_sahbi("حصلت مشكلة. العملية متنفذتش.");
			},
			always: () => {
				this.set_busy(false);
				this.focus_input();
			},
		});
	}
}
