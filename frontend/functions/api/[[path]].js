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
const MAX_ATTEMPTS = 4;
const RETRY_DELAY_MS = 3000;

function isHibernateWakeError(response) {
  return response.status === 503 && response.headers.get("x-render-routing") === "hibernate-wake-error";
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function onRequest(context) {
  const { request, env } = context;
  const backendOrigin = env.BACKEND_ORIGIN || DEFAULT_BACKEND_ORIGIN;
  const url = new URL(request.url);
  const backendUrl = backendOrigin + url.pathname + url.search;

  let response;
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    // Clone the ORIGINAL, still-unconsumed request on every attempt — the
    // Request constructor consumes whatever body object it's handed, so the
    // same clone can never be replayed twice.
    response = await fetch(new Request(backendUrl, request.clone()));
    if (!isHibernateWakeError(response)) {
      return response;
    }
    if (attempt < MAX_ATTEMPTS) {
      await sleep(RETRY_DELAY_MS);
    }
  }
  return response;
}
