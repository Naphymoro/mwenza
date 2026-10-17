// Method navigator page: walks the engine's decision tree one question at a
// time (/navigator/recommend) and shows the resulting design with its
// reasoning. The tree and designs live in the backend; a finished design can be
// sent to the paradigm and method page to be checked.

const NAVIGATOR_LAYERS = [
  ["approach", "Methodological choice"], ["logic", "Approach to theory"], ["strategy", "Strategy"], ["time_horizon", "Time horizon"],
  ["sampling", "Sampling"], ["sample_size", "Sample size"], ["data_collection", "Data collection"], ["analysis", "Analysis"], ["quality", "Quality criteria"],
];

let navigatorRequest = null;

function navigatorState() {
  state.navigator ||= { answers: [], result: null, error: "", paradigm: "" };
  return state.navigator;
}

async function navigatorGo(answers) {
  const nv = navigatorState();
  navigatorRequest?.abort();
  navigatorRequest = new AbortController();
  nv.error = "";
  render();
  try {
    nv.result = await enginePost("/navigator/recommend", { answers }, navigatorRequest.signal);
    nv.answers = answers;
    if (nv.result.complete && !nv.result.design.paradigms.includes(nv.paradigm)) nv.paradigm = nv.result.design.paradigms[0] || "";
  } catch (error) {
    if (error.name === "AbortError") return;
    nv.error = error instanceof TypeError ? engineUnreachableMessage() : error.message;
  } finally {
    navigatorRequest = null;
  }
  save(); render();
}

function navigatorAnswer(id) { navigatorGo([...navigatorState().answers, id]); }
function navigatorBack(index) { navigatorGo(navigatorState().answers.slice(0, index)); }
function restartNavigator() { Object.assign(navigatorState(), { answers: [], result: null, error: "" }); navigatorGo([]); }
function chooseNavigatorParadigm(name) { navigatorState().paradigm = name; save(); render(); }

// The design is Mwenza's text, not the student's, so it is recorded as pasted
// and the provenance ledger does not attribute it to them.
function sendDesignToParadigm() {
  const nv = navigatorState();
  if (!nv.result?.complete) return;
  const pd = paradigmState();
  const fields = { ...nv.result.method_fields, paradigm: nv.paradigm.split(" /")[0] };
  Object.entries(fields).forEach(([key, value]) => {
    pd.design[key] = Array.isArray(value) ? value.join("\n") : value;
    recordPaste(PARADIGM_DOCUMENT, pd.design[key]);
  });
  Object.assign(pd, { report: null, error: "", focus: null });
  state.page = "paradigm";
  save(); render(); notify("Design copied to the paradigm and method page. Adapt it to your study, then run the check.");
}

function renderNavigatorPath(path) {
  if (!path.length) return "";
  return `<ol class="nv-path">${path.map((step, index) => `<li><span class="nv-q">${esc(step.question)}</span><span class="nv-a">${esc(step.answer)}</span><button class="gt-link" onclick="navigatorBack(${index})">Change</button></li>`).join("")}</ol>`;
}

function renderNavigatorStep(step) {
  return `<div class="gt-panel"><div class="gt-panel-head"><strong>${esc(step.question)}</strong></div><p class="nv-why">${esc(step.why)}</p><div class="nv-options">${step.options.map((option) => `<button class="nv-option" onclick="navigatorAnswer('${option.id}')" ${navigatorRequest ? "disabled" : ""}><strong>${esc(option.label)}</strong>${option.hint ? `<span>${esc(option.hint)}</span>` : ""}</button>`).join("")}</div></div>`;
}

function renderNavigatorDesign(nv) {
  const design = nv.result.design;
  const value = (key) => Array.isArray(design[key]) ? `<ul>${design[key].map((item) => `<li>${esc(item)}</li>`).join("")}</ul>` : esc(design[key] === "mixed" ? "Mixed methods" : String(design[key]).charAt(0).toUpperCase() + String(design[key]).slice(1));
  return `<div class="gt-verdict aligned"><div><span class="gt-kicker">Suggested design · ${esc(design.strategy_family)}</span><strong>${esc(design.name)}</strong><p>${design.reasons.map(esc).join(" ")}</p></div></div>
    <div class="gt-panel"><div class="gt-panel-head"><strong>Design layers</strong><span>A starting point to adapt and justify, not a finished methodology</span></div><dl class="pd-profile nv-layers">${NAVIGATOR_LAYERS.map(([key, label]) => `<div><dt>${label}</dt><dd>${value(key)}</dd></div>`).join("")}</dl></div>
    <div class="gt-panel"><div class="gt-panel-head"><strong>Watch out for</strong></div><ul class="nv-cautions">${design.cautions.map((item) => `<li>${esc(item)}</li>`).join("")}</ul></div>
    <div class="gt-panel"><div class="gt-panel-head"><strong>Paradigms this design fits</strong><span>Your paradigm is your choice; pick the one you can defend</span></div><div class="nv-paradigms">${design.paradigms.map((name) => `<button class="nv-chip ${nv.paradigm === name ? "active" : ""}" onclick="chooseNavigatorParadigm(${esc(JSON.stringify(name))})">${esc(name)}</button>`).join("")}</div><div class="gt-intro-actions"><button class="gt-btn primary" onclick="sendDesignToParadigm()" ${nv.paradigm ? "" : "disabled"}>Check this design under ${esc(nv.paradigm.split(" /")[0] || "a paradigm")}</button></div></div>`;
}

function renderNavigator() {
  const nv = navigatorState();
  const result = nv.result;
  const body = nv.error ? `<div class="gt-error"><strong>The navigator didn't load</strong><p>${esc(nv.error)}</p></div>`
    : !result ? `<div class="gt-empty"><strong>Start from your research question</strong><p>Up to four questions lead to a design: approach, strategy, sampling, data collection, analysis and quality criteria, with the reasoning for each step.</p><div class="gt-intro-actions"><button class="gt-btn primary" onclick="navigatorGo([])" ${navigatorRequest ? "disabled" : ""}>${navigatorRequest ? "Loading…" : "Start"}</button></div></div>`
    : `${renderNavigatorPath(result.path)}${result.complete ? renderNavigatorDesign(nv) : renderNavigatorStep(result.next)}`;
  return `<div class="gt-page">
    <section class="gt-intro"><span class="m-kicker">Phase 2 · Methodology engine</span><h1>Method navigator</h1><p>Answer a few questions about your research question and Mwenza suggests a coherent design, explaining each step. Every suggested design passes the paradigm and method check, and you can send it there to adapt it to your study.</p><div class="gt-intro-actions">${result ? `<button class="gt-btn ghost" onclick="restartNavigator()">Start again</button>` : ""}${renderEngineField()}</div></section>
    <div class="gt-layout"><section class="gt-results">${body}</section></div>
  </div>`;
}
