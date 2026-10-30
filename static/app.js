const $ = s => document.querySelector(s);
const NS = "http://www.w3.org/2000/svg";
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
const svgEl = (tag, attrs = {}) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; };
const store = {
  get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} }
};

let chats = store.get("chats", []);
let settings = { theme: "system", lang: "auto", length: "short", ...store.get("settings", {}) };
let cur = null, busy = false, info = {};

const CHIPS = ["Fastest way from Indiranagar to Majestic", "Which metro goes to the airport?", "इंदिरानगर से मजेस्टिक कैसे जाएं?", "ಮೆಜೆಸ್ಟಿಕ್‌ನಿಂದ ಜಯನಗರಕ್ಕೆ ಹೇಗೆ ಹೋಗುವುದು?"];
function icon(name) { const s = svgEl("svg", { class: "ic" }); s.appendChild(svgEl("use", { href: "#i-" + name })); return s; }
function toast(t) { const n = $("#toast"); n.textContent = t; n.style.display = "block"; clearTimeout(toast.t); toast.t = setTimeout(() => n.style.display = "none", 3500); }
function saveChats() { store.set("chats", chats); }
function uuid() { return crypto.randomUUID ? crypto.randomUUID() : "s" + Date.now() + Math.random().toString(16).slice(2); }

/* theme and settings */
function applyTheme() {
  const dark = settings.theme === "dark" || (settings.theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}
function saveSettings() { store.set("settings", settings); applyTheme(); }

/* small markdown renderer: bold and lists, built with textContent so nothing is injected */
function inline(parent, t) {
  t.split(/(\*\*[^*]+\*\*)/).forEach(part => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) parent.appendChild(el("strong", "", part.slice(2, -2)));
    else parent.appendChild(document.createTextNode(part));
  });
}
function md(text) {
  const box = el("div"); let list = null;
  text.split("\n").forEach(line => {
    const m = line.match(/^\s*[-*]\s+(.*)/) || line.match(/^\s*\d+[.)]\s+(.*)/);
    if (m) { if (!list) { list = el("ul"); box.appendChild(list); } const li = el("li"); inline(li, m[1]); list.appendChild(li); }
    else { list = null; if (line.trim()) { const p = el("p"); inline(p, line.replace(/^#+\s*/, "")); box.appendChild(p); } }
  });
  return box;
}

/* route card built from tool JSON (not from model text) */
function journeyCard(c) {
  const card = el("div", "card");
  const stats = el("div", "stats");
  [["Time (est.)", c.minutes_estimated + " min"], ["Stops", c.total_stops], ["Changes", c.changes], ["Fare (approx.)", c.fare_inr_approx ? "₹" + c.fare_inr_approx + (c.fare_complete === false ? "+" : "") : "Not in data"]]
    .forEach(([k, v]) => { const d = el("div"); d.appendChild(el("span", "", k)); d.appendChild(el("b", "", String(v))); stats.appendChild(d); });
  card.appendChild(stats);

  // line diagram: one thick segment per leg, rings at stations where the line changes
  const svg = svgEl("svg", { viewBox: "0 0 600 70", class: "diagram", role: "img", "aria-label": "Route diagram" });
  const total = Math.max(c.total_stops, 1); let x = 25; const W = 550;
  c.legs.forEach((leg, i) => {
    const w = W * leg.stops / total;
    svg.appendChild(svgEl("line", { x1: x, y1: 30, x2: x + w, y2: 30, stroke: leg.color, "stroke-width": 8, "stroke-linecap": "round" }));
    const label = (px, name, anchor) => { const t = svgEl("text", { x: px, y: i % 2 ? 62 : 54, "text-anchor": anchor, "font-size": 12, style: "fill:var(--ink)" }); t.textContent = name; svg.appendChild(t); };
    if (i === 0) label(x, leg.from, "start");
    else label(x, leg.from, "middle");
    if (i === c.legs.length - 1) label(x + w, leg.to, "end");
    x += w;
  });
  let px = 25;
  const dot = (cx, big) => svg.appendChild(svgEl("circle", { cx, cy: 30, r: big ? 9 : 7, fill: "var(--surface)", stroke: "var(--ink)", "stroke-width": 3 }));
  dot(px, false);
  c.legs.forEach((leg, i) => { px += W * leg.stops / total; dot(px, i < c.legs.length - 1); });
  { // hide diagram labels that would overlap
    const tx = [...svg.querySelectorAll("text")]; let last = -999;
    tx.slice(0, -1).forEach(t => { const x = +t.getAttribute("x"); if (x - last < 170) t.remove(); else last = x; });
    const rest = [...svg.querySelectorAll("text")];
    if (rest.length > 2 && rest[rest.length - 1].getAttribute("x") - rest[rest.length - 2].getAttribute("x") < 170) rest[rest.length - 2].remove();
  }
  card.appendChild(svg);

  const ol = el("ol", "steps");
  c.legs.forEach(leg => {
    const li = el("li");
    const chip = el("span", "chip", leg.mode === "bus" ? leg.line : leg.line + " Line"); chip.style.borderLeftColor = leg.color;
    li.appendChild(chip);
    li.appendChild(document.createTextNode(`${leg.from} to ${leg.to}, ${leg.stops} stops`));
    ol.appendChild(li);
  });
  card.appendChild(ol);
  card.appendChild(el("p", "fine", c.mode === "bus" ? `${c.note} Fare is approximate${c.fare_complete === false ? " and missing for some legs" : ""}. Data as of ${c.as_of}.` : `Estimated times. Fare follows BMRCL slabs, check the official chart. Data as of ${c.as_of}.`));
  const copy = el("button", "btn small"); copy.appendChild(icon("copy")); copy.appendChild(document.createTextNode("Copy summary"));
  copy.onclick = () => { navigator.clipboard.writeText(`${c.origin} to ${c.destination}: ${c.legs.map(l => `${l.mode === "bus" ? l.line : l.line + " Line"} ${l.from} to ${l.to}`).join(", then ")}. About ${c.minutes_estimated} min, approx Rs ${c.fare_inr_approx}.`).then(() => toast("Copied")); };
  card.appendChild(copy);
  return card;
}

/* chat rendering */
function toolBtn(name, label, fn) { const b = el("button"); b.setAttribute("aria-label", label); b.title = label; b.appendChild(icon(name)); b.onclick = () => fn(b); return b; }

function renderMsg(m) {
  const row = el("div", "msg " + m.role);
  if (m.role === "user") { row.textContent = m.text; $("#messages").appendChild(row); return row; }
  const mark = svgEl("svg", { class: "mark" }); mark.appendChild(svgEl("use", { href: "#logo-mark" }));
  row.appendChild(mark);
  const body = el("div", "body"); body.appendChild(md(m.text));
  (m.cards || []).forEach(c => body.appendChild(journeyCard(c)));
  if (m.message_id) {
    const tools = el("div", "tools");
    tools.appendChild(toolBtn("copy", "Copy reply", () => navigator.clipboard.writeText(m.text).then(() => toast("Copied"))));
    const rate = (b, r) => fetch("/api/feedback", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message_id: m.message_id, rating: r }) })
      .then(() => { b.setAttribute("aria-pressed", "true"); toast("Thanks for the feedback"); });
    tools.appendChild(toolBtn("up", "Good answer", b => rate(b, 1)));
    tools.appendChild(toolBtn("down", "Wrong or unhelpful", b => rate(b, -1)));
    body.appendChild(tools);
  }
  row.appendChild(body);
  if (m.error) row.classList.add("err");
  $("#messages").appendChild(row);
  return row;
}

