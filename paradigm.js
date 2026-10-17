// Paradigm and method page: sends each layer of the design to the engine's
// /paradigm/check endpoint and shows how the layers follow from the paradigm,
// with coherent alternatives for every conflict. The rules live in the backend.

const PARADIGM_DOCUMENT = "paradigm-method";
const PARADIGM_OPTIONS = ["Positivism", "Post-positivism", "Critical realism", "Interpretivism", "Constructivism", "Pragmatism", "Critical theory", "Transformative", "Afrocentric", "Ubuntu", "Indigenous"];
const STRATEGY_OPTIONS = ["Survey", "Experiment", "Quasi-experiment", "Cohort study", "Case-control study", "Correlational design", "Secondary data analysis", "Case study", "Ethnography", "Phenomenology", "Grounded theory", "Narrative inquiry", "Participatory action research", "Design science research", "Explanatory sequential mixed methods", "Convergent mixed methods"];
const PARADIGM_LISTS = [
  ["data_collection", "Data collection", "One method per line, e.g. in-depth interviews"],
  ["analysis", "Analysis", "One method per line, e.g. thematic analysis"],
  ["quality", "Quality criteria", "One per line, e.g. credibility through member checking"],
  ["hypotheses", "Hypotheses", "Optional. One per line"],
  ["questions", "Research questions", "Optional. Used to check the time horizon"],
];
const PARADIGM_EXAMPLE = {
  title: "Home births in Kitui", paradigm: "Interpretivism", approach: "Qualitative", logic: "Inductive", strategy: "Phenomenology", time_horizon: "Cross-sectional",
  sampling: "Purposive sampling of mothers who delivered at home", sample_size: "About 20 mothers",
  data_collection: "Structured questionnaire", analysis: "Logistic regression", quality: "Reliability using Cronbach's alpha",
  hypotheses: "", questions: "How do rural mothers experience the decision to deliver at home?", claims: "Findings will be generalised to all women in Kenya.",
};
const PARADIGM_STATUS = {
  coherent: ["Coherent", "Every layer follows from the paradigm. Make sure each choice is justified in your methodology chapter, not just stated."],
  review: ["Review", "No contradictions, but some layers are in tension with the paradigm or lack a justification an examiner will ask for."],
  "needs-revision": ["Needs revision", "At least one layer contradicts the paradigm. Choose which side to keep; the alternatives below show coherent options either way."],
};
const LAYER_STATUS_LABEL = { coherent: "Coherent", tension: "Tension", conflict: "Conflict", missing: "Not stated", unrecognised: "Not recognised" };

let paradigmRequest = null;

function paradigmState() {
  state.paradigm ||= { design: Object.fromEntries(Object.keys(PARADIGM_EXAMPLE).map((key) => [key, ""])), report: null, error: "", focus: null };
  return state.paradigm;
}

function paradigmField(name, value) { paradigmState().design[name] = value; save(); }

function loadParadigmExample() {
  const pd = paradigmState();
  pd.design = { ...PARADIGM_EXAMPLE };
  Object.values(PARADIGM_EXAMPLE).forEach((value) => recordPaste(PARADIGM_DOCUMENT, value));
  Object.assign(pd, { report: null, error: "", focus: null });
  save(); render(); notify("Example loaded. It has one contradiction and several tensions; run the check to find them.");
}

function clearParadigm() { const pd = paradigmState(); pd.design = Object.fromEntries(Object.keys(PARADIGM_EXAMPLE).map((key) => [key, ""])); Object.assign(pd, { report: null, error: "", focus: null }); save(); render(); }

function importFromThread() {
  const thread = state.thread?.design;
  if (!thread || !Object.values(thread).some((value) => String(value || "").trim())) return notify("The golden thread page has no design to import yet.");
  const pd = paradigmState();
  ["paradigm", "approach", "strategy", "data_collection", "analysis", "hypotheses", "questions"].forEach((key) => { if (thread[key]) pd.design[key] = thread[key]; });
  pd.design.title ||= thread.title || "";
  save(); render(); notify("Imported paradigm, approach, strategy, questions, hypotheses, data collection and analysis from the golden thread.");
}

