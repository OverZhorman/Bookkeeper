// Bookkeeper interface. Plain JavaScript, no build step.

// ---------- tiny helpers ----------
const $ = (sel, el = document) => el.querySelector(sel);
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "html") el.innerHTML = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
const api = {
  async get(url) { const r = await fetch(url); if (!r.ok) throw new Error(`${r.status} ${await r.text()}`); return r.json(); },
  async send(method, url, body) {
    const r = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json();
  },
  post(url, body) { return this.send("POST", url, body || {}); },
  del(url) { return this.send("DELETE", url); },
};
const store = {
  get(k, d) { try { const v = localStorage.getItem("bk:" + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("bk:" + k, JSON.stringify(v)); } catch { /* private mode */ } },
};
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toast.timer); toast.timer = setTimeout(() => t.classList.remove("show"), 2600);
}
const fmtNum = (n) => n === null || n === undefined ? "—" : n >= 1e6 ? (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M" : n >= 1e4 ? Math.round(n / 1e3) + "k" : n >= 1e3 ? (n / 1e3).toFixed(1).replace(/\.0$/, "") + "k" : String(n);
const fmtDate = (s) => s ? String(s).slice(0, 10) : "—";
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

// ---------- vocabulary ----------
const POV = { first: "1st person", third: "3rd person", second: "2nd person", mixed: "Mixed", unsure: "Unsure", none: "Not checked yet" };
const POV_LONG = { first: "First person", third: "Third person", second: "Second person", mixed: "Mixed narration", unsure: "Couldn't tell", none: "Not checked yet" };
const POV_SOURCE = { site: "the site's own tag says so", text: "detected from the opening chapters", "other-site": "taken from a copy of this book on another site", user: "your correction" };
const SRC = { site: ["site", "Written on the site"], rule: ["rule", "Added by a tag rule"], text: ["text", "Found in the chapter text"], "other-site": ["copy", "From a copy on another site"], user: ["you", "Added by you"] };
const STATUS = { completed: "Completed", ongoing: "Ongoing", frozen: "Frozen / abandoned", unknown: "Unknown" };
const ACCESS = { free: "Free", partial: "Partly free", paid: "Paid" };
const LANGS = { ru: "Russian", en: "English", uk: "Ukrainian" };
const SHELVES = { want: "Want to read", reading: "Reading", read: "Read", dropped: "Dropped", hidden: "Hidden" };
const CATS = { narration: "Narration", genre: "Genres", theme: "Themes & tropes", protagonist: "Protagonist", setting: "Setting", relationship: "Relationships", content: "Content", format: "Format", origin: "Origin", demographic: "Audience", fanfic: "Fanfiction", other: "Other tags (as written on the site)" };
const SORTS = [["popularity", "Popularity"], ["rating", "Rating"], ["likes", "Likes"], ["updated", "Recently updated"], ["added", "Recently added"], ["words", "Length"], ["chapters", "Chapters"], ["title", "Title"], ["relevance", "Best match"], ["random", "Random"]];
const LENGTHS = [["", "Any length"], ["0-20000", "Short (under 20k words)"], ["20000-80000", "Medium (20–80k)"], ["80000-300000", "Long (80–300k)"], ["300000-", "Epic (300k+)"]];

let meta = { sites: {}, totals: {} };
let siteCounts = {};
let filters = {};
let tagLang = store.get("tagLang", "en");
let viewMode = store.get("viewMode", "grid");
const results = { books: [], total: 0, page: 0, loading: false, done: false, token: 0 };
let pollTimer = null;

const siteName = (id) => (meta.sites[id] && meta.sites[id].name) || id;
const tagLabel = (t) => (tagLang === "ru" && t.label_ru) ? t.label_ru : t.label;

// ---------- theme ----------
function applyTheme() {
  const t = store.get("theme", null);
  if (t) document.documentElement.setAttribute("data-theme", t); else document.documentElement.removeAttribute("data-theme");
}
$("#theme-btn").addEventListener("click", () => {
  const dark = document.documentElement.getAttribute("data-theme") === "dark" ||
    (!document.documentElement.getAttribute("data-theme") && matchMedia("(prefers-color-scheme: dark)").matches);
  store.set("theme", dark ? "light" : "dark"); applyTheme();
});
applyTheme();

// ---------- routing ----------
const LIST_KEYS = ["pov", "narrator", "tags", "any", "not", "sites", "lang", "status", "access", "pov_source"];
function parseHash() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [path, query] = raw.split("?");
  const params = Object.fromEntries(new URLSearchParams(query || ""));
  return { view: path || "library", params };
}
function toQuery(obj) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(obj)) if (v !== "" && v !== null && v !== undefined && !(Array.isArray(v) && !v.length)) p.set(k, Array.isArray(v) ? v.join(",") : v);
  return p.toString();
}
function readFilters(params) {
  const f = { ...params };
  for (const k of LIST_KEYS) f[k] = f[k] ? f[k].split(",").filter(Boolean) : [];
  return f;
}
function setFilters(next, keepBook = false) {
  const f = { ...next };
  if (!keepBook) delete f.book;
  location.hash = "#/library?" + toQuery(f);
}
function updateFilter(key, value) { setFilters({ ...filters, [key]: value }); }
function toggleIn(key, value) {
  const list = new Set(filters[key] || []);
  list.has(value) ? list.delete(value) : list.add(value);
  updateFilter(key, [...list]);
}

