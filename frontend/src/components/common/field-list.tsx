import { Check, X } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function FieldList({ children, className }: { children: ReactNode; className?: string }) {
  return <dl className={cn("grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-3", className)}>{children}</dl>;
}

export function FieldItem({ label, children, ltr, wide }: { label: string; children: ReactNode; ltr?: boolean; wide?: boolean }) {
  return (
    <div className={cn("min-w-0", wide && "sm:col-span-2 lg:col-span-3")}>
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className={cn("mt-1 text-sm [overflow-wrap:anywhere]", ltr && "ltr")}>{children ?? "—"}</dd>
    </div>
  );
}

/** Yes/No with an icon-like glyph so meaning is not conveyed by colour alone. */
export function YesNo({ value, yes, no }: { value: boolean | null | undefined; yes: string; no: string }) {
  if (value === null || value === undefined) return <>—</>;
  return (
    <span className={cn("inline-flex items-center gap-1", value ? "font-medium text-success" : "text-muted-foreground")}>
      {value ? <Check aria-hidden className="size-4" /> : <X aria-hidden className="size-4" />}
      {value ? yes : no}
    </span>
  );
}