function welcome() {
  const w = el("div", "welcome");
  w.appendChild(el("h2", "", "Where to?"));
  w.appendChild(el("p", "", "Name a station or place and I'll find the way by Namma Metro. I can also answer metro fare and rule questions."));
  return w;
}

function openChat(id) {
  cur = chats.find(c => c.id === id);
  $("#chatTitle").textContent = cur.title;
  const box = $("#messages"); box.replaceChildren();
  if (!cur.messages.length) box.appendChild(welcome());
  cur.messages.forEach(renderMsg);
  $("#chips").hidden = cur.messages.length > 0;
  box.scrollTop = box.scrollHeight;
  renderList(); show("chat");
}
function newChat() {
  if (cur && !cur.messages.length) { openChat(cur.id); return; }
  chats.unshift({ id: uuid(), title: "New chat", messages: [] });
  saveChats(); openChat(chats[0].id);
}
function renderList() {
  const ul = $("#chatList"); ul.replaceChildren();
  chats.forEach(c => {
    const li = el("li", c === cur ? "on" : "");
    const b = el("button", "", c.title); b.onclick = () => openChat(c.id);
    const x = el("button", "del"); x.setAttribute("aria-label", "Delete chat"); x.title = "Delete chat"; x.appendChild(icon("trash"));
    x.onclick = e => {
      e.stopPropagation();
      fetch("/api/reset/" + c.id, { method: "POST" }).catch(() => {});
      chats = chats.filter(k => k !== c); saveChats();
      if (!chats.length) { cur = null; newChat(); }
      else if (cur === c) openChat(chats[0].id);
      else renderList();
      toast("Chat deleted");
    };
    li.appendChild(b); li.appendChild(x); ul.appendChild(li);
  });
}

