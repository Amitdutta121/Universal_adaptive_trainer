"use client";

import { QuestionFigure as Figure } from "@/components/question-figure";
import type { QuestionFigure as ApiFigure } from "@/lib/api/types";
import type { QuestionFigure as MockFigure } from "./mock-figure-questions";

/** The mock's figure in the API's shape; the mock's own caption doubles as its `alt`. */
function toApiFigure(figure: MockFigure): ApiFigure {
  const caption = figure.caption ?? "";
  const alt = caption || "Figure";
  if (figure.kind === "mermaid") return { kind: "diagram", source: figure.source, alt, caption };
  if (figure.kind === "chart") return { kind: "chart", chart: figure.chart, alt, caption };
  return { kind: "computed", file: figure.src, alt, caption };
}

/** The promoted `QuestionFigure`, fed the experiment's mock figures (static SVGs in `public/`). */
export function QuestionFigure({ figure }: { figure: MockFigure }) {
  return <Figure figure={toApiFigure(figure)} src={figure.kind === "svg" ? figure.src : undefined} />;
}
