"use client";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function chipClass(tone: "ok" | "warn" | "critical" | "accent" | "muted" = "muted") {
  return cn(
    "review-chip",
    tone === "ok" && "review-chip-ok",
    tone === "warn" && "review-chip-warn",
    tone === "critical" && "review-chip-critical",
    tone === "accent" && "review-chip-accent",
    tone === "muted" && "review-chip-muted",
  );
}

export function statusTone(passed: boolean | null | undefined): "ok" | "critical" | "muted" {
  if (passed === true) return "ok";
  if (passed === false) return "critical";
  return "muted";
}

export function ReviewChip({
  children,
  tone = "muted",
  className,
}: {
  children: React.ReactNode;
  tone?: "ok" | "warn" | "critical" | "accent" | "muted";
  className?: string;
}) {
  return (
    <Badge variant="outline" className={cn(chipClass(tone), className)}>
      {children}
    </Badge>
  );
}

export function CodeBlock({ children, className }: { children: string; className?: string }) {
  return (
    <pre
      className={cn(
        "review-code overflow-x-auto rounded-[0.7rem] border px-4 py-3 font-mono text-[12.5px] leading-relaxed",
        className,
      )}
    >
      <code>{children}</code>
    </pre>
  );
}

export function MissingField({ label }: { label: string }) {
  return <p className="text-[13.5px] text-[var(--review-muted)]">{label}</p>;
}