let lastLibraryQuery = null;
async function route() {
  const { view, params } = parseHash();
  document.querySelectorAll("#tabs a").forEach((a) => a.classList.toggle("active", a.dataset.view === view));
  clearInterval(pollTimer);
  if (view === "library") {
    filters = readFilters(params);
    $("#q").value = filters.q || "";
    const { book, ...rest } = params;
    const q = toQuery(rest);
    if (q !== lastLibraryQuery || !$(".library")) { lastLibraryQuery = q; renderLibrary(); }
    if (book) openBook(+book); else closeDrawer(false);
  } else {
    lastLibraryQuery = null;
    closeDrawer(false);
    if (view === "sites") renderSites();
    else if (view === "downloads") renderDownloads();
    else if (view === "help") renderHelp();
    else renderLibrary();
  }
}
window.addEventListener("hashchange", route);
$("#search-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = $("#q").value.trim();
  setFilters({ ...(parseHash().view === "library" ? filters : {}), q, sort: q ? "relevance" : (filters.sort === "relevance" ? "" : filters.sort) });
});

// ---------- library ----------
function renderLibrary() {
  const app = $("#app");
  app.replaceChildren(h("div", { class: "library" }, h("aside", { class: "filters", id: "filters" }), h("section", { class: "results", id: "results" })));
  renderFilters();
  renderToolbar();
  loadResults(true);
}

function fgroup(title, body, action) {
  return h("div", { class: "fgroup" }, h("h3", {}, title, action || null), body);
}
function chip(label, on, onclick, extraClass = "", title) {
  return h("span", { class: `chip ${on ? "on" : ""} ${extraClass}`, onclick, title, role: "button", tabindex: 0 }, label);
}

async function renderFilters() {
  const el = $("#filters");
  if (!el) return;
  let saved = [];
  try { saved = await api.get("/api/searches"); } catch { /* ignore */ }
  const groups = [];
  if (saved.length) {
    groups.push(fgroup("Saved searches", h("div", { class: "chips" }, saved.map((s) =>
      h("span", { class: "chip", title: "Open this search" },
        h("span", { onclick: () => { location.hash = "#/library?" + s.query; } }, s.name),
        h("span", { class: "x", title: "Delete", onclick: async (e) => { e.stopPropagation(); await api.del(`/api/searches/${s.id}`); renderFilters(); } }, " ×"))))));
  }
  groups.push(fgroup("Narration", h("div", {},
    h("div", { class: "chips" }, ["first", "third", "second", "mixed", "unsure", "none"].map((p) =>
      chip(POV[p], filters.pov.includes(p), () => toggleIn("pov", p), "", POV_LONG[p]))),
    h("div", { class: "field" }, h("label", {}, "Narrator (Russian & Ukrainian first-person books)"),
      h("div", { class: "chips" }, [["male", "♂ Male narrator"], ["female", "♀ Female narrator"]].map(([v, l]) =>
        chip(l, filters.narrator.includes(v), () => toggleIn("narrator", v))))),
    h("div", { class: "field" }, h("label", {}, "How we know"),
      h("div", { class: "chips" }, [["site", "Site's own tag"], ["text", "Detected from text"], ["other-site", "From another site"], ["user", "Your correction"]].map(([v, l]) =>
        chip(l, filters.pov_source.includes(v), () => toggleIn("pov_source", v)))))),
    filters.pov.length || filters.narrator.length || filters.pov_source.length ? h("button", { onclick: () => setFilters({ ...filters, pov: [], narrator: [], pov_source: [] }) }, "clear") : null));

  groups.push(fgroup("Tags", tagPicker(), (filters.tags.length || filters.any.length || filters.not.length) ? h("button", { onclick: () => setFilters({ ...filters, tags: [], any: [], not: [] }) }, "clear") : null));

  const siteIds = Object.keys(meta.sites);
  groups.push(fgroup("Sites", h("div", {}, siteIds.map((s) =>
    h("label", { class: "check" }, h("input", { type: "checkbox", checked: filters.sites.includes(s), onchange: () => toggleIn("sites", s) }),
      siteName(s), h("span", { class: "count" }, fmtNum((siteCounts[s] || {}).books || 0)))))));

  groups.push(fgroup("Language", h("div", { class: "chips" }, Object.entries(LANGS).map(([k, v]) => chip(v, filters.lang.includes(k), () => toggleIn("lang", k))))));
  groups.push(fgroup("Status", h("div", { class: "chips" }, ["completed", "ongoing", "frozen"].map((k) => chip(STATUS[k], filters.status.includes(k), () => toggleIn("status", k))))));
  groups.push(fgroup("Access", h("div", { class: "chips" }, Object.entries(ACCESS).map(([k, v]) => chip(v, filters.access.includes(k), () => toggleIn("access", k))))));
  groups.push(fgroup("Original or translation", h("div", { class: "chips" },
    [["", "Both"], ["original", "Originals"], ["translation", "Translations"]].map(([k, v]) => chip(v, (filters.origin || "") === k, () => updateFilter("origin", k))))));

  const lenKey = `${filters.min_words || ""}-${filters.max_words || ""}`;
  groups.push(fgroup("Length", h("div", {},
    h("select", { class: "input", onchange: (e) => { const [a, b] = e.target.value.split("-"); setFilters({ ...filters, min_words: a || "", max_words: b || "" }); } },
      LENGTHS.map(([v, l]) => h("option", { value: v, selected: (v || "-") === lenKey || (v === "" && lenKey === "-") }, l))),
    h("div", { class: "row2" },
      h("div", { class: "field" }, h("label", {}, "Min chapters"), h("input", { class: "input", type: "number", min: 0, value: filters.min_chapters || "", onchange: (e) => updateFilter("min_chapters", e.target.value) })),
      h("div", { class: "field" }, h("label", {}, "Min rating (0–10)"), h("input", { class: "input", type: "number", min: 0, max: 10, step: 0.5, value: filters.min_rating || "", onchange: (e) => updateFilter("min_rating", e.target.value) }))))));

  groups.push(fgroup("Updated", h("div", { class: "chips" },
    [["", "Any time"], ["7", "This week"], ["30", "This month"], ["365", "This year"]].map(([k, v]) => chip(v, (filters.updated_within || "") === k, () => updateFilter("updated_within", k))))));

  groups.push(fgroup("My shelves", h("div", { class: "chips" },
    [["", "Everything"], ["unread", "Not read yet"], ["want", "Want to read"], ["reading", "Reading"], ["read", "Read"], ["favorite", "★ Favourites"], ["dropped", "Dropped"], ["hidden", "Hidden"]].map(([k, v]) =>
      chip(v, (filters.shelf || "") === k, () => updateFilter("shelf", k))))));

  groups.push(fgroup("More", h("div", {},
    h("label", { class: "check" }, h("input", { type: "checkbox", checked: (filters.dedupe ?? "1") !== "0", onchange: (e) => updateFilter("dedupe", e.target.checked ? "" : "0") }), "Show each book once (merge copies on different sites)"),
    h("label", { class: "check" }, h("input", { type: "checkbox", checked: filters.adult === "1", onchange: (e) => updateFilter("adult", e.target.checked ? "1" : "") }), "Include 18+ books"),
    h("label", { class: "check" }, h("input", { type: "checkbox", checked: filters.recommended === "1", onchange: (e) => updateFilter("recommended", e.target.checked ? "1" : "") }), "Only books recommended on forums"),
    h("label", { class: "check" }, h("input", { type: "checkbox", checked: tagLang === "ru", onchange: (e) => { tagLang = e.target.checked ? "ru" : "en"; store.set("tagLang", tagLang); renderLibrary(); } }), "Show tag names in Russian"))));

  el.replaceChildren(...groups);
}

