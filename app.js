const STORAGE_KEY = "mwenza-workspace-v1";

const STUDIO_ARTIFACTS = [
  ["briefing", "Briefing", "A concise overview of the selected sources."],
  ["study-guide", "Study guide", "Key concepts, questions, and revision prompts."],
  ["faq", "FAQ", "Questions and answers grounded in the selected material."],
  ["timeline", "Timeline", "Important dates and events found in the sources."],
  ["mind-map", "Mind map", "A text-based map of concepts and relationships."],
  ["audio", "Audio overview", "A production placeholder for background audio generation."],
];

const AGENTS = [
  ["librarian", "Librarian", "Maps questions to bounded evidence.", "source-librarian"],
  ["methodologist", "Methodologist", "Reviews methods, assumptions, and limitations.", "method-critic"],
  ["skeptic", "Sceptic", "Hunts contradictions and missing evidence.", "contradiction-hunter"],
  ["reproducer", "Reproducer", "Designs traceable analysis runs.", "reproducer"],
  ["scout", "Scout", "Plans lawful literature monitoring.", "research-scout"],
  ["synthesiser", "Synthesiser", "Creates grounded research syntheses.", "evidence-editor"],
];

const DEMO_SOURCES = [
  { id: "demo-1", name: "Welcome to Mwenza", type: "Guide", detail: "Built-in guide", text: "Mwenza is a source-grounded research notebook. It answers questions from the sources selected in a notebook, cites the source used, and says when the knowledge base does not contain an answer." },
  { id: "demo-2", name: "Research workflow notes", type: "Notes", detail: "Built-in example", text: "A useful research workflow is to collect sources, ask focused questions, compare evidence, save useful notes, and turn the material into a briefing or study guide." },
];

function loadWorkspace() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    if (saved) return saved;
  } catch (_) {}
  return { page: "overview", query: "", selectedSourceIds: DEMO_SOURCES.map((source) => source.id), sources: DEMO_SOURCES, messages: [], artifacts: [], modal: null, toast: "" };
}

const state = loadWorkspace();
const save = () => localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...state, modal: null, toast: "" }));
const source = (id) => state.sources.find((item) => item.id === id);
const selectedSources = () => state.sources.filter((item) => state.selectedSourceIds.includes(item.id));
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[char]);
const icon = (name) => ({ book: "▣", chat: "◌", studio: "✦", plus: "+", search: "⌕", close: "×", upload: "↑", note: "▤", link: "↗" }[name] || "•");

function notify(message) { state.toast = message; save(); render(); window.clearTimeout(window.__mwenzaToast); window.__mwenzaToast = window.setTimeout(() => { state.toast = ""; render(); }, 2600); }

