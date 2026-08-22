// Proxies /api/* to the Render backend so the session cookie is set on the
// same origin the browser sees (aladdin2.pages.dev), not a cross-site one.
// Safari's Intelligent Tracking Prevention (and increasingly Chrome/Firefox
// privacy modes) block third-party cookies by default, which silently broke
// login when the frontend called the Render domain directly. Runs at the
// edge on every request, so BACKEND_ORIGIN can be overridden via a Pages
// environment variable without a redeploy if the backend URL ever changes.
const DEFAULT_BACKEND_ORIGIN = "https://aladdin2-backend.onrender.com";

export async function onRequest(context) {
  const { request, env } = context;
  const backendOrigin = env.BACKEND_ORIGIN || DEFAULT_BACKEND_ORIGIN;
  const url = new URL(request.url);
  const backendUrl = backendOrigin + url.pathname + url.search;

  return fetch(new Request(backendUrl, request));
}
