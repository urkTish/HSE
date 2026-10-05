"use client";
import { createContext, useContext } from "react";
import type { Me } from "@/lib/permissions";

export const MeContext = createContext<Me | null>(null);

/** The signed-in user; only available inside the authenticated app shell. */
export function useMeData(): Me {
  const me = useContext(MeContext);
  if (!me) throw new Error("useMeData must be used inside the app shell");
  return me;
}