function addSourceFromText(name, type, text, detail = "Added locally") {
  const id = `source-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  state.sources.unshift({ id, name, type, detail, text: String(text || "").slice(0, 120000) });
  state.selectedSourceIds.push(id);
  state.page = "sources";
  state.modal = null;
  save(); render();
}

function openAddSource() { state.modal = "add-source"; render(); }
function closeModal() { state.modal = null; render(); }

function submitSource(event) {
  event.preventDefault();
  const form = new FormData(event.target);
  addSourceFromText(form.get("name") || "Untitled source", form.get("type") || "Notes", form.get("text") || "", "Added locally");
  notify("Source added to this notebook.");
}

function handleFiles(input) {
  [...(input.files || [])].forEach((file) => {
    const reader = new FileReader();
    reader.onload = () => addSourceFromText(file.name, file.type.includes("pdf") ? "PDF" : "File", reader.result, `${Math.round(file.size / 1024)} KB`);
    reader.onerror = () => notify(`Could not read ${file.name}.`);
    reader.readAsText(file);
  });
}

function toggleSource(id) {
  state.selectedSourceIds = state.selectedSourceIds.includes(id) ? state.selectedSourceIds.filter((item) => item !== id) : [...state.selectedSourceIds, id];
  save(); render();
}

function terms(text) { return [...new Set(String(text).toLowerCase().replace(/[^a-z0-9\s]/g, " ").split(/\s+/).filter((term) => term.length > 3))]; }
function retrieve(question) {
  const queryTerms = terms(question);
  return selectedSources().map((item) => {
    const sourceTerms = terms(`${item.name} ${item.text}`);
    const score = queryTerms.filter((term) => sourceTerms.includes(term)).length;
    return { item, score };
  }).filter((result) => result.score > 0).sort((a, b) => b.score - a.score);
}

function groundedAnswer(question) {
  const hits = retrieve(question).slice(0, 3);
  if (!hits.length) return { title: "Not in this notebook", text: "I do not have that information in the selected sources. I will not guess or use outside information.", citations: [] };
  const snippets = hits.map(({ item }) => {
    const lower = item.text.toLowerCase();
    const firstTerm = terms(question).find((term) => lower.includes(term));
    const start = Math.max(0, lower.indexOf(firstTerm || "") - 80);
    return item.text.slice(start, start + 300).trim();
  });
  return { title: "Grounded answer", text: snippets.join(" "), citations: hits.map(({ item }) => item.name) };
}

function ask(question) {
  const text = String(question || "").trim();
  if (!text) return;
  state.messages.push({ role: "user", text });
  state.messages.push({ role: "assistant", answer: groundedAnswer(text) });
  state.page = "chat";
  save(); render();
  requestAnimationFrame(() => document.querySelector(".chat-messages")?.scrollTo(0, 99999));
}

function runAgent(agentId) {
  const objective = window.prompt("What should this agent investigate in the selected sources?", "Summarise the strongest evidence and identify what remains uncertain.");
  if (!objective) return;
  const agent = AGENTS.find((item) => item[0] === agentId);
  const answer = groundedAnswer(objective);
  state.messages.push({ role: "assistant", answer: { title: `${agent[1]} run completed`, text: answer.text, citations: answer.citations, steps: ["Scoped selected sources", "Applied evidence-first policy", "Retrieved supporting passages", answer.citations.length ? "Prepared reviewable result" : "Abstained: needs more evidence"] } });
  state.page = "agents";
  save(); render();
}

function generateArtifact(kind) {
  const selected = selectedSources();
  if (!selected.length) return notify("Select at least one source first.");
  const meta = STUDIO_ARTIFACTS.find((item) => item[0] === kind);
  let body = "";
  if (kind === "audio") body = "Audio generation is queued for the Mwenza processing service. This browser prototype stores the request and keeps research available while generation runs.";
  else if (kind === "mind-map") body = selected.map((item) => `• ${item.name}\n  └─ ${item.text.slice(0, 180)}`).join("\n");
  else body = selected.map((item) => `${item.name}\n${item.text.slice(0, 500)}`).join("\n\n");
  state.artifacts.unshift({ id: `artifact-${Date.now()}`, type: meta[0], title: meta[1], body, createdAt: new Date().toISOString(), sourceNames: selected.map((item) => item.name) });
  state.page = "studio";
  save(); render(); notify(`${meta[1]} created from ${selected.length} source${selected.length === 1 ? "" : "s"}.`);
}

function renderSidebar() {
  return `<aside class="sidebar"><div class="brand"><div class="brand-mark">M</div><div><strong>Mwenza</strong><span>Evidence operating system</span></div></div><div class="workspace-switcher"><label>Notebook</label><select aria-label="Current notebook"><option>Research workspace</option></select></div><nav class="nav">${[["overview", "Overview", "book"], ["sources", "Sources", "upload"], ["chat", "Ask the notebook", "chat"], ["agents", "Agent lab", "studio"], ["studio", "Studio", "studio"]].map(([id, label, glyph]) => `<button class="${state.page === id ? "active" : ""}" onclick="go('${id}')">${icon(glyph)}<span>${label}</span></button>`).join("")}</nav><div class="sidebar-foot">Agents operate with bounded sources, least-privilege tools, visible steps, and an explicit abstention path.</div></aside>`;
}

function renderHeader(title, subtitle) { return `<header class="topbar"><div><h1>${title}</h1><p>${subtitle}</p></div><div class="top-actions"><label class="search">${icon("search")}<input placeholder="Search sources and artifacts…" value="${esc(state.query)}" oninput="state.query=this.value; render()" /></label><button class="button primary" onclick="openAddSource()">${icon("plus")}Add source</button></div></header>`; }

function renderSourceRow(item) {
  const checked = state.selectedSourceIds.includes(item.id);
  return `<div class="source-row ${checked ? "selected" : ""}"><input class="source-check" type="checkbox" ${checked ? "checked" : ""} onchange="toggleSource('${item.id}')" aria-label="Select ${esc(item.name)}" /><div class="source-icon">${esc(item.type.slice(0, 1))}</div><div class="source-main"><strong>${esc(item.name)}</strong><small>${esc(item.type)} · ${esc(item.detail)}</small></div><button class="icon-button" title="Open source" onclick="notify('Source preview will open here in the next backend slice.')">${icon("link")}</button></div>`;
}

function renderSourcesCard() { const list = state.sources.filter((item) => !state.query || `${item.name} ${item.text}`.toLowerCase().includes(state.query.toLowerCase())); return `<section class="card"><div class="card-header"><div><h2>Sources</h2><p>Select the evidence Mwenza may use for its answers and artifacts.</p></div><span class="eyebrow">${selectedSources().length} selected</span></div><div class="card-body"><div class="source-list">${list.length ? list.map(renderSourceRow).join("") : `<div class="empty">No sources match your search.</div>`}</div></div></section>`; }

function renderChat() {
  const messages = state.messages.length ? state.messages.map((message) => message.role === "user" ? `<div class="message user">${esc(message.text)}</div>` : `<div class="message assistant"><strong>${esc(message.answer.title)}</strong><div>${esc(message.answer.text)}</div>${message.answer.citations.length ? `<div class="citations">${message.answer.citations.map((item) => `<span class="citation">${esc(item)}</span>`).join("")}</div>` : ""}</div>`).join("") : `<div class="empty">Ask a question about the selected sources. If the answer is not there, Mwenza will say so.</div>`;
  return `<section class="card chat-card"><div class="card-header"><div><h2>Ask the notebook</h2><p>Grounded answers with source citations.</p></div><span class="eyebrow">${selectedSources().length} sources in scope</span></div><div class="chat-messages">${messages}</div><form class="chat-composer" onsubmit="event.preventDefault(); ask(this.elements.question.value); this.reset()"><textarea name="question" placeholder="Ask about the selected sources…" required></textarea><button class="button blue" type="submit">${icon("chat")}Ask</button></form></section>`;
}

function renderStudio() { const visible = state.artifacts.filter((item) => !state.query || `${item.title} ${item.body}`.toLowerCase().includes(state.query.toLowerCase())); return `<section class="card"><div class="card-header"><div><h2>Studio</h2><p>Turn selected sources into useful research artifacts.</p></div><span class="eyebrow">Background-ready</span></div><div class="card-body"><div class="studio-grid">${STUDIO_ARTIFACTS.map(([id, title, description]) => `<button class="studio-card" onclick="generateArtifact('${id}')"><strong>${icon(id === "audio" ? "studio" : "note")} ${title}</strong><span>${description}</span></button>`).join("")}</div><div class="artifact-list" style="margin-top:18px">${visible.map((item) => `<article class="artifact-row"><div class="source-icon">✦</div><div class="artifact-main"><strong>${esc(item.title)}</strong><small>${esc(item.sourceNames.join(", "))}</small><p>${esc(item.body.slice(0, 260))}${item.body.length > 260 ? "…" : ""}</p></div></article>`).join("") || `<div class="empty">Generated artifacts will appear here.</div>`}</div></div></section>`; }

function renderAgents() { return `<section class="card agent-lab"><div class="card-header"><div><h2>Agent lab</h2><p>Give a specialist a bounded research objective. Every run exposes its steps and citations.</p></div><span class="eyebrow">${selectedSources().length} sources in scope</span></div><div class="card-body"><div class="agent-grid">${AGENTS.map(([id, name, description, skill]) => `<article class="agent-card"><div class="agent-orb">✦</div><div><strong>${name}</strong><small>${skill}</small><p>${description}</p></div><button class="button blue" onclick="runAgent('${id}')">Run agent</button></article>`).join("")}</div><div class="run-log"><h3>Current workspace trace</h3>${state.messages.filter((item) => item.role === "assistant" && item.answer.steps).slice(-4).reverse().map((item) => `<article class="run-card"><div><strong>${esc(item.answer.title)}</strong><p>${esc(item.answer.text.slice(0, 260))}</p><div class="trace">${item.answer.steps.map((step) => `<span>${esc(step)}</span>`).join("")}</div></div>${item.answer.citations.length ? `<div class="citations">${item.answer.citations.map((citation) => `<span class="citation">${esc(citation)}</span>`).join("")}</div>` : ""}</article>`).join("") || `<div class="empty">No agent runs yet. Choose a specialist above.</div>`}</div></div></section>`; }

function renderOverview() { return `<div class="hero"><section class="hero-card"><span class="eyebrow">Research workspace</span><h2>Understand your sources before you write.</h2><p>Mwenza is a focused notebook for collecting evidence, asking grounded questions, and turning research material into briefings, guides, maps, and future audio conversations.</p><div class="hero-actions"><button class="button primary" onclick="go('sources')">${icon("upload")}Add or select sources</button><button class="button ghost" onclick="go('chat')">${icon("chat")}Ask a question</button></div></section><section class="stats-card card"><div class="stat"><strong>${state.sources.length}</strong><span>sources in this notebook</span></div><div class="stat"><strong>${selectedSources().length}</strong><span>sources currently in scope</span></div><div class="stat"><strong>${state.artifacts.length}</strong><span>saved studio artifacts</span></div></section></div><div class="workspace-grid"><div>${renderSourcesCard()}</div><div>${renderStudio()}</div></div>`; }

function renderAddSourceModal() { return `<div class="modal-backdrop" onclick="if(event.target===this) closeModal()"><form class="modal" onsubmit="submitSource(event)"><div class="card-header"><div><h2>Add a source</h2><p>Paste a text source now; file and URL connectors can use the same boundary.</p></div><button type="button" class="icon-button" onclick="closeModal()">${icon("close")}</button></div><div class="modal-body"><label>Choose local text file<input type="file" accept=".txt,.md,.csv,.json,.html,text/plain,text/markdown,text/csv,application/json" onchange="handleFiles(this)" /></label><label>Source name<input name="name" placeholder="e.g. Fieldwork notes" required /></label><label>Source type<select name="type"><option>Notes</option><option>PDF</option><option>Website</option><option>YouTube</option><option>Google Doc</option></select></label><label>Source text<textarea name="text" placeholder="Paste the source text here…" required></textarea></label></div><div class="modal-footer"><button type="button" class="button ghost" onclick="closeModal()">Cancel</button><button class="button primary" type="submit">Add source</button></div></form></div>`; }

function render() { const titles = { overview: ["Research workspace", "Collect, question, and synthesize from selected evidence."], sources: ["Sources", "Choose what the notebook is allowed to use."], chat: ["Ask the notebook", "Answers stay within the selected knowledge base."], agents: ["Agent lab", "Specialists collaborate through visible, reviewable research steps."], studio: ["Studio", "Create research artifacts from your sources."] }; const [title, subtitle] = titles[state.page] || titles.overview; document.querySelector("#app").innerHTML = `<div class="shell">${renderSidebar()}<main class="main">${renderHeader(title, subtitle)}<div class="content">${state.page === "overview" ? renderOverview() : state.page === "sources" ? renderSourcesCard() : state.page === "chat" ? renderChat() : state.page === "agents" ? renderAgents() : renderStudio()}</div></main></div>${state.modal === "add-source" ? renderAddSourceModal() : ""}${state.toast ? `<div class="toast">${esc(state.toast)}</div>` : ""}`; }

function go(page) { state.page = page; save(); render(); }
window.go = go; window.openAddSource = openAddSource; window.closeModal = closeModal; window.submitSource = submitSource; window.handleFiles = handleFiles; window.toggleSource = toggleSource; window.ask = ask; window.runAgent = runAgent; window.generateArtifact = generateArtifact; window.notify = notify;
render();
