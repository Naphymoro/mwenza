// Golden thread page: edits a research design, sends it to the engine's
// /golden-thread/check endpoint and draws the alignment map it returns.
// The checks live in the backend only, so the browser never re-implements them.

const THREAD_TEXT_FIELDS = [
  ["problem", "Problem statement", "What is wrong in the world, for whom, and with what consequence?"],
  ["gap", "Research gap", "What does existing research not yet show? Name the absence, conflict or limitation."],
  ["aim", "Aim", "One sentence: what will this study achieve?"],
];

const THREAD_LIST_FIELDS = [
  ["objectives", "Objectives", "One per line"],
  ["questions", "Research questions", "One per line, in the same order as the objectives"],
  ["hypotheses", "Hypotheses", "Optional. One per line"],
  ["constructs", "Theory constructs", "One per line, e.g. travel distance"],
  ["data_collection", "Data collection", "Instruments or methods, one per line"],
  ["analysis", "Analysis plan", "One method per line, e.g. logistic regression"],
  ["findings", "Findings", "Optional. Add once you have results"],
];

const THREAD_PARADIGMS = ["Positivism", "Post-positivism", "Interpretivism", "Constructivism", "Pragmatism", "Critical theory", "Transformative", "Afrocentric", "Ubuntu"];

const THREAD_EXAMPLE = {
  title: "Skilled birth attendance in rural Kenya",
  problem: "Maternal mortality remains high in rural Kenyan counties despite free maternity services, because many rural women still deliver at home without skilled birth attendance.",
  gap: "Studies of free maternity services in Kenya measure facility delivery rates, but few examine how household decision-making and travel distance shape skilled birth attendance among rural women.",
  aim: "To examine how household decision-making autonomy and travel distance influence skilled birth attendance among rural women in Kenya.",
  objectives: "To determine the relationship between travel distance and skilled birth attendance among rural women.\nTo assess the influence of household decision-making autonomy on skilled birth attendance among rural women.",
  questions: "What is the relationship between travel distance and skilled birth attendance among rural women?\nTo what extent does household decision-making autonomy influence skilled birth attendance among rural women?\nHow do rural women experience household decision-making about skilled birth attendance?",
  hypotheses: "Longer travel distance is associated with lower skilled birth attendance among rural women.\nGreater household decision-making autonomy is associated with higher skilled birth attendance among rural women.",
  paradigm: "Interpretivism",
  approach: "Quantitative",
  strategy: "Cross-sectional household survey",
  theory: "Andersen's Behavioral Model of Health Services Use",
  constructs: "travel distance\ndecision-making autonomy\nskilled birth attendance\nhealth literacy",
  data_collection: "Structured questionnaire measuring travel distance, household decision-making autonomy and skilled birth attendance",
  analysis: "Descriptive statistics\nMultivariable logistic regression",
  findings: "",
};

const THREAD_LAYERS = { problem: [0, "top"], gap: [1, "top"], aim: [2, "top"], objective: [3, "top"], question: [4, "top"], hypothesis: [5, "top"], finding: [6, "top"], paradigm: [0, "bottom"], design: [1, "bottom"], theory: [2, "bottom"], construct: [3, "bottom"], "data-collection": [4, "bottom"], analysis: [5, "bottom"] };
const THREAD_STATUS_COLOURS = { aligned: "#69cb91", weak: "#e3c15a", broken: "#ef6f6c", unknown: "#6e7d8d", declared: "#79b8ff" };
const THREAD_VERDICTS = { aligned: ["Aligned", "No errors or warnings. Ask your supervisor to confirm the argument reads as well as it links."], review: ["Review", "No breaks, but some links are weak or questionable. Work through the warnings below."], "needs-revision": ["Needs revision", "At least one link in the golden thread is broken. Fix the errors first; they are what an examiner would raise."] };

let threadRequest = null;

function threadState() {
  state.thread ||= { design: emptyThreadDesign(), report: null, error: "", focus: null };
  state.engineUrl ||= "http://localhost:8000";
  return state.thread;
}

function emptyThreadDesign() { return Object.fromEntries(Object.keys(THREAD_EXAMPLE).map((key) => [key, ""])); }
function threadField(name, value) { threadState().design[name] = value; save(); }
function threadEngineUrl(value) { state.engineUrl = value.trim().replace(/\/+$/, ""); save(); }

function loadThreadExample() {
  const thread = threadState();
  thread.design = { ...THREAD_EXAMPLE };
  thread.report = null; thread.error = ""; thread.focus = null;
  save(); render(); notify("Example loaded. It contains three planted flaws; run the check to find them.");
}

