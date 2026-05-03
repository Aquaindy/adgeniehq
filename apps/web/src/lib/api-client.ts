import { API_BASE_URL } from "@/lib/constants";

export class ApiError extends Error {
  status: number;
  code: string;
  details?: unknown;

  constructor(message: string, opts: { status: number; code?: string; details?: unknown }) {
    super(message);
    this.status = opts.status;
    this.code = opts.code ?? "http_error";
    this.details = opts.details;
  }
}

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  /** Skip auth header + 401 refresh logic (used by /auth/* itself). */
  skipAuth?: boolean;
};

let getAccessToken: () => string | null = () => null;
let onUnauthorized: () => Promise<string | null> = async () => null;

export function configureApiClient(opts: {
  getAccessToken: () => string | null;
  onUnauthorized: () => Promise<string | null>;
}) {
  getAccessToken = opts.getAccessToken;
  onUnauthorized = opts.onUnauthorized;
}

function buildUrl(path: string, query?: RequestOptions["query"]) {
  const url = new URL(path.replace(/^\//, ""), API_BASE_URL.replace(/\/$/, "") + "/");
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null) continue;
      url.searchParams.append(key, String(value));
    }
  }
  return url.toString();
}

async function performRequest(url: string, init: RequestInit, token: string | null): Promise<Response> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(url, { ...init, headers });
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, query, headers, skipAuth, ...rest } = options;

  const url = buildUrl(path, query);
  const baseInit: RequestInit = {
    ...rest,
    headers: {
      Accept: "application/json",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(headers ?? {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: "include",
  };

  const token = skipAuth ? null : getAccessToken();
  let response = await performRequest(url, baseInit, token);

  if (response.status === 401 && !skipAuth) {
    const refreshed = await onUnauthorized();
    if (refreshed) {
      response = await performRequest(url, baseInit, refreshed);
    }
  }

  if (!response.ok) {
    let payload: { error?: { code?: string; message?: string; details?: unknown } } = {};
    try {
      payload = await response.json();
    } catch {
      // ignore parse failure
    }
    throw new ApiError(payload.error?.message ?? response.statusText, {
      status: response.status,
      code: payload.error?.code,
      details: payload.error?.details,
    });
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