async function checkParadigm() {
  const pd = paradigmState();
  paradigmRequest?.abort();
  paradigmRequest = new AbortController();
  Object.assign(pd, { error: "", focus: null });
  render();
  const lines = (value) => String(value || "").split("\n").map((line) => line.trim()).filter(Boolean);
  const payload = Object.fromEntries(Object.entries(pd.design).map(([key, value]) => [key, PARADIGM_LISTS.some(([name]) => name === key) ? lines(value) : String(value || "").trim()]));
  try {
    pd.report = await enginePost("/paradigm/check", { ...payload, document_id: PARADIGM_DOCUMENT, pasted_segments: pendingPastes(PARADIGM_DOCUMENT) }, paradigmRequest.signal);
    clearPastes(PARADIGM_DOCUMENT);
    markProvenanceStale();
  } catch (error) {
    if (error.name === "AbortError") return;
    pd.error = error instanceof TypeError ? engineUnreachableMessage() : error.message;
  } finally {
    paradigmRequest = null;
  }
  save(); render();
  document.querySelector(".gt-results")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function focusParadigmLayer(id) { const pd = paradigmState(); pd.focus = pd.focus === id ? null : id; save(); render(); }

function renderParadigmIssue(issue) {
  return `<article class="gt-issue ${issue.severity}"><div class="gt-issue-head"><span class="gt-sev ${issue.severity}">${issue.severity === "error" ? "conflict" : issue.severity === "warning" ? "tension" : "note"}</span><strong>${esc(issue.message)}</strong></div>${issue.alternatives.length ? `<div class="pd-options"><b>Coherent options</b><ul>${issue.alternatives.map((item) => `<li>${esc(item)}</li>`).join("")}</ul></div>` : ""}<p><b>Why it matters</b>${esc(issue.teach)}</p><p class="gt-ask"><b>Ask yourself</b>${esc(issue.ask)}</p></article>`;
}

function renderParadigmProfile(profile) {
  if (!profile) return "";
  return `<div class="gt-panel"><div class="gt-panel-head"><strong>${esc(profile.name)}: what it commits you to</strong><span>Teaching summary</span></div><dl class="pd-profile"><div><dt>Ontology</dt><dd>${esc(profile.ontology)}</dd></div><div><dt>Epistemology</dt><dd>${esc(profile.epistemology)}</dd></div><div><dt>Axiology</dt><dd>${esc(profile.axiology)}</dd></div><div><dt>Typical logic</dt><dd>${esc(profile.logics.join(", "))}</dd></div><div><dt>Methodological choice</dt><dd>${esc(profile.approaches.join(", "))}</dd></div><div><dt>Typical strategies</dt><dd>${esc(profile.strategies.join(", "))}</dd></div><div><dt>Quality criteria</dt><dd>${esc(profile.quality.join("; "))}</dd></div></dl></div>`;
}

function renderParadigmResults(pd) {
  if (pd.error) return `<section class="gt-results"><div class="gt-error"><strong>Check didn't run</strong><p>${esc(pd.error)}</p></div></section>`;
  const report = pd.report;
  if (!report) return "";
  const [title, explanation] = PARADIGM_STATUS[report.status] || [report.status, ""];
  const issues = pd.focus ? report.issues.filter((issue) => issue.layers.includes(pd.focus)) : report.issues;
  const focused = report.layers.find((layer) => layer.id === pd.focus);
  return `<section class="gt-results">
    <div class="gt-verdict ${report.status === "coherent" ? "aligned" : report.status}"><div><span class="gt-kicker">Paradigm and method</span><strong>${title}</strong><p>${explanation}</p></div><dl><div><dt>${report.counts.error}</dt><dd>conflicts</dd></div><div><dt>${report.counts.warning}</dt><dd>tensions</dd></div><div><dt>${report.layers.filter((layer) => layer.status === "coherent").length}/${report.layers.length}</dt><dd>layers coherent</dd></div></dl></div>
    <div class="gt-panel"><div class="gt-panel-head"><strong>Design layers</strong><span>From philosophy (top) to technique (bottom). Select a layer to see its issues.</span></div><ol class="pd-layers">${report.layers.map((layer, index) => `<li><button class="pd-layer ${layer.status} ${pd.focus === layer.id ? "focused" : ""}" onclick="focusParadigmLayer('${layer.id}')"><span class="pd-step">${index + 1}</span><span class="pd-name">${esc(layer.label)}</span><span class="pd-value">${esc(layer.recognised || layer.value || "—")}${layer.source && layer.source !== "declared" ? ` <small>(${esc(layer.source)})</small>` : ""}</span><span class="pd-status ${layer.status}">${LAYER_STATUS_LABEL[layer.status] || layer.status}</span></button></li>`).join("")}</ol></div>
    ${renderParadigmProfile(report.profile)}
    <div class="gt-panel"><div class="gt-panel-head"><strong>${focused ? `Issues for ${esc(focused.label.toLowerCase())}` : "Issues"}</strong>${focused ? `<button class="gt-link" onclick="focusParadigmLayer('${focused.id}')">Show all issues</button>` : `<span>${report.issues.length} found, most serious first</span>`}</div><div class="gt-issues">${issues.map(renderParadigmIssue).join("") || `<div class="gt-empty small">No issues on this layer.</div>`}</div></div>
    <details class="gt-panel gt-details"><summary>Further reading</summary><ul class="pd-refs">${report.references.map((item) => `<li>${esc(item)}</li>`).join("")}</ul></details>
    <p class="gt-method">${esc(report.method.charAt(0).toUpperCase() + report.method.slice(1))}.</p>
  </section>`;
}

function renderParadigm() {
  const pd = paradigmState();
  const design = pd.design;
  const busy = Boolean(paradigmRequest);
  const paste = pasteHandler(PARADIGM_DOCUMENT);
  const input = (name, label, placeholder, list = "") => `<label class="gt-field"><span>${label}</span><input ${list ? `list="${list}"` : ""} value="${esc(design[name])}" placeholder="${esc(placeholder)}" oninput="paradigmField('${name}', this.value)" onpaste="${paste}" /></label>`;
  const select = (name, label, options) => `<label class="gt-field"><span>${label}</span><select onchange="paradigmField('${name}', this.value)">${options.map((item) => `<option value="${item}" ${design[name] === item ? "selected" : ""}>${item || "Choose…"}</option>`).join("")}</select></label>`;
  const area = ([name, label, hint], rows = 3) => `<label class="gt-field"><span>${label}</span><textarea rows="${rows}" placeholder="${esc(hint)}" oninput="paradigmField('${name}', this.value)" onpaste="${paste}">${esc(design[name])}</textarea></label>`;
  const list = (name) => area(PARADIGM_LISTS.find(([key]) => key === name));
  return `<div class="gt-page">
    <section class="gt-intro"><span class="m-kicker">Phase 1 · Methodology engine</span><h1>Paradigm and method</h1><p>Check that every layer of your methodology follows from your research paradigm: approach to theory, methodological choice, strategy, time horizon, sampling, data collection, analysis and quality criteria. Where layers clash, Mwenza shows coherent options in both directions. You decide what to change.</p><div class="gt-intro-actions"><button class="gt-btn ghost" onclick="loadParadigmExample()">Load example with flaws</button><button class="gt-btn ghost" onclick="importFromThread()">Import from golden thread</button><button class="gt-btn ghost" onclick="clearParadigm()">Clear</button></div></section>
    <div class="gt-layout">
      ${renderParadigmResults(pd)}
      <form class="gt-form" onsubmit="event.preventDefault(); checkParadigm()">
        ${input("title", "Working title", "Optional")}
        <fieldset><legend>1 · Philosophy</legend><div class="gt-row">${input("paradigm", "Paradigm", "e.g. Pragmatism", "pd-paradigms")}${select("logic", "Approach to theory", ["", "Deductive", "Inductive", "Abductive"])}</div><datalist id="pd-paradigms">${PARADIGM_OPTIONS.map((item) => `<option value="${item}"></option>`).join("")}</datalist></fieldset>
        <fieldset><legend>2 · Design</legend><div class="gt-row">${select("approach", "Methodological choice", ["", "Quantitative", "Qualitative", "Mixed methods"])}${select("time_horizon", "Time horizon", ["", "Cross-sectional", "Longitudinal"])}</div>${input("strategy", "Strategy", "e.g. Case study, survey, phenomenology", "pd-strategies")}<datalist id="pd-strategies">${STRATEGY_OPTIONS.map((item) => `<option value="${item}"></option>`).join("")}</datalist>${list("questions")}${list("hypotheses")}</fieldset>
        <fieldset><legend>3 · Techniques and quality</legend>${input("sampling", "Sampling technique", "e.g. Stratified random sampling, purposive sampling")}${area(["sample_size", "Sample size and its justification", "e.g. G*Power for a medium effect gives 128; or saturation"], 2)}${list("data_collection")}${list("analysis")}${list("quality")}${area(["claims", "Claims about your findings", "Optional, e.g. who the findings will apply to"], 2)}</fieldset>
        <div class="gt-submit">${renderEngineField()}<button class="gt-btn primary" type="submit" ${busy ? "disabled" : ""}>${busy ? "Checking…" : "Check paradigm fit"}</button></div>
      </form>
    </div>
  </div>`;
}