function clearThread() {
  const thread = threadState();
  thread.design = emptyThreadDesign();
  thread.report = null; thread.error = ""; thread.focus = null;
  save(); render();
}

function threadPayload(design) {
  const lines = (value) => String(value || "").split("\n").map((line) => line.trim()).filter(Boolean);
  return Object.fromEntries(Object.entries(design).map(([key, value]) => [key, THREAD_LIST_FIELDS.some(([name]) => name === key) ? lines(value) : String(value || "").trim()]));
}

async function checkThread() {
  const thread = threadState();
  threadRequest?.abort();
  threadRequest = new AbortController();
  thread.error = ""; thread.focus = null;
  render();
  try {
    const response = await fetch(`${state.engineUrl}/golden-thread/check`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(threadPayload(thread.design)), signal: threadRequest.signal });
    if (!response.ok) throw new Error(`The engine rejected the design (HTTP ${response.status}).`);
    thread.report = await response.json();
  } catch (error) {
    if (error.name === "AbortError") return;
    thread.error = error instanceof TypeError ? `Couldn't reach the Mwenza engine at ${state.engineUrl}. Start it with "uvicorn mwenza_engine.api:app --app-dir backend/src" and open this page from http://localhost (for example "python -m http.server").` : error.message;
  } finally {
    threadRequest = null;
  }
  save(); render();
  document.querySelector(".gt-results")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function focusThreadNode(id) { const thread = threadState(); thread.focus = thread.focus === id ? null : id; save(); render(); }

function threadShortLabel(node) {
  const named = { problem: "Problem", gap: "Gap", aim: "Aim", paradigm: "Paradigm", design: "Design", theory: "Theory" };
  if (named[node.id]) return named[node.id];
  const [prefix, index] = node.id.split("-");
  return `${{ obj: "O", rq: "RQ", h: "H", construct: "C", collection: "D", analysis: "A", finding: "F" }[prefix] || prefix}${index}`;
}

function threadNodeSeverity(report, id) {
  const levels = report.issues.filter((issue) => issue.node_ids.includes(id)).map((issue) => issue.severity);
  return levels.includes("error") ? "error" : levels.includes("warning") ? "warning" : "";
}

function renderThreadMap(report, focus) {
  const colW = 136, nodeW = 108, nodeH = 40, gapY = 14, top = 34;
  const nodes = report.nodes.filter((node) => THREAD_LAYERS[node.kind]);
  const stacks = {};
  nodes.forEach((node) => { const [col, band] = THREAD_LAYERS[node.kind]; (stacks[`${band}-${col}`] ||= []).push(node); });
  const topRows = Math.max(1, ...Object.entries(stacks).filter(([key]) => key.startsWith("top")).map(([, list]) => list.length));
  const bottomTop = top + topRows * (nodeH + gapY) + 40;
  const bottomRows = Math.max(1, ...Object.entries(stacks).filter(([key]) => key.startsWith("bottom")).map(([, list]) => list.length));
  const height = bottomTop + bottomRows * (nodeH + gapY) + 10;
  const width = 7 * colW;
  const pos = {};
  Object.entries(stacks).forEach(([key, list]) => {
    const [band, col] = key.split("-");
    list.forEach((node, row) => { pos[node.id] = { x: 12 + Number(col) * colW, y: (band === "top" ? top : bottomTop) + row * (nodeH + gapY) }; });
  });
  const touches = (edge) => !focus || edge.source === focus || edge.target === focus;
  const edges = report.edges.filter((edge) => pos[edge.source] && pos[edge.target]).map((edge) => {
    const a = pos[edge.source], b = pos[edge.target];
    const sx = a.x + nodeW, sy = a.y + nodeH / 2, tx = b.x, ty = b.y + nodeH / 2, bend = Math.max(30, (tx - sx) / 2);
    const colour = THREAD_STATUS_COLOURS[edge.status] || THREAD_STATUS_COLOURS.unknown;
    return `<path d="M${sx} ${sy} C${sx + bend} ${sy}, ${tx - bend} ${ty}, ${tx} ${ty}" fill="none" stroke="${colour}" stroke-width="${edge.status === "broken" ? 2.4 : 1.6}" ${["unknown", "declared"].includes(edge.status) ? 'stroke-dasharray="4 4"' : ""} opacity="${touches(edge) ? 0.95 : 0.12}"><title>${esc(`${edge.source} → ${edge.target}: ${edge.status}. ${edge.reason}`)}</title></path>`;
  }).join("");
  const boxes = nodes.map((node) => {
    const { x, y } = pos[node.id];
    const severity = threadNodeSeverity(report, node.id);
    const stroke = severity === "error" ? "#ef6f6c" : severity === "warning" ? "#e3c15a" : "#3a4a5a";
    const text = node.text.length > 17 ? `${node.text.slice(0, 16)}…` : node.text;
    const dim = focus && focus !== node.id && !report.edges.some((edge) => (edge.source === focus && edge.target === node.id) || (edge.target === focus && edge.source === node.id));
    return `<g class="gt-node" tabindex="0" role="button" aria-label="${esc(`${threadShortLabel(node)}: ${node.text}`)}" onclick="focusThreadNode('${node.id}')" onkeydown="if(event.key==='Enter') focusThreadNode('${node.id}')" opacity="${dim ? 0.3 : 1}"><title>${esc(node.text)}</title><rect x="${x}" y="${y}" width="${nodeW}" height="${nodeH}" rx="8" fill="${focus === node.id ? "#2a2018" : "#18222d"}" stroke="${focus === node.id ? "#e8a15d" : stroke}" stroke-width="${severity || focus === node.id ? 2 : 1.2}"/><text x="${x + 10}" y="${y + 16}" class="gt-node-label">${esc(threadShortLabel(node))}</text><text x="${x + 10}" y="${y + 31}" class="gt-node-text">${esc(text)}</text></g>`;
  }).join("");
  const bandLabels = `<text x="12" y="20" class="gt-band">ARGUMENT</text><text x="12" y="${bottomTop - 14}" class="gt-band">METHOD</text>`;
  return `<div class="gt-map-scroll"><svg class="gt-map" viewBox="0 0 ${width} ${height}" style="min-width:640px;max-width:${width}px" role="img" aria-label="Golden thread map: ${report.nodes.length} design elements and ${report.edges.length} links">${bandLabels}${edges}${boxes}</svg></div>`;
}

