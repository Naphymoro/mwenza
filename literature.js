// Literature page: searches published papers and passages through the engine's
// Asta connector and lets the student add chosen abstracts or passages to the
// notebook as ordinary sources, with a citation header the auditor can match.

const LITERATURE_MODES = [["papers", "Papers"], ["snippets", "Passages"]];
let literatureRequest = null;
let literatureStatusRequested = false;

function literatureState() {
  state.literature ||= { query: "", mode: "papers", yearFrom: "", yearTo: "", results: null, resultMode: "papers", attribution: "", error: "", status: null };
  return state.literature;
}

function literatureField(name, value) { literatureState()[name] = value; save(); }
function literatureMode(mode) { literatureState().mode = mode; save(); render(); }

async function loadLiteratureStatus() {
  literatureStatusRequested = true;
  const lit = literatureState();
  try { lit.status = await engineGet("/discovery/status"); lit.error = ""; }
  catch (error) { lit.status = null; lit.error = error instanceof TypeError ? engineUnreachableMessage() : error.message; }
  save(); render();
}

async function searchLiterature() {
  const lit = literatureState();
  if (lit.query.trim().length < 3) return notify("Type at least three characters to search.");
  literatureRequest?.abort();
  literatureRequest = new AbortController();
  const timer = setTimeout(() => literatureRequest?.abort(), 95000);
  lit.error = ""; lit.results = null;
  render();
  try {
    const body = { query: lit.query.trim(), limit: 10, ...(lit.yearFrom ? { year_from: Number(lit.yearFrom) } : {}), ...(lit.yearTo ? { year_to: Number(lit.yearTo) } : {}) };
    const response = await fetch(`${engineUrl()}/discovery/${lit.mode}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: literatureRequest.signal });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || `The engine returned HTTP ${response.status}.`);
    Object.assign(lit, { results: payload.results, resultMode: lit.mode, attribution: payload.attribution });
  } catch (error) {
    lit.error = error.name === "AbortError" ? "The search took longer than 95 seconds and was stopped. Unauthenticated access to Asta can be very slow; ask your administrator to configure ASTA_API_KEY." : error instanceof TypeError ? engineUnreachableMessage() : error.message;
  } finally {
    clearTimeout(timer);
    literatureRequest = null;
  }
  save(); render();
}

function shortAuthors(authors) {
  const surnames = authors.map((name) => name.trim().split(/\s+/).at(-1));
  return surnames.length > 2 ? `${surnames[0]} et al.` : surnames.join(" & ") || "Unknown author";
}

function citationHeader(paper) {
  const authors = paper.authors.length ? paper.authors.join(", ") : "Unknown author";
  return `${authors} (${paper.year || "n.d."}). ${paper.title}.${paper.venue ? ` ${paper.venue}.` : ""}`;
}

function literatureSourceId(prefix, value) { return `${prefix}-${String(value).replace(/[^\w.-]/g, "").slice(0, 100)}`; }

function addLiteratureSource(id, name, body, paper, kind) {
  if (source(id)) return notify("Already in your notebook.");
  const today = new Date().toISOString().slice(0, 10);
  const text = `${citationHeader(paper)}\n\n${body}\n\n${paper.url ? `Source: ${paper.url}\n` : ""}${kind} retrieved via the Asta Scientific Corpus Tool (Ai2) on ${today}. Read the full paper before citing it.`;
  state.sources.unshift({ id, name, type: "Paper", detail: `${kind} via Asta (Ai2)`, text });
  state.selectedSourceIds.push(id);
  save(); render(); notify(`Added to your notebook and selected: ${name}.`);
}

function addPaper(index) {
  const paper = literatureState().results[index];
  addLiteratureSource(literatureSourceId("asta", paper.paper_id), `${shortAuthors(paper.authors)} ${paper.year || "n.d."} — ${paper.title}`, paper.abstract || paper.tldr, paper, paper.abstract ? "Abstract" : "Summary");
}

function addSnippet(index) {
  const snippet = literatureState().results[index];
  const paper = snippet.paper;
  addLiteratureSource(literatureSourceId("asta-passage", `${paper.paper_id}-${snippet.text.length}-${snippet.text.slice(0, 24)}`), `${shortAuthors(paper.authors)} ${paper.year || "n.d."} — passage${snippet.section ? ` (${snippet.section})` : ""}`, snippet.text, paper, "Passage");
}

function renderPaperCard(paper, index) {
  const id = literatureSourceId("asta", paper.paper_id);
  const body = paper.abstract || paper.tldr;
  const added = Boolean(source(id));
  return `<article class="gt-issue lit-card"><div class="lit-head"><h3>${paper.url ? `<a href="${esc(paper.url)}" target="_blank" rel="noopener noreferrer">${esc(paper.title)}</a>` : esc(paper.title)}</h3>${paper.open_access ? `<span class="gt-sev ok">Open access</span>` : ""}</div><p class="lit-meta">${esc(paper.authors.slice(0, 6).join(", "))}${paper.authors.length > 6 ? " et al." : ""} · ${paper.year || "n.d."}${paper.venue ? ` · ${esc(paper.venue)}` : ""}</p>${body ? `<p class="lit-abstract">${esc(body)}</p>` : `<p class="ca-hint">No abstract available from the corpus.</p>`}<div class="lit-actions">${body ? `<button class="gt-btn ${added ? "ghost" : "primary"}" ${added ? "disabled" : ""} onclick="addPaper(${index})">${added ? "In your notebook" : `Add ${paper.abstract ? "abstract" : "summary"} to notebook`}</button>` : ""}</div></article>`;
}

function renderSnippetCard(snippet, index) {
  const paper = snippet.paper;
  return `<article class="gt-issue lit-card"><blockquote class="ca-quote"><span>${esc(paper.title || "Untitled paper")}${paper.year ? ` · ${paper.year}` : ""}${snippet.section ? ` · ${esc(snippet.section)}` : ""}</span>${esc(snippet.text)}</blockquote><p class="lit-meta">${esc(paper.authors.slice(0, 6).join(", "))}${paper.url ? ` · <a href="${esc(paper.url)}" target="_blank" rel="noopener noreferrer">Open paper</a>` : ""}</p><div class="lit-actions"><button class="gt-btn primary" onclick="addSnippet(${index})">Add passage to notebook</button></div></article>`;
}

function renderLiteratureStatus(status) {
  const licence = status.licence;
  if (!status.enabled) return `<div class="gt-empty"><strong>Literature search is off for this engine.</strong><p>Mwenza searches published research through Ai2's Asta Scientific Corpus Tool. Its licence allows academic, non-commercial research only, so each deployment turns it on and uses its own key.</p><pre class="pv-declaration">MWENZA_ASTA=on ASTA_API_KEY=your-key \\\n  uvicorn mwenza_engine.api:app --app-dir backend/src</pre><p class="ca-hint"><a href="${esc(licence.url)}" target="_blank" rel="noopener noreferrer">Read the licence</a> · <a href="${esc(licence.key_request_url)}" target="_blank" rel="noopener noreferrer">Request an API key</a> · Without a key, searches can take minutes.</p></div>`;
  return `<p class="lit-licence">${esc(status.attribution)} ${esc(licence.summary)} ${status.keyed ? "" : "<b>No API key is configured, so searches may be slow.</b>"} <a href="${esc(licence.url)}" target="_blank" rel="noopener noreferrer">Licence</a></p>`;
}

function renderLiterature() {
  const lit = literatureState();
  if (!literatureStatusRequested) setTimeout(loadLiteratureStatus);
  const busy = Boolean(literatureRequest);
  const status = lit.status;
  const results = lit.results;
  return `<div class="gt-page">
    <section class="gt-intro"><span class="m-kicker">Phase 1 · Literature</span><h1>Find literature</h1><p>Search published research beyond your notebook, then add the abstracts or passages you want to work with. Added items become ordinary sources: the citation audit can check claims against them, and the golden thread can use them as gap evidence.</p></section>
    <div class="gt-layout">
      ${!status && lit.error ? `<div class="gt-error"><strong>Couldn't reach the engine</strong><p>${esc(lit.error)}</p></div>` : ""}
      ${status ? renderLiteratureStatus(status) : ""}
      ${status?.enabled ? `<form class="gt-form lit-form" onsubmit="event.preventDefault(); searchLiterature()">
        <div class="pv-tabs gt-intro-actions" role="tablist">${LITERATURE_MODES.map(([id, label]) => `<button type="button" role="tab" aria-selected="${lit.mode === id}" class="gt-btn ${lit.mode === id ? "primary" : "ghost"}" onclick="literatureMode('${id}')">${label}</button>`).join("")}</div>
        <label class="gt-field"><span>${lit.mode === "papers" ? "Search papers" : "Find passages that say"}</span><input value="${esc(lit.query)}" placeholder="${lit.mode === "papers" ? "e.g. skilled birth attendance distance Kenya" : "e.g. distance to a facility reduces skilled birth attendance"}" oninput="literatureField('query', this.value)" /></label>
        ${lit.mode === "papers" ? `<div class="gt-row"><label class="gt-field"><span>From year</span><input type="number" min="1800" max="2100" value="${esc(lit.yearFrom)}" oninput="literatureField('yearFrom', this.value)" /></label><label class="gt-field"><span>To year</span><input type="number" min="1800" max="2100" value="${esc(lit.yearTo)}" oninput="literatureField('yearTo', this.value)" /></label></div>` : ""}
        <div class="gt-submit">${renderEngineField()}<button class="gt-btn primary" type="submit" ${busy ? "disabled" : ""}>${busy ? "Searching…" : "Search"}</button></div>
      </form>` : ""}
      ${busy ? `<div class="gt-empty"><strong>Searching the corpus…</strong><p>This can take up to a minute, longer without an API key.</p></div>` : ""}
      ${status?.enabled && lit.error ? `<div class="gt-error"><strong>Search didn't complete</strong><p>${esc(lit.error)}</p></div>` : ""}
      ${results && !busy ? `<section class="gt-panel"><div class="gt-panel-head"><strong>${results.length} ${lit.resultMode === "papers" ? "papers" : "passages"}</strong><span>${esc(lit.attribution)}</span></div><div class="gt-issues">${results.length ? results.map(lit.resultMode === "papers" ? renderPaperCard : renderSnippetCard).join("") : `<div class="gt-empty small">Nothing found. Try broader terms or remove the year limits.</div>`}</div></section>` : ""}
    </div>
  </div>`;
}
