/**
 * `/experiments/prompt-text` — design prototype of `PromptText`, the shared renderer for question
 * prompts (Markdown, code, lists, tables, math). Mock prompts across several subjects and question
 * types, with a toggle against today's plain-text rendering. No API, no LLM.
 */

import type { Metadata } from "next";
import { PromptTextExperience } from "./prompt-text-experience";

export const metadata: Metadata = {
  title: "PromptText — design prototype",
  description: "Question prompts rendered as Markdown across subjects and question types.",
};

export default function PromptTextExperimentPage() {
  return <PromptTextExperience />;
}