function renderThreadIssue(issue) {
  return `<article class="gt-issue ${issue.severity}"><div class="gt-issue-head"><span class="gt-sev ${issue.severity}">${issue.severity}</span><strong>${esc(issue.message)}</strong></div><p><b>Why it matters</b>${esc(issue.teach)}</p><p class="gt-ask"><b>Ask yourself</b>${esc(issue.ask)}</p>${issue.node_ids.length ? `<div class="gt-issue-nodes">${issue.node_ids.map((id) => `<button onclick="focusThreadNode('${id}')">${esc(id)}</button>`).join("")}</div>` : ""}</article>`;
}

function renderThreadResults(thread) {
  const report = thread.report;
  if (thread.error) return `<section class="gt-results"><div class="gt-error"><strong>Check didn't run</strong><p>${esc(thread.error)}</p></div></section>`;
  if (!report) return "";
  const [verdict, explanation] = THREAD_VERDICTS[report.status] || [report.status, ""];
  const judged = report.edges.filter((edge) => !["unknown", "declared"].includes(edge.status));
  const aligned = judged.filter((edge) => edge.status === "aligned").length;
  const issues = thread.focus ? report.issues.filter((issue) => issue.node_ids.includes(thread.focus)) : report.issues;
  const focusNode = report.nodes.find((node) => node.id === thread.focus);
  return `<section class="gt-results">
    <div class="gt-verdict ${report.status}"><div><span class="gt-kicker">Verdict</span><strong>${verdict}</strong><p>${explanation}</p></div><dl><div><dt>${report.counts.error}</dt><dd>errors</dd></div><div><dt>${report.counts.warning}</dt><dd>warnings</dd></div><div><dt>${aligned}/${judged.length}</dt><dd>links aligned</dd></div></dl></div>
    <div class="gt-panel"><div class="gt-panel-head"><strong>Golden thread map</strong><span>Approach: ${esc(report.approach.value)} (${esc(report.approach.source.replace(/-/g, " "))}). Select an element to trace its links.</span></div>${renderThreadMap(report, thread.focus)}<div class="gt-legend">${Object.entries(THREAD_STATUS_COLOURS).map(([status, colour]) => `<span><i style="background:${colour}"></i>${status}</span>`).join("")}<span><i class="gt-ring error"></i>has error</span><span><i class="gt-ring warning"></i>has warning</span></div></div>
    <div class="gt-panel"><div class="gt-panel-head"><strong>${thread.focus ? `Issues for ${esc(threadShortLabel(focusNode || { id: thread.focus }))}` : "Issues"}</strong>${thread.focus ? `<button class="gt-link" onclick="focusThreadNode('${thread.focus}')">Show all issues</button>` : `<span>${report.issues.length} found, most serious first</span>`}</div>${focusNode ? `<p class="gt-focus-text">${esc(focusNode.text)}</p>` : ""}<div class="gt-issues">${issues.map(renderThreadIssue).join("") || `<div class="gt-empty small">No issues on this element.</div>`}</div></div>
    <details class="gt-panel gt-details"><summary>Link details (${report.edges.length})</summary><table><thead><tr><th>Link</th><th>Relation</th><th>Status</th><th>Why</th></tr></thead><tbody>${report.edges.map((edge) => `<tr><td>${esc(edge.source)} → ${esc(edge.target)}</td><td>${esc(edge.relation)}</td><td><span class="gt-status" style="color:${THREAD_STATUS_COLOURS[edge.status]}">${esc(edge.status)}${edge.score !== null && !["aligned", "broken"].includes(edge.status) ? ` ${edge.score}` : ""}</span></td><td>${esc(edge.reason)}</td></tr>`).join("")}</tbody></table></details>
    <p class="gt-method">${esc(report.method.charAt(0).toUpperCase() + report.method.slice(1))}. Gap evidence currently uses sources uploaded to the engine, not the browser-only sources in this notebook.</p>
  </section>`;
}

