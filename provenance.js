// Provenance page: reads the engine's hash-chained ledger for a document and
// shows where each paragraph came from, what Mwenza flagged, what changed
// afterwards, and an AI-use declaration the student can hand to a supervisor.

const PROVENANCE_DOCUMENTS = [["citation-draft", "Citation audit draft", "audit"], ["golden-thread", "Golden thread design", "thread"], ["paradigm-method", "Paradigm and method", "paradigm"]];
const PROVENANCE_ORIGIN_CLASS = { typed: "ok", "present-at-start": "info", pasted: "warning", mixed: "warning" };
const PROVENANCE_KINDS = { "text-snapshot": ["Text recorded", "student"], "ai-check": ["Mwenza check", "mwenza"] };

let provenanceRequest = null;
let provenanceFresh = false;

function markProvenanceStale() { provenanceFresh = false; }

function provenanceState() {
  state.provenance ||= { documentId: PROVENANCE_DOCUMENTS[0][0], report: null, error: "" };
  return state.provenance;
}

function chooseProvenanceDocument(id) { Object.assign(provenanceState(), { documentId: id, report: null, error: "" }); save(); loadProvenance(); }

async function loadProvenance() {
  const ledger = provenanceState();
  provenanceRequest?.abort();
  provenanceRequest = new AbortController();
  provenanceFresh = true;
  ledger.error = "";
  render();
  try {
    const sourceIds = await syncSelectedSources(provenanceRequest.signal);
    const query = sourceIds.map((id) => `source_ids=${encodeURIComponent(id)}`).join("&");
    ledger.report = await engineGet(`/provenance/${encodeURIComponent(ledger.documentId)}${query ? `?${query}` : ""}`, provenanceRequest.signal);
  } catch (error) {
    if (error.name === "AbortError") return;
    ledger.error = error instanceof TypeError ? engineUnreachableMessage() : error.message;
  } finally {
    provenanceRequest = null;
  }
  save(); render();
}

async function copyDeclaration() {
  try { await navigator.clipboard.writeText(provenanceState().report.declaration); notify("Declaration copied."); }
  catch (_) { notify("Couldn't copy. Select the text and copy it instead."); }
}

