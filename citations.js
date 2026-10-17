// Citation audit page: sends a draft and the selected notebook sources to the
// engine's /citations/audit endpoint, then shows each sentence's verdict and
// the passage it was checked against. The matching rules live in the backend.

const AUDIT_EXAMPLE_SOURCES = [
  { id: "example-wanjiru-2019", name: "Wanjiru & Otieno 2019 — Distance and facility delivery", type: "Paper", detail: "Example source", text: "Wanjiru, M. and Otieno, J. (2019). Distance and facility delivery in Kitui County, Kenya.\n\nWe surveyed 812 women who had given birth in the previous two years. Women living more than 5 kilometres from a health facility were less likely to deliver with a skilled birth attendant. Overall, 46% of births in the sample were attended by skilled personnel. Household wealth was not significantly associated with skilled birth attendance after adjusting for distance." },
  { id: "example-achieng-2021", name: "Achieng 2021 — Decision-making autonomy and maternal care", type: "Paper", detail: "Example source", text: "Achieng, R. (2021). Decision-making autonomy and maternal care in western Kenya.\n\nWomen with greater household decision-making autonomy had higher odds of skilled birth attendance. Partner approval remained a strong influence on where women chose to deliver. Community health volunteers improved antenatal care attendance in the study villages." },
];

const AUDIT_EXAMPLE_DRAFT = "Women who live more than 5 kilometres from a health facility are less likely to deliver with a skilled birth attendant (Wanjiru & Otieno, 2019). In Kitui, 64% of births were attended by skilled personnel (Wanjiru & Otieno, 2019). Household wealth is significantly associated with skilled birth attendance (Wanjiru & Otieno, 2019). Achieng (2021) found that greater household decision-making autonomy raised the odds of skilled birth attendance. Mobile phone ownership improves childhood vaccination coverage (Achieng, 2021). Community health volunteers improved antenatal care attendance [1]. Previous research shows that 30% of rural women deliver at home.\n\nThis study will survey 400 women in Kitui.";

const AUDIT_VERDICTS = {
  supported: "Supported", partial: "Partly supported", contrasting: "Possible contrast", "misquoted-number": "Number not in source",
  unrelated: "Source doesn't discuss this", unresolved: "Citation not linked", unknown: "Too short to check", "needs-citation": "Needs a citation",
};
const AUDIT_STATUS = {
  supported: ["Citations hold up", "Every checked citation matched its source. Still read the passages: matching words is not the same as matching meaning."],
  review: ["Review", "No misrepresentations found, but some citations are partial, unlinked or missing."],
  "needs-revision": ["Needs revision", "At least one citation may misrepresent its source, misquote a number, or cite a source that doesn't discuss the claim."],
};

let auditRequest = null;

function auditState() {
  state.audit ||= { text: "", auditedText: "", report: null, error: "", focus: null, references: {} };
  return state.audit;
}

function auditText(value) { auditState().text = value; save(); }

function loadAuditExample() {
  const audit = auditState();
  AUDIT_EXAMPLE_SOURCES.forEach((example) => {
    if (!source(example.id)) state.sources.unshift({ ...example });
    if (!state.selectedSourceIds.includes(example.id)) state.selectedSourceIds.push(example.id);
  });
  Object.assign(audit, { text: AUDIT_EXAMPLE_DRAFT, auditedText: "", report: null, error: "", focus: null, references: {} });
  save(); render(); notify("Example draft and two example papers added. Run the audit to see what it finds.");
}

function clearAudit() { Object.assign(auditState(), { text: "", auditedText: "", report: null, error: "", focus: null, references: {} }); save(); render(); }

function setAuditReference(key, sourceId) {
  const audit = auditState();
  if (sourceId) audit.references[key] = sourceId; else delete audit.references[key];
  save(); runAudit();
}

function focusAuditSentence(index) { const audit = auditState(); audit.focus = audit.focus === index ? null : index; save(); render(); }

