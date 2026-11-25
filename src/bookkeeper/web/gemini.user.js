// ==UserScript==
// @name         Bookkeeper: Gemini batches
// @namespace    bookkeeper-local
// @version      __VERSION__
// @description  Lets Bookkeeper on this computer send its AI requests to this Gemini tab and read the answers back.
// @match        https://gemini.google.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        unsafeWindow
// @connect      127.0.0.1
// @connect      localhost
// @run-at       document-idle
// @noframes
// ==/UserScript==
// Made by Bookkeeper for you (see geminiweb.py). It only talks to Bookkeeper on this computer. Keep a Gemini tab open:
// every few seconds it asks Bookkeeper for a batch; with one, it opens a new chat, picks your mode, attaches the
// request as a file, sends it, waits for the whole answer and sends it back. It stops on a sign-in page or a limit.
// After a try that failed, the next one starts in a freshly loaded chat, so files that try left in the prompt (one
// that failed to upload keeps Send off) don't pile up.
(() => {
  "use strict";
  const BASE = "__BASE__";
  const TOKEN = "__TOKEN__";
  const PROMPT = "__PROMPT__";
  const POLL_MS = 8000;
  const ANSWER_MS = 50 * 60 * 1000;
  const NEW_CHAT = "https://gemini.google.com/app?hl=en";
  const VERSION = __VERSION__;
  let tab = sessionStorage.getItem("bookkeeper-tab");
  if (!tab) { tab = Math.random().toString(36).slice(2, 12); sessionStorage.setItem("bookkeeper-tab", tab); }
  let busy = false;

  // ---------- talking to Bookkeeper
  const call = (method, path, body) => new Promise((resolve, reject) => GM_xmlhttpRequest({
    method, url: BASE + path, timeout: 30000,
    headers: { "Content-Type": "application/json", "X-Bookkeeper-Token": TOKEN },
    data: body ? JSON.stringify(body) : undefined,
    onload: (r) => (r.status < 400 ? resolve(r.responseText ? JSON.parse(r.responseText) : null) : reject(new Error(`Bookkeeper answered ${r.status}`))),
    onerror: () => reject(new Error("Bookkeeper isn't running")),
    ontimeout: () => reject(new Error("Bookkeeper didn't answer")),
  }));
  const report = (id, fields) => call("POST", "/api/ai/web/report", { tab, id, ...fields }).catch(() => null);
  const fatal = (m) => Object.assign(new Error(m), { fatal: true });
  const retry = (m) => Object.assign(new Error(m), { fatal: false });

  // ---------- the Gemini page (buttons are found by their icons, which are the same in every language)
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const area = () => document.querySelector("fieldset.input-area-fieldset") || document;
  const iconName = (i) => (i.getAttribute("fonticon") || i.getAttribute("data-mat-icon-name") || i.textContent || "").trim();
  const iconOf = (b) => { const i = b.querySelector("mat-icon"); return i ? iconName(i) : ""; };
  const button = (icons, label) => [...area().querySelectorAll("button")]
    .find((b) => icons.includes(iconOf(b)) || label.test(b.getAttribute("aria-label") || ""));
  const enabled = (b) => !!b && !b.disabled && b.getAttribute("aria-disabled") !== "true";
  const sendBtn = () => button(["arrow_upward", "send"], /^send/i);
  const stopBtn = () => button(["stop", "stop_circle"], /^stop/i);
  const editor = () => document.querySelector("rich-textarea .ql-editor, [contenteditable=true][role=textbox]");
  const escape = () => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  const signedOut = () => !!document.querySelector('[data-test-id="mode-picker-sign-in-button"], [data-test-id="sign-out-banner"], a[href*="ServiceLogin"]');
  const isNewChat = () => /^\/app\/?$/.test(location.pathname) && !document.querySelector("model-response, user-query");
  const waitFor = async (fn, ms, every = 1000) => {
    const end = Date.now() + ms;
    while (Date.now() < end) { const v = fn(); if (v) return v; await sleep(every); }
    return null;
  };
  const FRESH = "bookkeeper-fresh";   // set when a try failed: the next one starts in a freshly loaded chat
  const visible = (e) => e.getClientRects().length > 0;
  const hover = (e) => { for (const t of ["pointerover", "pointerenter", "mouseover", "mouseenter"]) e.dispatchEvent(new MouseEvent(t, { bubbles: true })); };

  // Picks the mode, e.g. "Neon High": the whole name if the menu has it, otherwise each word in turn: "Neon" (an item
  // with that name on any of its lines, like "Deeper analysis / Neon"), then "High" (opening submenus such as
  // "Thinking level" to find it).
  async function pickMode(mode) {
    const norm = (s) => (s || "").toLowerCase().replace(/\s+/g, " ").trim();
    const want = norm(mode);
    const words = want.split(" ");
    const lines = (el) => (el.innerText || el.textContent || "").split("\n").map(norm).filter(Boolean);
    const first = (el) => lines(el)[0] || "";
    const vis = (e) => e.getClientRects().length > 0;
    // Its name ("Open mode picker, currently Neon") may be a label or text hidden inside the button
    const modeBtn = () => document.querySelector('[data-test-id="bard-mode-menu-button"] button')
      || [...document.querySelectorAll("button")].find((b) =>
        /mode picker/i.test(`${b.getAttribute("aria-label") || ""} ${b.getAttribute("title") || ""} ${b.innerText || ""}`))
      || document.querySelector('[data-test-id="bard-mode-menu-button"]');
    const shown = () => { const b = modeBtn(); if (!b) return "";
      const m = (b.getAttribute("aria-label") || "").match(/currently (.+)$/i);
      return [...new Set(norm(`${b.innerText || ""} ${m ? m[1] : ""}`).split(" "))].join(" "); };
    const has = (w) => shown().split(/[^\p{L}\p{N}.]+/u).includes(w);
    const items = () => {
      const roles = '[role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"], [role="option"], [role="radio"], [role="tab"]';
      const pops = [...document.querySelectorAll('[role="menu"], [role="listbox"], [role="dialog"], .cdk-overlay-pane, .mat-mdc-menu-panel')].filter(vis);
      const found = [...document.querySelectorAll(roles), ...pops.flatMap((p) => [...p.querySelectorAll('button, [role="button"]')])];
      const b = modeBtn();
      // never the upload menu ("Upload files", "Add from Drive"…): its items open file pickers
      const upload = (e) => { const m = e.closest('[role="menu"], .mat-mdc-menu-panel, .cdk-overlay-pane');
        return /^(upload|add from drive)/i.test(first(e)) || /upload files|add from drive/i.test(m ? m.innerText : ""); };
      return [...new Set(found)].filter((e) => vis(e) && e !== b && !(b && b.contains(e))
        && !e.closest("model-response, user-query, side-navigation, nav") && first(e) && !upload(e));
    };
    const isOpen = () => { const x = modeBtn().getAttribute("aria-expanded"); return x ? x === "true" : items().length > 0; };
    // Icons that mean "opens more": submenu arrows, and the chevrons of sections that unfold in place
    const MORE_ICON = /^(chevron_right|chevron_forward|arrow_right|arrow_forward|arrow_forward_ios|navigate_next|keyboard_arrow_right|expand_more|expand_less|keyboard_arrow_down|keyboard_arrow_up|arrow_drop_down|unfold_more)$/;
    const icons = (e) => [...e.querySelectorAll('mat-icon, .google-symbols, [class*="material-symbols"], [class*="material-icons"], [data-icon]')]
      .map((i) => (i.getAttribute("fonticon") || i.getAttribute("data-mat-icon-name") || i.getAttribute("data-icon") || i.textContent || "").trim().toLowerCase());
    // A setting rather than a choice, like "Thinking level": a single line named so. Pressing it shows its choices.
    const SETTING = /think|reason|level|effort|budget|размышл|мышлен|уровень|рівень|мислен/i;
    const opensMore = (e) => {
      const p = e.getAttribute("aria-haspopup");   // "menu" opens a submenu; "dialog" would open a window: not that
      if (p === "dialog") return false;
      return (!!p && p !== "false") || e.hasAttribute("aria-expanded")
        || /submenu|expan/i.test(typeof e.className === "string" ? e.className : "")
        || icons(e).some((n) => MORE_ICON.test(n)) || (lines(e).length === 1 && SETTING.test(first(e)));
    };
    // What an item is made of, for the message when the mode can't be picked
    const describe = (e) => `${e.tagName.toLowerCase()}${["role", "aria-haspopup", "aria-expanded"]
      .map((a) => (e.hasAttribute(a) ? ` ${a}=${e.getAttribute(a)}` : "")).join("")}${icons(e).length ? ` icons=${icons(e).join("+")}` : ""}`;
    // An item named so: the word as a whole word in its name or the line under it ("Deeper analysis / 4 Neon")
    const esc = (w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const named = (e, w) => { const re = new RegExp(`(^|[\\s·(])${esc(w)}($|[\\s·),])`, "u");
      return lines(e).slice(0, 2).some((l) => re.test(l)); };
    const press = async (e) => {
      for (const t of ["pointerover", "pointerenter", "mouseover", "mouseenter"]) e.dispatchEvent(new MouseEvent(t, { bubbles: true }));
      e.click();
      await sleep(1000);
    };
    const label = (e) => lines(e).slice(0, 2).join(" / ");
    const seen = new Set();
    const opened = [];   // each submenu pressed, and what it showed
    const note = () => items().forEach((e) => seen.add(label(e)));
    const open = async () => { if (!isOpen()) { modeBtn().click(); await sleep(1000); } note(); };
    // One word: an item named so, else look inside each submenu
    const choose = async (w) => {
      await open();
      const plain = (e) => !opensMore(e) && named(e, w);
      let hit = items().find(plain);
      if (hit) { await press(hit); return true; }
      const tried = new Set();
      for (let i = 0; i < 6; i++) {
        const more = items().filter((e) => opensMore(e) && !tried.has(first(e)));
        if (!more.length) break;
        // a submenu that already mentions the word (like "Thinking level / Low" for "high" won't, so try them all)
        more.sort((a, b) => named(b, w) - named(a, w));
        tried.add(first(more[0]));
        const before = new Set(items().map(label));
        await press(more[0]);
        note();
        const shownNow = items().map(label).filter((l) => !before.has(l));
        opened.push(`${first(more[0])} (${describe(more[0])}) showed ${shownNow.length ? shownNow.join(", ") : "nothing new"}`);
        hit = items().find(plain);
        if (hit) { await press(hit); return true; }
        if (!isOpen()) await open();
      }
      return false;
    };
    // A tab that has just opened may draw the mode button a while after the prompt box
    if (!(await waitFor(modeBtn, 30000))) {
      const btns = [...area().querySelectorAll("button")].map((b) => b.getAttribute("aria-label") || (b.innerText || "").trim()).filter(Boolean);
      return { ok: false, why: `no mode button showed up in 30 seconds; the prompt area's buttons: ${btns.join(", ") || "none"}` };
    }
    if (words.every(has)) return { ok: true };
    await open();
    const whole = items().find((e) => !opensMore(e) && named(e, want));
    const picked = whole ? (await press(whole), words) : [];
    if (!whole) for (const w of words) if (await choose(w)) picked.push(w);
    if (isOpen()) { escape(); await sleep(400); }
    if (isOpen()) { escape(); await sleep(400); }
    // Done when the mode button shows every word, or (as it may show only the model) every word was picked in the menu
    if (words.every(has) || (picked.length === words.length && has(words[0]))) return { ok: true };
    const missing = words.filter((w) => !picked.includes(w));
    const single = [...seen].filter((l) => !l.includes(" / "));   // one-line items: settings rather than modes
    return { ok: false, why: `the mode button shows "${shown() || "nothing"}"${missing.length ? `; no menu item for "${missing.join(" ")}"` : ""}`
      + `${opened.length ? `; opened ${opened.join("; ")}` : single.length ? `; nothing opened from ${single.join(", ")}` : ""}`, names: [...seen] };
  }

  // In Firefox-based browsers the script runs apart from the page, so the file and the events are made in the page's
  // own world: otherwise Gemini may not be able to read them.
  const FF = typeof cloneInto === "function" && typeof unsafeWindow !== "undefined";
  const W = FF ? unsafeWindow : window;
  const forPage = (o) => (FF ? cloneInto(o, W, { wrapReflectors: true }) : o);
  const files = (text, name) => {
    const dt = new W.DataTransfer();
    dt.items.add(new W.File(forPage([text]), name, forPage({ type: "text/plain" })));
    return dt;
  };
  const fire = (el, Kind, type, extra = {}) => el.dispatchEvent(new W[Kind](type, forPage({ bubbles: true, cancelable: true, ...extra })));
  const edText = () => { const ed = editor(); return ed ? (ed.innerText || "").trim() : ""; };
  // What the prompt area shows besides the prompt box itself (attached files show up here)
  const areaText = () => [...area().querySelectorAll("*")].filter((e) => !e.children.length && !e.closest("rich-textarea"))
    .map((e) => (e.textContent || "").trim()).filter(Boolean).join(" · ");
  const about = () => {
    const inputs = [...document.querySelectorAll("input[type=file]")];
    const gm = typeof GM_info !== "undefined" ? `${GM_info.scriptHandler || "?"} ${GM_info.version || ""}`.trim() : "?";
    return `file inputs: ${inputs.length}, taking .txt: ${inputs.filter((i) => /\.txt|text\/|^$/.test(i.accept || "")).length}; `
      + `${/firefox/i.test(navigator.userAgent) ? "Firefox-based" : "Chromium-based"} browser, ${gm}`;
  };

  // Ways to attach the request, tried in turn: each of the page's file inputs (as if you had picked the file in the
  // upload dialog), pasting the file into the prompt box, dropping it on the prompt area. The last resort pastes the
  // request itself into the prompt box as text. Returns true when it went in as a file.
  async function attach(text, name) {
    const stem = name.replace(/\.[^.]+$/, "").toLowerCase();
    const named = () => [...document.querySelectorAll("body *")].some((e) => {
      if (e.closest("model-response, user-query, side-navigation, nav")) return false;
      return [e.children.length < 6 ? e.textContent : "", e.getAttribute("title"), e.getAttribute("aria-label"), e.getAttribute("alt")]
        .some((v) => v && v.toLowerCase().includes(stem));
    });
    const sendWasOn = enabled(sendBtn());
    const shows = () => named() || (!sendWasOn && !edText() && enabled(sendBtn()));
    const uploading = () => !!area().querySelector('[role="progressbar"], mat-progress-spinner, mat-spinner, [class*="uploading"]');
    const before = areaText();
    const plus = button(["plus", "add", "add_circle"], /upload/i);
    const closeMenu = async () => {
      if (plus && plus.getAttribute("aria-expanded") === "true") { escape(); await sleep(300); }
      if (plus && plus.getAttribute("aria-expanded") === "true") { plus.click(); await sleep(300); }
    };
    const inputs = () => [...document.querySelectorAll("input[type=file]")].filter((i) => !i.webkitdirectory)
      .sort((a, b) => (b.accept || "*").length - (a.accept || "*").length);
    if (!inputs().length && plus) { plus.click(); await sleep(1200); }
    const ways = [...inputs().map((input, n) => [`file input ${n + 1}`, () => {
      input.files = files(text, name).files;
      fire(input, "Event", "input");
      fire(input, "Event", "change");
    }]),
    ["paste", () => { const ed = editor(); ed.focus(); fire(ed, "ClipboardEvent", "paste", { clipboardData: files(text, name) }); }],
    ["drop", () => {
      const zone = document.querySelector(".xap-uploader-dropzone") || area();
      const dt = files(text, name);
      for (const type of ["dragenter", "dragover", "drop"]) fire(zone, "DragEvent", type, { dataTransfer: dt });
    }]];
    const tried = [];
    for (const [how, go] of ways) {
      try { go(); } catch (e) { tried.push(`${how}: ${e.message || e}`); continue; }
      await sleep(800);
      await closeMenu();
      if (!(await waitFor(shows, 15000))) {
        const now = areaText();
        tried.push(`${how}: nothing showed up${now !== before ? ` (the prompt area now shows "${now.slice(0, 120)}")` : ""}`);
        continue;
      }
      if (!(await waitFor(() => !uploading(), 180000, 2000))) throw retry("Gemini kept uploading the request for minutes");
      return true;
    }
    await closeMenu();
    // The last resort: the request itself as text in the prompt box (Gemini cuts very long text, so it has to fit)
    if (await typeIn(text)) return false;
    const cut = bare(edText());
    clearBox();
    throw fatal(`couldn't attach the request (${tried.join("; ")}; pasting it as text: `
      + `${cut ? `Gemini kept only ${cut} of its ${bare(text)} characters, so a smaller batch might go in as text` : "nothing showed up"}). ${about()}`);
  }

  const bare = (s) => s.replace(/\s+/g, "").length;
  const clearBox = () => { const ed = editor(); if (!ed) return; ed.focus(); document.execCommand("selectAll"); document.execCommand("delete"); };

  // Request files are named bk + the time (bk123233.txt). One showing in the prompt (not in a sent message) is either
  // this try's or left over from a try that failed.
  const REQUEST_NAME = /^bk\d{6}(\.txt)?$/i;
  const requestFiles = () => [...document.querySelectorAll("body *")].filter((e) => !e.children.length && visible(e)
    && !e.closest("model-response, user-query, side-navigation, nav, rich-textarea")
    && REQUEST_NAME.test((e.textContent || "").trim()));
  // The attachment card around a file name: the nearest parent with a button of its own (never the whole prompt)
  const cardOf = (e) => {
    let c = e;
    for (let i = 0; i < 6 && c.parentElement && !c.parentElement.querySelector("rich-textarea"); i++) {
      c = c.parentElement;
      if (c.querySelector("button, [role=button]")) return c;
    }
    return c;
  };
  const REMOVE = /remove|delete|cancel|close|discard|удал|убра|видал|прибра/i;
  const removeBtn = (card) => [...card.querySelectorAll("button, [role=button]")].find((b) =>
    REMOVE.test(`${b.getAttribute("aria-label") || ""} ${b.getAttribute("title") || ""}`)
    || ["close", "cancel", "delete", "clear"].includes(iconOf(b)));
  // A card Gemini marked as failed (the red "!"): its icon, or words like "failed" in its labels
  const FAILED_ICON = /^(error|error_outline|warning|warning_amber|report|report_problem|priority_high)$/;
  const failedCard = (card) => [...card.querySelectorAll("mat-icon")].some((i) => FAILED_ICON.test(iconName(i)))
    || /fail|error|couldn.t|не удалось|ошибк|помилк/i.test([card, ...card.querySelectorAll("[aria-label], [title]")]
      .map((x) => `${x.getAttribute("aria-label") || ""} ${x.getAttribute("title") || ""}`).join(" "));
  const uploadFailed = () => requestFiles().some((e) => failedCard(cardOf(e)));

  // Takes out request files and text an earlier try left in the prompt. False when files are still there.
  async function clearPrompt() {
    for (let round = 0; round < 3 && requestFiles().length; round++) {
      for (const name of requestFiles()) {
        const card = cardOf(name);
        hover(card);
        await sleep(300);
        const b = removeBtn(card);
        if (b) { b.click(); await sleep(700); }
      }
    }
    if (edText()) clearBox();
    return !requestFiles().length;
  }

  // Puts text into the prompt box: a paste first, then typing it in. True when the box shows all of it.
  async function typeIn(text) {
    const ed = editor();
    if (!ed) return false;
    const want = bare(text);
    const has = () => bare(edText()) >= want * 0.98;
    ed.focus();
    const dt = new W.DataTransfer();
    dt.setData("text/plain", text);
    fire(ed, "ClipboardEvent", "paste", { clipboardData: dt });
    if (await waitFor(has, 8000, 500)) return true;
    if (bare(edText())) return false;   // it went in, but cut short
    ed.focus();
    document.execCommand("insertText", false, text);
    return !!(await waitFor(has, 20000, 500));
  }

  // The answer's text: its code blocks when it has any (that's where the JSON lines are), else the longest part of
  // its message text, else everything the answer shows.
  const answerText = (resp) => {
    const code = [...resp.querySelectorAll("pre")].map((e) => e.textContent || "").filter((t) => t.trim());
    if (code.length) return code.join("\n");
    const parts = [...resp.querySelectorAll("message-content")].map((e) => e.innerText || e.textContent || "");
    const best = parts.sort((a, b) => b.length - a.length)[0] || "";
    return best.trim() ? best : (resp.innerText || resp.textContent || "");
  };

  async function waitAnswer(job, before) {
    let last = null, same = 0, saved = false, emptySince = 0;
    const end = Date.now() + ANSWER_MS;
    while (Date.now() < end) {
      await sleep(5000);
      const all = document.querySelectorAll("model-response");
      if (all.length <= before) continue;
      if (!saved && /^\/app\/./.test(location.pathname)) { GM_setValue("sent", { id: job.id, url: location.href }); saved = true; }
      const resp = all[all.length - 1];
      const text = answerText(resp);
      const busyNow = !!stopBtn();
      if (!busyNow && !text.trim()) {
        // finished, as far as the page shows, but nothing to read: give it two minutes, then say what's there
        emptySince = emptySince || Date.now();
        if (Date.now() - emptySince > 120000) {
          const kids = [...resp.querySelectorAll("*")].slice(0, 40).map((e) => e.tagName.toLowerCase()).join(" ");
          throw retry(`Gemini's answer looked empty (it shows: ${kids || "nothing"})`);
        }
      } else emptySince = 0;
      same = !busyNow && text.trim() && text === last ? same + 1 : 0;
      last = text;
      if (same >= 2) return text;   // no Stop button and the same text for 10 seconds: Gemini has finished
    }
    throw retry("Gemini didn't finish answering in 50 minutes");
  }

  async function run(job) {
    const step = (s) => report(job.id, { step: s });
    if (!(await waitFor(editor, 30000))) throw retry("Gemini's prompt box didn't show");
    await sleep(1500);
    if (signedOut()) throw fatal("this Gemini tab isn't signed in");
    if (job.mode) {
      step(`choosing ${job.mode}`);
      const r = await pickMode(job.mode);
      if (!r.ok) throw fatal(`couldn't pick the mode "${job.mode}" (${r.why}). The menu shows: ${(r.names || []).join(", ") || "nothing readable"}`);
    }
    if (!(await clearPrompt())) {
      throw fatal("Gemini's prompt still holds request files from an earlier try, and they couldn't be removed. Remove "
        + "them in the Gemini tab (or press New chat), then start the run again");
    }
    step("attaching the request");
    const asFile = await attach(job.text, job.name);
    if (asFile && !(await typeIn(PROMPT))) throw fatal(`couldn't type into Gemini's prompt box. ${about()}`);
    if (!asFile) step("the file didn't attach, so the request went in as text");
    const ready = await waitFor(() => (uploadFailed() ? "failed" : enabled(sendBtn()) ? "send" : null), 90000, 2000);
    if (ready === "failed") throw retry("Gemini couldn't upload the request file (it marked the file as failed)");
    if (!ready) throw retry(`Gemini's Send button stayed off (the prompt area shows: ${areaText().slice(0, 200) || "nothing"})`);
    const before = document.querySelectorAll("model-response").length;
    sendBtn().click();
    step("waiting for Gemini to answer");
    return waitAnswer(job, before);
  }

  async function tick() {
    if (busy) return;
    let r;
    try { r = await call("GET", `/api/ai/web/job?tab=${tab}&v=${VERSION}`); } catch { return; }
    const job = r && r.job;
    if (!job) return;
    busy = true;
    try {
      const sent = GM_getValue("sent", null);
      let text;
      if (sent && sent.id === job.id && location.href === sent.url) {
        report(job.id, { step: "waiting for Gemini to answer" });   // the page reloaded after sending: read it here
        text = await waitAnswer(job, 0);
      } else {
        if (!isNewChat() || sessionStorage.getItem(FRESH)) {   // the next tick starts it in the newly loaded chat
          sessionStorage.removeItem(FRESH);
          location.href = NEW_CHAT;
          return;
        }
        text = await run(job);
      }
      await report(job.id, { text });
      GM_setValue("sent", null);
    } catch (e) {
      sessionStorage.setItem(FRESH, "1");   // what this try left in the prompt goes away with the page
      await report(job.id, { error: String(e.message || e), fatal: !!e.fatal });
      GM_setValue("sent", null);
    } finally {
      busy = false;
    }
  }

  setInterval(tick, POLL_MS);
  tick();
})();