function downloadDeclaration() {
  const ledger = provenanceState();
  const url = URL.createObjectURL(new Blob([ledger.report.declaration], { type: "text/markdown" }));
  const link = Object.assign(document.createElement("a"), { href: url, download: `${ledger.documentId}-ai-use-declaration.md` });
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const provenanceTime = (value) => new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

function renderProvenanceParagraph(item) {
  const feedback = item.feedback.map((entry) => `<li><b>${entry.tool === "citation-audit" ? "Citation audit" : "Golden thread"} #${entry.seq}</b> flagged ${esc([...new Set(entry.flags.map((flag) => flag.verdict))].join(", "))} · <span class="${entry.revised_after ? "pv-yes" : "pv-no"}">${entry.revised_after ? "revised afterwards" : "not revised since"}</span></li>`).join("");
  const verbatim = item.verbatim.map((match) => `<li class="${match.quoted ? "" : "pv-alert"}">${match.words} words identical to <b>${esc(match.source_name)}</b> · ${match.quoted ? "in quotation marks" : "not in quotation marks: quote and cite, or paraphrase"}<q>${esc(match.text.length > 160 ? `${match.text.slice(0, 159)}…` : match.text)}</q></li>`).join("");
  return `<article class="pv-paragraph"><div class="pv-paragraph-head"><span class="gt-sev ${PROVENANCE_ORIGIN_CLASS[item.origin] || "info"}">${esc(item.origin_label)}</span><small>${item.versions} version${item.versions === 1 ? "" : "s"} · first recorded ${esc(provenanceTime(item.first_seen))}${item.pasted_share > 0 && item.pasted_share < 1 ? ` · ${Math.round(item.pasted_share * 100)}% pasted` : ""}${item.open_feedback ? ` · <b class="pv-no">${item.open_feedback} open issue${item.open_feedback === 1 ? "" : "s"} in the latest check</b>` : ""}</small></div><p class="pv-text">${esc(item.text)}</p>${feedback ? `<ul class="pv-list">${feedback}</ul>` : ""}${verbatim ? `<ul class="pv-list">${verbatim}</ul>` : ""}</article>`;
}

function renderProvenanceResults(ledger) {
  if (ledger.error) return `<div class="gt-error"><strong>Couldn't load the ledger</strong><p>${esc(ledger.error)}</p></div>`;
  const report = ledger.report;
  if (!report) return provenanceRequest ? `<div class="gt-empty"><strong>Loading the ledger…</strong></div>` : "";
  const page = PROVENANCE_DOCUMENTS.find(([id]) => id === ledger.documentId);
  if (!report.events.length) return `<div class="gt-empty"><strong>Nothing recorded yet for this document.</strong><p>Each ${{ audit: "citation audit", thread: "golden thread check", paradigm: "paradigm and method check" }[page[2]]} records the text you submitted and what Mwenza flagged. Run one and it will appear here.</p><div class="gt-intro-actions"><button class="gt-btn primary" onclick="go('${page[2]}')">Go to ${esc(page[1].toLowerCase().replace(" draft", "").replace(" design", ""))}</button></div></div>`;
  const integrity = report.integrity;
  const counts = report.paragraphs.reduce((total, item) => ({ ...total, [item.origin]: (total[item.origin] || 0) + 1 }), {});
  return `<div class="gt-verdict ${integrity.valid ? "aligned" : "needs-revision"}"><div><span class="gt-kicker">Ledger integrity</span><strong>${integrity.valid ? "Hash chain intact" : "Chain broken"}</strong><p>${integrity.valid ? `All ${report.events.length} events for this document match their hashes. Head ${esc(integrity.head.slice(0, 16))}.` : `Event ${integrity.broken_at}: ${esc(integrity.reason)}. Records from that point on can't be trusted.`} The ledger is tamper-evident, not tamper-proof.</p></div><dl><div><dt>${report.paragraphs.length}</dt><dd>paragraphs</dd></div><div><dt>${counts.typed || 0}</dt><dd>typed in Mwenza</dd></div><div><dt>${(counts.pasted || 0) + (counts.mixed || 0)}</dt><dd>pasted</dd></div><div><dt>${report.paragraphs.filter((item) => item.revised_after_feedback).length}</dt><dd>revised after feedback</dd></div><div><dt>${report.paragraphs.filter((item) => item.open_feedback).length}</dt><dd>with open feedback</dd></div></dl></div>
    <div class="gt-panel"><div class="gt-panel-head"><strong>AI-use declaration</strong><div class="pv-actions"><button class="gt-btn ghost" onclick="copyDeclaration()">Copy</button><button class="gt-btn ghost" onclick="downloadDeclaration()">Download .md</button></div></div><pre class="pv-declaration">${esc(report.declaration)}</pre></div>
    <div class="gt-panel"><div class="gt-panel-head"><strong>Paragraph by paragraph</strong><span>Latest recorded version</span></div><div class="gt-issues">${report.paragraphs.map(renderProvenanceParagraph).join("")}</div></div>
    <details class="gt-panel gt-details"><summary>Ledger events (${report.events.length})</summary><ol class="pv-timeline">${report.events.map((event) => `<li class="${PROVENANCE_KINDS[event.kind]?.[1] || ""}"><time>${esc(provenanceTime(event.timestamp))}</time><strong>#${event.seq} ${esc(PROVENANCE_KINDS[event.kind]?.[0] || event.kind)}</strong><span>${esc(event.summary)}</span><code title="${esc(event.hash)}">${esc(event.hash.slice(0, 12))}</code></li>`).join("")}</ol></details>
    <p class="gt-method">${esc(report.method.charAt(0).toUpperCase() + report.method.slice(1))}.</p>`;
}

function renderProvenance() {
  const ledger = provenanceState();
  if (!provenanceFresh && !provenanceRequest) setTimeout(loadProvenance);
  return `<div class="gt-page">
    <section class="gt-intro"><span class="m-kicker">Phase 1 · Academic integrity</span><h1>Provenance ledger</h1><p>A tamper-evident record of how your work was written: what you typed, what you pasted, what Mwenza flagged, and what you changed afterwards. Use the declaration for your supervisor or an ethics form.</p><div class="gt-intro-actions pv-tabs" role="tablist">${PROVENANCE_DOCUMENTS.map(([id, label]) => `<button role="tab" aria-selected="${ledger.documentId === id}" class="gt-btn ${ledger.documentId === id ? "primary" : "ghost"}" onclick="chooseProvenanceDocument('${id}')">${label}</button>`).join("")}<button class="gt-btn ghost" onclick="loadProvenance()">Refresh</button></div></section>
    <div class="gt-layout"><section class="gt-results">${renderProvenanceResults(ledger)}</section></div>
  </div>`;
}
