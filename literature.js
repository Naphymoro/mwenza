// Literature page: searches open scholarly metadata (OpenAlex, Crossref, DOAJ)
// by default, or Ai2's Asta where an engine enables it. Students add chosen
// works to the notebook; the engine's licence fields decide whether an
// abstract can be stored or only the reference.

const LITERATURE_DOCUMENT = "literature";
const LITERATURE_MODES = [["papers", "Papers"], ["snippets", "Passages"]];
const SOURCE_LABELS = { openalex: "OpenAlex", crossref: "Crossref", doaj: "DOAJ", opencitations: "OpenCitations", asta: "Asta", europepmc: "Europe PMC", arxiv: "arXiv", africarxiv: "AfricArXiv" };
const LITERATURE_SCOPES = [["all", "All"], ["peer-reviewed", "Peer-reviewed only"], ["preprints", "Preprints only"]];
const REUSE_LABELS = { yes: ["Full text reusable", "ok"], restricted: ["Reuse restricted", "warning"], no: ["Full text not reusable", "info"], unknown: ["Reuse unknown", "info"] };
let literatureRequest = null;
let literatureStatusRequested = false;

function literatureState() {
  state.literature ||= { query: "", mode: "papers", provider: "open", yearFrom: "", yearTo: "", results: null, resultMode: "papers", resultProvider: "open", attribution: "", sourcesStatus: {}, error: "", status: null, citations: {} };
  state.literature.citations ||= {};
  state.literature.provider ||= "open";
  state.literature.scope ||= "all";
  return state.literature;
}

function literatureField(name, value) { literatureState()[name] = value; save(); }
function literatureScope(scope) { literatureState().scope = scope; save(); render(); }
function literatureMode(mode) { literatureState().mode = mode; save(); render(); }
function literatureProvider(provider) { const lit = literatureState(); lit.provider = provider; if (provider === "open") lit.mode = "papers"; save(); render(); }

async function loadLiteratureStatus() {
  literatureStatusRequested = true;
  const lit = literatureState();
  try {
    lit.status = await engineGet("/discovery/status");
    lit.error = "";
    if (lit.provider === "asta" && !lit.status.providers.asta.enabled) lit.provider = "open";
  } catch (error) {
    lit.status = null;
    lit.error = error instanceof TypeError ? engineUnreachableMessage() : error.message;
  }
  save(); render();
}