function renderGoldenThread() {
  const thread = threadState();
  const design = thread.design;
  const busy = Boolean(threadRequest);
  const text = ([name, label, hint]) => `<label class="gt-field"><span>${label}</span><textarea rows="3" placeholder="${esc(hint)}" oninput="threadField('${name}', this.value)">${esc(design[name])}</textarea></label>`;
  const list = ([name, label, hint]) => `<label class="gt-field"><span>${label}</span><textarea rows="${name === "questions" || name === "objectives" ? 4 : 3}" placeholder="${esc(hint)}" oninput="threadField('${name}', this.value)">${esc(design[name])}</textarea></label>`;
  const listField = (name) => list(THREAD_LIST_FIELDS.find(([key]) => key === name));
  return `<div class="gt-page">
    <section class="gt-intro"><span class="m-kicker">Phase 1 · Methodology engine</span><h1>Golden thread check</h1><p>Test whether your problem, gap, aim, objectives, questions, theory, design and analysis hold together as one argument, the way an examiner reads them. Mwenza explains each problem and asks you a question about it. It never rewrites your text.</p><div class="gt-intro-actions"><button class="gt-btn ghost" onclick="loadThreadExample()">Load example with flaws</button><button class="gt-btn ghost" onclick="clearThread()">Clear</button></div></section>
    <div class="gt-layout">
      ${renderThreadResults(thread)}
      <form class="gt-form" onsubmit="event.preventDefault(); checkThread()">
        <label class="gt-field"><span>Working title</span><input value="${esc(design.title)}" placeholder="Optional" oninput="threadField('title', this.value)" /></label>
        <fieldset><legend>1 · The argument</legend>${THREAD_TEXT_FIELDS.map(text).join("")}${listField("objectives")}${listField("questions")}${listField("hypotheses")}</fieldset>
        <fieldset><legend>2 · Philosophy and theory</legend><div class="gt-row"><label class="gt-field"><span>Paradigm</span><input list="gt-paradigms" value="${esc(design.paradigm)}" placeholder="e.g. Pragmatism" oninput="threadField('paradigm', this.value)" /><datalist id="gt-paradigms">${THREAD_PARADIGMS.map((item) => `<option value="${item}"></option>`).join("")}</datalist></label><label class="gt-field"><span>Approach</span><select onchange="threadField('approach', this.value)">${["", "Quantitative", "Qualitative", "Mixed methods"].map((item) => `<option value="${item}" ${design.approach === item ? "selected" : ""}>${item || "Choose…"}</option>`).join("")}</select></label></div><label class="gt-field"><span>Theoretical underpinning</span><input value="${esc(design.theory)}" placeholder="e.g. Theory of Planned Behaviour" oninput="threadField('theory', this.value)" /></label>${listField("constructs")}</fieldset>
        <fieldset><legend>3 · Design and analysis</legend><label class="gt-field"><span>Research strategy</span><input value="${esc(design.strategy)}" placeholder="e.g. Cross-sectional survey, case study, phenomenology" oninput="threadField('strategy', this.value)" /></label>${listField("data_collection")}${listField("analysis")}${listField("findings")}</fieldset>
        <div class="gt-submit"><label class="gt-engine"><span>Engine</span><input value="${esc(state.engineUrl)}" aria-label="Engine URL" onchange="threadEngineUrl(this.value)" /></label><button class="gt-btn primary" type="submit" ${busy ? "disabled" : ""}>${busy ? "Checking…" : "Check golden thread"}</button></div>
      </form>
    </div>
  </div>`;
}
