import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// Teach tailwind-merge the design-token spacing names (h-control, size-touch, …) so overrides resolve.
const twMerge = extendTailwindMerge({
  extend: { theme: { spacing: ["touch", "control", "control-sm"] } },
});

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
