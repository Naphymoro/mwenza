// Shared connection to the Mwenza evidence engine for the methodology pages.
// Browser sources are pushed to the engine under their own ids, so the engine
// can cite them; re-sending a source replaces the engine's copy.

function engineUrl() { state.engineUrl ||= "http://localhost:8000"; return state.engineUrl; }
function setEngineUrl(value) { state.engineUrl = value.trim().replace(/\/+$/, ""); save(); }

function engineUnreachableMessage() {
  return `Couldn't reach the Mwenza engine at ${engineUrl()}. Start it with "uvicorn mwenza_engine.api:app --app-dir backend/src" and open this page from http://localhost (for example "python -m http.server").`;
}

async function enginePost(path, body, signal) {
  const response = await fetch(`${engineUrl()}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });
  if (!response.ok) throw new Error(`The engine rejected the request to ${path} (HTTP ${response.status}).`);
  return response.json();
}

async function syncSelectedSources(signal) {
  const sources = selectedSources().filter((item) => String(item.text || "").trim());
  await Promise.all(sources.map((item) => enginePost("/sources/text", { name: item.name, text: item.text, source_id: item.id }, signal)));
  return sources.map((item) => item.id);
}

function renderEngineField() {
  return `<label class="gt-engine"><span>Engine</span><input value="${esc(engineUrl())}" aria-label="Engine URL" onchange="setEngineUrl(this.value)" /></label>`;
}
