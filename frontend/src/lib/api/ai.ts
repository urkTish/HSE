"use client";
import { useQuery } from "@tanstack/react-query";
import { api, notifyAuthError, toApiError, unwrap, type Schemas } from "./client";

export const aiKeys = {
  status: (pid: string) => ["ai-status", pid] as const,
  reports: (pid: string, page: number) => ["monthly-reports", pid, page] as const,
  report: (id: string) => ["monthly-report", id] as const,
};

export function useAiStatus(projectId: string | null, enabled = true) {
  return useQuery({
    queryKey: aiKeys.status(projectId ?? ""),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/ai/status", {
          params: { query: { project_id: projectId ?? "" } },
        }),
      ),
    enabled: Boolean(projectId) && enabled,
    staleTime: 60_000,
    retry: false,
  });
}

export type AiStreamEvent =
  | { event: "meta"; data: Schemas["AiStreamMeta"] }
  | { event: "status"; data: Schemas["AiStreamStatus"] }
  | { event: "delta"; data: Schemas["AiStreamDelta"] }
  | { event: "citations"; data: Schemas["AiCitation"][] }
  | { event: "chart"; data: Schemas["ChartSpec"] }
  | { event: "recommendations"; data: Schemas["AiRecommendation"][] }
  | { event: "done"; data: Schemas["AiAnswer"] }
  | { event: "error"; data: Schemas["AiStreamError"] };

/** Parse one SSE frame ("event:" + "data:" lines). Comment lines (": keep-alive") are ignored. */
export function parseSseFrame(frame: string): AiStreamEvent | null {
  let event = "message";
  const data: string[] = [];
  for (const raw of frame.split("\n")) {
    const line = raw.replace(/\r$/, "");
    if (!line || line.startsWith(":")) continue;
    const idx = line.indexOf(":");
    const field = idx === -1 ? line : line.slice(0, idx);
    const value = idx === -1 ? "" : line.slice(idx + 1).replace(/^ /, "");
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }
  if (data.length === 0) return null;
  try {
    return { event, data: JSON.parse(data.join("\n")) } as AiStreamEvent;
  } catch {
    return null;
  }
}

/**
 * POST /ai/ask as Server-Sent Events. Errors before the stream (403 AI_DISABLED, 429
 * AI_RATE_LIMITED, 503 AI_UNAVAILABLE, 404) are thrown as ApiError; errors during the stream
 * arrive as an `error` event.
 */
export async function askAi(body: Schemas["AiAskRequest"], onEvent: (e: AiStreamEvent) => void, signal?: AbortSignal): Promise<void> {
  const res = await fetch("/api/v1/ai/ask", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    let payload: unknown = null;
    try {
      payload = await res.json();
    } catch {
      payload = null;
    }
    const err = toApiError(res.status, payload);
    notifyAuthError(err);
    throw err;
  }
  const type = res.headers.get("content-type") ?? "";
  if (type.includes("application/json")) {
    onEvent({ event: "done", data: (await res.json()) as Schemas["AiAnswer"] });
    return;
  }
  if (!res.body) return;
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let i: number;
    while ((i = buf.indexOf("\n\n")) !== -1) {
      const frame = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const ev = parseSseFrame(frame);
      if (ev) onEvent(ev);
    }
  }
  const tail = parseSseFrame(buf);
  if (tail) onEvent(tail);
}