async function searchLiterature() {
  const lit = literatureState();
  if (lit.query.trim().length < 3) return notify("Type at least three characters to search.");
  literatureRequest?.abort();
  literatureRequest = new AbortController();
  const timer = setTimeout(() => literatureRequest?.abort(), 95000);
  Object.assign(lit, { error: "", results: null, citations: {} });
  render();
  try {
    const body = { query: lit.query.trim(), limit: 15, provider: lit.provider, scope: lit.scope, document_id: LITERATURE_DOCUMENT, ...(lit.yearFrom ? { year_from: Number(lit.yearFrom) } : {}), ...(lit.yearTo ? { year_to: Number(lit.yearTo) } : {}) };
    const response = await fetch(`${engineUrl()}/discovery/${lit.mode}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: literatureRequest.signal });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || `The engine returned HTTP ${response.status}.`);
    Object.assign(lit, { results: payload.results, resultMode: lit.mode, resultProvider: payload.provider, attribution: payload.attribution, sourcesStatus: payload.sources_status || {} });
    markProvenanceStale();
  } catch (error) {
    lit.error = error.name === "AbortError" ? "The search took longer than 95 seconds and was stopped." : error instanceof TypeError ? engineUnreachableMessage() : error.message;
  } finally {
    clearTimeout(timer);
    literatureRequest = null;
  }
  save(); render();
}

async function checkPublished(index) {
  const lit = literatureState();
  const work = lit.results[index];
  work.checking = true; render();
  try {
    const payload = await enginePost("/discovery/published-version", { doi: work.doi });
    if (payload.published) Object.assign(work, payload.published);
    else work.published_checked = true;
  } catch (error) {
    notify(error instanceof TypeError ? engineUnreachableMessage() : error.message);
  } finally {
    delete work.checking;
  }
  save(); render();
}

async function toggleCitations(index, direction) {
  const lit = literatureState();
  const doi = lit.results[index].doi;
  const current = lit.citations[doi];
  if (current && current.direction === direction && !current.loading) { delete lit.citations[doi]; save(); return render(); }
  lit.citations[doi] = { direction, loading: true, results: [], error: "" };
  render();
  try {
    const payload = await enginePost("/discovery/citations", { doi, direction, limit: 15 });
    lit.citations[doi] = { direction, loading: false, results: payload.results, error: "" };
  } catch (error) {
    lit.citations[doi] = { direction, loading: false, results: [], error: error instanceof TypeError ? engineUnreachableMessage() : error.message };
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

function addLiteratureSource(id, name, detail, body) {
  if (source(id)) return notify("Already in your notebook.");
  state.sources.unshift({ id, name, type: "Paper", detail, text: body });
  state.selectedSourceIds.push(id);
  save(); render(); notify(`Added to your notebook and selected: ${name}.`);
}

function addWork(work) {
  const today = new Date().toISOString().slice(0, 10);
  const name = `${shortAuthors(work.authors)} ${work.year || "n.d."} — ${work.title}`;
  const link = work.url ? `\nRead it at: ${work.url}` : "";
  if (work.sources?.includes("asta") || work.abstract_storable === undefined) {
    const body = work.abstract || work.tldr;
    return addLiteratureSource(literatureSourceId("asta", work.paper_id), name, `${work.abstract ? "Abstract" : "Summary"} via Asta (Ai2)`, `${citationHeader(work)}\n\n${body}\n${link}\n${work.abstract ? "Abstract" : "Summary"} retrieved via the Asta Scientific Corpus Tool (Ai2) on ${today}. Read the full paper before citing it.`);
  }
  const via = `${work.sources.map((key) => SOURCE_LABELS[key] || key).join(", ")} on ${today}`;
  const preprintNote = work.preprint ? `\nPREPRINT on ${work.server || "a preprint server"}: not peer reviewed.${work.published_url ? ` Published version (${work.published_source}): ${work.published_venue || work.published_doi} ${work.published_url}` : ""}` : "";
  const retraction = work.retracted ? "\nWARNING: this work has been retracted. Do not cite it as evidence; if you discuss it, say that it was retracted." : "";
  if (work.retracted && !window.confirm("This work has been retracted. Add it to your notebook anyway, marked as retracted?")) return;
  if (work.abstract_storable) {
    return addLiteratureSource(literatureSourceId("oa", work.doi || work.paper_id), name, `${work.preprint ? "Preprint · " : ""}Abstract via ${SOURCE_LABELS[work.abstract_source] || work.abstract_source} (${work.abstract_licence})`, `${citationHeader(work)}\n\n${work.abstract}\n${link}\nAbstract licence: ${work.abstract_licence}. Retrieved from ${via}. Read the full paper before citing it.${preprintNote}${retraction}`);
  }
  const reason = work.link_only ? "the hosting platform does not permit reusing it" : work.abstract ? "it may be under publisher copyright" : "no openly licensed abstract was found";
  addLiteratureSource(literatureSourceId("oa", work.doi || work.paper_id), name, work.preprint ? "Preprint · reference only" : "Reference only", `${citationHeader(work)}\n\nAbstract not stored because ${reason}.${link}\nReference retrieved from ${via}. Read the paper before citing it; Mwenza cannot check claims against a reference-only source.${preprintNote}${retraction}`);
}

function addPaper(index) { addWork(literatureState().results[index]); }
function addCitedWork(doi, index) { addWork(literatureState().citations[doi].results[index]); }

function addSnippet(index) {
  const snippet = literatureState().results[index];
  const paper = snippet.paper;
  const today = new Date().toISOString().slice(0, 10);
  addLiteratureSource(literatureSourceId("asta-passage", `${paper.paper_id}-${snippet.text.length}-${snippet.text.slice(0, 24)}`), `${shortAuthors(paper.authors)} ${paper.year || "n.d."} — passage${snippet.section ? ` (${snippet.section})` : ""}`, "Passage via Asta (Ai2)", `${citationHeader(paper)}\n\n${snippet.text}\n\n${paper.url ? `Source: ${paper.url}\n` : ""}Passage retrieved via the Asta Scientific Corpus Tool (Ai2) on ${today}. Read the full paper before citing it.`);
}

function addLabel(work) {
  if (work.abstract_storable === undefined) return work.abstract ? "Add abstract to notebook" : "Add summary to notebook";
  return work.abstract_storable ? "Add abstract to notebook" : "Add reference only";
}

function workIdFor(work) { return work.abstract_storable === undefined ? literatureSourceId("asta", work.paper_id) : literatureSourceId("oa", work.doi || work.paper_id); }

function renderWorkBadges(work) {
  if (work.abstract_storable === undefined) return work.open_access ? `<span class="gt-sev ok">Open access</span>` : "";
  const reuse = REUSE_LABELS[work.fulltext_reuse] || REUSE_LABELS.unknown;
  return [
    work.retracted ? `<span class="gt-sev error">Retracted</span>` : "",
    work.preprint ? `<span class="gt-sev warning" title="Not peer reviewed">Preprint${work.server ? ` · ${esc(work.server)}` : ""}</span>` : "",
    work.language && work.language !== "en" ? `<span class="gt-sev info">${esc(work.language.toUpperCase())}</span>` : "",
    work.link_only ? `<span class="gt-sev warning">Link only</span>` : "",
    work.open_access ? `<span class="gt-sev ok">Open access${work.oa_licence ? ` · ${esc(work.oa_licence.toUpperCase())}` : ""}</span>` : "",
    work.open_access && !work.link_only ? `<span class="gt-sev ${reuse[1]}">${reuse[0]}</span>` : "",
  ].join("");
}

function renderCitationList(work) {
  const entry = literatureState().citations[work.doi];
  if (!entry) return "";
  if (entry.loading) return `<div class="lit-cites"><p class="ca-hint">Looking up ${entry.direction === "citing" ? "works that cite this" : "works this cites"}…</p></div>`;
  if (entry.error) return `<div class="lit-cites"><p class="ca-hint">${esc(entry.error)}</p></div>`;
  if (!entry.results.length) return `<div class="lit-cites"><p class="ca-hint">OpenCitations has no ${entry.direction === "citing" ? "citing works" : "references"} recorded for this DOI.</p></div>`;
  return `<div class="lit-cites"><strong>${entry.direction === "citing" ? "Cited by" : "References"} (${entry.results.length}, from OpenCitations)</strong><ul>${entry.results.map((item, index) => `<li><a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.title || item.doi)}</a>${item.year ? ` · ${item.year}` : ""}${item.authors.length ? ` · ${esc(shortAuthors(item.authors))}` : ""}${item.title ? `<button class="gt-link" ${source(workIdFor(item)) ? "disabled" : ""} onclick="addCitedWork('${esc(work.doi)}', ${index})">${source(workIdFor(item)) ? "In notebook" : addLabel(item).replace(" to notebook", "")}</button>` : ""}</li>`).join("")}</ul></div>`;
}

function renderPaperCard(work, index) {
  const body = work.abstract || work.tldr;
  const added = Boolean(source(workIdFor(work)));
  const canAdd = work.abstract_storable !== undefined || body;
  const sources = (work.sources || []).filter((key) => key !== "opencitations").map((key) => SOURCE_LABELS[key] || key).join(" · ");
  const cites = literatureState().citations[work.doi];
  return `<article class="gt-issue lit-card"><div class="lit-head"><h3>${work.url ? `<a href="${esc(work.url)}" target="_blank" rel="noopener noreferrer">${esc(work.title)}</a>` : esc(work.title)}</h3><div class="lit-badges">${renderWorkBadges(work)}</div></div><p class="lit-meta">${esc(work.authors.slice(0, 6).join(", "))}${work.authors.length > 6 ? " et al." : ""} · ${work.year || "n.d."}${work.venue ? ` · ${esc(work.venue)}` : ""}${Number.isInteger(work.cited_by_count) ? ` · cited by ${work.cited_by_count}` : ""}${sources ? ` · <span class="lit-sources">via ${esc(sources)}</span>` : ""}</p>${body ? `<p class="lit-abstract">${esc(body)}</p>` : `<p class="ca-hint">No abstract available.</p>`}${work.abstract_licence ? `<p class="lit-licence-line">Abstract: ${esc(work.abstract_licence)}</p>` : ""}${work.published_url ? `<p class="lit-published">Published version: <a href="${esc(work.published_url)}" target="_blank" rel="noopener noreferrer">${esc(work.published_venue || work.published_doi)}</a> <span>(${esc(work.published_source)})</span></p>` : ""}${(work.notes || []).filter((note) => !note.startsWith("A published version exists")).map((note) => `<p class="lit-note">${esc(note)}</p>`).join("")}${work.preprint && !work.published_url && (work.doi || "").startsWith("10.1101/") ? (work.published_checked ? `<p class="ca-hint">bioRxiv and medRxiv report no published version yet.</p>` : `<button class="gt-link lit-check" ${work.checking ? "disabled" : ""} onclick="checkPublished(${index})">${work.checking ? "Checking…" : "Check for a published version"}</button>`) : ""}<div class="lit-actions">${canAdd ? `<button class="gt-btn ${added ? "ghost" : "primary"}" ${added ? "disabled" : ""} onclick="addPaper(${index})">${added ? "In your notebook" : addLabel(work)}</button>` : ""}${work.doi && work.abstract_storable !== undefined ? `<button class="gt-btn ${cites?.direction === "citing" ? "primary" : "ghost"}" onclick="toggleCitations(${index}, 'citing')">Cited by</button><button class="gt-btn ${cites?.direction === "references" ? "primary" : "ghost"}" onclick="toggleCitations(${index}, 'references')">References</button>` : ""}${work.oa_url && !work.link_only ? `<a class="gt-btn ghost" href="${esc(work.oa_url)}" target="_blank" rel="noopener noreferrer">Open-access copy</a>` : ""}</div>${renderCitationList(work)}</article>`;
}

function renderSnippetCard(snippet, index) {
  const paper = snippet.paper;
  return `<article class="gt-issue lit-card"><blockquote class="ca-quote"><span>${esc(paper.title || "Untitled paper")}${paper.year ? ` · ${paper.year}` : ""}${snippet.section ? ` · ${esc(snippet.section)}` : ""}</span>${esc(snippet.text)}</blockquote><p class="lit-meta">${esc(paper.authors.slice(0, 6).join(", "))}${paper.url ? ` · <a href="${esc(paper.url)}" target="_blank" rel="noopener noreferrer">Open paper</a>` : ""}</p><div class="lit-actions"><button class="gt-btn primary" onclick="addSnippet(${index})">Add passage to notebook</button></div></article>`;
}

function renderSourcesStatus(status) {
  const entries = Object.entries(status || {});
  if (!entries.length) return "";
  return `<div class="lit-status">${entries.map(([key, value]) => `<span class="${value.startsWith("ok") ? "ok" : "bad"}" title="${esc(value)}">${value.startsWith("ok") ? "✓" : "✕"} ${esc(SOURCE_LABELS[key] || key)}${value === "ok (DOI lookup)" ? " (DOI lookup)" : ""}</span>`).join("")}${entries.some(([, value]) => !value.startsWith("ok")) ? `<span class="lit-status-note">${esc(entries.filter(([, value]) => !value.startsWith("ok")).map(([key, value]) => `${SOURCE_LABELS[key] || key}: ${value.replace(/^error: /, "")}`).join(" "))}</span>` : ""}</div>`;
}

function renderLiteratureLicence(status, provider) {
  if (provider === "asta") {
    const asta = status.providers.asta;
    return `<p class="lit-licence">${esc(asta.attribution)} ${esc(asta.licence.summary)} ${asta.keyed ? "" : "<b>No API key is configured, so searches may be slow.</b>"} <a href="${esc(asta.licence.url)}" target="_blank" rel="noopener noreferrer">Licence</a></p>`;
  }
  const open = status.providers.open;
  const hints = [!open.openalex_key ? "Without an OpenAlex key, the engine has about 100 OpenAlex searches a day; set MWENZA_OPENALEX_KEY for ten times that." : "", !open.contact_email ? "Set MWENZA_CONTACT_EMAIL so Crossref and OpenAlex can identify this engine." : ""].filter(Boolean);
  return `<p class="lit-licence">${esc(open.attribution)} Each result shows which source supplied it, whether it is a preprint, and under which licence its abstract may be stored. Preprint licences vary per record. ${hints.length ? `<b>${esc(hints.join(" "))}</b>` : ""}</p>`;
}

function renderLiterature() {
  const lit = literatureState();
  if (!literatureStatusRequested) setTimeout(loadLiteratureStatus);
  const busy = Boolean(literatureRequest);
  const status = lit.status;
  const results = lit.results;
  const astaEnabled = Boolean(status?.providers?.asta?.enabled);
  const provider = astaEnabled ? lit.provider : "open";
  return `<div class="gt-page">
    <section class="gt-intro"><span class="m-kicker">Literature</span><h1>Find literature</h1><p>Search open scholarly records from OpenAlex, Crossref and the Directory of Open Access Journals, and preprints from arXiv, Europe PMC and AfricArXiv. Follow citations through OpenCitations and add the works you choose to your notebook. Mwenza stores an abstract only when its licence allows; otherwise it keeps the reference and a link.</p></section>
    <div class="gt-layout">
      ${!status && lit.error ? `<div class="gt-error"><strong>Couldn't reach the engine</strong><p>${esc(lit.error)}</p></div>` : ""}
      ${status ? renderLiteratureLicence(status, provider) : ""}
      ${status ? `<form class="gt-form lit-form" onsubmit="event.preventDefault(); searchLiterature()">
        ${astaEnabled ? `<div class="pv-tabs gt-intro-actions" role="tablist" aria-label="Search provider"><button type="button" role="tab" aria-selected="${provider === "open"}" class="gt-btn ${provider === "open" ? "primary" : "ghost"}" onclick="literatureProvider('open')">Open sources</button><button type="button" role="tab" aria-selected="${provider === "asta"}" class="gt-btn ${provider === "asta" ? "primary" : "ghost"}" onclick="literatureProvider('asta')">Asta (academic use)</button></div>` : ""}
        ${provider === "open" ? `<div class="pv-tabs gt-intro-actions" role="tablist" aria-label="Include">${LITERATURE_SCOPES.map(([id, label]) => `<button type="button" role="tab" aria-selected="${lit.scope === id}" class="gt-btn ${lit.scope === id ? "primary" : "ghost"}" onclick="literatureScope('${id}')">${label}</button>`).join("")}</div>` : ""}
        <div class="pv-tabs gt-intro-actions" role="tablist" aria-label="Search for">${LITERATURE_MODES.map(([id, label]) => { const off = id === "snippets" && provider !== "asta"; return `<button type="button" role="tab" aria-selected="${lit.mode === id}" class="gt-btn ${lit.mode === id ? "primary" : "ghost"}" ${off ? `disabled title="Passage search over open full text arrives in Phase C"` : ""} onclick="literatureMode('${id}')">${label}${off ? " (coming)" : ""}</button>`; }).join("")}</div>
        <label class="gt-field"><span>${lit.mode === "papers" ? "Search papers, or paste a DOI" : "Find passages that say"}</span><input value="${esc(lit.query)}" placeholder="${lit.mode === "papers" ? "e.g. skilled birth attendance distance Kenya" : "e.g. distance to a facility reduces skilled birth attendance"}" oninput="literatureField('query', this.value)" /></label>
        ${lit.mode === "papers" ? `<div class="gt-row"><label class="gt-field"><span>From year</span><input type="number" min="1800" max="2100" value="${esc(lit.yearFrom)}" oninput="literatureField('yearFrom', this.value)" /></label><label class="gt-field"><span>To year</span><input type="number" min="1800" max="2100" value="${esc(lit.yearTo)}" oninput="literatureField('yearTo', this.value)" /></label></div>` : ""}
        <div class="gt-submit">${renderEngineField()}<button class="gt-btn primary" type="submit" ${busy ? "disabled" : ""}>${busy ? "Searching…" : "Search"}</button></div>
      </form>` : ""}
      ${busy ? `<div class="gt-empty"><strong>Searching…</strong><p>${provider === "asta" ? "Asta can take up to a minute, longer without an API key." : lit.scope === "peer-reviewed" ? "Querying OpenAlex, Crossref and DOAJ in parallel." : "Querying OpenAlex, Crossref, DOAJ and the preprint servers in parallel. arXiv is queried at most once every three seconds, so this can take a few seconds."}</p></div>` : ""}
      ${status && lit.error ? `<div class="gt-error"><strong>Search didn't complete</strong><p>${esc(lit.error)}</p></div>` : ""}
      ${results && !busy ? `<section class="gt-panel"><div class="gt-panel-head"><strong>${results.length} ${lit.resultMode === "papers" ? "works" : "passages"}</strong><span>${esc(lit.attribution)}</span></div>${renderSourcesStatus(lit.sourcesStatus)}<div class="gt-issues">${results.length ? results.map(lit.resultMode === "papers" ? renderPaperCard : renderSnippetCard).join("") : `<div class="gt-empty small">Nothing found. Try broader terms or remove the year limits.</div>`}</div></section>` : ""}
    </div>
  </div>`;
}
