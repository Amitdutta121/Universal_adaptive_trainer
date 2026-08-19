"use client";

/**
 * Copy a block of text to the clipboard.
 *
 * The clipboard API is unavailable outside a secure context, so a failure is
 * reported rather than swallowed: the professor needs to know to select the text
 * by hand instead of pasting nothing into an assistant.
 */

import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";

export function CopyButton({
  text,
  label = "Copy",
  copiedLabel = "Copied",
  variant = "outline",
  size = "sm",
  className,
}: {
  text: string;
  label?: string;
  copiedLabel?: string;
  variant?: React.ComponentProps<typeof Button>["variant"];
  size?: React.ComponentProps<typeof Button>["size"];
  className?: string;
}) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Without this, a copy on an unmounting dialog would set state on a dead component.
  useEffect(() => () => void (timer.current && clearTimeout(timer.current)), []);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), 2_000);
    } catch {
      toast.error("Could not reach the clipboard", {
        description: "Select the text and copy it manually.",
      });
    }
  }

  return (
    <Button type="button" variant={variant} size={size} className={className} onClick={copy}>
      {copied ? <Check className="text-emerald-600" /> : <Copy />}
      {copied ? copiedLabel : label}
    </Button>
  );
}
