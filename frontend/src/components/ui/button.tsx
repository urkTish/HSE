import * as React from "react";
import { Slot } from "radix-ui";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  // Restyle (D-238): crisp emerald primary with a top sheen, platinum outline/secondary, pressed states,
  // one radius (md) and a 2px focus ring offset from the button on every variant.
  "inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium tracking-[0.005em] transition-[background-color,border-color,color,box-shadow,transform] duration-150 ease-(--ease) focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring active:translate-y-px disabled:pointer-events-none disabled:opacity-50 disabled:shadow-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "border border-primary-active/60 bg-primary bg-(image:--primary-sheen) text-primary-foreground shadow-btn hover:bg-primary-hover hover:bg-none active:bg-primary-active active:bg-none active:shadow-btn-pressed",
        destructive:
          "border border-destructive-hover/60 bg-destructive text-destructive-foreground shadow-btn hover:bg-destructive-hover active:shadow-btn-pressed",
        // Hard-to-undo actions that are not the main action (cancel permit, cut lock): visible, never the loudest.
        "destructive-outline": "border-2 border-destructive bg-surface text-destructive shadow-control hover:bg-danger-bg active:shadow-btn-pressed",
        outline:
          "border border-border-strong bg-surface bg-(image:--surface-sheen) text-foreground shadow-control hover:border-input hover:bg-accent hover:bg-none hover:text-accent-foreground active:shadow-btn-pressed",
        secondary:
          "border border-border bg-secondary text-secondary-foreground shadow-control hover:border-border-strong hover:bg-accent active:shadow-btn-pressed",
        ghost: "hover:bg-accent hover:text-accent-foreground active:bg-secondary",
        link: "text-primary underline-offset-4 hover:underline active:translate-y-0",
      },
      size: {
        default: "h-control px-4",
        sm: "h-control-sm px-3",
        lg: "h-12 px-6 text-base",
        icon: "size-control",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export function Button({ className, variant, size, asChild = false, type, ...props }: ButtonProps) {
  const Comp = asChild ? Slot.Root : "button";
  return (
    <Comp
      className={cn(buttonVariants({ variant, size, className }))}
      type={asChild ? undefined : (type ?? "button")}
      {...props}
    />
  );
}

export { buttonVariants };
