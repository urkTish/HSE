export type AuthEvent = "expired" | "unauthenticated" | "privacy";
type Listener = (e: AuthEvent) => void;

const listeners = new Set<Listener>();

export function onAuthEvent(fn: Listener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export function emitAuthEvent(e: AuthEvent): void {
  listeners.forEach((fn) => fn(e));
}
