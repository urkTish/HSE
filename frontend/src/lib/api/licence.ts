"use client";
import { useQuery } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "./client";

export type Licence = Schemas["LicenceRead"];
export const licenceKey = ["licence"] as const;

/** Licence state for the banner and the licence page (D-289). No key installed = state "none". */
export function useLicence() {
  return useQuery({
    queryKey: licenceKey,
    queryFn: () => unwrap(api.GET("/api/v1/licence")),
    staleTime: 5 * 60_000,
    retry: false,
  });
}

/** Bytes → GB with one decimal (storage meter). */
export function gb(bytes: number): string {
  return (bytes / 1024 ** 3).toFixed(1);
}