function tagPicker() {
  let mode = store.get("tagMode", "tags");
  const wrap = h("div", { class: "tagbox" });
  const modeSwitch = h("div", { class: "mode-switch" }, [["tags", "Must have"], ["any", "Any of"], ["not", "Exclude"]].map(([k, l]) =>
    h("button", { class: mode === k ? "on" : "", onclick: (e) => { mode = k; store.set("tagMode", k); [...modeSwitch.children].forEach((b) => b.classList.toggle("on", b === e.target)); } }, l)));
  const input = h("input", { class: "input", placeholder: "Type a tag: LitRPG, попаданцы, harem…", autocomplete: "off" });
  const box = h("div", { class: "suggest hidden" });
  let opts = [], sel = -1;
  const pick = (t) => { if (!t) return; const list = new Set(filters[mode] || []); list.add(t.id); input.value = ""; box.classList.add("hidden"); updateFilter(mode, [...list]); };
  const show = debounce(async () => {
    const q = input.value.trim();
    try { opts = await api.get(`/api/tags?q=${encodeURIComponent(q)}&limit=25`); } catch { opts = []; }
    sel = -1;
    box.replaceChildren(...opts.map((t, i) => h("div", { class: "opt", onmousedown: (e) => { e.preventDefault(); pick(t); } },
      h("span", {}, tagLabel(t)), t.label_ru && tagLang !== "ru" ? h("span", { class: "ru" }, t.label_ru) : null, h("span", { class: "n" }, fmtNum(t.books)))));
    box.classList.toggle("hidden", !opts.length);
  }, 150);
  input.addEventListener("input", show);
  input.addEventListener("focus", show);
  input.addEventListener("blur", () => setTimeout(() => box.classList.add("hidden"), 150));
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault(); sel = Math.max(0, Math.min(opts.length - 1, sel + (e.key === "ArrowDown" ? 1 : -1)));
      [...box.children].forEach((c, i) => c.classList.toggle("sel", i === sel));
    } else if (e.key === "Enter") { e.preventDefault(); pick(opts[sel >= 0 ? sel : 0]); }
  });
  const selected = h("div", { class: "chips", style: { marginTop: "8px" } });
  const addChips = (key, cls, prefix) => (filters[key] || []).forEach((id) => {
    const c = h("span", { class: `chip ${cls}`, title: "Click to remove", onclick: () => toggleIn(key, id) }, prefix, h("span", { "data-tag": id }, id), h("span", { class: "x" }, "×"));
    selected.append(c);
  });
  addChips("tags", "inc", "+ "); addChips("any", "any", "≈ "); addChips("not", "exc", "− ");
  // replace ids with readable labels
  selected.querySelectorAll("[data-tag]").forEach(async (s) => {
    try { const t = await api.get(`/api/tags/${encodeURIComponent(s.dataset.tag)}`); s.textContent = tagLabel(t); } catch { /* keep id */ }
  });
  wrap.append(modeSwitch, input, box, selected);
  return wrap;
}

function renderToolbar() {
  const res = $("#results");
  const sortSel = h("select", { class: "input", style: { width: "auto" }, onchange: (e) => updateFilter("sort", e.target.value) },
    SORTS.filter(([k]) => k !== "relevance" || filters.q).map(([k, l]) => h("option", { value: k, selected: (filters.sort || (filters.q ? "relevance" : "popularity")) === k }, l)));
  const orderBtn = h("button", { class: "btn", title: "Reverse the order", onclick: () => updateFilter("order", filters.order === "asc" ? "" : "asc") }, filters.order === "asc" ? "↑" : "↓");
  const modeSeg = h("div", { class: "seg" },
    h("button", { class: viewMode === "grid" ? "on" : "", title: "Covers", onclick: () => { viewMode = "grid"; store.set("viewMode", "grid"); drawResults(true); modeSeg.children[0].classList.add("on"); modeSeg.children[1].classList.remove("on"); } }, "▦"),
    h("button", { class: viewMode === "list" ? "on" : "", title: "List", onclick: () => { viewMode = "list"; store.set("viewMode", "list"); drawResults(true); modeSeg.children[1].classList.add("on"); modeSeg.children[0].classList.remove("on"); } }, "☰"));
  const toolbar = h("div", { class: "toolbar" },
    h("button", { class: "btn filters-toggle", onclick: () => $("#filters").classList.toggle("open") }, "Filters"),
    h("div", { class: "count", id: "count" }, h("span", { class: "spinner", style: { display: "inline-block", verticalAlign: "middle" } })),
    sortSel, orderBtn, modeSeg,
    h("button", { class: "btn", title: "Check narration of the books shown that haven't been checked yet", onclick: analyseShown }, "Check narration"),
    h("button", { class: "btn", onclick: saveSearch }, "Save search"));
  res.replaceChildren(toolbar, activeFilters(), h("div", { id: "items" }), h("div", { class: "loadmore", id: "sentinel" }));
}

