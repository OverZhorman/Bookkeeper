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
// The server's own words when something fails ({"detail": …} from the API), not the raw response.
async function failure(r) {
  let text = await r.text();
  try { const j = JSON.parse(text); text = j.detail || j.error || text; } catch { /* not JSON */ }
  return new Error(typeof text === "string" ? text : JSON.stringify(text));
}
const api = {
  async get(url) { const r = await fetch(url); if (!r.ok) throw await failure(r); return r.json(); },
  async send(method, url, body) {
    const r = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
    if (!r.ok) throw await failure(r);
    return r.json();
  },
  post(url, body) { return this.send("POST", url, body || {}); },
  del(url) { return this.send("DELETE", url); },
};
const store = {
  get(k, d) { try { const v = localStorage.getItem("bk:" + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("bk:" + k, JSON.stringify(v)); } catch { /* private mode */ } },
};
// Replace an element's children, skipping the empty (null / false) ones.
const fill = (el, ...kids) => el.replaceChildren(...kids.flat(Infinity).filter((k) => k !== null && k !== undefined && k !== false));
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
const CATS = { narration: "Narration", genre: "Genres", theme: "Themes & tropes", protagonist: "Protagonist", setting: "Setting", orientation: "Orientation", relationship: "Relationships", content: "Content", format: "Format", origin: "Origin", demographic: "Audience", fandom: "Fandoms", fanfic: "Fanfiction", other: "Other tags (as written on the site)" };
const AGES = [
  ["G", "G", "For everyone."],
  ["PG-13", "PG-13", "Teens and up (12+ / 13+): some violence or romance, nothing explicit."],
  ["R", "R", "16+: violence, sex scenes without explicit detail."],
  ["NC-17", "NC-17", "18+: explicit sex or violence."],
  ["NC-21", "NC-21", "21+: extreme content."],
  ["unknown", "Not rated", "The site gives no age rating (books marked 18+ count as NC-17)."],
];
const UPDATED = [["7", "a week"], ["30", "a month"], ["91", "3 months"], ["182", "half a year"], ["365", "a year"], ["730", "2 years"]];
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
const tagLabel = (t) => (tagLang === "ru" && t.label_ru) ? t.label_ru : (tagLang === "uk" && (t.label_uk || t.label_ru)) ? (t.label_uk || t.label_ru) : t.label;

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
const LIST_KEYS = ["pov", "narrator", "sites", "lang", "status", "access", "pov_source", "orient", "age"];
// A tag id as it goes into the Tags field (quoted when it has spaces or symbols the field reads as operators).
const qtok = (id) => /[\s()|&,"«»]|^[-!?−]|\*$/.test(id) ? `"${id}"` : id;
function fromLists(must, anyof, exclude) {
  const parts = must.map(qtok);
  if (anyof.length) parts.push(anyof.length > 1 ? "(" + anyof.map(qtok).join(" | ") + ")" : qtok(anyof[0]));
  parts.push(...exclude.map((t) => "-" + qtok(t)));
  return parts.join(" ");
}
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
  // Searches saved before 0.4 kept tags in three lists (must have / any of / exclude): read them as a query.
  const list = (v) => (v ? String(v).split(",").filter(Boolean) : []);
  if (!f.tq && (f.tags || f.any || f.not)) f.tq = fromLists(list(f.tags), list(f.any), list(f.not));
  delete f.tags; delete f.any; delete f.not;
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
  const tab = ["tag", "tags", "labels"].includes(view) ? "tags" : view;  // tag pages and label fixing live under Tags
  document.querySelectorAll("#tabs a").forEach((a) => a.classList.toggle("active", a.dataset.view === tab));
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
    else if (view === "tag" && params.id) renderTag(params.id);
    else if (view === "tags") renderAllTags();
    else if (view === "labels") renderLabels();
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

  groups.push(fgroup("Tags", queryBox("tq", { placeholder: "Romance −Harem, (Isekai | Reincarnation)…" }),
    h("span", { class: "gactions" }, h("a", { href: "#/tags", title: "Every tag, with what it means and how tags relate" }, "all tags"),
      filters.tq ? h("button", { onclick: () => updateFilter("tq", "") }, "clear") : null)));

  groups.push(fgroup("Fanfiction", h("div", {},
    h("div", { class: "chips" }, [["", "Both", "Original works and fanfiction"], ["original", "Original works", "Books that aren't fanfiction"], ["fanfic", "Fanfiction", "Fanfiction of any fandom"]].map(([k, l, tip]) =>
      chip(l, (filters.kind || "") === k, () => updateFilter("kind", k), "", tip))),
    h("div", { class: "field" }, h("label", {}, "Fandoms — works the same way as tags"),
      queryBox("fq", { fandom: true, placeholder: "Harry Potter | Naruto, −Genshin…" }))),
    filters.kind || filters.fq ? h("button", { onclick: () => setFilters({ ...filters, kind: "", fq: "" }) }, "clear") : null));

  groups.push(fgroup("Orientation", h("div", { class: "chips" }, (meta.orientations || []).map((o) =>
    withHover(chip(tagLabel(o), filters.orient.includes(o.id), () => toggleIn("orient", o.id)), o.id))),
    filters.orient.length ? h("button", { onclick: () => updateFilter("orient", []) }, "clear") : null));

  groups.push(fgroup("Age rating", h("div", { class: "chips" }, AGES.map(([k, l, tip]) =>
    chip(l, filters.age.includes(k), () => toggleIn("age", k), "", tip))),
    filters.age.length ? h("button", { onclick: () => updateFilter("age", []) }, "clear") : null));

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

  const anyTime = !filters.updated_within && !filters.stale;
  groups.push(fgroup("Updated", h("div", {},
    h("div", { class: "chips" }, chip("Any time", anyTime, () => setFilters({ ...filters, updated_within: "", stale: "" }))),
    h("div", { class: "field" }, h("label", {}, "Updated within the last"),
      h("div", { class: "chips" }, UPDATED.filter(([k]) => +k <= 365).map(([k, v]) =>
        chip(v, filters.updated_within === k, () => setFilters({ ...filters, updated_within: filters.updated_within === k ? "" : k, stale: "" }))))),
    h("div", { class: "field" }, h("label", {}, "Not updated for at least"),
      h("div", { class: "chips" }, UPDATED.map(([k, v]) =>
        chip(v, filters.stale === k, () => setFilters({ ...filters, stale: filters.stale === k ? "" : k, updated_within: "" }), "",
          `Books whose last update was more than ${v} ago (books without a known date are left out)`)))))));

  groups.push(fgroup("My shelves", h("div", { class: "chips" },
    [["", "Everything"], ["unread", "Not read yet"], ["want", "Want to read"], ["reading", "Reading"], ["read", "Read"], ["favorite", "★ Favourites"], ["dropped", "Dropped"], ["hidden", "Hidden"]].map(([k, v]) =>
      chip(v, (filters.shelf || "") === k, () => updateFilter("shelf", k))))));

  groups.push(fgroup("More", h("div", {},
    h("label", { class: "check" }, h("input", { type: "checkbox", checked: (filters.dedupe ?? "1") !== "0", onchange: (e) => updateFilter("dedupe", e.target.checked ? "" : "0") }), "Show each book once (merge copies on different sites)"),
    h("label", { class: "check", title: "Saved for next time. 18+ books are collected either way." }, h("input", { type: "checkbox", checked: !!meta.hide_adult, onchange: async (e) => { meta.hide_adult = e.target.checked; await api.post("/api/settings", { hide_adult: e.target.checked }); setFilters({ ...filters, adult: "" }); renderLibrary(); } }), "Hide 18+ books"),
    h("label", { class: "check" }, h("input", { type: "checkbox", checked: filters.adult === "only", onchange: (e) => updateFilter("adult", e.target.checked ? "only" : "") }), "Only 18+ books"),
    h("label", { class: "check" }, h("input", { type: "checkbox", checked: filters.recommended === "1", onchange: (e) => updateFilter("recommended", e.target.checked ? "1" : "") }), "Only books recommended on forums"),
    h("div", { class: "field" }, h("label", {}, "Tag names in"),
      h("div", { class: "chips" }, [["en", "English"], ["ru", "Русский"], ["uk", "Українська"]].map(([k, l]) =>
        chip(l, tagLang === k, () => { tagLang = k; store.set("tagLang", k); renderLibrary(); })))))));

  el.replaceChildren(...groups);
}

// ---------- the Tags and Fandoms fields ----------
const OPS = [
  ["not", "−", "without", "Without: −Harem (or !Harem, NOT Harem) leaves out books with the tag. On a word you already typed, it switches it."],
  ["or", "|", "or", "Either: Isekai | Reincarnation shows books with at least one of them (OR / ИЛИ work too)."],
  ["and", "&", "and", "Both: Romance & Magic shows books with both. A space or a comma means the same."],
  ["group", "( )", "group", "Brackets group things: (Isekai | Reincarnation) −Harem. With text selected, puts it in brackets."],
  ["maybe", "?", "possibly", "Possibly: ?System also counts books whose opening chapters suggest the tag. Plain tags count only certain ones."],
  ["quote", "“ ”", "exact", "A name with spaces in quotes: \"slow burn\". Names Bookkeeper knows work without quotes too."],
  ["prefix", "*", "starts with", "Starts with: fandom* matches every tag whose name starts with “fandom”."],
];
const QUERY_HELP = [
  ["Romance", "books with the tag — any name or alias works: Романтика, Любовь…"],
  ["−Romance   !Romance", "books without it (also NOT Romance, НЕ Romance)"],
  ["Romance Magic", "both (also Romance & Magic, Romance, Magic)"],
  ["Isekai | Reincarnation", "either one (also OR, ИЛИ, АБО)"],
  ["(Isekai | Reincarnation) −Harem", "brackets group things"],
  ["?System", "has the tag, or possibly has it (found in the opening chapters)"],
  ["−?Harem", "not even possibly"],
  ["\"slow burn\"", "a name with spaces; names Bookkeeper knows work without quotes too"],
  ["fandom*", "every tag whose name starts with “fandom”"],
];
let refocus = null;  // the field to focus again after the library redraws (after Enter)
let openSuggest = null;  // repositions the open suggestion list when the filters scroll

// Suggestion lists float over the page (wider than a narrow field), under the field or above it when there's no room.
function placeList(box, input) {
  const r = input.getBoundingClientRect();
  const w = Math.min(Math.max(r.width, 420), innerWidth - 16);
  const below = innerHeight - r.bottom - 12;
  Object.assign(box.style, { width: `${w}px`, left: `${Math.max(8, Math.min(r.left, innerWidth - w - 8))}px` });
  if (below < 240 && r.top > below) Object.assign(box.style, { top: "", bottom: `${innerHeight - r.top + 4}px`, maxHeight: `${Math.min(380, r.top - 12)}px` });
  else Object.assign(box.style, { bottom: "", top: `${r.bottom + 4}px`, maxHeight: `${Math.min(380, below)}px` });
}

function addToQuery(t, how = "") {
  const key = t.category === "fandom" ? "fq" : "tq";
  const cur = (filters[key] || "").trim();
  const tok = how + qtok(t.id);
  setFilters({ ...filters, [key]: cur ? `${cur} ${tok}` : tok });
}

function otherName(t) {
  const shown = tagLabel(t);
  const alt = tagLang === "en" ? (t.label_ru || t.label_uk) : t.label;
  return alt && alt !== shown ? h("span", { class: "ru" }, alt) : null;
}

function queryBox(key, { fandom = false, placeholder = "" } = {}) {
  const input = h("input", { class: "input", placeholder, autocomplete: "off", spellcheck: "false", "aria-label": fandom ? "Fandoms" : "Tags" });
  input.value = filters[key] || "";
  const box = h("div", { class: "suggest hidden" });
  const reads = h("div", { class: "reads" });
  const help = h("div", { class: "qhelp hidden" },
    h("table", {}, QUERY_HELP.map(([ex, what]) => h("tr", {}, h("td", {}, h("code", {}, ex)), h("td", {}, what)))),
    h("div", { class: "faint", style: { marginTop: "4px" } }, "Tab completes a name, Enter searches. Possible tags (dotted on the book page) only count with ?."));
  let opts = [], sel = -1, seg = null, caret = null, blurTimer = null, quiet = false;

  const apply = (again) => {
    const v = input.value.trim();
    box.classList.add("hidden");
    if (v === (filters[key] || "")) return;
    filters = { ...filters, [key]: v };  // first, so a click elsewhere that took the focus sees the new value
    refocus = again ? key : null;
    setFilters(filters);
  };
  const range = () => (document.activeElement === input ? [input.selectionStart, input.selectionEnd] : caret || [input.value.length, input.value.length]);

  // What is being typed at the caret: the last one to three words since a bracket, | or &, or the inside of "…".
  const segment = () => {
    const end = range()[0];
    const before = input.value.slice(0, end);
    if ((before.match(/"/g) || []).length % 2) {
      const start = before.lastIndexOf('"');
      return { start, end, text: before.slice(start + 1), quoted: true, words: [] };
    }
    if (!before.trim()) return { start: end, end, text: "", quoted: false, words: [] };
    if (/\s$/.test(before)) return null;
    const cut = Math.max(...'()|&,"«»'.split("").map((c) => before.lastIndexOf(c))) + 1;
    const words = [...before.slice(cut).matchAll(/\S+/g)].map((m) => ({ text: m[0], at: cut + m.index }));
    const take = [];
    for (let i = words.length - 1; i >= 0 && take.length < 3; i--) {
      const lead = words[i].text.match(/^[-!?−]*/)[0].length;  // −Harem, ?System: the name starts after the mark
      take.unshift({ text: words[i].text.slice(lead), at: words[i].at + lead });
      if (lead) break;
    }
    const named = take.filter((w) => w.text);
    if (!named.length || named[named.length - 1].text.endsWith("*")) return null;
    return { start: named[0].at, end, text: named.map((w) => w.text).join(" "), quoted: false, words: named };
  };

  const place = () => placeList(box, input);
  const draw = () => {
    openSuggest = place;
    place();
    box.replaceChildren(...opts.map((o, i) => h("div", { class: `opt ${i === sel ? "sel" : ""}`, onmousedown: (e) => { e.preventDefault(); insert(o); } },
      h("div", { class: "l1" }, h("span", { class: "name" }, tagLabel(o)), otherName(o),
        o.matched && o.matched.toLowerCase() !== tagLabel(o).toLowerCase() ? h("span", { class: "alias" }, `≈ ${o.matched}`) : null,
        h("span", { class: "n" }, fmtNum(o.books || 0))),
      o.description ? h("div", { class: "d" }, o.description) : null)),
    h("div", { class: "foot" }, "Tab or click: insert · ↑ ↓: choose · Enter: search"));
    box.classList.toggle("hidden", !opts.length);
  };

  const suggest = debounce(async () => {
    seg = segment();
    if (!seg) { box.classList.add("hidden"); return; }
    const asked = input.value;
    const q = new URLSearchParams({ text: seg.text, lang: tagLang, fandom: fandom ? 1 : 0, quoted: seg.quoted ? 1 : 0, limit: 12 });
    try { opts = await api.get("/api/tags/complete?" + q); } catch { opts = []; }
    if (asked !== input.value || document.activeElement !== input) return;
    sel = -1;
    draw();
  }, 120);

  const explain = debounce(async () => {
    const v = input.value.trim();
    if (!v) {
      reads.replaceChildren(h("span", { class: "faint" }, fandom ? "Type a fandom, or several: Naruto | Bleach" : "Type a tag. Space = and, | = or, − = without"));
      return;
    }
    let r;
    try { r = await api.get("/api/tagquery?" + new URLSearchParams({ q: v, lang: tagLang, fandom: fandom ? 1 : 0 })); } catch { return; }
    if (input.value.trim() !== v) return;
    fill(reads,
      h("div", {}, h("span", { class: "faint" }, "Reads as: "), r.text || "—"),
      r.unknown.length ? h("div", { class: "warn" }, `No ${fandom ? "fandom" : "tag"} called ${r.unknown.map((u) => `“${u}”`).join(", ")} yet, so ${r.unknown.length === 1 ? "it matches" : "they match"} nothing. Pick a name from the suggestions (Tab).`) : null,
      v !== (filters[key] || "") ? h("div", { class: "hint" }, "Press Enter to search") : null);
  }, 200);

  const insert = (o) => {
    if (!o || !seg) return;
    const v = input.value;
    let start = seg.start, end = seg.end;
    if (seg.quoted && v[end] === '"') end++;
    if (!seg.quoted && seg.words.length && o.replace_words) start = seg.words[Math.max(0, seg.words.length - o.replace_words)].at;
    const rest = v.slice(end).replace(/^\s+/, "");
    input.value = v.slice(0, start) + o.insert + " " + rest;
    const pos = start + o.insert.length + 1;
    input.focus();
    input.setSelectionRange(pos, pos);
    box.classList.add("hidden");
    explain();
  };

  // The word (or "quoted name") around a position, with its − ! ? marks.
  const wordAt = (v, pos) => {
    let s, e;
    const quotes = (v.slice(0, pos).match(/"/g) || []).length;
    if (quotes % 2) { s = v.lastIndexOf('"', pos - 1); e = v.indexOf('"', pos); e = e < 0 ? v.length : e + 1; }
    else if (v[pos - 1] === '"') { s = v.lastIndexOf('"', pos - 2); e = pos; }
    else {
      s = pos; e = pos;
      while (s > 0 && !/[\s()|&,"]/.test(v[s - 1])) s--;
      while (e < v.length && !/[\s()|&,"]/.test(v[e])) e++;
      return [s, e];
    }
    while (s > 0 && /[-!?−]/.test(v[s - 1])) s--;
    return [Math.max(0, s), e];
  };
  const op = (kind) => {
    const v = input.value;
    const [a, b] = range();
    let next = v, pos = a;
    const gap = (i) => (i > 0 && !/[\s(]/.test(v[i - 1]) ? " " : "");
    if (kind === "not" || kind === "maybe" || kind === "prefix") {
      const [s, e] = a === b ? wordAt(v, a) : [a, a];
      if (s < e) {  // on a word: switch its mark
        const word = v.slice(s, e);
        const lead = word.match(/^[-!?−]*/)[0];
        let name = word.slice(lead.length), neg = /[-!−]/.test(lead), maybe = lead.includes("?");
        if (kind === "not") neg = !neg;
        else if (kind === "maybe") maybe = !maybe;
        else if (!name.startsWith('"')) name = name.endsWith("*") ? name.slice(0, -1) : name + "*";
        const nw = (neg ? "-" : "") + (maybe ? "?" : "") + name;
        next = v.slice(0, s) + nw + v.slice(e);
        pos = s + nw.length;
      } else {  // between words: put the mark down for the next one
        const ins = (kind === "prefix" ? "" : gap(a)) + { not: "-", maybe: "?", prefix: "*" }[kind];
        next = v.slice(0, a) + ins + v.slice(b);
        pos = a + ins.length;
      }
    } else if (kind === "or" || kind === "and") {
      const left = v.slice(0, a).replace(/\s+$/, ""), right = v.slice(b).replace(/^\s+/, "");
      const sym = !left ? (kind === "or" ? "| " : "& ") : (kind === "or" ? " | " : " & ");
      next = left + sym + right;
      pos = left.length + sym.length;
    } else {
      const [o, c] = kind === "group" ? ["(", ")"] : ['"', '"'];
      const pre = a === b ? gap(a) : "";
      next = v.slice(0, a) + pre + o + v.slice(a, b) + c + v.slice(b);
      pos = a === b ? a + pre.length + 1 : b + 2;
    }
    input.value = next;
    input.focus();
    input.setSelectionRange(pos, pos);
    explain();
    suggest();
  };
  // Buttons act on mouse-down so the field keeps its focus and caret (and on Enter/Space from the keyboard).
  const press = (fn) => ({ onmousedown: (e) => { e.preventDefault(); fn(); }, onclick: (e) => { if (e.detail === 0) fn(); } });
  const ops = h("div", { class: "ops" },
    OPS.map(([kind, sym, word, tip]) => h("button", { type: "button", title: tip, ...press(() => op(kind)) }, h("b", {}, sym), " ", word)),
    h("button", { type: "button", class: "ghost", title: "Empty the field and search again", ...press(() => { input.value = ""; apply(false); explain(); }) }, "clear"),
    h("button", { type: "button", class: "ghost", title: "How to write a tag search", ...press(() => help.classList.toggle("hidden")) }, "help"));

  const remember = () => { caret = [input.selectionStart, input.selectionEnd]; };
  input.addEventListener("input", () => { suggest(); explain(); });
  input.addEventListener("focus", () => { clearTimeout(blurTimer); if (!quiet) suggest(); quiet = false; });
  ["keyup", "click", "select"].forEach((ev) => input.addEventListener(ev, remember));
  input.addEventListener("click", suggest);
  input.addEventListener("blur", () => {
    remember();
    box.classList.add("hidden");
    // Leaving the field searches too, unless the click that took the focus does that itself.
    const v = input.value.trim();
    if (v !== (filters[key] || "")) {
      filters = { ...filters, [key]: v };
      blurTimer = setTimeout(() => {
        const { view, params } = parseHash();
        if (view === "library" && (params[key] || "") !== v) setFilters(filters);
      }, 220);
    }
  });
  input.addEventListener("keydown", (e) => {
    const open = !box.classList.contains("hidden") && opts.length > 0;
    if (open && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault();
      const d = e.key === "ArrowDown" ? 1 : -1;
      sel = sel < 0 ? (d > 0 ? 0 : opts.length - 1) : (sel + d + opts.length) % opts.length;
      draw();
    } else if (open && e.key === "Tab" && !e.shiftKey) { e.preventDefault(); insert(opts[Math.max(0, sel)]); }
    else if (e.key === "Enter") { e.preventDefault(); if (open && sel >= 0) insert(opts[sel]); else apply(true); }
    else if (e.key === "Escape" && open) { e.stopPropagation(); box.classList.add("hidden"); }
  });
  explain();
  if (refocus === key) {
    refocus = null;
    requestAnimationFrame(() => { quiet = true; input.focus(); input.setSelectionRange(input.value.length, input.value.length); });
  }
  return h("div", { class: "qbox" }, h("div", { class: "tagbox" }, input, box), ops, reads, help);
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
  if (filters.tq) parts.push(chip(`Tags: ${filters.tq} ×`, true, () => updateFilter("tq", ""), "", "Remove the tag search"));
  if (filters.fq) parts.push(chip(`Fandoms: ${filters.fq} ×`, true, () => updateFilter("fq", ""), "", "Remove the fandom search"));
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
  const why = t.maybe ? "Possible tag: found in the opening chapters, not certain."
    : derived ? `Added by Bookkeeper (${t.sources.map((s) => SRC[s] ? SRC[s][1] : s).join(", ")}).` : "";
  return withHover(h("span", { class: `mini-tag ${t.maybe ? "maybe" : derived ? "derived" : ""}` }, tagLabel(t)), t.id, why);
}
const ageBadge = (b) => b.adult ? h("span", { class: "adult-badge", title: `Age rating ${b.age_rating || "NC-17"}` }, b.age_rating === "NC-21" ? "21+" : "18+") : null;
function statsLine(b) {
  return [b.words ? `${fmtNum(b.words)} words` : null, b.chapters ? `${b.chapters} ch.` : null, b.status && b.status !== "unknown" ? STATUS[b.status] : null,
    b.rating ? `★ ${b.rating.toFixed(1)}` : null, b.likes ? `♥ ${fmtNum(b.likes)}` : null].filter(Boolean);
}
function siteBadges(b) {
  return [h("span", { class: "site-badge" }, siteName(b.site)), ...(b.copies || []).map((c) => h("span", { class: "site-badge", title: "Also on this site" }, "+ " + siteName(c.site)))];
}
function renderCard(b) {
  const c = coverEl(b);
  c.append(h("div", { class: "badges" }, povBadge(b.pov, b.pov_source), ageBadge(b)));
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
      h("div", { class: "line" }, h("span", { class: "muted" }, (b.authors || []).join(", ")), povBadge(b.pov, b.pov_source), ageBadge(b), siteBadges(b),
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
  if (d.queued || d.handoff || d.downloads.some((x) => x.state === "queued" || x.state === "running")) drawerTimer = setInterval(() => refreshBook(id), 2500);
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
    d.has_text === false
      ? h("div", { class: "faint", style: { fontSize: "12.5px" } }, `${siteName(d.site)} protects its chapter text, so Bookkeeper can't make a file from it. Read it on the site, or use a browser extension below.`)
      : h("div", { class: "shelf" }, ["epub", "fb2", "txt"].map((f) => h("button", { class: "btn small", onclick: dl(f) }, `⬇ ${f.toUpperCase()}`))),
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
      return withHover(h("span", { class: `chip ${own ? "" : "derived"}`, onclick: (e) => addToQuery(t, e.shiftKey ? "-" : "") },
        tagLabel(t), h("span", { class: "tag-src" }, t.sources.map((s) => SRC[s] ? SRC[s][0] : s).join("+"))), t.id, `${srcText}. Click: books with this tag · Shift+click: books without it.`);
    }))));
  const possible = d.possible_tags || [];
  if (possible.length) {
    tagSections.push(h("div", { class: "tagcat" }, h("div", { class: "cat" }, "Possible tags — found in the opening chapters, not certain"),
      h("div", { class: "chips" }, possible.map((t) => withHover(h("span", { class: "chip maybe", onclick: (e) => addToQuery(t, e.shiftKey ? "-?" : "?") },
        tagLabel(t), h("span", { class: "tag-src" }, `${Math.round((t.score || 0) * 100)}%`)), t.id,
        `${t.why ? `Mentioned ${t.why} in the opening chapters; ` : ""}the % is how strongly. Tag searches count it only with ?${qtok(t.id)}. Click: books that possibly have it.`)))));
  }

  const facts = [
    ["Site", siteName(d.site)], ["Status", STATUS[d.status] || "—"], ["Chapters", d.chapters ?? "—"], ["Length", d.words ? `${fmtNum(d.words)} words` : "—"],
    ["Rating", d.rating ? `${d.rating.toFixed(1)} / 10${d.votes ? ` (${fmtNum(d.votes)})` : ""}` : "—"], ["Likes", fmtNum(d.likes)], ["Views", fmtNum(d.views)],
    ["Access", ACCESS[d.access] || "—"], ["Language", LANGS[d.lang] || d.lang || "—"], ["Type", d.is_translation === 1 ? "Translation" : d.is_translation === 0 ? "Original" : "—"],
    ["Age rating", d.age_rating || "Not rated"], ["Updated", fmtDate(d.updated_at)], ["Added to library", fmtDate(d.added_at)],
  ];
  if (d.extra && d.extra.series) facts.splice(1, 0, ["Series", d.extra.series]);

  const note = h("textarea", { class: "note", placeholder: "Your notes about this book…" });
  note.value = d.note || "";
  note.addEventListener("change", async () => { await api.post(`/api/books/${d.id}/user`, { note: note.value }); toast("Note saved"); });

  fill($("#drawer-inner"),
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
      h("div", { class: "faint", style: { fontSize: "12px", marginTop: "6px" } }, d.logged_in
        ? "You're logged in on this site: downloads include every chapter your account can read, including ones you bought."
        : d.can_login ? "Downloads include the free chapters. Log in on the Sites page to include chapters you bought."
        : "Downloads include the chapters the site shows to every visitor."),
      handoffBox(d)),
    d.description ? h("div", { class: "section" }, h("h3", {}, "Description"), h("div", { class: "desc" }, d.description)) : null,
    h("div", { class: "section" }, h("h3", {}, "Tags"), tagSections.length ? tagSections : h("p", { class: "muted" }, "No tags yet."),
      h("div", { class: "legend" }, h("span", {}, "solid: written on the site"), h("span", {}, "dashed: added by Bookkeeper (rules, text, other copies)"),
        h("span", {}, "dotted: possible"), h("span", {}, "click a tag to search with it, Shift+click to leave it out"))),
    h("div", { class: "section" }, h("h3", {}, "Details"), h("div", { class: "facts" }, facts.map(([k, v]) => h("div", { class: "fact" }, h("div", { class: "k" }, k), h("div", { class: "v" }, String(v)))))),
    d.recommendations.length ? h("div", { class: "section" }, h("h3", {}, "Recommended on forums"), h("ul", {}, d.recommendations.map((r) => h("li", {}, h("a", { href: r.post_url, target: "_blank" }, `${r.source}${r.at ? ", " + fmtDate(r.at) : ""}`))))) : null,
    h("div", { class: "section" }, h("h3", {}, "My notes"), note));
}

function handoffBox(d) {
  const ext = (d.extension_downloads || []).join(", ");
  const box = h("div", { class: "handoff" });
  if (d.handoff) {
    const mins = Math.ceil(d.handoff.seconds_left / 60);
    box.append(h("div", { class: "activity" }, h("span", { class: "dot on" }),
      `Opened in ${d.handoff.browser}. Download the book there; Bookkeeper picks up the file from `, h("span", { class: "mono" }, d.handoff.folder), ` (waiting ${mins} more min).`),
      h("button", { class: "btn small ghost", onclick: async () => { await api.del(`/api/books/${d.id}/handoff`); refreshBook(d.id); } }, "Stop waiting"));
  } else {
    box.append(h("button", { class: "btn small", title: "Opens this book in your own Waterfox, where your extensions are",
      onclick: async () => {
        try { await api.post(`/api/books/${d.id}/handoff`); toast("Opened in your browser — download the book there"); }
        catch (e) { toast(String(e.message || e)); }
        refreshBook(d.id);
      } }, "Open in my Waterfox to download with an extension"),
      h("div", { class: "faint", style: { fontSize: "12px", marginTop: "4px" } },
        ext ? `${ext} can download this site's books (also chapters Bookkeeper can't save). ` : "For sites where a browser extension (for example ExLoader) can download books. ",
        "The file you save there appears here and on the Downloads page."));
  }
  return box;
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
    h("div", { id: "browserbox" }),
    h("div", { class: "sites", id: "sitecards" }), h("div", { class: "planned", id: "planned" })));
  drawBrowserBox();
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
      h("p", { class: "muted", style: { margin: "0 0 10px", maxWidth: "820px" } },
        "These sites from your list don't have a connector yet. Several of them block the server Bookkeeper was built on, but they probably work from your computer. ",
        h("b", {}, "Test from this computer"), " visits a few pages of the site slowly (home, catalog, one book, one chapter) and saves what it sees into a ZIP file. Send that ZIP to finish the site's connector. If a page shows an “are you human?” check, a normal Waterfox window (or Edge, if Waterfox is not installed) opens so you can complete it yourself."),
      h("table", {}, h("tr", {}, h("th", {}, "Site"), h("th", {}, "Status"), h("th", {}, "Test")),
        data.planned.map((p) => h("tr", {}, h("td", {}, h("a", { href: p.home, target: "_blank" }, p.name)), h("td", { class: "muted" }, p.reason),
          h("td", { id: `test-${p.id}`, style: { minWidth: "260px" } }, testCell(p.id))))),
      h("div", { style: { marginTop: "18px", display: "flex", gap: "8px", flexWrap: "wrap" } },
        h("button", { class: "btn", onclick: async () => { await api.post("/api/maintenance/match"); toast("Looking for the same books on different sites…"); } }, "Find the same books across sites now"),
        h("button", { class: "btn", onclick: async () => { await api.post("/api/maintenance/retag"); toast("Re-applying tag rules in the background…"); } }, "Re-apply my tag rules"),
        h("a", { class: "btn", href: "#/labels", title: "Say what the most common unrecognized site labels mean" }, "Fix site labels")));
  }
}
function testCell(siteId) {
  const cell = h("div", {}, h("button", { class: "btn small", onclick: () => runTest(siteId) }, "Test from this computer"));
  refreshTest(siteId, cell);
  return cell;
}
async function runTest(siteId) {
  await api.post(`/api/diagnose/${siteId}`, { browser: true });
  toast("Test started — it takes a minute or two");
  const cell = $(`#test-${siteId}`);
  const poll = async () => { const st = await refreshTest(siteId, cell && cell.firstChild); if (st === "running") setTimeout(poll, 2500); };
  poll();
}
async function refreshTest(siteId, cell) {
  let st;
  try { st = await api.get(`/api/diagnose/${siteId}`); } catch { return; }
  if (!cell || !st || st.state === "none") return st && st.state;
  const parts = [];
  if (st.state === "running") parts.push(h("div", { class: "activity" }, h("span", { class: "dot on" }), st.summary));
  else {
    parts.push(h("button", { class: "btn small", onclick: () => runTest(siteId) }, "Test again"));
    if (st.zip) parts.push(" ", h("a", { class: "btn small primary", href: `/api/diagnose/${siteId}/zip` }, "Download the test ZIP"));
    parts.push(h("div", { class: "faint", style: { fontSize: "12px", marginTop: "4px" } }, st.summary));
  }
  cell.replaceChildren(...parts);
  return st.state;
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
      h("label", { class: "check" }, h("input", { type: "checkbox", checked: !!settings.include_adult, onchange: async (e) => { await api.post(`/api/sites/${s.id}`, { include_adult: e.target.checked }); toast("Saved"); } }), "Collect 18+ books (you can hide them in the library)"),
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
    accountBox(s),
    det);
}

