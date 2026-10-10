import * as React from "react";
import { cn } from "@/lib/utils";

export function Input({ className, type = "text", ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      type={type}
      className={cn(
        "flex h-control w-full rounded-md border border-input bg-surface px-3 py-2 text-base lg:text-sm placeholder:text-muted-foreground/80 shadow-control transition-[border-color,box-shadow] duration-150 hover:border-foreground/45 focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring disabled:cursor-not-allowed disabled:bg-muted disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-1 aria-invalid:ring-destructive",
        // File inputs: the picker button looks like a secondary button instead of the bare browser default.
        "file:me-3 file:h-full file:cursor-pointer file:rounded-sm file:border-0 file:border-e file:border-border file:bg-secondary file:px-3 file:text-sm file:font-medium file:text-secondary-foreground",
        type === "file" && "cursor-pointer py-1 ps-1",
        className,
      )}
      {...props}
    />
  );
}