function activeFilters() {
  const parts = [];
  if (filters.q) parts.push(chip(`“${filters.q}” ×`, true, () => setFilters({ ...filters, q: "", sort: filters.sort === "relevance" ? "" : filters.sort })));
  const any = Object.entries(filters).some(([k, v]) => k !== "sort" && k !== "order" && (Array.isArray(v) ? v.length : v));
  if (any) parts.push(h("button", { class: "btn small ghost", onclick: () => setFilters({ sort: filters.sort || "" }) }, "Reset all filters"));
  return h("div", { class: "active-filters" }, parts);
}

async function loadResults(reset) {
  if (reset) { results.books = []; results.page = 0; results.done = false; results.token++; }
  if (results.loading || results.done) return;
  results.loading = true;
  const token = results.token;
  const params = { ...filters, page: results.page + 1, per_page: 48 };
  delete params.book;
  try {
    const data = await api.get("/api/books?" + toQuery(params));
    if (token !== results.token) return;
    results.page = data.page;
    results.total = data.total;
    results.capped = data.total_capped;
    results.books.push(...data.books);
    results.done = data.books.length < data.per_page;
    drawResults(reset);
  } catch (e) {
    $("#items").replaceChildren(h("div", { class: "empty" }, h("h2", {}, "Something went wrong"), h("p", {}, String(e.message || e))));
  } finally {
    if (token === results.token) results.loading = false;
  }
}

function drawResults(reset) {
  const count = $("#count");
  if (count) count.replaceChildren(results.capped ? "10,000+ books" : `${results.total.toLocaleString()} book${results.total === 1 ? "" : "s"}`,
    " ", h("span", { class: "muted" }, meta.totals.books ? `of ${Number(meta.totals.books).toLocaleString()} in your library` : ""));
  const items = $("#items");
  if (!items) return;
  if (!results.books.length) {
    const emptyLibrary = !meta.totals.books;
    items.replaceChildren(h("div", { class: "empty" },
      h("h2", {}, emptyLibrary ? "Your library is empty so far" : "No books match these filters"),
      emptyLibrary ? h("p", {}, "Open the Sites page and switch on the sites you read. Bookkeeper starts collecting books in the background; they appear here as they come in.") : h("p", {}, "Try removing a filter, or include books whose narration hasn't been checked yet."),
      emptyLibrary ? h("p", {}, h("a", { class: "btn primary", href: "#/sites" }, "Go to Sites")) : null));
  } else {
    const container = viewMode === "grid" ? h("div", { class: "grid" }) : h("div", { class: "list" });
    results.books.forEach((b) => container.append(viewMode === "grid" ? renderCard(b) : renderRow(b)));
    items.replaceChildren(container);
  }
  const s = $("#sentinel");
  if (s) s.replaceChildren(results.done ? (results.books.length ? h("span", { class: "faint" }, "That's everything.") : "") : h("span", { class: "spinner" }));
  observeSentinel();
}

let observer = null;
function observeSentinel() {
  if (observer) observer.disconnect();
  const s = $("#sentinel");
  if (!s || results.done) return;
  observer = new IntersectionObserver((entries) => { if (entries.some((e) => e.isIntersecting)) loadResults(false); }, { rootMargin: "600px" });
  observer.observe(s);
}

function povBadge(pov, source) {
  const p = pov || "none";
  const mark = source === "site" ? " ✓" : source === "user" ? " ✎" : source === "other-site" ? " ⇄" : "";
  const why = pov ? `${POV_LONG[p]} — ${POV_SOURCE[source] || ""}` : "Narration not checked yet";
  return h("span", { class: `pov ${p}`, title: why }, POV[p] + mark);
}
function coverEl(b) {
  const c = h("div", { class: "cover" });
  if (b.cover) {
    const img = h("img", { src: `/api/cover/${b.id}`, alt: "", loading: "lazy" });
    img.addEventListener("error", () => img.replaceWith(h("div", { class: "ph" }, b.title)));
    c.append(img);
  } else c.append(h("div", { class: "ph" }, b.title));
  return c;
}
function tagMini(t) {
  const derived = !t.sources.includes("site") && !t.sources.includes("user");
  return h("span", { class: `mini-tag ${derived ? "derived" : ""}`, title: derived ? `Added by Bookkeeper (${t.sources.map((s) => SRC[s] ? SRC[s][1] : s).join(", ")})` : "" }, tagLabel(t));
}
function statsLine(b) {
  return [b.words ? `${fmtNum(b.words)} words` : null, b.chapters ? `${b.chapters} ch.` : null, b.status && b.status !== "unknown" ? STATUS[b.status] : null,
    b.rating ? `★ ${b.rating.toFixed(1)}` : null, b.likes ? `♥ ${fmtNum(b.likes)}` : null].filter(Boolean);
}
function siteBadges(b) {
  return [h("span", { class: "site-badge" }, siteName(b.site)), ...(b.copies || []).map((c) => h("span", { class: "site-badge", title: "Also on this site" }, "+ " + siteName(c.site)))];
}
function renderCard(b) {
  const c = coverEl(b);
  c.append(h("div", { class: "badges" }, povBadge(b.pov, b.pov_source)));
  if (b.favorite) c.append(h("span", { class: "fav" }, "★"));
  return h("article", { class: "card", onclick: () => setFilters({ ...filters, book: b.id }, true) },
    c,
    h("div", { class: "body" },
      h("div", { class: "title", title: b.title }, b.title),
      h("div", { class: "author" }, (b.authors || []).join(", ") || "—"),
      h("div", { class: "tagrow" }, siteBadges(b), (b.tags || []).slice(0, 5).map(tagMini)),
      h("div", { class: "stats" }, statsLine(b).map((s) => h("span", {}, s)))));
}
function renderRow(b) {
  return h("article", { class: "row", onclick: () => setFilters({ ...filters, book: b.id }, true) },
    coverEl(b),
    h("div", {},
      h("div", { class: "title" }, b.title, b.favorite ? " ★" : ""),
      h("div", { class: "line" }, h("span", { class: "muted" }, (b.authors || []).join(", ")), povBadge(b.pov, b.pov_source), siteBadges(b),
        b.shelf ? h("span", { class: "pill" }, SHELVES[b.shelf] || b.shelf) : null),
      h("div", { class: "line" }, (b.tags || []).slice(0, 10).map(tagMini)),
      h("div", { class: "snippet" }, b.snippet || ""),
      h("div", { class: "line faint", style: { fontSize: "12px" } }, statsLine(b).join(" · "))));
}

