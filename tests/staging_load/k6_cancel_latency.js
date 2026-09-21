// F-1: cancel latency < 100 ms @ p(99) — k6 variant (staging load).
//
// Staging model (MVP-PROMPTS §F-1): 50 parallel LLM sessions, each cancelled
// SESSION_DELAY_S (5 s) after its own start. With PER-VU iterations the natural
// session cadence lands near the 10 RPS of new sessions from the spec.
//
// Measurement is end-to-end: from POST /sessions/{id}/cancel (send) until the SSE
// stream actually closes (last chunk after cancel), i.e. the graph stopped.
//
// Run on staging:
//   k6 run --vus 50 --env BASE_URL=https://staging.example.com tests/staging_load/k6_cancel_latency.js
//
// Env overrides:
//   BASE_URL         required  web-server base URL
//   SESSION_DELAY_S  default 5  seconds between session start and cancel (staging)
//   ITERS            default 1000 (DoD: 1000 samples for p99 statistics)
//   BUDGET_MS        default 100  threshold: p(99) latency wallet
//
// Thresholds: p(99) < BUDGET_MS, checks pass 100%, http_req_failed < 1%.
import { check, sleep } from 'k6';
import http from 'k6/http';
import { Counter, Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL;
const SESSION_DELAY_S = parseFloat(__ENV.SESSION_DELAY_S || '5');
const ITERS = parseInt(__ENV.ITERS || '1000', 10);
const BUDGET_MS = parseFloat(__ENV.BUDGET_MS || '100');

const cancelLatency = new Trend('cancel_latency_ms');
const cancelledCount = new Counter('cancel_sessions_total');

export const options = {
  scenarios: {
    cancel_latency: {
      executor: 'per-vu-iterations',
      vus: 50,
      iterations: ITERS,
      maxDuration: '10m',
    },
  },
  thresholds: {
    // F-1 DoD: p99 cancel latency < 100 ms, p50/p95 reported in the JSON output.
    cancel_latency_ms: [`p(99)<${BUDGET_MS}`],
    checks: ['rate==1'],
    http_req_failed: ['rate<0.01'],
  },
};

function newSessionId() {
  // Random session id used only if the API tolerates client-supplied ids; most
  // deployments return the id from POST /sessions and this fallback is unused.
  return `k6-${Date.now().toString(16)}-${Math.floor(Math.random() * 0xffff).toString(16)}`;
}

// Opens a streaming GET, keeps it alive until the server closes it after cancel.
function openStream(client, sessionId) {
  return client.request('GET', `${BASE_URL}/sessions/${sessionId}/stream`, {
    headers: { Accept: 'text/event-stream' },
    timeout: '90s', // generous; the stream must close on its own after cancel
  });
}

export default async function () {
  if (!BASE_URL) {
    throw new Error('BASE_URL env is required (staging web-server URL)');
  }
  const client = http.newAsyncClient();

  // 1. Create the LLM session.
  const created = await client.request('POST', `${BASE_URL}/sessions`, {
    json: { request_id: newSessionId() },
  });
  check(created, { 'create session 200': (r) => r.status === 200 });
  const sessionId = created.json('session_id');
  if (!sessionId) {
    return; // session creation failed: checks guard already failed
  }

  // 2. Keep the SSE stream open in the background (the "running graph").
  const streamPromise = openStream(client, sessionId);

  // 3. Let the graph run a while, then cancel end-to-end.
  sleep(SESSION_DELAY_S);
  const tCancel = Date.now();
  const cancel = await client.request(
    'POST',
    `${BASE_URL}/sessions/${sessionId}/cancel`,
    { json: { reason: 'user_cancelled', user_id: 'f1-k6' } },
  );
  check(cancel, { 'cancel 202': (r) => r.status === 202 });

  // 4. Wait until the server actually closes the stream (graph stopped).
  const stream = await streamPromise;
  const latencyMs = Date.now() - tCancel;
  cancelLatency.add(latencyMs);
  cancelledCount.add(1);
  check(stream, {
    'stream closed after cancel': (r) => r.status === 200,
    'partial answer returned': (r) => r.body && r.body.includes('partial_answer'),
  });
  check(latencyMs, {
    'cancel latency < 100 ms': (v) => v < BUDGET_MS,
  });
  if (__ENV.FORENSIC_CHECK === '1') {
    const forensic = await client.request(
      'GET',
      `${BASE_URL}/sessions/${sessionId}/forensic`,
      { timeout: '10s' },
    );
    check(forensic, {
      'forensic log has session_cancelled': (r) => r.body && r.body.includes('session_cancelled'),
    });
  }
}