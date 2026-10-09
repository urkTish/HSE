"use client";
import { useEffect, useSyncExternalStore } from "react";
import { api, ApiError, unwrap, type Schemas } from "@/lib/api/client";

/**
 * Phase 6d offline tolerance on the phone (EXE-6, P6d-6, AC59).
 *
 * - The offline pack (planned instances, template and topic libraries, the deployment list of the user's
 *   scope; no ID numbers or card tokens) and the outbox of unsent checklist submissions and toolbox talks are
 *   kept in IndexedDB, encrypted with AES-GCM under a non-extractable key generated on this device.
 * - Everything is deleted at logout, when another user signs in on the device, and after the cache window
 *   (`offline_cache_hours`, 72 h by default): the pack at its `expires_at`, each outbox item 72 h after it
 *   was recorded (the server refuses it after `offline_submit_max_hours` anyway).
 * - Each submission carries its client_uuid, so sending it again never creates anything twice.
 */

type S = Schemas;
const DB = "hse-field";
const STORE = "kv";
const DEFAULT_CACHE_HOURS = 72;

export type OutboxKind = "checklist" | "talk";
export interface OutboxItem {
  id: string; // client_uuid
  kind: OutboxKind;
  project_id: string;
  label: string;
  created_at: string;
  expires_at: string;
  body: S["SubmissionCreate"] | S["TalkCreate"];
  /** Set when the server refused the item (4xx): kept so the user sees why, until discarded. */
  error?: { code: string; message: string; message_ar?: string | null } | null;
  /** Record created on the server (the item is then removed); kept for the caller only. */
  sent_id?: string;
}
export interface CachedPack {
  pack: S["OfflinePack"];
  cached_at: string;
}

/* ───────────── encrypted key-value store ───────────── */

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function tx<T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await openDb();
  try {
    return await new Promise<T>((resolve, reject) => {
      const r = fn(db.transaction(STORE, mode).objectStore(STORE));
      r.onsuccess = () => resolve(r.result);
      r.onerror = () => reject(r.error);
    });
  } finally {
    db.close();
  }
}

let keyPromise: Promise<CryptoKey> | null = null;
function deviceKey(): Promise<CryptoKey> {
  keyPromise ??= (async () => {
    const existing = (await tx<CryptoKey | undefined>("readonly", (s) => s.get("__key"))) ?? null;
    if (existing) return existing;
    const k = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
    await tx("readwrite", (s) => s.put(k, "__key"));
    return k;
  })().catch((e) => {
    keyPromise = null;
    throw e;
  });
  return keyPromise;
}

async function putEnc(name: string, value: unknown): Promise<void> {
  const key = await deviceKey();
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const data = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, new TextEncoder().encode(JSON.stringify(value)));
  await tx("readwrite", (s) => s.put({ iv, data }, name));
}

async function getEnc<T>(name: string): Promise<T | null> {
  const row = await tx<{ iv: Uint8Array; data: ArrayBuffer } | undefined>("readonly", (s) => s.get(name));
  if (!row) return null;
  try {
    const key = await deviceKey();
    const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: row.iv as BufferSource }, key, row.data);
    return JSON.parse(new TextDecoder().decode(plain)) as T;
  } catch {
    return null;
  }
}

async function del(name: string): Promise<void> {
  await tx("readwrite", (s) => s.delete(name));
}

const available = () => typeof window !== "undefined" && typeof indexedDB !== "undefined" && Boolean(globalThis.crypto?.subtle);

/* ───────────── observable snapshot ───────────── */

interface Snapshot {
  outbox: OutboxItem[];
  packs: Record<string, CachedPack>;
  loaded: boolean;
}
let snap: Snapshot = { outbox: [], packs: {}, loaded: false };
const listeners = new Set<() => void>();
function emit(next: Partial<Snapshot>) {
  snap = { ...snap, ...next };
  listeners.forEach((l) => l());
}
function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}
const EMPTY: Snapshot = { outbox: [], packs: {}, loaded: false };

/** Outbox and cached packs of this device (re-renders on change). */
export function useFieldOffline(): Snapshot {
  return useSyncExternalStore(subscribe, () => snap, () => EMPTY);
}

let queue: Promise<unknown> = Promise.resolve();
/** Serialise read-modify-write of the store. */
function serial<T>(fn: () => Promise<T>): Promise<T> {
  const p = queue.then(fn, fn);
  queue = p.catch(() => undefined);
  return p;
}