let openAccount = new Set();
function accountBox(s) {
  const a = s.account;
  if (!a) return null;
  const act = (action, msg) => async () => {
    try { await api.post(`/api/sites/${s.id}/account`, { action }); toast(msg); } catch (e) { toast(String(e.message || e)); }
    drawSites(false);
  };
  const who = a.logged_in ? `Logged in${a.user ? ` as ${a.user}` : ""}${a.how === "waterfox" ? " (copied from your Waterfox)" : a.how === "auto" ? " (automatically)" : ""}` : "Not logged in";
  const busy = a.state === "working";
  const buttons = h("div", { class: "shelf", style: { marginTop: "6px" } },
    h("button", { class: "btn small primary", disabled: busy, title: "Opens the site's login page in a browser window. Log in there as usual.", onclick: act("login", "A browser window is opening — log in there") }, a.logged_in ? "Log in again…" : "Log in…"),
    a.user_waterfox ? h("button", { class: "btn small", disabled: busy, title: "If you're already logged in to this site in your own Waterfox, Bookkeeper copies that login", onclick: act("import", "Copying your Waterfox login…") }, "Use my Waterfox login") : null,
    a.logged_in ? h("button", { class: "btn small ghost", disabled: busy, onclick: act("check", "Checking the login…") }, "Check") : null,
    a.logged_in ? h("button", { class: "btn small ghost danger", disabled: busy, onclick: act("logout", "Logged out") }, "Log out") : null);
  const parts = [h("div", {}, h("b", {}, "Account: "), who), a.why ? h("div", { class: "faint", style: { fontSize: "12px" } }, `Logging in gives you: ${a.why}`) : null, buttons];
  if (a.message) parts.push(h("div", { class: ["failed", "needed"].includes(a.state) ? "errbox" : "activity" }, busy ? h("span", { class: "dot on" }) : null, a.message));
  if (s.login_autofill && a.can_save_password) {
    const login = h("input", { class: "input", placeholder: "Login, e-mail or phone", value: a.saved_login || "", autocomplete: "off" });
    const pwd = h("input", { class: "input", type: "password", placeholder: a.has_password ? "Saved (leave empty to keep it)" : "Password", autocomplete: "new-password" });
    const auto = h("input", { type: "checkbox", checked: a.auto_pref !== false });
    parts.push(h("details", { class: "settings", open: openAccount.has(s.id), ontoggle: (e) => e.target.open ? openAccount.add(s.id) : openAccount.delete(s.id) },
      h("summary", {}, !a.has_password ? "Log in automatically with a saved password"
        : a.auto_failed ? "Automatic login: paused (it failed last time)" : "Automatic login: on"),
      a.auto_failed && a.has_password ? h("div", { class: "faint", style: { fontSize: "12px" } },
        "The hidden window couldn't log in (often a bot check). Bookkeeper won't keep trying: log in yourself with “Log in…” or “Use my Waterfox login”. Saving the password again lets it try once more.") : null,
      h("div", { class: "body" },
        h("div", { class: "faint", style: { fontSize: "12px" } }, "Bookkeeper logs in by itself in a hidden window, and again whenever the login runs out. The password is encrypted with your Windows account and stays on this computer."),
        h("div", { class: "row2" }, login, pwd),
        h("label", { class: "check" }, auto, "Log in again by itself when the login runs out"),
        h("div", { class: "shelf" },
          h("button", { class: "btn small primary", onclick: async () => {
            if (!login.value.trim()) { toast("Enter your login first"); return; }
            try { await api.post(`/api/sites/${s.id}/credentials`, { login: login.value, password: pwd.value, auto: auto.checked }); toast("Saved — logging in…"); }
            catch (e) { toast(String(e.message || e)); }
            pwd.value = ""; drawSites(false);
          } }, "Save and log in"),
          a.saved_login ? h("button", { class: "btn small ghost danger", onclick: async () => { await api.post(`/api/sites/${s.id}/credentials`, { forget: true }); toast("Saved login and password removed"); drawSites(false); } }, "Forget saved password") : null))));
  } else if (!s.login_autofill) {
    parts.push(h("div", { class: "faint", style: { fontSize: "12px", marginTop: "4px" } }, "Bookkeeper can't fill in this site's login form for you, so log in yourself once with “Log in…” (or copy your Waterfox login). Bookkeeper keeps the session."));
  }
  return h("div", { class: "account" }, parts);
}

