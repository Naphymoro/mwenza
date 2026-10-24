// Mwenza's model on Workers AI, for DeerFlow's gateway: an OpenAI-style /v1/chat/completions (streaming and tool
// calls included) answered through the AI binding, so no outside API key or company is involved. Modelled on NDIM's
// Worker (nidm-rwanda-dashboard/cloudflare/engine-container/src/ai.ts) but separate, with its own token and cap.
//
// Costs stay small: the Worker picks the model (callers cannot ask for a dearer one), caps the reply length and stops
// for the day once MWENZA_AI_DAILY_NEURONS are used. Workers AI's free 10,000 Neurons a day are per account and NDIM
// caps itself at 9,000, so keep this cap low.

export interface Env {
  AI: Ai;
  DB: D1Database;
  MWENZA_AI_TOKEN?: string;
  MWENZA_AI_MODEL?: string;
  MWENZA_AI_DAILY_NEURONS?: string;
}

const DAILY_NEURONS = 3000;
const MAX_TOKENS = 6000; // reasoning models spend part of it thinking
const PATH = "/v1/chat/completions";

const today = () => new Date().toISOString().slice(0, 10);

const refusal = (message: string, status: number) =>
  new Response(JSON.stringify({ error: { message } }), { status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });

function record(env: Env, neurons: number) {
  return env.DB.prepare(
    "INSERT INTO ai_usage (day, requests, neurons) VALUES (?, 1, ?) " +
    "ON CONFLICT(day) DO UPDATE SET requests = requests + 1, neurons = neurons + excluded.neurons",
  ).bind(today(), neurons).run();
}

// LangChain may send content as a list of blocks; Workers AI models take a string.
function flatten(messages: any[]) {
  return messages.map((message) => Array.isArray(message?.content)
    ? { ...message, content: message.content.map((block: any) => typeof block === "string" ? block : block?.type === "text" ? block.text : "").join("") }
    : message);
}

async function chat(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
  let used: { neurons: number } | null;
  try {
    used = await env.DB.prepare("SELECT neurons FROM ai_usage WHERE day = ?").bind(today()).first<{ neurons: number }>();
  } catch (error) {
    console.error("reading today's AI usage failed; refusing (the cap must hold)", error);
    return refusal("Mwenza's model is unavailable right now. Try again in a minute.", 503);
  }
  if ((used?.neurons ?? 0) >= Number(env.MWENZA_AI_DAILY_NEURONS || DAILY_NEURONS)) {
    return refusal("Mwenza's model has used today's allowance. It resets at 00:00 UTC.", 429);
  }
  let body: any;
  try {
    body = await request.json();
  } catch {
    return refusal("The request body is not JSON.", 400);
  }
  if (!Array.isArray(body?.messages)) return refusal("messages must be a list.", 400);
  const inputs = {
    messages: flatten(body.messages),
    ...(body.tools ? { tools: body.tools } : {}),
    temperature: typeof body.temperature === "number" ? body.temperature : 0.3,
    max_tokens: Math.min(Number(body.max_tokens || body.max_completion_tokens) || MAX_TOKENS, MAX_TOKENS),
    stream: body.stream === true,
  };
  let out: any;
  try {
    out = await env.AI.run(env.MWENZA_AI_MODEL as any, inputs as any);
  } catch (error) {
    console.error("Workers AI failed", error);
    return refusal("Mwenza's model is not answering right now. Try again in a minute.", 502);
  }
  if (!(out instanceof ReadableStream)) {
    ctx.waitUntil(record(env, Number(out?.usage?.neurons) || 0));
    return Response.json(out);
  }
  // Each streamed chunk carries the running usage; the last Neurons figure is the reply's total.
  let neurons = 0;
  let tail = "";
  const decoder = new TextDecoder();
  const counted = new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      const text = tail + decoder.decode(chunk, { stream: true });
      for (const match of text.matchAll(/"neurons":\s*([\d.]+)/g)) neurons = Math.max(neurons, Number(match[1]));
      tail = text.slice(-64); // a figure split across chunks is read on the next one
      controller.enqueue(chunk);
    },
    flush() {
      ctx.waitUntil(record(env, neurons));
    },
  });
  return new Response(out.pipeThrough(counted), { headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-store" } });
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const token = (request.headers.get("Authorization") || "").replace(/^Bearer\s+/i, "");
    // Anything without the token, or off the one route, looks like nothing is here.
    if (!env.MWENZA_AI_TOKEN || !env.MWENZA_AI_MODEL || token !== env.MWENZA_AI_TOKEN) return new Response("Not Found", { status: 404 });
    if (request.method !== "POST" || new URL(request.url).pathname !== PATH) return new Response("Not Found", { status: 404 });
    return chat(request, env, ctx);
  },
} satisfies ExportedHandler<Env>;