async function load(): Promise<void> {
  const outbox = (await getEnc<OutboxItem[]>("outbox")) ?? [];
  const index = (await getEnc<string[]>("packs")) ?? [];
  const packs: Record<string, CachedPack> = {};
  for (const pid of index) {
    const p = await getEnc<CachedPack>(`pack:${pid}`);
    if (p) packs[pid] = p;
  }
  emit({ outbox, packs, loaded: true });
}

/* ───────────── lifecycle: owner, purge, logout ───────────── */

/** Delete every 6d offline record on this device (logout, another user, P6d-6). */
export async function clearFieldCache(): Promise<void> {
  keyPromise = null;
  emit({ outbox: [], packs: {}, loaded: true });
  if (!available()) return;
  await new Promise<void>((resolve) => {
    const r = indexedDB.deleteDatabase(DB);
    r.onsuccess = r.onerror = r.onblocked = () => resolve();
  });
}

/** Drop the pack and outbox items past the cache window; returns how many records were deleted. */
export function purgeExpired(now = Date.now()): Promise<number> {
  if (!available()) return Promise.resolve(0);
  return serial(async () => {
    let n = 0;
    const outbox = (await getEnc<OutboxItem[]>("outbox")) ?? [];
    const keep = outbox.filter((i) => Date.parse(i.expires_at) > now);
    if (keep.length !== outbox.length) {
      n += outbox.length - keep.length;
      await putEnc("outbox", keep);
    }
    const index = (await getEnc<string[]>("packs")) ?? [];
    const left: string[] = [];
    for (const pid of index) {
      const p = await getEnc<CachedPack>(`pack:${pid}`);
      if (p && Date.parse(p.pack.expires_at) > now) left.push(pid);
      else {
        n += 1;
        await del(`pack:${pid}`);
      }
    }
    if (left.length !== index.length) await putEnc("packs", left);
    await load();
    return n;
  });
}

/** First call per session: wipe the device cache when it belongs to another user, then purge and load. */
export async function initFieldOffline(userId: string): Promise<number> {
  if (!available()) return 0;
  try {
    const owner = await serial(() => getEnc<string>("owner"));
    if (owner && owner !== userId) await clearFieldCache();
    if (owner !== userId) await serial(() => putEnc("owner", userId));
    return await purgeExpired();
  } catch {
    return 0;
  }
}

/* ───────────── offline pack ───────────── */

export function cacheHoursOf(pack: S["OfflinePack"] | null | undefined): number {
  if (!pack) return DEFAULT_CACHE_HOURS;
  const h = (Date.parse(pack.expires_at) - Date.parse(pack.generated_at)) / 3_600_000;
  return h > 0 ? h : DEFAULT_CACHE_HOURS;
}

export async function downloadPack(projectId: string): Promise<CachedPack> {
  const pack = await unwrap(api.GET("/api/v1/projects/{project_id}/field-offline-pack", { params: { path: { project_id: projectId } } }));
  const cached: CachedPack = { pack, cached_at: new Date().toISOString() };
  await serial(async () => {
    await putEnc(`pack:${projectId}`, cached);
    const index = (await getEnc<string[]>("packs")) ?? [];
    if (!index.includes(projectId)) await putEnc("packs", [...index, projectId]);
    await load();
  });
  return cached;
}

export async function deletePack(projectId: string): Promise<void> {
  await serial(async () => {
    await del(`pack:${projectId}`);
    const index = (await getEnc<string[]>("packs")) ?? [];
    await putEnc(
      "packs",
      index.filter((x) => x !== projectId),
    );
    await load();
  });
}

/* ───────────── outbox ───────────── */

async function saveOutbox(fn: (items: OutboxItem[]) => OutboxItem[]): Promise<void> {
  await serial(async () => {
    const items = (await getEnc<OutboxItem[]>("outbox")) ?? [];
    await putEnc("outbox", fn(items));
    await load();
  });
}

export function discardOutbox(id: string): Promise<void> {
  return saveOutbox((items) => items.filter((i) => i.id !== id));
}

function isTransient(e: unknown): boolean {
  return !(e instanceof ApiError) || e.status === 0 || e.status >= 500 || e.code === "NETWORK_ERROR";
}

async function post(item: OutboxItem): Promise<{ id: string }> {
  const path = { params: { path: { project_id: item.project_id } } };
  if (item.kind === "checklist") {
    return unwrap(api.POST("/api/v1/projects/{project_id}/checklist-submissions", { ...path, body: item.body as S["SubmissionCreate"] }));
  }
  return unwrap(api.POST("/api/v1/projects/{project_id}/toolbox-talks", { ...path, body: item.body as S["TalkCreate"] }));
}