async function analyseShown() {
  const ids = results.books.filter((b) => !b.pov).map((b) => b.id);
  if (!ids.length) { toast("Every book shown already has its narration checked"); return; }
  await api.post("/api/analyze", { ids });
  toast(`Queued ${ids.length} book${ids.length === 1 ? "" : "s"} for checking — results appear within a few minutes`);
}
async function saveSearch() {
  const name = prompt("Name this search (it will appear at the top of the filters):");
  if (!name) return;
  const { book, ...rest } = filters;
  await api.post("/api/searches", { name, query: toQuery(rest) });
  toast("Search saved"); renderFilters();
}

// ---------- book drawer ----------
let drawerBook = null, drawerTimer = null;
function closeDrawer(updateHash = true) {
  $("#drawer").classList.remove("open"); $("#scrim").classList.remove("open"); $("#drawer").setAttribute("aria-hidden", "true");
  clearInterval(drawerTimer); drawerBook = null;
  if (updateHash && parseHash().params.book) { const { book, ...rest } = filters; setFilters(rest, false); }
}
$("#scrim").addEventListener("click", () => closeDrawer());
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && drawerBook) closeDrawer(); });

async function openBook(id) {
  if (drawerBook === id && $("#drawer").classList.contains("open")) return;
  drawerBook = id;
  $("#drawer").classList.add("open"); $("#scrim").classList.add("open"); $("#drawer").setAttribute("aria-hidden", "false");
  $("#drawer-inner").replaceChildren(h("div", { class: "loadmore" }, h("span", { class: "spinner" })));
  await refreshBook(id);
}
async function refreshBook(id) {
  let d;
  try { d = await api.get(`/api/books/${id}`); } catch (e) { $("#drawer-inner").replaceChildren(h("p", {}, String(e))); return; }
  if (drawerBook !== id) return;
  renderBook(d);
  clearInterval(drawerTimer);
  if (d.queued || d.downloads.some((x) => x.state === "queued" || x.state === "running")) drawerTimer = setInterval(() => refreshBook(id), 2500);
}

function narrationBox(d) {
  const a = d.analysis;
  const box = h("div", { class: "narr" });
  box.append(h("div", { class: "big" }, povBadge(d.pov, d.pov_source),
    h("span", { class: "why" }, d.pov ? POV_SOURCE[d.pov_source] || "" : d.queued ? "Queued for checking…" : "Not checked yet.")));
  const facts = [];
  if (a && a.pov && !a.error) {
    facts.push(`Text check: ${POV_LONG[a.pov].toLowerCase()}${a.confidence ? ` (${Math.round(a.confidence * 100)}% sure)` : ""}, from ${a.chapters} chapter${a.chapters === 1 ? "" : "s"}, ${fmtNum(a.words)} words of narration.`);
    if (a.narrator) facts.push(`Narrator: ${a.narrator === "male" ? "male (♂)" : "female (♀)"}.`);
    if (a.tense) facts.push(`Tense: ${a.tense}.`);
    if (a.game_system) facts.push("Has game-style system messages.");
    if (a.details && a.details.note) facts.push(`Note: ${a.details.note}.`);
  } else if (a && a.error) facts.push(`Couldn't read the text: ${a.error}.`);
  if (facts.length) box.append(h("div", { class: "why", style: { marginTop: "8px" } }, facts.join(" ")));
  if (a && a.details && a.details.segments && a.details.segments.length) {
    box.append(h("div", { class: "segbar", title: "Each block is a piece of the opening chapters, coloured by how it is narrated" },
      a.details.segments.map((s) => h("span", { class: s.label, title: `Chapters ${s.chapters.join(", ")}: ${s.label} (I/me per 1000 words: ${s.i_per_1000}, he/she: ${s.he_she_per_1000})` }))));
    box.append(h("div", { class: "legend" }, h("span", {}, "■ green: 1st person"), h("span", {}, "■ grey: 3rd person"), h("span", {}, "■ purple: 2nd person")));
  }
  const setPov = async (p) => { await api.post(`/api/books/${d.id}/user`, { pov: p }); toast(p ? "Saved your correction" : "Correction removed"); refreshBook(d.id); results.token++; };
  box.append(h("div", { class: "correct" }, "Wrong? Set it yourself:",
    ["first", "third", "second", "mixed"].map((p) => h("button", { class: `btn small ${d.user_pov === p ? "primary" : ""}`, onclick: () => setPov(p) }, POV[p])),
    d.user_pov ? h("button", { class: "btn small ghost", onclick: () => setPov(null) }, "Undo") : null,
    h("button", { class: "btn small ghost", title: "Read the opening chapters again", onclick: async () => { await api.post("/api/analyze", { ids: [d.id], force: true }); toast("Queued for checking"); refreshBook(d.id); } }, "Check again")));
  return box;
}

