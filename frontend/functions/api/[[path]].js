// Proxies /api/* to the Render backend so the session cookie is set on the
// same origin the browser sees (aladdin2.pages.dev), not a cross-site one.
// Safari's Intelligent Tracking Prevention (and increasingly Chrome/Firefox
// privacy modes) block third-party cookies by default, which silently broke
// login when the frontend called the Render domain directly. Runs at the
// edge on every request, so BACKEND_ORIGIN can be overridden via a Pages
// environment variable without a redeploy if the backend URL ever changes.
const DEFAULT_BACKEND_ORIGIN = "https://aladdin2-backend.onrender.com";

// Render's free tier hibernates the backend after inactivity. Confirmed live
// 2026-09-02: while the wake-up is in flight, Render's own edge answers with
// a bodyless 503 carrying `x-render-routing: hibernate-wake-error` BEFORE the
// request ever reaches our app (verified: hitting the backend directly right
// after seeds this same response, then a few seconds later starts returning
// real 200s). This function forwarded that straight to the browser with zero
// retries, so every cold request — login included — failed with a generic,
// misleading "Invalid email or password" from the frontend's own catch-all
// error text, not a real auth failure. Retrying here is safe specifically
// BECAUSE this exact response proves the app was never reached: there is no
// double-execution risk on a login/register POST that never ran.
//
// 2026-09-09a: the original 4-attempt/3s budget (~9s of retry sleep) was too
// short. Directly measured against the live backend: repeated cold wakes
// took anywhere from ~15s up to ~90s+ before the first real 200. Raised the
// budget to comfortably clear the slowest wake observed.
//
// 2026-09-09b: raising the budget wasn't enough on its own — a user hit the
// SAME misleading error again afterward. Reproduced live: the very FIRST
// connection attempt to a cold instance doesn't always get the tidy
// hibernate-wake-error 503 at all. Sometimes it just hangs — zero bytes,
// for 25-30s — before failing outright, because Render's own edge hasn't
// finished standing up routing yet. `fetch()` throws in that case instead
// of returning a response, which this loop never caught: one unlucky first
// attempt crashed straight past every retry. Fixed by (1) wrapping fetch in
// a per-attempt timeout via AbortController so a hang can't silently eat
// the whole budget on one attempt, and (2) catching the resulting exception
// and treating it exactly like a hibernate-wake-error — retryable, for the
// same reason: a connection that never received a byte back could not have
// been processed by the app on the other end, so retrying a POST here
// carries no double-execution risk either.
const MAX_ATTEMPTS = 13;
const RETRY_DELAY_MS = 8000;
const PER_ATTEMPT_TIMEOUT_MS = 10000;

function isHibernateWakeError(response) {
  return response.status === 503 && response.headers.get("x-render-routing") === "hibernate-wake-error";
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Cloudflare Pages Functions' CPU-time limit only meters actual computation,
// not I/O wait, so a long-running loop of sleep()/fetch() calls here doesn't
// run into it — the same reasoning the 2026-09-09a retry-budget increase
// already relied on. The AbortController timeout below bounds each
// individual attempt so a hang can't consume the loop's entire budget by
// itself.
async function attemptFetch(backendUrl, request, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(new Request(backendUrl, request.clone()), { signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

export async function onRequest(context) {
  const { request, env } = context;
  const backendOrigin = env.BACKEND_ORIGIN || DEFAULT_BACKEND_ORIGIN;
  const url = new URL(request.url);
  const backendUrl = backendOrigin + url.pathname + url.search;

  // Tracks the last real response received (a hibernate-wake-error 503),
  // separately from a connection-level failure, so the two can be told
  // apart once the loop runs out of attempts.
  let lastResponse = null;
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    try {
      const response = await attemptFetch(backendUrl, request, PER_ATTEMPT_TIMEOUT_MS);
      if (!isHibernateWakeError(response)) {
        return response;
      }
      lastResponse = response;
    } catch {
      // Connection-level failure (timeout/abort, DNS, TCP reset) — the
      // request never reached the app. Treated the same as a
      // hibernate-wake-error: retryable, no double-execution risk.
      lastResponse = null;
    }
    if (attempt < MAX_ATTEMPTS) {
      await sleep(RETRY_DELAY_MS);
    }
  }

  if (lastResponse) {
    return lastResponse; // the last hibernate-wake-error 503, forwarded as-is
  }

  // Every attempt failed at the connection level — return a real, readable
  // response instead of letting the last exception propagate as an
  // unhandled Cloudflare error page (which the frontend's generic catch-all
  // would otherwise render as a misleading auth failure, same as the bug
  // this whole retry loop exists to prevent).
  return new Response(
    JSON.stringify({
      detail: "The backend is not responding after repeated attempts. Please try again shortly.",
    }),
    { status: 503, headers: { "content-type": "application/json" } },
  );
}
