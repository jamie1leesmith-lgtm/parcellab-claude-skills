#!/usr/bin/env node
/**
 * Onyx MCP Server (zero-dependency)
 *
 * Bridges an MCP client (Claude Code) to an Onyx instance's REST API so you can
 * pull Onyx-indexed knowledge into Claude. Speaks JSON-RPC 2.0 over stdio using
 * newline-delimited messages (the MCP stdio transport) and calls Onyx over HTTP
 * with Node's built-in fetch — no npm install required (Node >= 18).
 *
 * Configuration (environment variables):
 *   ONYX_API_URL   Base API URL, including the /api suffix.
 *                    Cloud:       https://cloud.onyx.app/api
 *                    Self-hosted: https://onyx.your-company.com/api
 *   ONYX_API_TOKEN A Personal Access Token (onyx_pat_...) or API key.
 *   ONYX_PERSONA_ID Optional. Assistant/persona id for chat (default 5 —
 *                    pauL, parcelLab's general-purpose Onyx assistant).
 */

const API_URL = (process.env.ONYX_API_URL || '').replace(/\/+$/, '');
const API_TOKEN = process.env.ONYX_API_TOKEN || '';
// An explicitly configured id always wins — including 0, Onyx's built-in
// default assistant. Only a missing/invalid value falls back to pauL (5).
const configuredPersonaId = Number.parseInt(process.env.ONYX_PERSONA_ID ?? '', 10);
const DEFAULT_PERSONA_ID = Number.isNaN(configuredPersonaId) ? 5 : configuredPersonaId;

const SERVER_INFO = { name: 'onyx', version: '0.1.0' };
const DEFAULT_PROTOCOL = '2025-06-18';

// ---------------------------------------------------------------------------
// Onyx REST helpers
// ---------------------------------------------------------------------------

function assertConfigured() {
  if (!API_URL || !API_TOKEN) {
    throw new Error('Onyx is not configured. Run /onyx-setup to add your Onyx URL and token, then restart Claude Code.');
  }
}