async function runAudit() {
  const audit = auditState();
  if (!audit.text.trim()) return notify("Paste a draft paragraph first.");
  auditRequest?.abort();
  auditRequest = new AbortController();
  audit.error = ""; audit.focus = null;
  render();
  try {
    const sourceIds = await syncSelectedSources(auditRequest.signal);
    audit.references = Object.fromEntries(Object.entries(audit.references).filter(([, id]) => sourceIds.includes(id)));
    const text = audit.text;
    audit.report = await enginePost("/citations/audit", { text, source_ids: sourceIds, references: audit.references }, auditRequest.signal);
    audit.auditedText = text;
  } catch (error) {
    if (error.name === "AbortError") return;
    audit.error = error instanceof TypeError ? engineUnreachableMessage() : error.message;
  } finally {
    auditRequest = null;
  }
  save(); render();
  document.querySelector(".gt-results")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function auditItems(sentence) {
  return [...sentence.citations.map((check) => ({ ...check, kind: "citation" })), ...sentence.flags.map((flag) => ({ verdict: flag, severity: "warning", kind: "flag" }))];
}

function renderAuditCard(item, sentence, report, showSentence) {
  const guide = report.guidance[item.verdict] || {};
  const severity = item.severity || "ok";
  const head = item.kind === "flag" ? "No citation" : `${esc(item.label)}${item.source_name ? ` → ${esc(item.source_name)}` : ""}`;
  const passage = item.passage ? `<blockquote class="ca-quote"><span>${esc(item.passage.source_name)}${item.passage.page ? `, p. ${item.passage.page}` : ""}${item.coverage !== null ? ` · ${Math.round(item.coverage * 100)}% of claim terms found` : ""}</span>${esc(item.passage.quote)}</blockquote>` : "";
  const notes = (item.notes || []).map((note) => `<li>${esc(note)}</li>`).join("");
  const mapper = item.verdict === "unresolved" ? renderAuditMapper(item) : "";
  return `<article class="gt-issue ${severity} ca-card">${showSentence ? `<button class="ca-sentence-link" onclick="focusAuditSentence(${sentence.index})">“${esc(sentence.text.length > 140 ? `${sentence.text.slice(0, 139)}…` : sentence.text)}”</button>` : ""}<div class="gt-issue-head"><span class="gt-sev ${severity === "ok" ? "ok" : severity}">${esc(AUDIT_VERDICTS[item.verdict] || item.verdict)}</span><strong>${head}</strong></div>${notes ? `<ul class="ca-notes">${notes}</ul>` : ""}${passage}${mapper}${item.verdict !== "supported" ? `<p><b>Why it matters</b>${esc(guide.teach)}</p><p class="gt-ask"><b>Ask yourself</b>${esc(guide.ask)}</p>` : `<p class="gt-ask"><b>Ask yourself</b>${esc(guide.ask)}</p>`}</article>`;
}

function renderAuditMapper(item) {
  const options = selectedSources().filter((entry) => !item.candidates.length || item.candidates.includes(entry.id));
  if (!options.length) return `<p class="ca-hint">Add the source for ${esc(item.label)} to the evidence library and select it, then run the audit again.</p>`;
  return `<label class="ca-mapper"><span>Link ${esc(item.label)} to</span><select data-key="${esc(item.key)}" onchange="setAuditReference(this.dataset.key, this.value)"><option value="">Choose a selected source…</option>${options.map((entry) => `<option value="${esc(entry.id)}">${esc(entry.name)}</option>`).join("")}</select></label>`;
}

function renderAnnotatedDraft(report, focus) {
  const text = auditState().auditedText;
  let cursor = 0, html = "";
  report.sentences.forEach((sentence) => {
    html += esc(text.slice(cursor, sentence.start));
    const level = sentence.severity || (sentence.citations.length ? "ok" : "");
    html += level ? `<button class="ca-sentence ${level} ${focus === sentence.index ? "focused" : ""}" onclick="focusAuditSentence(${sentence.index})">${esc(sentence.text)}</button>` : `<span class="ca-plain">${esc(sentence.text)}</span>`;
    cursor = sentence.end;
  });
  return `<div class="ca-draft">${html}${esc(text.slice(cursor))}</div>`;
}

function renderAuditResults(audit) {
  const report = audit.report;
  if (audit.error) return `<section class="gt-results"><div class="gt-error"><strong>Audit didn't run</strong><p>${esc(audit.error)}</p></div></section>`;
  if (!report) return "";
  if (audit.text !== audit.auditedText) return `<section class="gt-results"><div class="gt-empty"><strong>The draft has changed since the last audit.</strong><p>Run the audit again to see results for the current text.</p></div></section>`;
  const [title, explanation] = AUDIT_STATUS[report.status] || [report.status, ""];
  const counts = report.counts;
  const errors = counts.contrasting + counts["misquoted-number"] + counts.unrelated;
  const judged = counts.supported + counts.partial + errors;
  const focused = report.sentences.find((sentence) => sentence.index === audit.focus);
  const problems = report.sentences.flatMap((sentence) => auditItems(sentence).filter((item) => item.severity && item.severity !== "info").map((item) => ({ item, sentence })));
  problems.sort((a, b) => ({ error: 0, warning: 1 }[a.item.severity] ?? 2) - ({ error: 0, warning: 1 }[b.item.severity] ?? 2));
  return `<section class="gt-results">
    <div class="gt-verdict ${report.status === "supported" ? "aligned" : report.status}"><div><span class="gt-kicker">Citation audit</span><strong>${title}</strong><p>${explanation}</p></div><dl><div><dt>${errors}</dt><dd>problems</dd></div><div><dt>${counts.partial + counts.unresolved + counts["needs-citation"]}</dt><dd>to review</dd></div><div><dt>${counts.supported}/${judged}</dt><dd>checked citations supported</dd></div></dl></div>
    <div class="gt-panel"><div class="gt-panel-head"><strong>Your draft</strong><span>Select a sentence to see the passage it was checked against.</span></div>${renderAnnotatedDraft(report, audit.focus)}<div class="gt-legend"><span><i class="ca-swatch error"></i>problem</span><span><i class="ca-swatch warning"></i>review</span><span><i class="ca-swatch ok"></i>supported</span><span>no mark: not a cited claim</span></div></div>
    <div class="gt-panel"><div class="gt-panel-head"><strong>${focused ? `Sentence ${focused.index}` : "What to fix"}</strong>${focused ? `<button class="gt-link" onclick="focusAuditSentence(${focused.index})">Show everything to fix</button>` : `<span>${problems.length} item${problems.length === 1 ? "" : "s"}, most serious first</span>`}</div><div class="gt-issues">${focused ? (auditItems(focused).map((item) => renderAuditCard(item, focused, report, false)).join("") || `<div class="gt-empty small">This sentence has no citation and doesn't read as a claim that needs one.</div>`) : (problems.map(({ item, sentence }) => renderAuditCard(item, sentence, report, true)).join("") || `<div class="gt-empty small">Nothing to fix. Select a sentence to read the passage behind it.</div>`)}</div></div>
    <p class="gt-method">${esc(report.method.charAt(0).toUpperCase() + report.method.slice(1))}. Checked against the ${selectedSources().length} notebook source${selectedSources().length === 1 ? "" : "s"} selected in the evidence library.</p>
  </section>`;
}

function renderCitationAudit() {
  const audit = auditState();
  const busy = Boolean(auditRequest);
  return `<div class="gt-page">
    <section class="gt-intro"><span class="m-kicker">Phase 1 · Methodology engine</span><h1>Citation audit</h1><p>Check that each source you cite actually says what your sentence claims, that numbers match, and that factual claims carry a citation. Mwenza shows you the passage it compared against. It never rewrites your text.</p><div class="gt-intro-actions"><button class="gt-btn ghost" onclick="loadAuditExample()">Load example with flaws</button><button class="gt-btn ghost" onclick="clearAudit()">Clear</button><button class="gt-btn ghost" onclick="go('sources')">Choose sources (${selectedSources().length} selected)</button></div></section>
    <div class="gt-layout">
      ${renderAuditResults(audit)}
      <form class="gt-form" onsubmit="event.preventDefault(); runAudit()">
        <label class="gt-field"><span>Draft text</span><textarea rows="12" placeholder="Paste a paragraph or section with citations, e.g. (Ouma, 2021), Ouma et al. (2021) or [3]." oninput="auditText(this.value)">${esc(audit.text)}</textarea></label>
        <p class="ca-hint">Author–year citations are matched to selected sources by surname and year in the source's name or opening text. Numbered citations such as [3] need linking once; Mwenza remembers the link.</p>
        <div class="gt-submit">${renderEngineField()}<button class="gt-btn primary" type="submit" ${busy ? "disabled" : ""}>${busy ? "Auditing…" : "Audit citations"}</button></div>
      </form>
    </div>
  </div>`;
}