async function drawBrowserBox() {
  const el = $("#browserbox");
  if (!el) return;
  let st;
  try { st = await api.get("/api/settings"); } catch { return; }
  const save = async (key, value) => { await api.post("/api/settings", { [key]: value }); toast("Saved"); drawBrowserBox(); };
  const d = st.detected || {};
  el.replaceChildren(h("details", { class: "settings browserbox", open: store.get("browserBoxOpen", false), ontoggle: (e) => store.set("browserBoxOpen", e.target.open) },
    h("summary", {}, `Browser: ${d.engine}`, d.waterfox ? "" : " (Waterfox not found)"),
    h("div", { class: "body" },
      h("div", { class: "field" }, h("label", {}, "Browser for logins and site tests"),
        h("select", { class: "input", onchange: (e) => save("browser", e.target.value) },
          [["auto", "Waterfox when installed, otherwise Edge"], ["waterfox", "Waterfox (or Firefox)"], ["edge", "Microsoft Edge"]].map(([v, l]) => h("option", { value: v, selected: (st.browser || "auto") === v }, l)))),
      h("div", { class: "field" }, h("label", {}, "Waterfox program (leave empty to find it by itself)"),
        h("input", { class: "input", placeholder: d.waterfox || String.raw`C:\Program Files\Waterfox\waterfox.exe`, value: st.waterfox_path || "", onchange: (e) => save("waterfox_path", e.target.value) })),
      h("div", { class: "field" }, h("label", {}, "Folder your Waterfox saves downloads to (for books downloaded with an extension)"),
        h("input", { class: "input", placeholder: d.downloads_dir || "", value: st.browser_downloads_dir || "", onchange: (e) => save("browser_downloads_dir", e.target.value) })),
      h("div", { class: "faint", style: { fontSize: "12px" } }, "Logins and site tests use their own Waterfox profile in Bookkeeper's data folder; your normal Waterfox profile isn't changed. Author.Today chapters are read through Microsoft Edge."))));
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
      h("div", { class: "help-card" }, h("h2", {}, "Searching by tags"),
        h("p", {}, "Type into the Tags field in the library filters. Suggestions appear as you type, in any language; Tab puts one in, Enter searches. The buttons under the field add the operators, and resting the mouse on one explains it. The line under the field says how your search reads."),
        h("table", { class: "syntax" }, QUERY_HELP.map(([ex, what]) => h("tr", {}, h("td", {}, h("code", {}, ex)), h("td", {}, what)))),
        h("p", {}, "The Fandoms field works the same way, but every name in it is a fandom.")),
      h("div", { class: "help-card" }, h("h2", {}, "Tag pages"),
        h("p", {}, "Rest the mouse on any tag for a short description. ", h("b", {}, "About this tag"), " (or ", h("a", { href: "#/tags" }, "All tags"), ") opens its page: its names in English, Russian and Ukrainian, aliases, ",
          h("b", {}, "parent tags"), " (broader tags every book with it also gets), ", h("b", {}, "child tags"), " (narrower tags that can't appear without it, numbered 1, 2, 2.1…), ",
          h("b", {}, "related tags"), " (tags that usually appear with it in your library) and ", h("b", {}, "anti-tags"), " (tags that contradict it, plus common tags that almost never appear with it).")),
      h("div", { class: "help-card" }, h("h2", {}, "Possible tags"),
        h("p", {}, "While reading a book's opening chapters for the narration, Bookkeeper also counts words that point to a tag: cultivation terms, system messages, dragons, school life and so on. Tags that come up often enough are added as ", h("b", {}, "possible"), " (dotted on the book page, with how strongly they showed up)."),
        h("p", {}, "Plain tag searches ignore them; write ", h("code", {}, "?System"), " to include them, or ", h("code", {}, "−?Harem"), " to leave out even possible ones. Books checked before version 0.4 are read again slowly in the background, when nothing else is waiting.")),
      h("div", { class: "help-card" }, h("h2", {}, "Fanfiction, orientation and age rating"),
        h("p", {}, "These filters work like Ficbook's. ", h("b", {}, "Orientation"), " uses the tags Het, Slash, Femslash, Gen, Mixed and Other (from Ficbook and other sites). ", h("b", {}, "Age rating"),
          " uses the site's own rating as G / PG-13 / R / NC-17 / NC-21 (16+ counts as R, 18+ as NC-17, 21+ as NC-21); books marked 18+ without a rating count as NC-17.")),
      h("div", { class: "help-card" }, h("h2", {}, "Editing tags"),
        h("p", {}, "Open ", h("a", { href: "#/tags" }, "Tags"), " in the top bar, click a tag, then ", h("b", {}, "✎ Edit tag"),
          ". There you can change its names in the three languages, its category and description, add or remove aliases, parent tags, child tags and anti-tags. Every change is saved at once and applies to every book; ",
          h("b", {}, "Undo all my changes"), " puts one of Bookkeeper's own tags back."),
        h("p", {}, h("b", {}, "+ New tag"), " on the Tags page makes a tag of your own; on an unrecognized label's page, ", h("b", {}, "Make it a shared tag"),
          " turns that label into one. Your changes are saved in ", h("span", { class: "mono" }, meta.user_tags_file || "data/my_tags.toml"), ".")),
      h("div", { class: "help-card" }, h("h2", {}, "Fixing site labels"),
        h("p", {}, "Sites write tags their own way, and some labels aren't one of Bookkeeper's shared tags (Wattpad hashtags, character names, series names). ",
          h("a", { href: "#/labels" }, "Fix site labels"), " lists them, most common first, with suggestions. Say once what a label means and every book with it follows, including books that arrive later. ",
          h("b", {}, "Hide"), " removes junk labels; ", h("b", {}, "Leave as is"), " takes a label off the list; ", h("b", {}, "Undo"), " brings anything back."),
        h("p", {}, h("b", {}, "✨ Fix with an AI chat"), " lets Gemini, ChatGPT or another chat do the reading, a batch at a time, on your own subscription: copy the request, paste it into the chat, paste the reply back, check it and apply it. A whole import can be undone."),
        h("p", {}, "When Bookkeeper maps a label to the wrong tag, press ✎ next to it under “Written on the sites as” on the tag's page. Fixes are saved in the [fixes] table of ",
          h("span", { class: "mono" }, meta.user_tags_file || "data/my_tags.toml"), ".")),
      h("div", { class: "help-card" }, h("h2", {}, "Your own tag rules"),
        h("p", {}, "Open ", h("span", { class: "mono" }, meta.user_tags_file || "data/my_tags.toml"), " in Notepad. You can map site labels to tags and add rules like “harem → romance”. Then press “Re-apply my tag rules” on the Sites page.")),
      h("div", { class: "help-card" }, h("h2", {}, "Your data"),
        h("p", {}, "Everything lives in ", h("span", { class: "mono" }, meta.data_dir || "data"), ": the library database, downloads, logs, browser profiles and your saved logins (encrypted, in accounts). Copy that folder to back it up.")),
      h("div", { class: "help-card" }, h("h2", {}, "Being polite to the sites"),
        h("p", {}, "Each site gets its own slow, steady pace. If a site shows a bot check or blocks requests, Bookkeeper stops working on that site and tells you on the Sites page instead of retrying over and over.")),
      h("div", { class: "help-card" }, h("h2", {}, "Logging in"),
        h("p", {}, "On the Sites page, sites with an account box can be logged in to. ", h("b", {}, "Log in…"), " opens the site's login page in a Waterfox window: log in as usual (captchas and e-mail codes work). ",
          h("b", {}, "Use my Waterfox login"), " copies the login from your own Waterfox if you're already logged in there."),
        h("p", {}, "On Author.Today, Rulate and Ficbook you can also save your login and password: Bookkeeper then logs in by itself, and again whenever the login runs out. The password is encrypted with your Windows account."),
        h("p", {}, "Logged in, Bookkeeper sees what your account sees: 18+ books and the chapters you bought, which downloads then include.")),
      h("div", { class: "help-card" }, h("h2", {}, "Downloading with a browser extension"),
        h("p", {}, "Some sites don't let you download even what you bought, but extensions such as ExLoader can. Open a book and press ", h("b", {}, "Open in my Waterfox"), ": the book opens in your normal Waterfox, where your extensions are. Download it with the extension, and Bookkeeper picks up the file from your downloads folder and lists it under the book.")),
      h("div", { class: "help-card" }, h("h2", {}, "18+ books"),
        h("p", {}, "18+ and 21+ books are collected like any other. To keep them out of sight, tick ", h("b", {}, "Hide 18+ books"), " in the library filters (under More). Some sites only show them to logged-in readers.")))));
}