function renderBook(d) {
  const shelfBtns = h("div", { class: "shelf" },
    Object.entries(SHELVES).map(([k, l]) => h("button", { class: `btn small ${d.shelf === k ? "primary" : ""}`, onclick: async () => { await api.post(`/api/books/${d.id}/user`, { shelf: d.shelf === k ? null : k }); refreshBook(d.id); } }, l)),
    h("button", { class: `btn small ${d.favorite ? "primary" : ""}`, onclick: async () => { await api.post(`/api/books/${d.id}/user`, { favorite: !d.favorite }); refreshBook(d.id); } }, d.favorite ? "★ Favourite" : "☆ Favourite"));

  const dl = (fmt) => async () => { await api.post("/api/downloads", { book_id: d.id, fmt }); toast(`${fmt.toUpperCase()} download started`); refreshBook(d.id); };
  const downloads = h("div", {},
    h("div", { class: "shelf" }, ["epub", "fb2", "txt"].map((f) => h("button", { class: "btn small", onclick: dl(f) }, `⬇ ${f.toUpperCase()}`))),
    d.downloads.length ? h("div", { style: { marginTop: "10px", display: "grid", gap: "6px" } }, d.downloads.slice(0, 4).map(downloadLine)) : null);

  const byCat = {};
  for (const t of d.tags) {
    if (t.category === "narration" && ["pov-first", "pov-third", "pov-second"].includes(t.id)) continue;
    (byCat[t.category || "other"] = byCat[t.category || "other"] || []).push(t);
  }
  const order = (meta.categories || Object.keys(CATS));
  const tagSections = order.filter((c) => byCat[c]).map((c) => h("div", { class: "tagcat" }, h("div", { class: "cat" }, CATS[c] || c),
    h("div", { class: "chips" }, byCat[c].map((t) => {
      const own = t.sources.includes("site") || t.sources.includes("user");
      const srcText = t.sources.map((s) => SRC[s] ? SRC[s][1] : s).join("; ") + (t.raw.length ? ` — on the site: “${t.raw.join("”, “")}”` : "");
      return h("span", { class: `chip ${own ? "" : "derived"}`, style: own ? {} : { borderStyle: "dashed" }, title: `${srcText}. Click to show books with this tag.`,
        onclick: () => setFilters({ ...filters, tags: [...new Set([...(filters.tags || []), t.id])] }) },
        tagLabel(t), h("span", { class: "tag-src" }, t.sources.map((s) => SRC[s] ? SRC[s][0] : s).join("+")));
    }))));

  const facts = [
    ["Site", siteName(d.site)], ["Status", STATUS[d.status] || "—"], ["Chapters", d.chapters ?? "—"], ["Length", d.words ? `${fmtNum(d.words)} words` : "—"],
    ["Rating", d.rating ? `${d.rating.toFixed(1)} / 10${d.votes ? ` (${fmtNum(d.votes)})` : ""}` : "—"], ["Likes", fmtNum(d.likes)], ["Views", fmtNum(d.views)],
    ["Access", ACCESS[d.access] || "—"], ["Language", LANGS[d.lang] || d.lang || "—"], ["Type", d.is_translation === 1 ? "Translation" : d.is_translation === 0 ? "Original" : "—"],
    ["Updated", fmtDate(d.updated_at)], ["Added to library", fmtDate(d.added_at)],
  ];
  if (d.extra && d.extra.series) facts.splice(1, 0, ["Series", d.extra.series]);

  const note = h("textarea", { class: "note", placeholder: "Your notes about this book…" });
  note.value = d.note || "";
  note.addEventListener("change", async () => { await api.post(`/api/books/${d.id}/user`, { note: note.value }); toast("Note saved"); });

  $("#drawer-inner").replaceChildren(
    h("button", { class: "icon-btn close", title: "Close (Esc)", onclick: () => closeDrawer() }, "✕"),
    h("div", { class: "dhead" }, coverEl(d),
      h("div", {},
        h("h2", {}, d.title),
        d.alt_titles.length ? h("div", { class: "alt" }, d.alt_titles.slice(0, 6).join(" · ")) : null,
        h("div", { class: "authors" }, d.authors.join(", ") || "Unknown author"),
        h("div", { class: "actions" },
          h("a", { class: "btn primary", href: d.url, target: "_blank", rel: "noopener" }, `Open on ${siteName(d.site)} ↗`),
          d.copies.map((c) => h("a", { class: "btn", href: c.url, target: "_blank", rel: "noopener", title: "The same book on another site" }, `${siteName(c.site)} ↗`))))),
    h("div", { class: "section" }, h("h3", {}, "Narration"), narrationBox(d)),
    h("div", { class: "section" }, h("h3", {}, "My shelves"), shelfBtns),
    h("div", { class: "section" }, h("h3", {}, "Download for your e-reader"), downloads,
      h("div", { class: "faint", style: { fontSize: "12px", marginTop: "6px" } }, "Downloads include the chapters the site lets you read: free ones, and bought ones if you're logged in.")),
    d.description ? h("div", { class: "section" }, h("h3", {}, "Description"), h("div", { class: "desc" }, d.description)) : null,
    h("div", { class: "section" }, h("h3", {}, "Tags"), tagSections.length ? tagSections : h("p", { class: "muted" }, "No tags yet."),
      h("div", { class: "legend" }, h("span", {}, "solid: written on the site"), h("span", {}, "dashed: added by Bookkeeper (rules, text, other copies)"))),
    h("div", { class: "section" }, h("h3", {}, "Details"), h("div", { class: "facts" }, facts.map(([k, v]) => h("div", { class: "fact" }, h("div", { class: "k" }, k), h("div", { class: "v" }, String(v)))))),
    d.recommendations.length ? h("div", { class: "section" }, h("h3", {}, "Recommended on forums"), h("ul", {}, d.recommendations.map((r) => h("li", {}, h("a", { href: r.post_url, target: "_blank" }, `${r.source}${r.at ? ", " + fmtDate(r.at) : ""}`))))) : null,
    h("div", { class: "section" }, h("h3", {}, "My notes"), note));
}

