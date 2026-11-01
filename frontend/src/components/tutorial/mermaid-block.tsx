"use client";

import { useEffect, useId, useState } from "react";

/**
 * A Mermaid diagram block. Mermaid is loaded on first use (it is large) and runs with
 * `securityLevel: "strict"`: no click handlers, html labels sanitised. A diagram that does not
 * parse shows its source instead.
 */
export function MermaidBlock({ source, caption }: { source: string; caption?: string }) {
  const id = `mermaid-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setSvg(null);
    setFailed(false);
    import("mermaid")
      .then(async ({ default: mermaid }) => {
        mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "neutral" });
        const result = await mermaid.render(id, source);
        if (!cancelled) setSvg(result.svg);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [id, source]);

  return (
    <figure className="space-y-2">
      {failed ? (
        <div className="space-y-1">
          <p className="text-destructive text-sm">This diagram could not be drawn.</p>
          <pre className="overflow-x-auto rounded-md border bg-muted/40 p-3 font-mono text-xs">
            {source}
          </pre>
        </div>
      ) : svg ? (
        <div
          className="overflow-x-auto [&_svg]:mx-auto"
          // biome-ignore lint/security/noDangerouslySetInnerHtml: mermaid's own svg, sanitised by it under securityLevel "strict"
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      ) : (
        <p className="text-muted-foreground text-sm">Drawing the diagram…</p>
      )}
      {caption ? (
        <figcaption className="text-muted-foreground text-sm">{caption}</figcaption>
      ) : null}
    </figure>
  );
}
