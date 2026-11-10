"use client";

import { ChartBlock } from "@/components/tutorial/chart-block";
import { MermaidBlock } from "@/components/tutorial/mermaid-block";
import type { QuestionFigure as Figure } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/** Where a computed figure's SVG is served (`app/web/routes/api/figures.py`). */
export function figureSrc(file: string): string {
  return `/api/figures/${file}`;
}

/**
 * The figure of a question (ADR-080), under its prompt. Diagrams and charts reuse the tutorial
 * blocks; a computed SVG is shown through `<img>`, never inlined, so a script inside it cannot run.
 * `src` overrides where a computed figure is loaded from (the figure experiment's static files).
 */
export function QuestionFigure({
  figure,
  src,
  className,
}: {
  figure: Figure;
  src?: string;
  className?: string;
}) {
  const caption = figure.caption || undefined;
  return (
    <div className={cn("rounded-xl border border-border/60 bg-white p-4", className)}>
      {figure.kind === "diagram" ? (
        <MermaidBlock source={figure.source} caption={caption} alt={figure.alt} />
      ) : figure.kind === "chart" ? (
        <ChartBlock chart={figure.chart} caption={caption} alt={figure.alt} />
      ) : (
        <figure className="space-y-2">
          {/* biome-ignore lint/performance/noImgElement: a generated SVG, not an optimisable photo */}
          <img
            src={src ?? figureSrc(figure.file)}
            alt={figure.alt}
            className="mx-auto block h-auto max-h-[22rem] w-auto max-w-full"
          />
          {caption ? (
            <figcaption className="text-muted-foreground text-sm">{caption}</figcaption>
          ) : null}
        </figure>
      )}
    </div>
  );
}