// ---------- tag hover cards ----------
const tagCache = new Map();
function tagBrief(id) {
  if (!tagCache.has(id)) tagCache.set(id, api.get(`/api/tag?id=${encodeURIComponent(id)}`).catch(() => null));
  return tagCache.get(id);
}
const tagHref = (id) => `#/tag?id=${encodeURIComponent(id)}`;
const hcard = h("div", { class: "hcard hidden", role: "tooltip" });
document.body.append(hcard);
let hoverTimer = null, hideTimer = null, hoverEl = null;
hcard.addEventListener("mouseenter", () => clearTimeout(hideTimer));
hcard.addEventListener("mouseleave", () => hideHover());
document.addEventListener("scroll", (e) => {
  if (e.target === hcard) return;
  hideHover(0);
  if (openSuggest && !(e.target instanceof Element && e.target.classList.contains("suggest"))) openSuggest();
}, true);
function hideHover(delay = 200) {
  clearTimeout(hoverTimer); clearTimeout(hideTimer);
  hideTimer = setTimeout(() => { hcard.classList.add("hidden"); hoverEl = null; }, delay);
}
// A short description of the tag when the mouse rests on `el`, with a link to the tag's page.
function withHover(el, id, extra) {
  el.addEventListener("mouseenter", () => {
    clearTimeout(hideTimer); clearTimeout(hoverTimer);
    hoverTimer = setTimeout(() => { hoverEl = el; showHover(el, id, extra); }, 450);
  });
  el.addEventListener("mouseleave", () => hideHover());
  return el;
}
async function showHover(el, id, extra) {
  const t = await tagBrief(id);
  if (!t || hoverEl !== el || !el.isConnected) return;
  const shown = tagLabel(t);
  const names = [t.label, t.label_ru, t.label_uk].filter((n, i, all) => n && n !== shown && all.indexOf(n) === i);
  fill(hcard,
    h("div", { class: "h1" }, h("b", {}, shown), h("span", { class: "cat" }, CATS[t.category] || t.category || "")),
    names.length ? h("div", { class: "names" }, names.join(" · ")) : null,
    t.description ? h("div", { class: "desc" }, t.description)
      : !t.known && t.category !== "fandom" ? h("div", { class: "desc faint" }, "A label as written on the site (not one of Bookkeeper's shared tags).") : null,
    t.aliases && t.aliases.length ? h("div", {}, h("span", { class: "k" }, "Also called: "), t.aliases.slice(0, 6).join(", ")) : null,
    t.parents && t.parents.length ? h("div", {}, h("span", { class: "k" }, "Always also: "), t.parents.map(tagLabel).join(", ")) : null,
    extra ? h("div", { class: "faint" }, extra) : null,
    h("div", { class: "faint" }, `${fmtNum(t.books || 0)} book${t.books === 1 ? "" : "s"}`, t.possible ? ` · ${fmtNum(t.possible)} more possibly` : "",
      t.children ? ` · ${t.children} narrower tag${t.children === 1 ? "" : "s"}` : ""),
    h("div", { class: "acts" },
      h("a", { class: "btn small", href: tagHref(id), onclick: () => hideHover(0) }, !t.known && t.category === "other" ? "Fix this label →" : "About this tag →"),
      h("button", { class: "btn small", title: "Show only books with this tag", onclick: () => { hideHover(0); addToQuery(t, ""); } }, "+ Add"),
      h("button", { class: "btn small", title: "Leave out books with this tag", onclick: () => { hideHover(0); addToQuery(t, "-"); } }, "− Exclude")));
  hcard.classList.remove("hidden");
  const r = el.getBoundingClientRect(), w = hcard.offsetWidth, ht = hcard.offsetHeight;
  const left = Math.max(8, Math.min(r.left, innerWidth - w - 8));
  const top = r.bottom + 6 + ht > innerHeight - 8 ? Math.max(8, r.top - ht - 6) : r.bottom + 6;
  hcard.style.left = `${left}px`; hcard.style.top = `${top}px`;
}

// ---------- tag pages ----------
const tagLink = (x) => withHover(h("a", { href: tagHref(x.id) }, tagLabel(x)), x.id);
const countOf = (n) => h("span", { class: "n" }, fmtNum(n || 0));
function numbered(items, render, cls = "") {
  if (!items || !items.length) return h("p", { class: "faint" }, "—");
  return h("ol", { class: `nlist ${cls}` }, items.map((x, i) => h("li", {}, h("span", { class: "num" }, `${i + 1})`), render(x))));
}
// Child tags as 1), 2), 2.1), 2.1.1)… — each one under the most specific tag it belongs to.
function treeList(nodes, prefix = "") {
  return h("ol", { class: "nlist" }, nodes.map((n, i) => {
    const num = prefix ? `${prefix}.${i + 1}` : String(i + 1);
    return h("li", {}, h("span", { class: "num" }, `${num})`), tagLink(n), countOf(n.books), n.children.length ? treeList(n.children, num) : null);
  }));
}