async function onyxRequest(method, path, body) {
  assertConfigured();
  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${API_TOKEN}`,
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(`Onyx API ${method} ${path} failed (${res.status}): ${text.slice(0, 500)}`);
  }
  return text;
}

async function onyxJson(method, path, body) {
  const text = await onyxRequest(method, path, body);
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

/** Semantic document search. Uses /query/document-search (available to all roles). */
async function searchOnyx({ query, document_sets = [] }) {
  const data = await onyxJson('POST', '/query/document-search', {
    message: query,
    search_type: 'hybrid',
    retrieval_options: {
      filters: {
        source_type: null,
        document_set: document_sets.length ? document_sets : null,
        time_cutoff: null,
        tags: null,
      },
      enable_auto_detect_filters: false,
    },
    evaluation_type: 'skip',
  });
  // Newer Onyx returns `top_documents`; older builds returned `documents`.
  return data?.top_documents || data?.documents || [];
}

// Resolve a persona/assistant id. The default is 5 — pauL, parcelLab's
// general-purpose Onyx assistant. Persona 0, Onyx's built-in default assistant
// (not listed by GET /persona, which only returns custom assistants), still
// works when set explicitly via ONYX_PERSONA_ID or the tool's persona_id argument.
function resolvePersonaId(explicit) {
  if (explicit != null) return explicit;
  return DEFAULT_PERSONA_ID;
}

// POST a chat message, tolerating both the current (`send-chat-message`) and
// legacy (`send-message`) endpoint names.
async function postChatMessage(payload) {
  try {
    return await onyxRequest('POST', '/chat/send-chat-message', payload);
  } catch (err) {
    if (String(err).includes('(404)')) {
      return onyxRequest('POST', '/chat/send-message', payload);
    }
    throw err;
  }
}

/** Full RAG chat answer: create a session, send one message, collect the answer. */
async function chatWithOnyx({ query, document_sets = [], persona_id }) {
  const personaId = await resolvePersonaId(persona_id);
  const session = await onyxJson('POST', '/chat/create-chat-session', {
    persona_id: personaId,
    description: 'Claude Code (Onyx plugin)',
  });
  const sessionId = session?.chat_session_id;
  if (!sessionId) throw new Error('Onyx did not return a chat_session_id.');

  const raw = await postChatMessage({
    chat_session_id: sessionId,
    parent_message_id: null,
    message: query,
    search_doc_ids: [],
    file_descriptors: [],
    prompt_id: null,
    retrieval_options: {
      run_search: 'auto',
      real_time: true,
      filters: {
        document_set: document_sets.length ? document_sets : null,
        source_type: null,
        time_cutoff: null,
        tags: null,
      },
    },
    regenerate: false,
  });

  let answer = '';
  let documents = [];

  // Try a single JSON object first (oldest style).
  try {
    const obj = JSON.parse(raw);
    if (obj.answer || obj.documents || obj.top_documents) {
      return { answer: (obj.answer || '').trim(), documents: obj.documents || obj.top_documents || [] };
    }
  } catch {
    /* fall through to line-by-line streaming parse */
  }

  for (const line of raw.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    let chunk;
    try {
      chunk = JSON.parse(trimmed);
    } catch {
      continue;
    }
    // Current schema: { obj: { type: 'message_delta', content } | { final_documents } }
    const o = chunk.obj;
    if (o && typeof o === 'object') {
      if (o.type === 'message_delta' && o.content) answer += o.content;
      if (o.final_documents && o.final_documents.length) documents = o.final_documents;
      continue;
    }
    // Legacy streaming schema.
    if (chunk.answer_piece) answer += chunk.answer_piece;
    else if (chunk.answer) answer = chunk.answer;
    if (chunk.top_documents) documents = chunk.top_documents;
  }

  return { answer: answer.trim(), documents };
}

/** Reassemble a full document from its chunks. */
async function fetchDocument({ document_id }) {
  const encoded = encodeURIComponent(document_id);
  const info = await onyxJson('GET', `/document/document-size-info?document_id=${encoded}`);
  const numChunks = Number(info?.num_chunks) || 0;
  let content = '';
  for (let i = 0; i < numChunks; i++) {
    const chunk = await onyxJson('GET', `/document/chunk-info?document_id=${encoded}&chunk_id=${i}`);
    if (chunk?.content) content += chunk.content + '\n\n';
  }
  return content.trim();
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function formatSearchResults(docs) {
  if (!docs.length) return 'No matching documents found in Onyx.';
  return docs
    .map((d, i) => {
      const title = d.semantic_identifier || d.document_id || `Result ${i + 1}`;
      const source = d.link || d.document_id || 'unknown source';
      const score = typeof d.score === 'number' ? ` (score ${d.score.toFixed(3)})` : '';
      const snippet = (d.blurb || d.content || '').trim();
      return `### ${i + 1}. ${title}${score}\nSource: ${source}\ndocument_id: ${d.document_id}\n\n${snippet}`;
    })
    .join('\n\n---\n\n');
}

function formatChat({ answer, documents }) {
  let out = answer || '(no answer returned)';
  if (documents?.length) {
    const cites = documents
      .map((d, i) => `[${i + 1}] ${d.semantic_identifier || d.document_id} — ${d.link || d.document_id}`)
      .join('\n');
    out += `\n\n**Sources:**\n${cites}`;
  }
  return out;
}

// ---------------------------------------------------------------------------
// Tool registry
// ---------------------------------------------------------------------------

