import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Data table. On phones (< 768px) rows stack into cards by default (`stack`), each cell showing its
 * column name from the TD `label` prop; pass `stack={false}` for small inline tables that fit.
 * `compact` keeps each phone card short: cells flow without labels (TD `data-keep-label` keeps one,
 * `data-full` puts a cell on its own line); use it for long registers whose values explain themselves.
 */
export function Table({ className, stack = true, compact = false, ...props }: React.TableHTMLAttributes<HTMLTableElement> & { stack?: boolean; compact?: boolean }) {
  return (
    <div className="glass w-full overflow-x-auto rounded-xl border">
      <table className={cn("w-full caption-bottom text-sm", stack && "table-stack", stack && compact && "table-compact", className)} {...props} />
    </div>
  );
}
export function THead({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cn("bg-table-head [&_tr]:border-b [&_tr]:border-border", className)} {...props} />;
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