// Names, category and description of a tag (editing one, or making a new one).
function tagForm(v, opts = {}) {
  const b = opts.builtin || {};
  const field = (caption, el, hint) => h("label", { class: "field" }, h("span", {}, caption, hint ? h("span", { class: "faint" }, ` ${hint}`) : null), el);
  const input = (k, ph) => { const el = h("input", { class: "input", placeholder: b[k] || ph }); el.value = v[k] || ""; return el; };
  const en = input("label", "English name"), ru = input("label_ru", "Русское название"), uk = input("label_uk", "Українська назва");
  const cats = (meta.categories || Object.keys(CATS)).filter((c) => c !== "other" || v.category === "other");
  const cat = h("select", { class: "input" }, cats.map((c) => h("option", { value: c, selected: c === (v.category || "theme") }, CATS[c] || c)));
  const desc = h("textarea", { class: "note", placeholder: b.description || "What the tag means, in a sentence or two" });
  desc.value = v.description || "";
  const status = h("span", { class: "faint" });
  const save = async () => {
    fill(status, h("span", { class: "spinner tiny" }), " Saving…");
    const ok = await opts.onSave({ label: en.value, label_ru: ru.value, label_uk: uk.value, category: cat.value, description: desc.value });
    if (!ok) fill(status);
  };
  return h("div", { class: "tagform" },
    h("div", { class: "row3" }, field("English", en), field("Русский", ru), field("Українська", uk)),
    field("Category", cat),
    field("Description", desc, opts.builtin ? "(leave a field empty for Bookkeeper's own)" : ""),
    h("div", { class: "shelf" }, h("button", { class: "btn small primary", onclick: save }, opts.saveText || "Save"), opts.extra || null, status));
}

async function renderTag(id) {
  const app = $("#app");
  const editing = parseHash().params.edit === "1";
  const keepScroll = renderTag.keepScroll;
  renderTag.keepScroll = null;
  if (keepScroll == null) app.replaceChildren(h("div", { class: "page" }, h("div", { class: "loadmore" }, h("span", { class: "spinner" }))));
  let t;
  try { t = await api.get(`/api/tag?id=${encodeURIComponent(id)}&full=1`); }
  catch (e) { app.replaceChildren(h("div", { class: "page" }, h("h1", {}, "Couldn't open this tag"), h("p", {}, String(e.message || e)))); return; }
  if (parseHash().params.id !== id) return;
  const name = tagLabel(t);
  const key = t.category === "fandom" ? "fq" : "tq";
  const show = (q) => { location.hash = "#/library?" + toQuery({ [key]: q }); };
  const sec = (title, sub, body) => h("section", { class: "tsec" }, h("h2", {}, title, sub ? h("span", { class: "sub" }, ` — ${sub}`) : null), body);
  // Every change is saved at once; then the page shows the tag again, where you were.
  const redo = async (fn, done) => {
    try { await fn(); } catch (e) { toast(String(e.message || e)); return false; }
    tagCache.clear();
    if (done) toast(done);
    renderTag.keepScroll = scrollY;
    await renderTag(id);
    return true;
  };
  const link = (kind, other, on) => redo(() => api.post("/api/tag/link", { id: t.id, kind, other, on }));
  const linkEditor = (items, kind, placeholder) => h("div", {},
    items.length ? h("div", { class: "chips" }, items.map((x) => h("span", { class: "chip static" }, tagLink(x),
      h("button", { class: "edit", title: "Remove this link", onclick: () => link(kind, x.id, false) }, "×"))))
      : h("p", { class: "faint" }, "—"),
    h("div", { class: "addrow" }, tagPicker((o) => link(kind, o.id, true), placeholder)));
  const aliasInput = h("input", { class: "input small", placeholder: "+ another name, as a site writes it…" });
  const addAlias = () => {
    const text = aliasInput.value.trim();
    if (text) redo(() => api.post("/api/tag/alias", { id: t.id, alias: text, on: true }), `“${text}” now means ${name}, for every book`);
  };
  aliasInput.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); addAlias(); } });

  const shareForm = h("div", {});
  const makeShared = () => shareForm.replaceChildren(h("div", { class: "editbox" },
    h("p", { class: "faint", style: { margin: "0 0 8px" } }, `“${t.label}” becomes a shared tag: give it names in the other languages, a category and a description. Its books keep it, and other spellings of it join it.`),
    tagForm({ [/[а-яёіїєґ]/i.test(t.label) ? "label_ru" : "label"]: t.label, category: "theme" }, {
      saveText: "Make it a shared tag",
      onSave: async (v) => {
        try { await api.post("/api/tag/new", { ...v, from_label: t.label }); } catch (e) { toast(String(e.message || e)); return false; }
        tagCache.clear();
        toast(`“${t.label}” is a shared tag now`);
        location.hash = tagHref(t.id) + "&edit=1";
        return true;
      } })));

  const view = [
    h("div", { class: "crumbs" }, h("a", { href: "#/tags" }, "All tags"), " › ", CATS[t.category] || t.category || ""),
    h("div", { class: "titlerow" }, h("h1", {}, name),
      t.editable ? h("a", { class: `btn small ${editing ? "primary" : ""}`, href: tagHref(t.id) + (editing ? "" : "&edit=1"),
        title: editing ? "Back to reading" : "Change its names, description, aliases, parent and child tags, anti-tags" }, editing ? "✓ Done editing" : "✎ Edit tag") : null,
      t.editable ? h("a", { class: "btn small", href: "#/tags?" + toQuery({ ai: t.id }),
        title: "Let Gemini, ChatGPT or another AI chat sort this tag's aliases into child tags, add aliases and fix its names, description and links" }, "✨ Improve with an AI chat") : null),
    h("div", { class: "names" }, [["English", t.label], ["Русский", t.label_ru], ["Українська", t.label_uk]].filter(([, v]) => v).map(([k, v]) =>
      h("span", {}, h("span", { class: "faint" }, `${k}: `), v))),
    t.description ? h("p", { class: "lead" }, t.description)
      : !t.known && t.category !== "fandom" ? h("p", { class: "lead" }, "A label as written on the site. It isn't one of Bookkeeper's shared tags, so it has no translations or family. Say below what it means, and every book with it follows.") : null,
    h("div", { class: "stats" }, `${fmtNum(t.books || 0)} book${t.books === 1 ? "" : "s"} in your library`,
      t.possible ? ` · ${fmtNum(t.possible)} more possibly (found in their opening chapters)` : ""),
    h("div", { class: "actions" },
      h("button", { class: "btn primary", onclick: () => show(qtok(t.id)) }, "Show books with it"),
      h("button", { class: "btn", onclick: () => show("-" + qtok(t.id)) }, "Show books without it"),
      t.possible ? h("button", { class: "btn", title: "Books with the tag, plus books that possibly have it", onclick: () => show("?" + qtok(t.id)) }, "Include possible ones") : null,
      h("button", { class: "btn ghost", title: "Add it to the search you already have in the library", onclick: () => addToQuery(t, "") }, "Add to my search")),
  ];
  if (t.fixable || t.fix) {
    view.push(h("section", { class: "tsec fixbox" }, h("h2", {}, t.fix ? "Fixed label" : "Fix this label",
      h("span", { class: "sub" }, " — what it means, for every book with it")),
      fixerFor({ label: t.fix ? t.fix.label : t.label, id: t.id, books: t.books, fix: t.fix }),
      t.fixable ? h("div", { class: "faint", style: { fontSize: "12.5px", marginTop: "8px" } }, "Means none of the shared tags? ",
        h("button", { class: "btn small", onclick: makeShared }, "Make it a shared tag"), " · ", h("a", { href: "#/labels" }, "all labels to fix →")) : null,
      shareForm));
  }
  if (editing && t.editable) {
    view.push(h("section", { class: "tsec editbox" }, h("h2", {}, "Names and description"),
      tagForm(t.values, {
        builtin: Object.keys(t.builtin || {}).length ? t.builtin : null,
        onSave: (v) => redo(() => api.post("/api/tag/edit", { id: t.id, ...v }), "Saved"),
        extra: [
          t.edited ? h("button", { class: "btn small ghost", title: "Names, description, parent and child links and anti-tags go back to Bookkeeper's own (label fixes stay)",
            onclick: () => confirm(`Undo all your changes to “${name}”?`) && redo(() => api.post("/api/tag/reset", { id: t.id }), "Back to Bookkeeper's version") }, "Undo all my changes") : null,
          t.user_tag ? h("button", { class: "btn small ghost danger",
            onclick: () => confirm(`Delete the tag “${name}”? Its books keep their site labels.`) && redo(() => api.post("/api/tag/delete", { id: t.id }), "Tag deleted") }, "Delete tag") : null,
        ] })));
  }
  if (t.fixes_here.length) {
    view.push(sec("Your label fixes", `site labels you said mean “${name}”`, h("div", { class: "lrows" },
      t.fixes_here.map((f) => labelRow({ label: f.label, books: null, fix: { tags: f.tags, hidden: false, separate: false } })))));
  }
  if (editing && t.editable) {
    view.push(
      sec("Aliases", "other names that mean the same: a label written this way gives every book this tag", h("div", {},
        t.aliases.length ? h("div", { class: "chips" }, t.aliases.map((a) => h("span", { class: "chip static" }, a,
          h("button", { class: "edit", title: `Remove: “${a}” won't mean ${name} any more`, onclick: () => redo(() => api.post("/api/tag/alias", { id: t.id, alias: a, on: false }), `“${a}” doesn't mean ${name} any more`) }, "×"))))
          : h("p", { class: "faint" }, "—"),
        h("div", { class: "addrow" }, aliasInput, h("button", { class: "btn small", onclick: addAlias }, "Add")))),
      sec("Parent tags", `broader tags every “${name}” book also gets`, linkEditor(t.parents_all, "parent", "+ add a broader tag…")),
      sec("Child tags", `narrower tags that can't appear without “${name}”`, linkEditor(t.children_direct, "child", "+ add a narrower tag…")),
      sec("Anti-tags", `tags that contradict “${name}”`, linkEditor(t.anti, "anti", "+ add a contradicting tag…")),
      sec("See also", "related tags worth a look from here; they don't change any book's tags", linkEditor(t.see_also || [], "related", "+ add a related tag…")));
  } else {
    view.push(
      sec("Aliases", "other names that mean the same", numbered(t.aliases, (a) => a, "cols")),
      sec("Parent tags", `broader tags every “${name}” book also gets`, numbered(t.parents, (x) => h("span", {}, tagLink(x), countOf(x.books)))),
      t.ancestors.length ? h("div", { class: "further" }, "Further up: ", t.ancestors.map((x, i) => [i ? ", " : "", tagLink(x)])) : null,
      sec("Child tags", `narrower tags that can't appear without “${name}”`, t.children_tree.length ? treeList(t.children_tree) : h("p", { class: "faint" }, "—")),
      sec("Anti-tags", `tags that contradict “${name}”`, numbered(t.anti, (x) => h("span", {}, tagLink(x), countOf(x.books)))),
      t.see_also && t.see_also.length ? sec("See also", `related tags linked to “${name}”`, numbered(t.see_also, (x) => h("span", {}, tagLink(x), countOf(x.books)))) : null);
  }
  view.push(
    sec("Related tags", `tags that usually appear with “${name}” in your library`,
      numbered(t.related, (x) => h("span", {}, tagLink(x), h("span", { class: "n" }, `in ${x.share}% of these books`)))),
    t.rarely.length ? sec("Rarely together", `common tags that almost never appear with “${name}” in your library`,
      numbered(t.rarely, (x) => h("span", {}, tagLink(x), h("span", { class: "n" }, `${fmtNum(x.together)} book${x.together === 1 ? "" : "s"} with both`)))) : null,
    t.combined.length ? sec("Combined labels", `site labels that mean “${name}” plus another tag`, h("div", { class: "chips" }, t.combined.map((x) =>
      h("span", { class: "chip static" }, x.label, h("span", { class: "n" }, "= " + [name, ...x.with.map(tagLabel)].join(" + ")))))) : null,
    t.seen_as.length ? sec("Written on the sites as", "✎ when a label doesn't really mean this tag", seenAs(t)) : null,
    t.sites.length ? sec("On the sites", null, h("div", { class: "chips" }, t.sites.map((s) =>
      h("span", { class: "chip static" }, siteName(s.site), countOf(s.books))))) : null);
  fill(app, h("div", { class: `page tagpage ${editing ? "editing" : ""}` }, view));
  if (keepScroll != null) scrollTo(0, keepScroll);
}

// The site labels behind a tag; ✎ opens a fixer for one of them (when Bookkeeper maps it to the wrong tag).
function seenAs(t) {
  const slot = h("div", {});
  let open = null;
  const chips = h("div", { class: "chips" }, t.seen_as.map((s) => h("span", { class: "chip static" }, s.raw, countOf(s.books),
    s.fixed ? h("span", { class: "n", title: "You fixed this label" }, "✓") : null,
    h("button", { class: "edit", title: `“${s.raw}” doesn't mean this tag? Say what it means`, onclick: () => {
      if (open === s.raw) { open = null; slot.replaceChildren(); return; }
      open = s.raw;
      slot.replaceChildren(h("div", { class: "lrow" }, h("div", { class: "lhead" }, h("span", { class: "lname" }, s.raw), h("span", { class: "n" }, booksText(s.books))),
        fixerFor({ label: s.raw, books: s.books }, { remap: true, exclude: [t.id] })));
    } }, "✎"))));
  return h("div", {}, chips, slot);
}