const TOOLS = [
  {
    name: 'onyx_search',
    description:
      'Semantic search across your Onyx knowledge base. Returns the most relevant document chunks ' +
      '(title, source link, relevance score, and a snippet). Use this to pull raw source material ' +
      'from Onyx into Claude. Optionally scope to specific document sets.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'The natural-language search query.' },
        document_sets: {
          type: 'array',
          items: { type: 'string' },
          description: 'Optional Onyx document-set names to restrict the search to.',
        },
      },
      required: ['query'],
    },
    handler: async (args) => formatSearchResults(await searchOnyx(args)),
  },
  {
    name: 'onyx_ask',
    description:
      "Ask Onyx a question and get a synthesized, cited answer using Onyx's LLM + RAG pipeline " +
      '(as if you were chatting inside Onyx). Best when you want a direct answer rather than raw ' +
      'documents. Optionally scope to specific document sets.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'The question to ask Onyx.' },
        document_sets: {
          type: 'array',
          items: { type: 'string' },
          description: 'Optional Onyx document-set names to restrict retrieval to.',
        },
        persona_id: {
          type: 'number',
          description:
            'Optional Onyx assistant/persona id. Defaults to ONYX_PERSONA_ID, or 5 ' +
            "(pauL, parcelLab's general-purpose assistant) if unset.",
        },
      },
      required: ['query'],
    },
    handler: async (args) => formatChat(await chatWithOnyx(args)),
  },
  {
    name: 'onyx_fetch_document',
    description:
      'Fetch the full text of a single Onyx document by its document_id (reassembled from all chunks). ' +
      'Use after onyx_search when a snippet is not enough and you need the complete source.',
    inputSchema: {
      type: 'object',
      properties: {
        document_id: { type: 'string', description: 'The Onyx document_id (from an onyx_search result).' },
      },
      required: ['document_id'],
    },
    handler: async (args) => (await fetchDocument(args)) || 'Document has no retrievable content.',
  },
];

const TOOL_MAP = new Map(TOOLS.map((t) => [t.name, t]));

// ---------------------------------------------------------------------------
// JSON-RPC / MCP plumbing over stdio
// ---------------------------------------------------------------------------

function send(msg) {
  process.stdout.write(JSON.stringify(msg) + '\n');
}

function reply(id, result) {
  send({ jsonrpc: '2.0', id, result });
}

function replyError(id, code, message) {
  send({ jsonrpc: '2.0', id, error: { code, message } });
}

async function handleMessage(msg) {
  const { id, method, params } = msg;

  // Notifications (no id) require no response.
  if (id === undefined || id === null) return;

  switch (method) {
    case 'initialize':
      reply(id, {
        protocolVersion: params?.protocolVersion || DEFAULT_PROTOCOL,
        capabilities: { tools: {} },
        serverInfo: SERVER_INFO,
      });
      return;

    case 'ping':
      reply(id, {});
      return;

    case 'tools/list':
      reply(id, {
        tools: TOOLS.map(({ name, description, inputSchema }) => ({ name, description, inputSchema })),
      });
      return;

    case 'tools/call': {
      const tool = TOOL_MAP.get(params?.name);
      if (!tool) {
        replyError(id, -32602, `Unknown tool: ${params?.name}`);
        return;
      }
      try {
        const output = await tool.handler(params.arguments || {});
        reply(id, { content: [{ type: 'text', text: output }] });
      } catch (err) {
        reply(id, {
          content: [{ type: 'text', text: `Error: ${err instanceof Error ? err.message : String(err)}` }],
          isError: true,
        });
      }
      return;
    }

    default:
      replyError(id, -32601, `Method not found: ${method}`);
  }
}

// Read newline-delimited JSON from stdin.
let buffer = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk) => {
  buffer += chunk;
  let newline;
  while ((newline = buffer.indexOf('\n')) !== -1) {
    const line = buffer.slice(0, newline).trim();
    buffer = buffer.slice(newline + 1);
    if (!line) continue;
    let msg;
    try {
      msg = JSON.parse(line);
    } catch {
      continue; // ignore malformed lines
    }
    handleMessage(msg).catch((err) => {
      if (msg && msg.id != null) replyError(msg.id, -32603, String(err));
    });
  }
});

process.stdin.on('end', () => process.exit(0));
