"use client";

import { useId, useState } from "react";
import { QuestionFigure } from "@/components/question-figure";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { QuestionFigure as Figure } from "@/lib/api/types";

type ChartFigure = Extract<Figure, { kind: "chart" }>;

/**
 * Edit a question's figure in review (ADR-080): a diagram's Mermaid source, a chart's spec as
 * JSON, and any figure's alt text and caption. A computed figure's picture is its program's, so
 * only its text is editable here. Chart JSON that does not parse is reported through `onError`
 * and the last valid figure is kept; the server checks the rest when the review is submitted.
 */
export function QuestionFigureEditor({
  figure,
  onChange,
  onError,
}: {
  figure: Figure;
  onChange: (figure: Figure) => void;
  onError: (message: string | null) => void;
}) {
  const id = useId();
  const [chartText, setChartText] = useState(() =>
    figure.kind === "chart" ? JSON.stringify(figure.chart, null, 2) : "",
  );
  const [chartError, setChartError] = useState<string | null>(null);

  function editChart(text: string) {
    setChartText(text);
    let message: string | null = null;
    try {
      const chart = JSON.parse(text) as ChartFigure["chart"];
      if (typeof chart !== "object" || chart === null || Array.isArray(chart)) {
        message = "The chart spec must be a JSON object.";
      } else {
        onChange({ ...(figure as ChartFigure), chart });
      }
    } catch (error) {
      message = `The chart spec is not valid JSON: ${error instanceof Error ? error.message : error}`;
    }
    setChartError(message);
    onError(message);
  }

  return (
    <section className="space-y-3 rounded-md border p-3" aria-label="Edit the figure">
      <div className="font-medium text-sm">Figure ({figure.kind})</div>
      {figure.kind === "diagram" ? (
        <div className="space-y-1">
          <Label htmlFor={`${id}-source`}>Mermaid source</Label>
          <Textarea
            id={`${id}-source`}
            rows={8}
            className="font-mono text-xs"
            value={figure.source}
            onChange={(event) => onChange({ ...figure, source: event.target.value })}
          />
        </div>
      ) : figure.kind === "chart" ? (
        <div className="space-y-1">
          <Label htmlFor={`${id}-chart`}>Chart spec (JSON)</Label>
          <Textarea
            id={`${id}-chart`}
            rows={10}
            className="font-mono text-xs"
            value={chartText}
            aria-invalid={chartError ? true : undefined}
            onChange={(event) => editChart(event.target.value)}
          />
          {chartError ? (
            <p role="alert" className="text-destructive text-xs">
              {chartError}
            </p>
          ) : null}
        </div>
      ) : (
        <p className="text-muted-foreground text-xs">
          The picture is drawn by the question's program; regenerate a copy for a new one.
        </p>
      )}
      <div className="space-y-1">
        <Label htmlFor={`${id}-alt`}>Alt text</Label>
        <Input
          id={`${id}-alt`}
          value={figure.alt}
          onChange={(event) => onChange({ ...figure, alt: event.target.value })}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor={`${id}-caption`}>Caption</Label>
        <Input
          id={`${id}-caption`}
          value={figure.caption}
          onChange={(event) => onChange({ ...figure, caption: event.target.value })}
        />
      </div>
      {chartError ? null : <QuestionFigure figure={figure} />}
    </section>
  );
}
