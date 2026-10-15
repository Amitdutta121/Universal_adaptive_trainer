/**
 * Payload shapes of the trusted tutorial renderers. Mirrors the contracts in
 * `app/tutorials/renderers.py`; the backend checks every payload against them before saving, and
 * the API types it as an open object, so the registry narrows it here.
 */

import type { Schemas } from "@/lib/api/types";

export type TutorialBlock = Schemas["TutorialBlockOut"];
export type TutorialRenderer = Schemas["TutorialRenderer"];

export interface MarkdownPayload {
  markdown: string;
}

export interface MermaidPayload {
  mermaid: string;
  caption?: string;
}

export interface ChartPayload {
  chart: {
    type: "bar" | "line" | "pie" | "doughnut" | "scatter";
    data: { labels: string[]; datasets: { label: string; data: number[] }[] };
  };
  caption?: string;
}

export interface HtmlPayload {
  html: string;
  title?: string;
}
