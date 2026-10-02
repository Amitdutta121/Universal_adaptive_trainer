"use client";

/** Inline text for a card: `code` spans only. */

import { Fragment } from "react";

export function CardText({ text }: { text: string }) {
  const parts = text.split(/(`[^`]+`)/g).filter(Boolean);
  return (
    <>
      {parts.map((part, index) => {
        const key = `${index}:${part}`;
        return part.startsWith("`") ? (
          <code key={key} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.86em] text-foreground">
            {part.slice(1, -1)}
          </code>
        ) : (
          <Fragment key={key}>{part}</Fragment>
        );
      })}
    </>
  );
}
