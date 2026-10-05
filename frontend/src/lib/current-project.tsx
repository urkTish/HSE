"use client";
import { createContext, useCallback, useContext, useMemo, useSyncExternalStore, type ReactNode } from "react";
import { useProjects } from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/client";

const STORAGE_KEY = "hse.currentProjectId";
const listeners = new Set<() => void>();

function readStored(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStored(id: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, id);
  } catch {
    // storage unavailable (private mode): selection simply is not remembered
  }
  memory = id;
  listeners.forEach((l) => l());
}

let memory: string | null = null;

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

interface CurrentProjectValue {
  projectId: string | null;
  project: Schemas["ProjectRead"] | null;
  projects: Schemas["ProjectRead"][];
  setProjectId: (id: string) => void;
  isLoading: boolean;
}

const Ctx = createContext<CurrentProjectValue | null>(null);

export function CurrentProjectProvider({ children }: { children: ReactNode }) {
  const query = useProjects({ page_size: 100, sort: "code" });
  const stored = useSyncExternalStore(
    subscribe,
    () => memory ?? readStored(),
    () => null,
  );
  const projects = useMemo(() => query.data?.items ?? [], [query.data]);
  const project = projects.find((p) => p.id === stored) ?? projects[0] ?? null;
  const setProjectId = useCallback((id: string) => writeStored(id), []);
  const value = useMemo<CurrentProjectValue>(
    () => ({ projectId: project?.id ?? null, project, projects, setProjectId, isLoading: query.isLoading }),
    [project, projects, setProjectId, query.isLoading],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useCurrentProject(): CurrentProjectValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useCurrentProject must be used inside CurrentProjectProvider");
  return v;
}
