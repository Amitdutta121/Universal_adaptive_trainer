/** Tutorial style fields in a professor's words, shared by the Tutorials page and the editor. */

import type { Schemas } from "@/lib/api/types";

export const FORMAT_LABELS: Record<Schemas["TutorialRenderer"], string> = {
  markdown: "Text",
  mermaid: "Diagram",
  chartjs: "Chart",
  html: "Interactive",
  video_clip: "Video clip",
};

export const LEVEL_LABELS: Record<Schemas["GuidanceLevel"], string> = {
  worked: "Worked example",
  faded: "Faded",
  cue: "Cue",
};

/** `code_behavior` -> "Code behavior". */
export function humanize(value: string) {
  const text = value.replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
