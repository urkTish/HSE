import type { FieldValues, Path, UseFormSetError } from "react-hook-form";
import { ApiError } from "@/lib/api/client";

export function emptyToNull(v: string | null | undefined): string | null {
  const s = (v ?? "").trim();
  return s === "" ? null : s;
}

export function numberOrNull(v: string | null | undefined): number | null {
  const s = (v ?? "").trim();
  return s === "" ? null : Number(s);
}

/** Map 422 field errors (`loc: ["body", "field", ...]`) onto form fields. */
export function applyServerErrors<T extends FieldValues>(
  err: unknown,
  setError: UseFormSetError<T>,
  translate: (type: string, msg: string) => string,
): void {
  if (!(err instanceof ApiError)) return;
  for (const fe of err.fieldErrors) {
    const parts = fe.loc.filter((p) => p !== "body").map(String);
    if (parts.length === 0) continue;
    setError(parts.join(".") as Path<T>, { type: "server", message: translate(fe.type, fe.msg) });
  }
}

export const ARABIC_SCRIPT = /[؀-ۿ]/;
