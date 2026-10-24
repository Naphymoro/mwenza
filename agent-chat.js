// Research chat on the Mwenza agent (DeerFlow), through the engine's /agent/chat. The engine streams the steps
// the agent takes and then one reply that Mwenza's constitution has already checked; drafts it withdrew are never
// sent. Without the agent the chat answers from the sources in scope (groundedAnswer in app.js).

// Private chats stay on this machine's local model; the engine stores the flag and never lets it be turned off.
const ROUTE_NOTES = {
  private: "Private chat: answered by the local model on this machine. Nothing in this chat left it.",
  "local-fallback": "The main model was unavailable, so Mwenza's local model answered. Its supervision is weaker: check its suggestions with care.",
};

const AGENT_TITLES = { answer: "Mwenza", question: "Mwenza asks", unavailable: "Mwenza is unavailable", error: "Mwenza couldn't answer" };

async function probeAgent() {
  try {
    const status = await engineGet("/agent/status");
    state.agentEnabled = Boolean(status.enabled);
    state.agentPrivateAvailable = Boolean(status.private_available);
  } catch (_) {
    state.agentEnabled = false;
    state.agentPrivateAvailable = false;
  }
  render();
}

async function* sseEvents(body) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    let cut;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      const event = (frame.match(/^event: (.*)$/m) || [])[1] || "message";
      const data = frame.split("\n").filter((line) => line.startsWith("data: ")).map((line) => line.slice(6)).join("\n");
      if (data) yield [event, JSON.parse(data)];
    }
    if (done) return;
  }
}

function agentRouteNote(route) {
  return ROUTE_NOTES[route] ? `<div class="m-agent-route ${route === "private" ? "private" : ""}">${esc(ROUTE_NOTES[route])}</div>` : "";
}

// Once a chat has been private it stays private; the engine enforces this too.
function togglePrivateChat() {
  if (state.agentThreadId && state.agentPrivate) return notify("This chat is private and stays private. Start a new chat for a standard one.");
  state.agentPrivate = !state.agentPrivate;
  save();
  render();
}

function renderPrivateToggle() {
  if (!state.agentEnabled || !state.agentPrivateAvailable) return "";
  const on = Boolean(state.agentPrivate);
  return `<button type="button" class="m-compose-tool m-private-toggle ${on ? "on" : ""}" aria-pressed="${on}" onclick="togglePrivateChat()" title="Private chats use only the local model on this machine, for transcripts, health records and other sensitive material.">${on ? "● Private: stays on this machine" : "○ Private chat"}</button>`;
}

// Data files go to the chat's uploads in DeerFlow, where the agent lists them and the sandbox reads them.
const MAX_ATTACHMENT = 50 * 1024 * 1024;

async function attachAgentFile(input) {
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  if (file.size > MAX_ATTACHMENT) return notify("That file is larger than 50 MB.");
  const form = new FormData();
  form.append("file", file);
  const params = new URLSearchParams({ private: String(Boolean(state.agentPrivate)) });
  if (state.agentThreadId) params.set("thread_id", state.agentThreadId);
  try {
    const response = await fetch(`${engineUrl()}/agent/upload?${params}`, { method: "POST", body: form });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `The engine rejected the file (HTTP ${response.status}).`);
    Object.assign(state, { agentThreadId: data.thread_id, agentPrivate: Boolean(data.private), page: "chat" });
    state.agentPendingFiles = [...(state.agentPendingFiles || []), ...(data.details || [])];  // sent with the next message
    state.messages.push({ role: "user", text: `Attached ${data.files.join(", ")}` });
    save();
    render();
  } catch (error) {
    notify(error instanceof TypeError ? engineUnreachableMessage() : error.message);
  }
}

function renderAttachButton() {
  if (!state.agentEnabled) return "";
  return `<label class="m-compose-tool m-attach">⇪ Attach data<input type="file" hidden accept=".csv,.tsv,.txt,.json,.xlsx,.xls,.sav,.dta,.rds" onchange="attachAgentFile(this)" /></label>`;
}

function agentReviewNote(review) {
  if (!review || review.status === "pass") return "";
  const kinds = [...new Set((review.findings || []).map((finding) => finding.kind))];
  const text = review.status === "blocked"
    ? "Mwenza's integrity check changed this reply: it labelled what it could not verify and withheld any text written for you to paste."
    : `Mwenza's integrity check noted: ${kinds.join(", ").replace(/-/g, " ")}.`;
  return `<div class="m-agent-review">${esc(text)}</div>`;
}

// Bold and inline code only: enough for the agent's replies, with everything escaped first.
function agentRunsNote(runs) {
  if (!runs?.length) return "";
  const items = runs.map((run) => run.kind === "rerun"
    ? `Re-ran analysis ${run.capsule_id}: ${run.agree ? "same results" : "results differ"}`
    : `Analysis ${run.capsule_id} recorded in your provenance log`);
  return `<div class="m-agent-route">${items.map(esc).join(" · ")}</div>`;
}

function agentText(text) {
  return esc(text).replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>").replace(/`([^`\n]+)`/g, "<code>$1</code>");
}

async function askAgent(text) {
  const answer = { title: AGENT_TITLES.answer, text: "", steps: [], pending: true, agent: true };
  state.messages.push({ role: "user", text }, { role: "assistant", answer });
  state.page = "chat";
  render();
  const scroll = () => requestAnimationFrame(() => document.querySelector(".m-chat-scroll")?.scrollTo(0, 99999));
  scroll();
  try {
    const response = await fetch(`${engineUrl()}/agent/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: text, thread_id: state.agentThreadId || null, private: Boolean(state.agentPrivate), files: state.agentPendingFiles || [] }) });
    if (!response.ok) throw new Error(`The engine rejected the chat (HTTP ${response.status}).`);
    state.agentPendingFiles = [];
    for await (const [event, data] of sseEvents(response.body)) {
      if (event === "thread") Object.assign(state, { agentThreadId: data.thread_id, agentPrivate: Boolean(data.private) });
      else if (event === "step") answer.steps.push(data.label);
      else if (event === "notice") answer.status = data.message;
      else if (event === "reply") Object.assign(answer, { text: data.text, title: AGENT_TITLES[data.kind] || AGENT_TITLES.answer, review: data.review, route: data.route, runs: data.runs });
      else if (event === "error") Object.assign(answer, { text: data.message, title: AGENT_TITLES.error });
      render();
      scroll();
    }
  } catch (error) {
    Object.assign(answer, { text: error instanceof TypeError ? engineUnreachableMessage() : error.message, title: AGENT_TITLES.error });
  } finally {
    answer.pending = false;
    if (!answer.text) Object.assign(answer, { text: "The connection closed before Mwenza replied. Try again.", title: AGENT_TITLES.error });
    save();
    render();
    scroll();
  }
}
