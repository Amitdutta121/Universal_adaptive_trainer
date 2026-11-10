"use client";

import { useEffect, useRef } from "react";
import type { ChartPayload } from "./types";

/** Axis titles, for the chart types that have axes. */
function axisTitles(chart: ChartPayload["chart"]) {
  if (chart.type === "pie" || chart.type === "doughnut") return undefined;
  const axis = (text: string | null | undefined) =>
    text ? { title: { display: true, text } } : undefined;
  const x = axis(chart.x_title);
  const y = axis(chart.y_title);
  return x || y ? { ...(x ? { x } : {}), ...(y ? { y } : {}) } : undefined;
}

/**
 * A Chart.js block. The chart is data only (type, labels, datasets, axis titles): no callbacks.
 * `alt` is the text a screen reader reads; it defaults to the caption.
 */
export function ChartBlock({ chart, caption, alt }: ChartPayload & { alt?: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!canvas.current) return;
    let destroyed = false;
    let instance: { destroy(): void } | null = null;
    import("chart.js/auto").then(({ default: Chart }) => {
      if (destroyed || !canvas.current) return;
      instance = new Chart(canvas.current, {
        type: chart.type,
        data: { labels: chart.data.labels ?? [], datasets: chart.data.datasets },
        options: { responsive: true, animation: false, scales: axisTitles(chart) },
      });
    });
    return () => {
      destroyed = true;
      instance?.destroy();
    };
  }, [chart]);

  return (
    <figure className="space-y-2">
      <canvas ref={canvas} role="img" aria-label={alt || caption || "Chart"} />
      {caption ? (
        <figcaption className="text-muted-foreground text-sm">{caption}</figcaption>
      ) : null}
    </figure>
  );
}