function downloadLine(x) {
  const pct = x.total ? Math.round((100 * x.progress) / x.total) : x.state === "done" ? 100 : 0;
  return h("div", { style: { display: "grid", gridTemplateColumns: "60px 1fr auto", gap: "10px", alignItems: "center", fontSize: "12.5px" } },
    h("b", {}, x.fmt.toUpperCase()),
    x.state === "done" ? h("span", { class: "muted" }, x.file) : x.state === "error" ? h("span", { style: { color: "var(--danger)" } }, x.error) :
      h("div", {}, h("div", { class: "progress" }, h("span", { style: { width: `${pct}%` } })), h("span", { class: "faint" }, x.state === "queued" ? "waiting…" : `${x.progress} / ${x.total || "?"} chapters`)),
    x.state === "done" ? h("a", { class: "btn small primary", href: `/api/downloads/${x.id}/file` }, "Save file") : h("span"));
}

// ---------- sites page ----------
async function renderSites() {
  const app = $("#app");
  app.replaceChildren(h("div", { class: "page" }, h("h1", {}, "Sites"),
    h("p", { class: "lead" }, "Switch on the sites you want in your library. Bookkeeper reads each one slowly in the background (by default about one page every 1–2 seconds, so you don't get banned): first the catalog, then each book's details, then the opening chapters to check the narration. You can keep using the app while it works."),
    h("div", { class: "sites", id: "sitecards" }), h("div", { class: "planned", id: "planned" })));
  await drawSites(true);
  pollTimer = setInterval(() => drawSites(false), 3000);
}
let openSettings = new Set();
async function drawSites(first) {
  let data;
  try { data = await api.get("/api/sites"); } catch { return; }
  siteCounts = Object.fromEntries(data.sites.map((s) => [s.id, s.counts]));
  const cards = $("#sitecards");
  if (!cards) return;
  if (document.activeElement && cards.contains(document.activeElement) && !first) return; // don't redraw under the cursor
  cards.replaceChildren(...data.sites.map(siteCard));
  if (first) {
    $("#planned").replaceChildren(
      h("h2", { style: { fontSize: "17px", margin: "0 0 4px" } }, "Coming next"),
      h("p", { class: "muted", style: { margin: "0 0 10px" } }, "These sites from your list don't have a connector yet."),
      h("table", {}, h("tr", {}, h("th", {}, "Site"), h("th", {}, "Status")),
        data.planned.map((p) => h("tr", {}, h("td", {}, h("a", { href: p.home, target: "_blank" }, p.name)), h("td", { class: "muted" }, p.reason)))),
      h("div", { style: { marginTop: "18px", display: "flex", gap: "8px", flexWrap: "wrap" } },
        h("button", { class: "btn", onclick: async () => { await api.post("/api/maintenance/match"); toast("Looking for the same books on different sites…"); } }, "Find the same books across sites now"),
        h("button", { class: "btn", onclick: async () => { await api.post("/api/maintenance/retag"); toast("Re-applying tag rules in the background…"); } }, "Re-apply my tag rules")));
  }
}
function siteCard(s) {
  const c = s.counts || {};
  const status = !s.enabled ? "paused" : s.status;
  const label = { running: "Collecting", idle: s.enabled ? "Waiting" : "Off", paused: "Off", blocked: "Blocked", error: "Problem", done: "Up to date" }[status] || status;
  const settings = s.settings || {};
  const det = h("details", { class: "settings", open: openSettings.has(s.id), ontoggle: (e) => e.target.open ? openSettings.add(s.id) : openSettings.delete(s.id) },
    h("summary", {}, "Settings"),
    h("div", { class: "body" },
      h("div", { class: "field" }, h("label", {}, `Pause between requests, seconds (default ${s.default_interval})`),
        h("input", { class: "input", type: "number", min: 0.5, max: 30, step: 0.5, value: settings.min_interval || s.default_interval,
          onchange: async (e) => { await api.post(`/api/sites/${s.id}`, { min_interval: +e.target.value }); toast("Saved"); } })),
      h("label", { class: "check" }, h("input", { type: "checkbox", checked: settings.analyze !== false, onchange: async (e) => { await api.post(`/api/sites/${s.id}`, { analyze: e.target.checked }); toast("Saved"); } }), "Check narration of each book (reads its opening chapters)"),
      h("label", { class: "check" }, h("input", { type: "checkbox", checked: !!settings.include_adult, onchange: async (e) => { await api.post(`/api/sites/${s.id}`, { include_adult: e.target.checked }); toast("Saved"); } }), "Include 18+ books"),
      Object.entries(s.extra_settings || {}).map(([key, def]) => h("div", { class: "field" }, h("label", {}, def.label),
        h("textarea", { class: "note", style: { minHeight: "54px" }, onchange: async (e) => { await api.post(`/api/sites/${s.id}`, { [key]: e.target.value }); toast("Saved — collecting with the new settings"); } },
          settings[key] ?? def.default)))));
  const live = s.live || {};
  const busy = s.enabled && live.activity && !["idle", "starting"].includes(live.activity);
  return h("div", { class: "sitecard" },
    h("div", { class: "top" },
      h("div", {}, h("h2", {}, h("a", { href: s.home, target: "_blank", style: { color: "inherit" } }, s.name)),
        h("span", { class: `pill ${status}` }, label)),
      h("label", { class: "switch", title: s.enabled ? "Stop collecting" : "Start collecting" },
        h("input", { type: "checkbox", checked: s.enabled, onchange: async (e) => { await api.post(`/api/sites/${s.id}`, { enabled: e.target.checked }); drawSites(false); } }), h("span"))),
    h("div", { class: "numbers" },
      h("div", {}, h("b", {}, fmtNum(c.books || 0)), h("span", {}, "books")),
      h("div", {}, h("b", {}, fmtNum(c.detailed || 0)), h("span", {}, "with details")),
      h("div", {}, h("b", {}, fmtNum(c.analyzed || 0)), h("span", {}, "text checked")),
      h("div", {}, h("b", {}, fmtNum(c.first_person || 0)), h("span", {}, "1st person"))),
    h("div", { class: "activity" }, h("span", { class: `dot ${busy ? "on" : ""}` }), s.enabled ? (live.activity || "starting") : "Not collecting",
      s.full_done ? h("span", { class: "faint" }, " · whole catalog listed") : null),
    s.status_msg ? h("div", { class: "errbox" }, s.status_msg, " ", h("button", { class: "btn small", onclick: async () => { await api.post(`/api/sites/${s.id}/retry`); toast("Trying again"); } }, "Try again")) : null,
    live.browser_error ? h("div", { class: "errbox" }, `Narration checks are off for this site: ${live.browser_error}`) : null,
    h("div", { class: "note" }, s.note),
    det);
}

