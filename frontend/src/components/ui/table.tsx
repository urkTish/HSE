import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Data table. On phones (< 768px) rows stack into cards by default (`stack`), each cell showing its
 * column name from the TD `label` prop; pass `stack={false}` for small inline tables that fit.
 */
export function Table({ className, stack = true, ...props }: React.TableHTMLAttributes<HTMLTableElement> & { stack?: boolean }) {
  return (
    <div className="w-full overflow-x-auto rounded-xl border border-border bg-surface shadow-sm">
      <table className={cn("w-full caption-bottom text-sm", stack && "table-stack", className)} {...props} />
    </div>
  );
}
export function THead({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cn("bg-muted/80 [&_tr]:border-b [&_tr]:border-border", className)} {...props} />;
}
export function TBody({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("[&_tr:last-child]:border-0", className)} {...props} />;
}
export function TR({ className, ...props }: React.HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("border-b border-border transition-colors hover:bg-accent/70", className)} {...props} />;
}
export function TH({ className, ...props }: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      scope="col"
      className={cn("h-11 px-3 text-start align-middle text-xs font-semibold tracking-[0.02em] whitespace-nowrap text-muted-foreground", className)}
      {...props}
    />
  );
}
export function TD({ className, label, ...props }: React.TdHTMLAttributes<HTMLTableCellElement> & { label?: string }) {
  return <td data-label={label} className={cn("px-3 py-3 align-middle", className)} {...props} />;
}
