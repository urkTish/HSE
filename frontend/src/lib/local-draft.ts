"use client";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { FieldValues, UseFormReturn } from "react-hook-form";

/**
 * Offline-tolerant draft for field forms (incidents, observations): form values are kept in
 * this device's localStorage while typing and restored after a reload or lost signal.
 * Only used for new records; cleared after a successful save.
 */
export function useLocalDraft<T extends FieldValues>(key: string, form: UseFormReturn<T>, enabled: boolean) {
  const [restored, setRestored] = useState(false);
  const loaded = useRef(false);
  const storageKey = `hse.draft.${key}`;

  useEffect(() => {
    if (!enabled || loaded.current) return;
    loaded.current = true;
    try {
      const raw = window.localStorage.getItem(storageKey);
      if (raw) {
        const parsed = JSON.parse(raw) as { values: T };
        form.reset({ ...form.getValues(), ...parsed.values });
        queueMicrotask(() => setRestored(true));
      }
    } catch {
      // storage unavailable or corrupt: start empty
    }
  }, [enabled, form, storageKey]);

  useEffect(() => {
    if (!enabled) return;
    const sub = form.watch((values) => {
      try {
        window.localStorage.setItem(storageKey, JSON.stringify({ values, saved_at: new Date().toISOString() }));
      } catch {
        // quota or private mode: the draft is simply not kept
      }
    });
    return () => sub.unsubscribe();
  }, [enabled, form, storageKey]);

  function clear() {
    try {
      window.localStorage.removeItem(storageKey);
    } catch {
      // ignore
    }
    setRestored(false);
  }

  return { restored, clear };
}

function subscribeOnline(cb: () => void): () => void {
  window.addEventListener("online", cb);
  window.addEventListener("offline", cb);
  return () => {
    window.removeEventListener("online", cb);
    window.removeEventListener("offline", cb);
  };
}

/** True while the browser reports a network connection. */
export function useOnline(): boolean {
  return useSyncExternalStore(
    subscribeOnline,
    () => navigator.onLine,
    () => true,
  );
}