// ---------- downloads page ----------
async function renderDownloads() {
  const app = $("#app");
  app.replaceChildren(h("div", { class: "page" }, h("h1", {}, "Downloads"),
    h("p", { class: "lead" }, "Books you downloaded. The files are also saved in ", h("span", { class: "mono" }, meta.downloads_dir || "data/downloads"), ", so you can copy them to your e-reader straight from that folder."),
    h("div", { id: "dl" })));
  const draw = async () => {
    let list = [];
    try { list = await api.get("/api/downloads"); } catch { return; }
    const el = $("#dl"); if (!el) return;
    if (!list.length) { el.replaceChildren(h("div", { class: "empty" }, h("h2", {}, "Nothing downloaded yet"), h("p", {}, "Open a book and press EPUB, FB2 or TXT."))); return; }
    el.replaceChildren(h("table", { class: "dl-table" },
      h("tr", {}, h("th", {}, "Book"), h("th", {}, "Format"), h("th", {}, "Progress"), h("th", {}, "")),
      list.map((x) => h("tr", {},
        h("td", {}, h("a", { href: `#/library?book=${x.book_id}` }, x.title), h("div", { class: "faint" }, siteName(x.site), x.options && x.options.note ? ` · ${x.options.note}` : "")),
        h("td", {}, x.fmt.toUpperCase()),
        h("td", { style: { minWidth: "220px" } }, downloadLine(x)),
        h("td", {}, h("button", { class: "btn small ghost danger", onclick: async () => { await api.del(`/api/downloads/${x.id}`); draw(); } }, "Delete"))))));
  };
  await draw();
  pollTimer = setInterval(draw, 2500);
}

// ---------- help page ----------
function renderHelp() {
  $("#app").replaceChildren(h("div", { class: "page" }, h("h1", {}, "How Bookkeeper works"),
    h("p", { class: "lead" }, "Bookkeeper collects books from the sites you read, merges their tags into one shared list, adds the tags authors forgot, and works out how each book is narrated."),
    h("div", { class: "help-grid" },
      h("div", { class: "help-card" }, h("h2", {}, "How narration is detected"),
        h("p", {}, "For each book Bookkeeper reads the opening chapters, throws away dialogue, quoted thoughts, game messages and author notes, then counts “I / я” against “he / she / он / она” in the narration that's left, chapter by chapter."),
        h("p", {}, "On a test of 41 books with known narration it got 40 right and said “unsure” about the last one. In Russian and Ukrainian it also tells a male narrator from a female one by verb endings (я пошёл / я пошла)."),
        h("p", {}, "If a site's own tag says “от первого лица”, that wins over the text check. Your own correction wins over everything.")),
      h("div", { class: "help-card" }, h("h2", {}, "Where tags come from"),
        h("ul", {}, h("li", {}, h("b", {}, "site"), ": written on the book's page."), h("li", {}, h("b", {}, "rule"), ": implied by another tag (LitRPG → RPG elements)."),
          h("li", {}, h("b", {}, "text"), ": found in the chapters (narration, narrator, game messages)."), h("li", {}, h("b", {}, "copy"), ": from the same book on another site."), h("li", {}, h("b", {}, "you"), ": added by you."))),
      h("div", { class: "help-card" }, h("h2", {}, "Your own tag rules"),
        h("p", {}, "Open ", h("span", { class: "mono" }, meta.user_tags_file || "data/my_tags.toml"), " in Notepad. You can map site labels to tags and add rules like “harem → romance”. Then press “Re-apply my tag rules” on the Sites page.")),
      h("div", { class: "help-card" }, h("h2", {}, "Your data"),
        h("p", {}, "Everything lives in ", h("span", { class: "mono" }, meta.data_dir || "data"), ": the library database, downloads, logs and the browser profile used for Author.Today. Copy that folder to back it up.")),
      h("div", { class: "help-card" }, h("h2", {}, "Being polite to the sites"),
        h("p", {}, "Each site gets its own slow, steady pace. If a site shows a bot check or blocks requests, Bookkeeper stops working on that site and tells you on the Sites page instead of retrying over and over.")),
      h("div", { class: "help-card" }, h("h2", {}, "Paid chapters"),
        h("p", {}, "Bookkeeper only reads what the site lets you read: free chapters, plus bought ones if you are logged in. The narration check only needs the first few chapters, which are almost always free.")))));
}

// ---------- start ----------
async function boot() {
  try {
    meta = await api.get("/api/meta");
    const s = await api.get("/api/sites");
    siteCounts = Object.fromEntries(s.sites.map((x) => [x.id, x.counts]));
  } catch (e) { console.error(e); }
  if (!location.hash) location.hash = "#/library";
  route();
  setInterval(async () => { try { meta = { ...meta, ...(await api.get("/api/meta")) }; } catch { /* offline */ } }, 15000);
}
boot();
