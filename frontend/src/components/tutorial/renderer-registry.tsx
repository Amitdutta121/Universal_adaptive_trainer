"use client";

import type { ReactNode } from "react";
import { ChartBlock } from "./chart-block";
import { HtmlFrame } from "./html-frame";
import { MarkdownBlock } from "./markdown-block";
import { MermaidBlock } from "./mermaid-block";
import type {
  ChartPayload,
  HtmlPayload,
  MarkdownPayload,
  MermaidPayload,
  VideoClipPayload,
} from "./types";
import { VideoClipBlock } from "./video-clip-block";

type Payload = Record<string, unknown>;

/**
 * Renderer name -> component. The only way a tutorial block reaches the screen: a renderer that is
 * not listed here, or a payload missing its fields, gets the safe fallback, never raw output.
 */
const RENDERERS: Record<string, (payload: Payload) => ReactNode | null> = {
  markdown: (payload) =>
    typeof payload.markdown === "string" ? (
      <MarkdownBlock markdown={(payload as unknown as MarkdownPayload).markdown} />
    ) : null,
  mermaid: (payload) => {
    if (typeof payload.mermaid !== "string") return null;
    const { mermaid, caption } = payload as unknown as MermaidPayload;
    return <MermaidBlock source={mermaid} caption={caption} />;
  },
  chartjs: (payload) => {
    const chart = payload.chart as ChartPayload["chart"] | undefined;
    if (!chart || typeof chart !== "object" || !chart.data) return null;
    return <ChartBlock chart={chart} caption={payload.caption as string | undefined} />;
  },
  html: (payload) => {
    if (typeof payload.html !== "string") return null;
    const { html, title } = payload as unknown as HtmlPayload;
    return <HtmlFrame html={html} title={title ?? ""} />;
  },
  video_clip: (payload) => {
    const clip = payload as unknown as VideoClipPayload;
    const valid =
      clip.provider === "youtube" &&
      typeof clip.video_id === "string" &&
      /^[A-Za-z0-9_-]{11}$/.test(clip.video_id) &&
      typeof clip.start === "number" &&
      typeof clip.end === "number" &&
      clip.end > clip.start;
    return valid ? <VideoClipBlock clip={clip} /> : null;
  },
};

export function TutorialBlockView({ renderer, payload }: { renderer: string; payload: Payload }) {
  const render = Object.hasOwn(RENDERERS, renderer) ? RENDERERS[renderer] : undefined;
  const content = render ? render(payload) : null;
  if (content) return <>{content}</>;
  return (
    <p className="rounded-md border border-dashed p-3 text-muted-foreground text-sm">
      This block cannot be shown here (
      {render ? "its content is incomplete" : `unknown format "${renderer}"`}).
    </p>
  );
}
