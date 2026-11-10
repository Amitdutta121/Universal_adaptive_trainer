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
    data: {
      /** Empty or absent for a scatter chart, whose points carry their own x. */
      labels?: string[];
      datasets: { label: string; data: number[] | { x: number; y: number }[] }[];
    };
    x_title?: string | null;
    y_title?: string | null;
  };
  caption?: string;
}

export interface HtmlPayload {
  html: string;
  title?: string;
}

export interface VideoClipPayload {
  provider: "youtube";
  video_id: string;
  /** Seconds. */
  start: number;
  end: number;
  title?: string;
  /** What is said in the range. */
  transcript?: string;
}
