import createClient from "openapi-fetch";
import type { components, paths } from "./schema";
import { emitAuthEvent } from "./auth-events";

export type Schemas = components["schemas"];
export type ErrorCode = Schemas["ErrorCode"];
export type FieldError = Schemas["FieldError"];

/** Same-origin client: Next rewrites /api/v1/* to the backend, so the httpOnly cookie is sent automatically. */
export const api = createClient<paths>({ baseUrl: "", credentials: "same-origin" });

export class ApiError extends Error {
  readonly status: number;
  readonly code: ErrorCode | "NETWORK_ERROR" | "UNKNOWN";
  readonly messageAr: string | null;
  readonly fieldErrors: FieldError[];

  constructor(
    status: number,
    detail: Partial<Schemas["ErrorDetail"]> | null,
    fallbackCode: "NETWORK_ERROR" | "UNKNOWN" = "UNKNOWN",
  ) {
    super(detail?.message ?? `HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = detail?.code ?? fallbackCode;
    this.messageAr = detail?.message_ar ?? null;
    this.fieldErrors = detail?.errors ?? [];
  }
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

export function toApiError(status: number, body: unknown): ApiError {
  if (isRecord(body) && isRecord(body.detail)) {
    return new ApiError(status, body.detail as Partial<Schemas["ErrorDetail"]>);
  }
  return new ApiError(status, null);
}

/** Codes that mean the browser session is gone or blocked and the shell must react. */
const SESSION_CODES = new Set<string>(["SESSION_EXPIRED", "UNAUTHENTICATED"]);

export function notifyAuthError(err: ApiError): void {
  if (err.status === 401 && SESSION_CODES.has(err.code)) {
    emitAuthEvent(err.code === "SESSION_EXPIRED" ? "expired" : "unauthenticated");
  } else if (err.status === 403 && err.code === "PRIVACY_ACK_REQUIRED") {
    emitAuthEvent("privacy");
  }
}

type FetchResult<T> = { data?: T; error?: unknown; response: Response };

/** Resolve an openapi-fetch call to its data or throw a typed ApiError. */
export async function unwrap<T>(promise: Promise<FetchResult<T>>): Promise<T> {
  let result: FetchResult<T>;
  try {
    result = await promise;
  } catch {
    throw new ApiError(0, null, "NETWORK_ERROR");
  }
  if (!result.response.ok) {
    const err = toApiError(result.response.status, result.error);
    notifyAuthError(err);
    throw err;
  }
  return result.data as T;
}

/** Download a file endpoint (exports) through fetch so errors are shown instead of navigating away. */
export async function downloadFile(url: string, fallbackName: string): Promise<void> {
  const res = await fetch(url, { credentials: "same-origin" });
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      body = null;
    }
    const err = toApiError(res.status, body);
    notifyAuthError(err);
    throw err;
  }
  const disposition = res.headers.get("content-disposition") ?? "";
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
  const name = match?.[1] ? decodeURIComponent(match[1]) : fallbackName;
  const blob = await res.blob();
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(href);
}

/** POST a multipart form (file uploads, workforce import) and return the typed JSON body. */
export async function postForm<T>(url: string, form: FormData): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, { method: "POST", body: form, credentials: "same-origin" });
  } catch {
    throw new ApiError(0, null, "NETWORK_ERROR");
  }
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  if (!res.ok) {
    const err = toApiError(res.status, body);
    notifyAuthError(err);
    throw err;
  }
  return body as T;
}
