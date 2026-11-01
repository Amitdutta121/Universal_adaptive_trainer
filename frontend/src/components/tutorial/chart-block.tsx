"use client";

import { useEffect, useRef } from "react";
import type { ChartPayload } from "./types";

/** A Chart.js block. The payload's chart is data only (type, labels, datasets): no callbacks. */
export function ChartBlock({ chart, caption }: ChartPayload) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!canvas.current) return;
    let destroyed = false;
    let instance: { destroy(): void } | null = null;
    import("chart.js/auto").then(({ default: Chart }) => {
      if (destroyed || !canvas.current) return;
      instance = new Chart(canvas.current, {
        type: chart.type,
        data: chart.data,
        options: { responsive: true, animation: false },
      });
    });
    return () => {
      destroyed = true;
      instance?.destroy();
    };
  }, [chart]);

  return (
    <figure className="space-y-2">
      <canvas ref={canvas} role="img" aria-label={caption || "Chart"} />
      {caption ? (
        <figcaption className="text-muted-foreground text-sm">{caption}</figcaption>
      ) : null}
    </figure>
  );
}
