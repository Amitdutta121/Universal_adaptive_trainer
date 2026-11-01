/**
 * Layout primitives from Launch UI: section, badge, glow, mockup frame, feature item,
 * navbar, footer and the dashed layout lines. Server-safe; no client state.
 */

import { cva, type VariantProps } from "class-variance-authority";
import type * as React from "react";

import { cn } from "@/lib/utils";

export function Section({ className, ...props }: React.ComponentProps<"section">) {
  return (
    <section
      data-slot="section"
      className={cn("line-b px-4 py-12 sm:py-24 md:py-32", className)}
      {...props}
    />
  );
}

export function Badge({ className, ...props }: React.ComponentProps<"span">) {
  return (
    <span
      data-slot="badge"
      className={cn(
        "inline-flex items-center gap-2 rounded-full border border-border/100 px-2.5 py-1 font-semibold text-foreground text-xs dark:border-border/20",
        className,
      )}
      {...props}
    />
  );
}

const glowVariants = cva("pointer-events-none absolute w-full", {
  variants: {
    variant: {
      top: "top-0",
      above: "-top-[128px]",
      bottom: "bottom-0",
      below: "-bottom-[128px]",
      center: "top-[50%]",
    },
  },
  defaultVariants: {
    variant: "top",
  },
});

export function Glow({
  className,
  variant,
  ...props
}: React.ComponentProps<"div"> & VariantProps<typeof glowVariants>) {
  return (
    <div data-slot="glow" className={cn(glowVariants({ variant }), className)} {...props}>
      <div
        className={cn(
          "absolute left-1/2 h-[256px] w-[60%] -translate-x-1/2 scale-[2.5] rounded-[50%] bg-radial from-10% from-brand-foreground/50 to-60% to-brand-foreground/0 opacity-20 sm:h-[512px] dark:opacity-100",
          variant === "center" && "-translate-y-1/2",
        )}
      />
      <div
        className={cn(
          "absolute left-1/2 h-[128px] w-[40%] -translate-x-1/2 scale-200 rounded-[50%] bg-radial from-10% from-brand/30 to-60% to-brand-foreground/0 opacity-20 sm:h-[256px] dark:opacity-100",
          variant === "center" && "-translate-y-1/2",
        )}
      />
    </div>
  );
}

export function MockupFrame({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="mockup-frame"
      className={cn(
        "relative z-10 flex overflow-hidden rounded-2xl bg-border/50 p-2 dark:bg-border/10",
        className,
      )}
      {...props}
    />
  );
}

export function Mockup({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="mockup"
      className={cn(
        "relative z-10 flex overflow-hidden rounded-md border border-border/70 shadow-2xl dark:border-border/5 dark:border-t-border/15",
        className,
      )}
      {...props}
    />
  );
}

export function Item({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="item"
      className={cn("flex flex-col gap-4 p-4 text-foreground", className)}
      {...props}
    />
  );
}

export function ItemTitle({ className, ...props }: React.ComponentProps<"h3">) {
  return (
    <h3
      data-slot="item-title"
      className={cn(
        "flex items-center gap-2 font-semibold text-sm leading-none tracking-tight sm:text-base",
        className,
      )}
      {...props}
    />
  );
}

export function ItemDescription({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="item-description"
      className={cn(
        "flex max-w-[260px] flex-col gap-2 text-balance text-muted-foreground text-sm",
        className,
      )}
      {...props}
    />
  );
}

export function LayoutLines({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      aria-hidden
      className={cn("pointer-events-none fixed inset-0 top-0", className)}
      {...props}
    >
      <div className="line-y line-dashed mx-auto flex h-full max-w-container flex-col" />
    </div>
  );
}

export function Footer({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="footer"
      className={cn("bg-background pt-12 pb-4 text-foreground", className)}
      {...props}
    />
  );
}

export function FooterContent({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="footer-content"
      className={cn("grid grid-cols-2 gap-8 sm:grid-cols-3 md:grid-cols-4", className)}
      {...props}
    />
  );
}

export function FooterColumn({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div data-slot="footer-column" className={cn("flex flex-col gap-4", className)} {...props} />
  );
}

export function FooterBottom({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="footer-bottom"
      className={cn(
        "mt-8 flex flex-col items-center justify-between gap-4 border-border border-t pt-4 text-muted-foreground text-xs sm:flex-row dark:border-border/15",
        className,
      )}
      {...props}
    />
  );
}