async function renderAllTags() {
  const app = $("#app");
  app.replaceChildren(h("div", { class: "page" }, h("div", { class: "loadmore" }, h("span", { class: "spinner" }))));
  let all = [];
  try { all = await api.get("/api/tags/all"); } catch { /* shown as empty */ }
  if (parseHash().view !== "tags") return;
  const filter = h("input", { class: "input", placeholder: "Find a tag: type part of a name in any language…", style: { maxWidth: "420px" } });
  const body = h("div", {});
  const newForm = h("div", {});
  const aiSlot = h("div", {});
  const openAi = (q) => {
    if (aiSlot.firstChild && q == null) { aiSlot.replaceChildren(); return; }
    aiSlot.replaceChildren(tagAiPanel(q || ""));
  };
  const draw = () => {
    const q = filter.value.trim().toLowerCase().replace(/ё/g, "е");
    const by = {};
    for (const t of all) {
      if (q && ![t.id, t.label, t.label_ru, t.label_uk].some((n) => n && n.toLowerCase().replace(/ё/g, "е").includes(q))) continue;
      const cat = t.known || t.category === "fandom" ? t.category : "other";
      (by[cat] = by[cat] || []).push(t);
    }
    const order = meta.categories || Object.keys(CATS);
    const sections = order.filter((c) => by[c]).map((c) => h("section", { class: "tsec" },
      h("h2", {}, CATS[c] || c, h("span", { class: "sub" }, ` — ${by[c].length}`),
        c === "other" ? h("a", { class: "btn small", href: "#/labels", style: { marginLeft: "10px" } }, "Fix these labels →") : null),
      h("div", { class: "chips" }, by[c].sort((a, b) => (b.books || 0) - (a.books || 0) || tagLabel(a).localeCompare(tagLabel(b))).map((t) =>
        withHover(h("a", { class: `chip ${t.books ? "" : "empty"}`, href: tagHref(t.id) }, tagLabel(t), countOf(t.books)), t.id)))));
    body.replaceChildren(...(sections.length ? sections : [h("p", { class: "muted" }, "No tag matches that.")]));
  };
  filter.addEventListener("input", debounce(draw, 120));
  const openNew = () => newForm.replaceChildren(h("div", { class: "editbox", style: { marginBottom: "14px" } },
    h("h2", { style: { fontSize: "16px", margin: "0 0 8px" } }, "New tag"),
    tagForm({ category: "theme" }, {
      saveText: "Create the tag",
      extra: h("button", { class: "btn small ghost", onclick: () => newForm.replaceChildren() }, "Cancel"),
      onSave: async (v) => {
        let r;
        try { r = await api.post("/api/tag/new", v); } catch (e) { toast(String(e.message || e)); return false; }
        toast("Tag created");
        location.hash = tagHref(r.id) + "&edit=1";
        return true;
      } })));
  app.replaceChildren(h("div", { class: "page" }, h("h1", {}, "Tags"),
    h("p", { class: "lead" }, "Bookkeeper's shared tags, grouped like on the book page, with the number of books in your library that have each. Rest the mouse on a tag for a short description; click it for its page, where ✎ Edit tag changes its names, description, aliases, parent and child tags and anti-tags."),
    h("div", { class: "toolbar2" },
      h("button", { class: "btn primary", onclick: openNew }, "+ New tag"),
      h("a", { class: "btn", href: "#/labels", title: "Labels from the sites that aren't shared tags, most common first" }, "Fix site labels"),
      h("a", { class: "btn", href: "#/labels?tab=mine" }, "My label fixes"),
      h("button", { class: "btn", title: "Let Gemini, ChatGPT or another AI chat sort aliases into child tags and fix parent, child and anti-tag links, many tags at a time", onclick: () => openAi() }, "✨ Improve tags with an AI chat")),
    newForm,
    aiSlot,
    h("div", { style: { margin: "0 0 6px" } }, filter),
    h("div", { class: "legend", style: { marginBottom: "6px" } }, h("span", {}, "Faded: no book has it yet"), h("span", {}, "Tag names in: "),
      ...[["en", "English"], ["ru", "Русский"], ["uk", "Українська"]].map(([k, l]) => chip(l, tagLang === k, () => { tagLang = k; store.set("tagLang", k); renderAllTags(); }))),
    body));
  draw();
  const { params } = parseHash();
  if (params.ai != null) openAi(params.ai);
}

// ---------- fixing site labels ----------
// A small "type a tag" field: suggestions as you type, Enter or a click picks one.
function tagPicker(onPick, placeholder = "Means… type a tag") {
  const input = h("input", { class: "input small", placeholder, autocomplete: "off", spellcheck: "false" });
  const box = h("div", { class: "suggest hidden" });
  let opts = [], sel = -1;
  const pick = (o) => { if (!o) return; input.value = ""; box.classList.add("hidden"); onPick(o); };
  const draw = () => {
    openSuggest = () => placeList(box, input);
    placeList(box, input);
    fill(box, opts.map((o, i) => h("div", { class: `opt ${i === sel ? "sel" : ""}`, onmousedown: (e) => { e.preventDefault(); pick(o); } },
      h("div", { class: "l1" }, h("span", { class: "name" }, tagLabel(o)), otherName(o), h("span", { class: "n" }, fmtNum(o.books || 0))),
      o.description ? h("div", { class: "d" }, o.description) : null)));
    box.classList.toggle("hidden", !opts.length);
  };
  const suggest = debounce(async () => {
    const q = input.value.trim();
    if (!q) { box.classList.add("hidden"); return; }
    try { opts = await api.get("/api/tags/complete?" + new URLSearchParams({ text: q, lang: tagLang, quoted: 1, limit: 10 })); } catch { opts = []; }
    if (q !== input.value.trim() || document.activeElement !== input) return;
    sel = opts.length ? 0 : -1;
    draw();
  }, 120);
  input.addEventListener("input", suggest);
  input.addEventListener("blur", () => box.classList.add("hidden"));
  input.addEventListener("keydown", (e) => {
    const open = !box.classList.contains("hidden") && opts.length > 0;
    if (open && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault(); sel = (sel + (e.key === "ArrowDown" ? 1 : -1) + opts.length) % opts.length; draw();
    } else if (e.key === "Enter") { e.preventDefault(); if (open) pick(opts[Math.max(0, sel)]); }
    else if (e.key === "Escape" && open) { e.stopPropagation(); box.classList.add("hidden"); }
  });
  return h("span", { class: "tagpick" }, input, box);
}

const booksText = (n) => `${fmtNum(n)} book${n === 1 ? "" : "s"}`;

// What a site label means: suggestions, a tag picker, Hide (and Keep separate for a label mapped to the wrong tag).
// Once fixed: the meaning, "+ another tag" and Undo. Every action applies to every book with the label.
function labelFixer(item, opts = {}) {
  const box = h("div", { class: "fixer" });
  const note = h("span", { class: "note" });
  let fix = item.fix || null, adding = false;
  const send = async (body, doing) => {
    fill(box, h("span", { class: "faint" }, h("span", { class: "spinner tiny" }), ` ${doing}…`));
    try {
      const r = await api.post("/api/labels/fix", { label: item.label, ...body });
      fix = r.undone ? null : { tags: r.tags, hidden: r.hidden, separate: r.separate };
      adding = false;
      tagCache.clear();
      draw(`${r.undone ? "Undone: " : ""}${booksText(r.books)} updated.`);
      if (opts.onChange) opts.onChange(fix, r);
    } catch (e) {
      draw();
      fill(note, h("span", { class: "warn" }, String(e.message || e)));
    }
  };
  const setTags = (ids) => send({ tags: ids }, ids.length > 1 ? "Adding the tag" : "Fixing");
  const draw = (done) => {
    fill(note, done ? h("span", { class: "faint" }, done) : null);
    const parts = [];
    if (fix && !adding) {
      parts.push(h("span", { class: "fixed" }, "✓ ", fix.hidden ? "Hidden from books" : fix.separate ? "Left as it is (a tag of its own)"
        : ["Means ", fix.tags.map((t, i) => [i ? " + " : "", tagLink(t)])]));
      if (!fix.hidden && !fix.separate) {
        parts.push(h("button", { class: "btn small ghost", title: "It means another tag as well", onclick: () => { adding = true; draw(); } }, "+ another tag"));
      }
      parts.push(h("button", { class: "btn small ghost", title: "Go back to how Bookkeeper read this label before", onclick: () => send({ undo: true }, "Undoing") }, "Undo"));
    } else if (fix && adding) {
      parts.push(tagPicker((o) => setTags([...fix.tags.map((t) => t.id), o.id]), "…and also: type a tag"),
        h("button", { class: "btn small ghost", onclick: () => { adding = false; draw(); } }, "Cancel"));
    } else {
      const sug = item.suggestions || [];
      if (sug.length) {
        parts.push(h("span", { class: "sugs" }, sug.map((s) => h("button", {
          class: "chip sug", onclick: () => setTags([s.id]),
          title: `${s.why === "company" ? `${s.share}% of the books with this label also have this tag` : "Its name looks like this label"}. Click: the label means this tag.${s.description ? `\n${s.description}` : ""}`,
        }, tagLabel(s), s.why === "company" ? h("span", { class: "why" }, `${s.share}%`) : null))));
      }
      parts.push(tagPicker((o) => setTags([o.id]), opts.remap ? "Means instead… type a tag" : "Means… type a tag"));
      if (opts.remap) {
        parts.push(h("button", { class: "btn small ghost", title: "Bookkeeper maps this label to the wrong tag: keep it as a tag of its own", onclick: () => send({ separate: true }, "Fixing") }, "Keep separate"));
      }
      parts.push(h("button", { class: "btn small ghost", title: "Not a real tag (a site name, a year, a typo…): remove it from every book. You can undo it later.", onclick: () => send({ hide: true }, "Hiding") }, "Hide"));
      if (!opts.remap) {
        parts.push(h("button", { class: "btn small ghost", title: "It's fine as it is: keep it as a tag of its own, and take it off the list of labels to fix", onclick: () => send({ separate: true }, "Saving") }, "Leave as is"));
      }
    }
    fill(box, parts, note);
  };
  draw();
  return box;
}

// labelFixer with its suggestions, fetched first (tag pages).
function fixerFor(item, opts = {}) {
  const holder = h("div", {}, h("span", { class: "spinner tiny" }));
  api.get("/api/labels/suggest?" + new URLSearchParams({ label: item.label, id: item.id || "" }))
    .then((r) => holder.replaceChildren(labelFixer({ ...item, fix: item.fix || r.fix,
      suggestions: r.suggestions.filter((s) => !(opts.exclude || []).includes(s.id)) }, opts)))
    .catch(() => holder.replaceChildren(labelFixer(item, opts)));
  return holder;
}

function labelRow(x, n) {
  const row = h("div", { class: `lrow ${x.fix ? "done" : ""}` });
  fill(row,
    h("div", { class: "lhead" },
      n ? h("span", { class: "num" }, `${n}.`) : null,
      h("a", { class: "lname", href: tagHref(x.id || x.label), title: "The label's page" }, x.label),
      x.books != null ? h("span", { class: "n" }, booksText(x.books)) : null,
      x.sites && x.sites.length ? h("span", { class: "lsites" }, x.sites.slice(0, 4).map((s) => `${siteName(s.site)} ${fmtNum(s.books)}`).join(" · ")) : null,
      x.spellings && x.spellings.length ? h("span", { class: "faint", title: x.spellings.join("\n") },
        `also “${x.spellings.slice(0, 2).join("”, “")}”${x.spellings.length > 2 ? ` +${x.spellings.length - 2}` : ""}`) : null,
      x.id ? h("a", { class: "faint", href: "/#/library?" + toQuery({ tq: qtok(x.id) }), target: "_blank", title: "The books with this label, in a new tab" }, "books ↗") : null),
    labelFixer(x, { onChange: (fix) => row.classList.toggle("done", !!fix) }));
  return row;
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return; } catch { /* not allowed here: the old way */ }
  const ta = h("textarea", { style: { position: "fixed", left: "-9999px" } });
  ta.value = text;
  document.body.append(ta);
  ta.select();
  document.execCommand("copy");
  ta.remove();
}

