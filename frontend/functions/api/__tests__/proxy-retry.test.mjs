// Regression test for the [[path]].js proxy's hibernate-wake-error retry.
// No test framework is set up in this frontend yet, and this one file
// doesn't warrant introducing one — the function only uses fetch/Request/
// Response/setTimeout, all real Node 18+ globals, so plain `node` runs it
// unmodified. Run with: node frontend/functions/api/__tests__/proxy-retry.test.mjs
import assert from "node:assert/strict";
import { onRequest } from "../[[path]].js";

const realFetch = globalThis.fetch;
let failures = 0;

function test(name, fn) {
  return Promise.resolve()
    .then(fn)
    .then(() => console.log(`PASS  ${name}`))
    .catch((err) => {
      failures += 1;
      console.error(`FAIL  ${name}\n      ${err.stack || err}`);
    });
}

function hibernateResponse() {
  return new Response(null, {
    status: 503,
    headers: { "x-render-routing": "hibernate-wake-error" },
  });
}

async function run() {
  await test("retries through 3 hibernate-wake-errors then returns the real success", async () => {
    let calls = 0;
    globalThis.fetch = async () => {
      calls += 1;
      if (calls <= 3) return hibernateResponse();
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    };
    const start = Date.now();
    const req = new Request("https://aladdin2.pages.dev/api/health");
    const res = await onRequest({ request: req, env: {} });
    const elapsed = Date.now() - start;
    assert.equal(res.status, 200);
    assert.equal(calls, 4, "expected exactly 4 attempts (3 failures + 1 success)");
    assert.ok(elapsed >= 3 * 3000 - 50, `expected ~3 retry delays elapsed, got ${elapsed}ms`);
  });

  await test("gives up after MAX_ATTEMPTS and returns the last hibernate-wake-error, not an infinite loop", async () => {
    let calls = 0;
    globalThis.fetch = async () => {
      calls += 1;
      return hibernateResponse();
    };
    const req = new Request("https://aladdin2.pages.dev/api/health");
    const res = await onRequest({ request: req, env: {} });
    assert.equal(res.status, 503);
    assert.equal(res.headers.get("x-render-routing"), "hibernate-wake-error");
    assert.equal(calls, 4, "expected the loop to stop at MAX_ATTEMPTS=4, not retry forever");
  });

  await test("does NOT retry a real 503 that lacks the hibernate-wake-error signal", async () => {
    let calls = 0;
    globalThis.fetch = async () => {
      calls += 1;
      return new Response(null, { status: 503 }); // no x-render-routing header
    };
    const req = new Request("https://aladdin2.pages.dev/api/health");
    const res = await onRequest({ request: req, env: {} });
    assert.equal(res.status, 503);
    assert.equal(calls, 1, "a plain 503 with no hibernate signal must not trigger a retry");
  });

  await test("does NOT retry a normal 401 (e.g. real invalid-credentials login failure)", async () => {
    let calls = 0;
    globalThis.fetch = async () => {
      calls += 1;
      return new Response(JSON.stringify({ detail: "Invalid email or password" }), { status: 401 });
    };
    const req = new Request("https://aladdin2.pages.dev/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: "x@example.com", password: "wrong" }),
    });
    const res = await onRequest({ request: req, env: {} });
    assert.equal(res.status, 401);
    assert.equal(calls, 1);
  });

  await test("forwards a POST JSON body correctly, and unchanged across a retry", async () => {
    const bodiesSeen = [];
    let calls = 0;
    globalThis.fetch = async (reqArg) => {
      calls += 1;
      const text = await reqArg.text();
      bodiesSeen.push(text);
      if (calls === 1) return hibernateResponse();
      return new Response(null, { status: 200 });
    };
    const payload = JSON.stringify({ email: "user@example.com", password: "hunter2" });
    const req = new Request("https://aladdin2.pages.dev/api/auth/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: payload,
    });
    const res = await onRequest({ request: req, env: {} });
    assert.equal(res.status, 200);
    assert.equal(calls, 2);
    assert.deepEqual(bodiesSeen, [payload, payload], "the same body must reach the backend on every attempt");
  });

  await test("honors env.BACKEND_ORIGIN override", async () => {
    let seenUrl;
    globalThis.fetch = async (reqArg) => {
      seenUrl = reqArg.url;
      return new Response(null, { status: 200 });
    };
    const req = new Request("https://aladdin2.pages.dev/api/health");
    await onRequest({ request: req, env: { BACKEND_ORIGIN: "https://staging-backend.example.com" } });
    assert.equal(seenUrl, "https://staging-backend.example.com/api/health");
  });

  globalThis.fetch = realFetch;
  console.log(failures === 0 ? "\nALL TESTS PASSED" : `\n${failures} TEST(S) FAILED`);
  process.exit(failures === 0 ? 0 : 1);
}

run();