async function send(text) {
  if (busy) return;
  text = text.trim();
  if (!text) { toast("Type a message first."); return; }
  if (/(\+91|(?<!\d)[6-9]\d{9}(?!\d)|@|\b\d[A-Za-z]{2}\d{2}[A-Za-z]{2}\d{3}\b)/.test(text)) toast("That looks like personal details. They are removed before saving.");
  busy = true; $("#sendBtn").disabled = true;
  if (!cur.messages.length) { $("#messages").replaceChildren(); cur.title = text.slice(0, 32); $("#chatTitle").textContent = cur.title; }
  const um = { role: "user", text }; cur.messages.push(um); renderMsg(um);
  $("#chips").hidden = true;
  $("#input").value = ""; autoGrow();
  const wait = renderMsg({ role: "bot", text: "Checking the metro map..." });
  $("#messages").scrollTop = 1e9;
  try {
    const r = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: cur.id, message: text, language: settings.lang, length: settings.length }) });
    const data = await r.json();
    wait.remove();
    if (!r.ok) renderMsg({ role: "bot", text: data.detail || "Something went wrong. Please try again.", error: true });
    else { const bm = { role: "bot", text: data.reply, cards: data.cards, message_id: data.message_id }; cur.messages.push(bm); renderMsg(bm); }
  } catch {
    wait.remove(); renderMsg({ role: "bot", text: "Cannot reach the server. Check that it is running and your internet is on.", error: true });
  }
  saveChats(); renderList(); busy = false; $("#sendBtn").disabled = false; $("#messages").scrollTop = 1e9;
}

function autoGrow() { const t = $("#input"); t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 140) + "px"; }