// Fixing labels with an AI chat (Gemini, ChatGPT…): copy a batch of labels as a prompt, paste the reply back.
function aiPanel(getFilters, onApplied) {
  const limit = h("select", { class: "input", style: { width: "auto" } },
    [100, 250, 500, 1000].map((n) => h("option", { value: n, selected: n === 250 }, `${n} labels`)));
  const info = h("span", { class: "faint" });
  const copy = async () => {
    fill(info, h("span", { class: "spinner tiny" }), " Preparing…");
    try {
      const { site, q } = getFilters();
      const r = await api.get("/api/labels/export?" + toQuery({ site, q, limit: limit.value }));
      await copyText(r.text);
      fill(info, `Copied ${r.count} of ${fmtNum(r.total)} labels (${fmtNum(r.chars)} characters).`);
      toast("Copied: paste it into the AI chat");
    } catch (e) { fill(info, h("span", { class: "warn" }, String(e.message || e))); }
  };
  const download = () => {
    const { site, q } = getFilters();
    location.href = "/api/labels/export.txt?" + toQuery({ site, q, limit: limit.value });
  };
  const reply = h("textarea", { class: "note", placeholder: "Paste the AI's whole reply here…", style: { minHeight: "110px" } });
  const preview = h("div", { class: "aipreview" });
  const fileIn = h("input", { type: "file", accept: ".txt,.json,.jsonl,.md,text/plain", class: "hidden",
    onchange: async (e) => { const f = e.target.files[0]; if (f) { reply.value = await f.text(); check(); } } });
  const check = async () => {
    if (!reply.value.trim()) { toast("Paste the AI's reply first"); return; }
    fill(preview, h("span", { class: "spinner tiny" }), " Checking the answers…");
    try { drawPreview(await api.post("/api/labels/import/check", { text: reply.value })); }
    catch (e) { fill(preview, h("div", { class: "warn" }, String(e.message || e))); }
  };
  const meaning = (it) => it.problem ? h("span", { class: "warn" }, it.problem)
    : it.action === "hide" ? h("span", { class: "muted" }, "hide from every book")
    : it.action === "keep" ? h("span", { class: "muted" }, "leave as it is")
    : h("span", {}, it.tags.map((t, i) => [i ? " + " : "", t.label]));
  const drawPreview = (r) => {
    const c = r.counts;
    const newChecks = r.new_tags.map((t) => ({ t, box: h("input", { type: "checkbox", checked: !t.problem && t.used_by > 0, disabled: !!t.problem }) }));
    const itemChecks = r.items.map((it) => ({ it, box: h("input", { type: "checkbox", checked: !it.problem, disabled: !!it.problem }) }));
    const applyBtn = h("button", { class: "btn primary" });
    const count = () => { applyBtn.textContent = `Apply ${itemChecks.filter((x) => x.box.checked).length} answers`; };
    itemChecks.forEach((x) => x.box.addEventListener("change", count));
    count();
    applyBtn.addEventListener("click", async () => {
      applyBtn.disabled = true;
      fill(result, h("span", { class: "spinner tiny" }), " Fixing the labels on your books…");
      try {
        const done = await api.post("/api/labels/import/apply", { text: reply.value,
          keys: itemChecks.filter((x) => x.box.checked).map((x) => x.it.key),
          new_tags: newChecks.filter((x) => x.box.checked).map((x) => x.t.id) });
        reply.value = "";
        fill(preview, h("div", { class: "fixed" }, `✓ Fixed ${fmtNum(done.labels)} labels on ${booksText(done.books)}`,
          done.new_tags ? `, with ${done.new_tags} new tag${done.new_tags === 1 ? "" : "s"}` : "", ". "),
          h("button", { class: "btn small ghost", onclick: async () => {
            try { await api.post("/api/labels/import/undo", { id: done.import }); toast("Import undone"); fill(preview); onApplied(); }
            catch (e) { toast(String(e.message || e)); }
          } }, "Undo this import"),
          h("div", { class: "faint" }, "They left the list below. Copy the next batch and repeat."));
        tagCache.clear();
        onApplied();
      } catch (e) { applyBtn.disabled = false; fill(result, h("span", { class: "warn" }, String(e.message || e))); }
    });
    const result = h("span", {});
    fill(preview,
      h("div", { class: "aisum" }, `${r.items.length} answers: ${c.tags} mean shared tags, ${c.hide} to hide, ${c.keep} to leave as they are`,
        c.problems ? h("span", { class: "warn" }, `, ${c.problems} can't be used`) : null, "."),
      newChecks.length ? h("div", { class: "ainew" }, h("b", {}, "New tags it suggests"), newChecks.map(({ t, box }) => h("label", { class: "check" }, box,
        h("span", {}, h("b", {}, t.label || t.label_ru), t.label_ru && t.label ? ` / ${t.label_ru}` : "", ` · ${CATS[t.category] || t.category}`,
          t.parents && t.parents.length ? h("span", {}, " · child of ", h("b", {}, t.parents.map((x) => x.label).join(" + "))) : null,
          t.anti && t.anti.length ? h("span", { class: "faint" }, ` · contradicts ${t.anti.map((x) => x.label).join(", ")}`) : null,
          t.description ? h("span", { class: "faint" }, ` — ${t.description}`) : null,
          h("span", { class: "faint" }, t.problem ? ` (${t.problem})` : ` · for ${t.used_by} label${t.used_by === 1 ? "" : "s"}`))))) : null,
      h("div", { class: "airows" }, itemChecks.map(({ it, box }) => h("label", { class: `airow ${it.problem ? "bad" : ""}` }, box,
        h("span", { class: "lname" }, it.label), h("span", { class: "n" }, fmtNum(it.books)), h("span", { class: "arrow" }, "→"), meaning(it)))),
      h("div", { class: "shelf", style: { marginTop: "8px" } }, applyBtn,
        h("button", { class: "btn small ghost", onclick: () => { itemChecks.forEach((x) => { if (!x.box.disabled) x.box.checked = true; }); count(); } }, "Tick all"),
        h("button", { class: "btn small ghost", onclick: () => { itemChecks.forEach((x) => { x.box.checked = false; }); count(); } }, "Untick all"),
        result));
  };
  return h("div", { class: "aibox" },
    h("h2", {}, "Fix labels with an AI chat"),
    h("p", { class: "faint" }, "Gemini, ChatGPT or any other chat can do the reading for you, on your own subscription. Bookkeeper writes the request; the chat answers in a format Bookkeeper reads back. You check the answers before anything changes, and the whole import can be undone."),
    h("div", { class: "aistep" }, h("span", { class: "stepn" }, "1"), h("div", {},
      h("div", { class: "shelf" }, limit, h("button", { class: "btn small primary", onclick: copy }, "Copy the request"),
        h("button", { class: "btn small", onclick: download, title: "For very long requests: attach the file in the chat instead of pasting" }, "Download as a file"), info),
      h("div", { class: "faint" }, "The most common labels in the list below (with its site and search filters), the shared tags, and instructions. Paste it into the chat and send it, or attach the file."))),
    h("div", { class: "aistep" }, h("span", { class: "stepn" }, "2"), h("div", {},
      reply,
      h("div", { class: "shelf", style: { marginTop: "6px" } }, h("button", { class: "btn small primary", onclick: check }, "Check the answers"),
        h("button", { class: "btn small", onclick: () => fileIn.click() }, "Load a file…"), fileIn,
        h("span", { class: "faint" }, "Copy the chat's whole reply (its code block has a copy button). If it stops halfway, paste what it wrote: the rest stays in the list.")))),
    preview);
}

// Improving shared tags with an AI chat: their aliases become child tags, wrong ones move, links get fixed.
const LINK_WORDS = { parent: ["is a child of", "is no longer a child of"], child: ["gets the child tag", "loses the child tag"],
  anti: ["contradicts", "no longer contradicts"], related: ["is related to (see also)", "is no longer related to"], tag: ["", ""] };
