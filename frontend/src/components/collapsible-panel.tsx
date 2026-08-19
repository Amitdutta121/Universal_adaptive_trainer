"use client";

/**
 * A titled block that stays shut until it is asked for.
 *
 * The reference material behind an upload — a long prompt, a whole example
 * document, the limits a validator enforces — is needed once, while a professor is
 * producing a document, and never again. Open by default it buries the two things
 * they came for: the upload, and the rows they already have.
 */

import { ChevronDown } from "lucide-react";
import { useId, useState } from "react";
import { Button } from "@/components/ui/button";

export function CollapsiblePanel({
  title,
  summary,
  openLabel,
  closeLabel = "Hide",
  defaultOpen = false,
  actions,
  children,
}: {
  title: string;
  summary?: string;
  openLabel: string;
  closeLabel?: string;
  /** Starts expanded instead of shut, for content worth showing up front. */
  defaultOpen?: boolean;
  /** Shown beside the toggle only while open — a copy button, typically. */
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const contentId = useId();

  return (
    <div className="rounded-lg border">
      <div className="flex flex-wrap items-center gap-2 px-3 py-2">
        <div className="min-w-0">
          <p className="font-medium text-sm">{title}</p>
          {summary ? <p className="text-muted-foreground text-xs">{summary}</p> : null}
        </div>
        <div className="ml-auto flex items-center gap-2">
          {open ? actions : null}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-expanded={open}
            aria-controls={contentId}
            onClick={() => setOpen(!open)}
          >
            <ChevronDown
              className={open ? "rotate-180 transition-transform" : "transition-transform"}
            />
            {open ? closeLabel : openLabel}
          </Button>
        </div>
      </div>
      {open ? (
        <div id={contentId} className="border-t p-3">
          {children}
        </div>
      ) : null}
    </div>
  );
}