export type SendResult<T> = { status: "sent"; record: T } | { status: "queued" } | { status: "rejected"; error: unknown };

/**
 * Keep the submission on the device first, then send it. Sent → removed from the outbox; no signal or a
 * server error → it waits in the outbox ("waiting to send"); refused (4xx) → removed and the error returned
 * to the form, so the user can correct it.
 */
export async function submitWithOutbox<T extends { id: string }>(kind: OutboxKind, projectId: string, body: OutboxItem["body"], label: string, cacheHours = DEFAULT_CACHE_HOURS): Promise<SendResult<T>> {
  const now = Date.now();
  const item: OutboxItem = {
    id: body.client_uuid,
    kind,
    project_id: projectId,
    label,
    created_at: new Date(now).toISOString(),
    expires_at: new Date(now + cacheHours * 3_600_000).toISOString(),
    body,
  };
  const stored = available();
  if (stored) {
    try {
      await saveOutbox((items) => [...items.filter((i) => i.id !== item.id), item]);
    } catch {
      // storage unavailable: send directly
    }
  }
  if (typeof navigator !== "undefined" && !navigator.onLine && stored) return { status: "queued" };
  try {
    const record = (await post(item)) as T;
    if (stored) await discardOutbox(item.id).catch(() => undefined);
    return { status: "sent", record };
  } catch (e) {
    if (isTransient(e) && stored) return { status: "queued" };
    if (stored) await discardOutbox(item.id).catch(() => undefined);
    return { status: "rejected", error: e };
  }
}

let flushing = false;
/** Send every waiting item (on reconnect, every minute and on "Send now"). Refused items keep their error. */
export async function flushOutbox(): Promise<{ sent: number; failed: number }> {
  if (flushing || !available()) return { sent: 0, failed: 0 };
  flushing = true;
  let sent = 0;
  let failed = 0;
  try {
    const items = (await serial(() => getEnc<OutboxItem[]>("outbox"))) ?? [];
    for (const it of items) {
      if (it.error) continue;
      try {
        await post(it);
        await discardOutbox(it.id);
        sent += 1;
      } catch (e) {
        if (isTransient(e)) break;
        failed += 1;
        const err = e as ApiError;
        await saveOutbox((list) => list.map((x) => (x.id === it.id ? { ...x, error: { code: err.code, message: err.message, message_ar: err.messageAr } } : x)));
      }
    }
  } finally {
    flushing = false;
  }
  return { sent, failed };
}

/** Mounted once in the shell: owner check, purge on load and every minute, send on reconnect. */
export function useFieldOfflineSync(userId: string | null | undefined, onSent?: (n: number) => void) {
  useEffect(() => {
    if (!userId || !available()) return;
    let alive = true;
    const tick = async () => {
      await purgeExpired().catch(() => 0);
      if (navigator.onLine && snap.outbox.some((i) => !i.error)) {
        const r = await flushOutbox();
        if (alive && r.sent) onSent?.(r.sent);
      }
    };
    void initFieldOffline(userId).then(() => tick());
    const timer = window.setInterval(() => void tick(), 60_000);
    const online = () => void tick();
    window.addEventListener("online", online);
    return () => {
      alive = false;
      window.clearInterval(timer);
      window.removeEventListener("online", online);
    };
  }, [userId, onSent]);
}

/* ───────────── photos and signatures ───────────── */

const MAX_EDGE = 1600;
const MAX_BYTES = 5 * 1024 * 1024;

/** On-device compression (EXE-5): longest edge ≤ 1600 px, JPEG; the server strips EXIF on receipt. */
export async function compressPhoto(file: File): Promise<S["PhotoInput"]> {
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const i = new Image();
      i.onload = () => resolve(i);
      i.onerror = () => reject(new Error("image"));
      i.src = url;
    });
    const scale = Math.min(1, MAX_EDGE / Math.max(img.naturalWidth, img.naturalHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(img.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(img.naturalHeight * scale));
    canvas.getContext("2d")?.drawImage(img, 0, 0, canvas.width, canvas.height);
    const data = canvas.toDataURL("image/jpeg", 0.8);
    const b64 = data.slice(data.indexOf(",") + 1);
    if (b64.length * 0.75 > MAX_BYTES) throw new Error("too_large");
    const base = file.name.replace(/\.[^.]+$/, "") || "photo";
    return { file_name: `${base}.jpg`, content_base64: b64 };
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function newUuid(): string {
  return crypto.randomUUID();
}