const FIELD_WORDS = { label: "English name", label_ru: "Russian name", label_uk: "Ukrainian name", category: "category", description: "description" };
function tagAiPanel(startQ) {
  const q = h("input", { class: "input small", value: startQ || "", placeholder: "Which tags: names or ids, separated by commas (empty: most aliases first)", style: { minWidth: "320px", flex: "1" } });
  const cat = h("select", { class: "input", style: { width: "auto" } }, h("option", { value: "" }, "All categories but fandoms"),
    (meta.categories || Object.keys(CATS)).filter((c) => c !== "other").map((c) => h("option", { value: c }, CATS[c] || c)));
  const limit = h("select", { class: "input", style: { width: "auto" } },
    [300, 600, 1000, 2000, 4000].map((n) => h("option", { value: n, selected: n === 600 }, `about ${fmtNum(n)} aliases`)));
  const again = h("input", { type: "checkbox" });
  const reviewedNote = h("span", { class: "faint" });
  const info = h("span", { class: "faint" });
  const params = () => ({ q: q.value.trim(), cat: cat.value, reviewed: again.checked ? 1 : 0, limit: limit.value });
  const copy = async () => {
    fill(info, h("span", { class: "spinner tiny" }), " Preparing…");
    try {
      const r = await api.get("/api/tagai/export?" + toQuery(params()));
      if (!r.tags) { fill(info, h("span", { class: "warn" }, "No tag with aliases left here. Tick “again” to include the ones already reviewed.")); return; }
      await copyText(r.text);
      fill(info, `Copied ${r.tags} of ${fmtNum(r.total)} tags with ${fmtNum(r.aliases)} aliases (${fmtNum(r.chars)} characters).`);
      reviewedNote.textContent = r.reviewed ? `${fmtNum(r.reviewed)} reviewed so far` : "";
      toast("Copied: paste it into the AI chat");
    } catch (e) { fill(info, h("span", { class: "warn" }, String(e.message || e))); }
  };
  const download = () => { location.href = "/api/tagai/export.txt?" + toQuery(params()); };
  const reply = h("textarea", { class: "note", placeholder: "Paste the AI's whole reply here…", style: { minHeight: "110px" } });
  const preview = h("div", { class: "aipreview" });
  const past = h("div", {});
  const fileIn = h("input", { type: "file", accept: ".txt,.json,.jsonl,.md,text/plain", class: "hidden",
    onchange: async (e) => { const f = e.target.files[0]; if (f) { reply.value = await f.text(); check(); } } });
  const check = async () => {
    if (!reply.value.trim()) { toast("Paste the AI's reply first"); return; }
    fill(preview, h("span", { class: "spinner tiny" }), " Checking the answers…");
    try { drawPreview(await api.post("/api/tagai/check", { text: reply.value })); }
    catch (e) { fill(preview, h("div", { class: "warn" }, String(e.message || e))); }
  };
  const names = (list) => list.map((t, i) => [i ? " + " : "", t.label]);
  const undo = async (id) => {
    if (!confirm("Undo this whole import? Its aliases, links, names and descriptions go back to how they were, and the tags it made are deleted.")) return;
    try { await api.post("/api/tagai/undo", { id }); toast("Import undone"); tagCache.clear(); fill(preview); loadHistory(); }
    catch (e) { toast(String(e.message || e)); }
  };
  const drawPreview = (r) => {
    const c = r.counts;
    const newChecks = r.new_tags.map((t) => ({ t, box: h("input", { type: "checkbox", checked: !t.problem && t.used_by > 0, disabled: !!t.problem }) }));
    const rows = [...r.edits, ...r.aliases, ...r.links].map((it) => ({ it, box: h("input", { type: "checkbox", checked: !it.problem, disabled: !!it.problem }) }));
    const applyBtn = h("button", { class: "btn primary" });
    const result = h("span", {});
    const count = () => { applyBtn.textContent = `Apply ${rows.filter((x) => x.box.checked).length} changes`; };
    rows.forEach((x) => x.box.addEventListener("change", count));
    count();
    applyBtn.addEventListener("click", async () => {
      applyBtn.disabled = true;
      fill(result, h("span", { class: "spinner tiny" }), " Changing the tags on your books…");
      try {
        const done = await api.post("/api/tagai/apply", { text: reply.value,
          keys: rows.filter((x) => x.box.checked).map((x) => x.it.key),
          new_tags: newChecks.filter((x) => x.box.checked).map((x) => x.t.id) });
        reply.value = "";
        tagCache.clear();
        fill(preview, h("div", { class: "fixed" }, `✓ ${fmtNum(done.labels)} aliases changed, ${fmtNum(done.links)} links changed`,
          done.edits ? `, ${fmtNum(done.edits)} names and descriptions` : "",
          done.new_tags ? `, ${done.new_tags} new tag${done.new_tags === 1 ? "" : "s"}` : "", ` on ${booksText(done.books)}. `),
          done.import ? h("button", { class: "btn small ghost", onclick: () => undo(done.import) }, "Undo this import") : null,
          h("div", { class: "faint" }, `${done.reviewed} tag${done.reviewed === 1 ? "" : "s"} marked as reviewed: the next request brings the next ones.`));
        loadHistory();
      } catch (e) { applyBtn.disabled = false; fill(result, h("span", { class: "warn" }, String(e.message || e))); }
    });
    const aliasRow = ({ it, box }) => h("label", { class: `airow ${it.problem ? "bad" : ""}` }, box,
      h("span", { class: "lname" }, it.label), it.new ? h("span", { class: "n", title: "No book has this label yet: it's a new alias, for books that arrive later" }, "new alias") : null,
      it.before.length ? h("span", { class: "faint" }, names(it.before)) : null, h("span", { class: "arrow" }, "→"),
      it.problem ? h("span", { class: "warn" }, it.problem) : it.action === "hide" ? h("span", { class: "muted" }, "hide from every book")
        : it.action === "keep" ? h("span", { class: "muted" }, "a label of its own (no shared tag)") : h("span", {}, names(it.tags)));
    const shown = (it, v) => it.field === "category" ? (CATS[v] || v) : v;
    const editRow = ({ it, box }) => h("label", { class: `airow ${it.problem ? "bad" : ""}`, title: it.field === "description" ? `Before: ${it.old || "no description"}` : "" }, box,
      h("span", { class: "lname" }, it.label), h("span", { class: "muted" }, FIELD_WORDS[it.field] || it.field),
      it.field !== "description" ? h("span", { class: "faint" }, it.old ? shown(it, it.old) : "—") : null, h("span", { class: "arrow" }, "→"),
      it.problem ? h("span", { class: "warn" }, it.problem) : h("span", {}, shown(it, it.new)),
      it.keep && !it.problem ? h("span", { class: "n" }, `“${it.keep}” stays an alias`) : null);
    const linkRow = ({ it, box }) => h("label", { class: `airow ${it.problem ? "bad" : ""}` }, box,
      h("span", { class: "lname" }, it.label), h("span", { class: it.on ? "" : "muted" }, (LINK_WORDS[it.kind] || ["", ""])[it.on ? 0 : 1]),
      it.other_label ? h("b", {}, it.other_label) : null, it.problem ? h("span", { class: "warn" }, `(${it.problem})`) : null);
    const aRows = rows.filter((x) => "action" in x.it), eRows = rows.filter((x) => "field" in x.it);
    const lRows = rows.filter((x) => !("action" in x.it) && !("field" in x.it));
    fill(preview,
      h("div", { class: "aisum" }, `${c.aliases} aliases to move, ${c.new_aliases} new aliases, ${c.keep + c.hide} to keep apart or hide, ${c.links} link changes, ${c.edits} names and descriptions, ${c.new_tags} new tags`,
        c.problems ? h("span", { class: "warn" }, `, ${c.problems} can't be used`) : null, ".",
        r.reviewed.length ? h("span", { class: "faint", title: r.reviewed.map((t) => t.label).join("\n") }, ` Reviewed: ${r.reviewed.length} tag${r.reviewed.length === 1 ? "" : "s"}.`) : null),
      newChecks.length ? h("div", { class: "ainew" }, h("b", {}, "New tags it suggests"), newChecks.map(({ t, box }) => h("label", { class: "check" }, box,
        h("span", {}, h("b", {}, t.label || t.label_ru), t.label_ru && t.label ? ` / ${t.label_ru}` : "", ` · ${CATS[t.category] || t.category}`,
          t.parents.length ? h("span", {}, " · child of ", h("b", {}, names(t.parents))) : null,
          t.anti.length ? h("span", { class: "faint" }, ` · contradicts ${t.anti.map((x) => x.label).join(", ")}`) : null,
          t.description ? h("span", { class: "faint" }, ` — ${t.description}`) : null,
          h("span", { class: "faint" }, t.problem ? ` (${t.problem})` : ` · ${t.used_by} alias${t.used_by === 1 ? "" : "es"}`),
          t.unknown && t.unknown.length ? h("span", { class: "warn" }, ` (no tag ${t.unknown.map((x) => `“${x}”`).join(", ")})`) : null)))) : null,
      eRows.length ? h("div", { class: "airows", style: { marginBottom: "6px" } }, eRows.map(editRow)) : null,
      aRows.length ? h("div", { class: "airows" }, aRows.map(aliasRow)) : null,
      lRows.length ? h("div", { class: "airows", style: { marginTop: "6px" } }, lRows.map(linkRow)) : null,
      h("div", { class: "shelf", style: { marginTop: "8px" } }, applyBtn,
        h("button", { class: "btn small ghost", onclick: () => { rows.forEach((x) => { if (!x.box.disabled) x.box.checked = true; }); count(); } }, "Tick all"),
        h("button", { class: "btn small ghost", onclick: () => { rows.forEach((x) => { x.box.checked = false; }); count(); } }, "Untick all"),
        result));
  };
  const loadHistory = async () => {
    let list = [];
    try { list = await api.get("/api/tagai/imports"); } catch { /* none shown */ }
    fill(past, list.length ? h("details", {}, h("summary", { class: "faint" }, `Earlier imports (${list.length})`),
      list.map((m) => h("div", { class: "lhead" }, h("span", {}, new Date(m.at).toLocaleString()),
        h("span", { class: "n" }, `${fmtNum(m.count)} aliases, ${fmtNum(m.link_count || 0)} links, ${m.edit_count ? `${fmtNum(m.edit_count)} names and descriptions, ` : ""}${booksText(m.books)}`),
        m.new_tags && m.new_tags.length ? h("span", { class: "faint" }, `${m.new_tags.length} new tag${m.new_tags.length === 1 ? "" : "s"}`) : null,
        m.undone ? h("span", { class: "faint" }, "undone") : h("button", { class: "btn small ghost", onclick: () => undo(m.id) }, "Undo this import")))) : null);
  };
  loadHistory();
  return h("div", { class: "aibox" },
    h("h2", {}, "Improve tags with an AI chat"),
    h("p", { class: "faint" }, "Many site labels became aliases of a broad tag though they name something narrower. The chat sorts them out: it suggests child tags (“Monster protagonist” under “Non-human lead”) and moves the aliases to them, moves, keeps apart or hides wrong aliases, adds new aliases and combined labels, fixes names, categories and descriptions, and adds or removes parent, child, anti-tag and related (“see also”) links. Books keep the broad tag through the parent link. You check every change first, and a whole import can be undone."),
    h("div", { class: "aistep" }, h("span", { class: "stepn" }, "1"), h("div", {},
      h("div", { class: "shelf" }, q, cat),
      h("div", { class: "shelf", style: { marginTop: "6px" } }, limit,
        h("label", { class: "check", title: "Tags you applied an answer for are left out of the next request, unless you tick this" }, again, "again, with reviewed tags"),
        h("button", { class: "btn small primary", onclick: copy }, "Copy the request"),
        h("button", { class: "btn small", onclick: download, title: "For very long requests: attach the file in the chat instead of pasting" }, "Download as a file"), info),
      h("div", { class: "faint" }, "The tags with the most aliases first (or the ones you named), with their links and how many books have each alias, plus the list of shared tags and instructions. ", reviewedNote))),
    h("div", { class: "aistep" }, h("span", { class: "stepn" }, "2"), h("div", {},
      reply,
      h("div", { class: "shelf", style: { marginTop: "6px" } }, h("button", { class: "btn small primary", onclick: check }, "Check the answers"),
        h("button", { class: "btn small", onclick: () => fileIn.click() }, "Load a file…"), fileIn,
        h("span", { class: "faint" }, "Copy the chat's whole reply (its code block has a copy button).")))),
    preview, past);
}

async function renderLabels() {
  const { params } = parseHash();
  const tab = params.tab === "mine" ? "mine" : "todo";
  let site = params.site || "", q = params.q || "", offset = 0, total = 0;
  const app = $("#app");
  const list = h("div", { class: "lrows" });
  const more = h("div", { class: "loadmore" });
  const summary = h("span", { class: "muted" });
  const aiSlot = h("div", {});
  const remember = () => history.replaceState(null, "", "#/labels?" + toQuery({ site, q }));
  const load = async (reset) => {
    if (reset) { offset = 0; list.replaceChildren(); }
    fill(more, h("span", { class: "spinner" }));
    let r;
    try { r = await api.get("/api/labels?" + toQuery({ site, q, offset, limit: 50 })); }
    catch (e) { fill(more, h("span", { class: "warn" }, String(e.message || e))); return; }
    total = r.total;
    summary.textContent = `${fmtNum(r.total)} label${r.total === 1 ? "" : "s"}${site ? ` on ${siteName(site)}` : ""} on ${fmtNum(r.books)} books`;
    r.labels.forEach((x, i) => list.append(labelRow(x, offset + i + 1)));
    offset += r.labels.length;
    fill(more, offset < total ? h("button", { class: "btn", onclick: () => load(false) }, `Show ${Math.min(50, total - offset)} more`)
      : h("span", { class: "faint" }, total ? "That's all of them." : q ? "No label matches that." : "Nothing left to fix here."));
  };
  const loadMine = async () => {
    fill(more, h("span", { class: "spinner" }));
    let fixes = [], imports = [];
    try { [fixes, imports] = await Promise.all([api.get("/api/labels/fixes"), api.get("/api/labels/imports")]); }
    catch (e) { fill(more, h("span", { class: "warn" }, String(e.message || e))); return; }
    summary.textContent = `${fmtNum(fixes.length)} fix${fixes.length === 1 ? "" : "es"}`;
    const importRows = imports.length ? h("div", { class: "editbox", style: { marginTop: "10px" } }, h("h2", { style: { fontSize: "15px", margin: "0 0 6px" } }, "Imported from an AI chat"),
      imports.map((m) => h("div", { class: "lhead" }, h("span", {}, new Date(m.at).toLocaleString()), h("span", { class: "n" }, `${fmtNum(m.count)} labels, ${booksText(m.books)}`),
        m.new_tags && m.new_tags.length ? h("span", { class: "faint" }, `${m.new_tags.length} new tag${m.new_tags.length === 1 ? "" : "s"}`) : null,
        m.undone ? h("span", { class: "faint" }, "undone") : h("button", { class: "btn small ghost", onclick: async () => {
          if (!confirm("Undo this whole import? Its labels go back to how they were, and the tags it made are deleted.")) return;
          try { await api.post("/api/labels/import/undo", { id: m.id }); toast("Import undone"); tagCache.clear(); loadMine(); }
          catch (e) { toast(String(e.message || e)); }
        } }, "Undo this import")))) : null;
    list.replaceChildren(...[importRows, ...fixes.map((f) => labelRow({ label: f.label, books: f.books, fix: { tags: f.tags, hidden: f.hidden, separate: f.separate } }))].filter(Boolean));
    fill(more, fixes.length ? h("span", { class: "faint" }, "They're kept in the [fixes] table of my_tags.toml.") : h("span", { class: "faint" }, "No fixes yet."));
  };
  const siteSel = h("select", { class: "input", style: { width: "auto" }, onchange: (e) => { site = e.target.value; remember(); load(true); } },
    h("option", { value: "" }, "All sites"), Object.keys(meta.sites).map((s) => h("option", { value: s, selected: s === site }, siteName(s))));
  const search = h("input", { class: "input", placeholder: "Find a label…", value: q, style: { maxWidth: "260px" } });
  search.addEventListener("input", debounce(() => { q = search.value.trim(); remember(); load(true); }, 350));
  const aiBtn = h("button", { class: "btn", title: "Let Gemini, ChatGPT or another AI chat suggest what the labels mean, a batch at a time", onclick: () => {
    if (aiSlot.firstChild) { aiSlot.replaceChildren(); store.set("aiPanel", false); return; }
    aiSlot.replaceChildren(aiPanel(() => ({ site, q }), () => load(true)));
    store.set("aiPanel", true);
  } }, "✨ Fix with an AI chat");
  app.replaceChildren(h("div", { class: "page labels" },
    h("div", { class: "crumbs" }, h("a", { href: "#/tags" }, "All tags"), " › Fix site labels"),
    h("h1", {}, "Fix site labels"),
    h("p", { class: "lead" }, "These labels came from the sites but aren't one of Bookkeeper's shared tags, so they have no translations or family, and a search for a shared tag misses them. Say once what a label means and every book with it follows: the books you have now and the ones that arrive later. Most common first."),
    h("div", { class: "seg ltabs" },
      h("a", { class: tab === "todo" ? "on" : "", href: "#/labels" }, "To fix"),
      h("a", { class: tab === "mine" ? "on" : "", href: "#/labels?tab=mine" }, "My fixes")),
    tab === "todo" ? h("div", { class: "lfilters" }, siteSel, search, aiBtn, summary) : h("div", { class: "lfilters" }, summary),
    tab === "todo" ? aiSlot : null,
    h("div", { class: "legend" }, tab === "todo"
      ? [h("span", {}, "Click a suggestion, or type a tag. Hide removes junk labels (site names, years…) from every book; Leave as is takes a label off this list."), h("span", {}, "Everything can be undone.")]
      : [h("span", {}, "Undo puts a label back the way Bookkeeper read it before.")]),
    list, more));
  if (tab === "todo" && store.get("aiPanel", false)) aiSlot.replaceChildren(aiPanel(() => ({ site, q }), () => load(true)));
  if (tab === "todo") await load(true); else await loadMine();
}

// ---------- start ----------
async function boot() {
  try {
    meta = await api.get("/api/meta");
    $("#app-version").textContent = meta.version ? `v${meta.version}` : "";
    const s = await api.get("/api/sites");
    siteCounts = Object.fromEntries(s.sites.map((x) => [x.id, x.counts]));
  } catch (e) { console.error(e); }
  if (!location.hash) location.hash = "#/library";
  route();
  setInterval(async () => { try { meta = { ...meta, ...(await api.get("/api/meta")) }; } catch { /* offline */ } }, 15000);
}
boot();