/* planner */
let planning = false;
async function plan() {
  if (planning) return; planning = true; setTimeout(() => planning = false, 1500);
  const out = $("#planOut"); out.replaceChildren();
  const pref = $("#planPref").value;
  const body = { origin: $("#planFrom").value, destination: $("#planTo").value, preference: pref };
  if (!body.origin.trim() || !body.destination.trim()) { out.appendChild(el("p", "muted", "Enter both a start and an end station.")); return; }
  try {
    const r = await fetch("/api/route", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const d = await r.json();
    if (!r.ok) { out.appendChild(el("p", "muted", d.detail)); return; }
    out.appendChild(journeyCard(d));
    const ask = el("button", "btn"); ask.textContent = "Ask NammaAI about this route";
    ask.onclick = () => { newChat(); send(`Explain the route from ${d.origin} to ${d.destination}`); };
    out.appendChild(ask);
  } catch { out.appendChild(el("p", "muted", "Cannot reach the server.")); }
}

/* views */
function show(v) {
  document.querySelectorAll(".view").forEach(s => s.hidden = s.id !== "view-" + v);
  document.querySelectorAll(".nav[data-view]").forEach(b => b.setAttribute("aria-current", b.dataset.view === v));
}

/* startup */
function wire() {
  $("#newChat").onclick = newChat;
  document.querySelectorAll(".nav[data-view]").forEach(b => b.onclick = () => show(b.dataset.view));
  $("#themeBtn").onclick = () => { settings.theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark"; $("#setTheme").value = settings.theme; saveSettings(); };
  $("#sendBtn").onclick = () => send($("#input").value);
  $("#input").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send($("#input").value); } });
  $("#input").addEventListener("input", autoGrow);
  document.addEventListener("keydown", e => { if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { e.preventDefault(); show("chat"); $("#input").focus(); } });
  $("#swapBtn").onclick = () => { const a = $("#planFrom"), b = $("#planTo"); [a.value, b.value] = [b.value, a.value]; };
  $("#planGo").onclick = plan;
  $("#exportBtn").onclick = () => {
    if (!cur || !cur.messages.length) { toast("Nothing to export yet."); return; }
    const txt = `# ${cur.title}\n\n` + cur.messages.map(m => `**${m.role === "user" ? "You" : "NammaAI"}:** ${m.text}`).join("\n\n");
    const a = el("a"); a.href = URL.createObjectURL(new Blob([txt], { type: "text/markdown" })); a.download = "nammaai-chat.md"; a.click();
  };
  [["#setTheme", "theme"], ["#setLang", "lang"], ["#setLen", "length"]].forEach(([id, key]) => { $(id).value = settings[key]; $(id).onchange = e => { settings[key] = e.target.value; saveSettings(); }; });
  $("#clearAll").onclick = async () => {
    if (!confirm("Delete all chats?")) return;
    await Promise.all(chats.map(c => fetch("/api/reset/" + c.id, { method: "POST" }).catch(() => {})));
    chats = []; saveChats(); newChat(); toast("All chats deleted");
  };
  CHIPS.forEach(t => { const b = el("button", "", t); b.onclick = () => send(t); $("#chips").appendChild(b); });
  CHIPS.slice(0, 5).forEach(t => { const li = el("li"); const b = el("button", "", t); b.onclick = () => { show("chat"); send(t); }; li.appendChild(b); $("#examples").appendChild(li); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") $("#loader").classList.add("off"); });
}

async function boot() {
  applyTheme(); wire();
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);
  const loader = $("#loader"); loader.onclick = () => loader.classList.add("off");
  const status = $("#loadStatus"); const t0 = Date.now();
  try {
    status.textContent = "Loading stations";
    info = await (await fetch("/api/info")).json();
    status.textContent = "Checking alerts";
  } catch { status.textContent = "Server not responding"; }
  await new Promise(r => setTimeout(r, Math.max(0, 1300 - (Date.now() - t0))));
  status.textContent = "Ready";
  setTimeout(() => loader.classList.add("off"), 250);

  if (info.alerts && info.alerts.length) { const b = $("#banner"); b.hidden = false; b.textContent = "Alert: " + info.alerts[0].text; }
  const dl = $("#stations"); (info.stations || []).forEach(s => { const o = el("option"); o.value = s; dl.appendChild(o); });
  const p = info.providers && info.providers[0];
  $("#note").textContent = (p ? `Messages are sent to ${p.name} to generate replies. ` : "No AI key configured. ") + "Do not share personal details. No live train or bus data. Data as of " + (info.as_of || "n/a") + ".";
  if (chats.length) openChat(chats[0].id); else newChat();
}
boot();
