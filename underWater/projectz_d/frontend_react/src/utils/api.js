const rawApiBase = import.meta.env.VITE_API_BASE_URL || "/api";
const API_BASE_URL = rawApiBase.endsWith("/")
  ? rawApiBase.slice(0, -1)
  : rawApiBase;
const CSRF_COOKIE_NAME = "csrftoken";
const SAFE_HTTP_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);

let csrfBootstrapPromise = null;

function buildUrl(path) {
  if (/^https?:\/\//i.test(path)) {
    return path;
  }

  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
}

function readCookie(name) {
  const escapedName = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = document.cookie.match(
    new RegExp(`(?:^|;\\s*)${escapedName}=([^;]*)`)
  );
  return match ? decodeURIComponent(match[1]) : "";
}

function readCsrfToken() {
  return readCookie(CSRF_COOKIE_NAME);
}

async function ensureCsrfCookie() {
  const existing = readCsrfToken();
  if (existing) {
    return existing;
  }

  if (!csrfBootstrapPromise) {
    csrfBootstrapPromise = fetch(buildUrl("/auth/csrf"), {
      method: "GET",
      credentials: "include"
    })
      .catch(() => null)
      .finally(() => {
        csrfBootstrapPromise = null;
      });
  }

  await csrfBootstrapPromise;
  return readCsrfToken();
}

export async function apiRequest(path, options = {}) {
  const { body, headers = {}, ...restOptions } = options;
  const method = String(restOptions.method || "GET").toUpperCase();
  const hasBody = body !== undefined;
  const isJsonBody = hasBody && !(body instanceof FormData);
  const requestHeaders = {
    ...(isJsonBody ? { "Content-Type": "application/json" } : {}),
    ...headers
  };

  if (!SAFE_HTTP_METHODS.has(method) && !("X-CSRFToken" in requestHeaders)) {
    const csrfToken = await ensureCsrfCookie();
    if (csrfToken) {
      requestHeaders["X-CSRFToken"] = csrfToken;
    }
  }

  const response = await fetch(buildUrl(path), {
    credentials: "include",
    ...restOptions,
    method,
    headers: requestHeaders,
    body: isJsonBody ? JSON.stringify(body) : body
  });

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const errorMessage =
      typeof payload === "object" &&
      payload &&
      "message" in payload &&
      payload.message
        ? String(payload.message)
        : `Request failed (${response.status})`;

    const error = new Error(errorMessage);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }

  return payload;
}
