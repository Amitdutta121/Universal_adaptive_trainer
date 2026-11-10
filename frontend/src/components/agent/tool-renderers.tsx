"use client";

/**
 * How the agent's tool calls show in the chat (Task 35).
 *
 * `preview_styles` renders the compared styles side by side with their worked examples,
 * `draft_style` renders the drafted style as a card with both examples and their answers,
 * `show_design` renders the course design as three cards the professor revises in place
 * (an earlier version of the same design collapses to one line),
 * and every other tool shows one status line, with the app's refusal when it refused. No tool
 * moves the professor to another page: everything happens in the chat.
 */

import { useAgent, useRenderTool } from "@copilotkit/react-core/v2";
import { useQueryClient } from "@tanstack/react-query";
import { Check, CircleAlert, Loader2 } from "lucide-react";
import { useEffect } from "react";
import { z } from "zod";
import type { QuestionFigure } from "@/lib/api/types";
import { QuestionBody } from "@/components/question-body";
import { useChatAsk } from "./chat-ask";
import { type CourseDesign, DesignCard } from "./design-card";

export type StyleSample = {
  prompt: string;
  figure?: QuestionFigure | null;
  code?: string | null;
};

export type ComparedStyle = {
  id: string;
  name: string;
  summary: string;
  checked_by?: string;
  examples?: StyleSample[];
};

function parse<T>(result: string | undefined): T | null {
  if (!result) return null;
  try {
    return JSON.parse(result) as T;
  } catch {
    return null;
  }
}

/** A refusal the app sent back for the model to explain (`ToolRefusal`). */
function refusalOf(result: string | undefined): string | null {
  const parsed = parse<{ error?: unknown }>(result);
  return parsed && typeof parsed.error === "string" ? parsed.error : null;
}

const LABELS: Record<string, string> = {
  import_material: "Import material",
  propose_curriculum: "Draft a curriculum",
  design_curriculum: "Plan the curriculum",
  suggest_styles: "Suggest question styles",
  suggest_recipes: "Suggest tutorial recipes",
  show_design: "Show the course design",
  approve_course_design: "Save the course design",
  edit_curriculum: "Edit the curriculum",
  coverage_report: "Check coverage",
  approve_curriculum: "Save the curriculum",
  save_style: "Add a style",
  publish_set: "Publish to students",
  plan_generation: "Price a generation run",
  run_generation: "Start generation",
  course_overview: "Read the course",
  preview_styles: "Compare styles",
  suggest_setup: "Suggest a setup",
  review_summary: "Check the review queue",
  student_report: "Read student progress",
  list_recipes: "Read the tutorial recipes",
  draft_recipe: "Draft a recipe",
  try_recipe: "Try a recipe",
  save_recipe: "Save a recipe",
  decide_recipe: "Approve or stop a recipe",
  subject_options: "Read the subjects",
  set_course_subject: "Set the subject",
  draft_style: "Draft a question style",
};

/** Tools that change the course; the Studio's cached reads are refetched when one completes. */
const WRITES = new Set([
  "import_material",
  "approve_curriculum",
  "approve_course_design",
  "edit_curriculum",
  "save_style",
  "set_course_subject",
  "publish_set",
  "run_generation",
  "save_recipe",
  "decide_recipe",
]);

/** Write calls already refetched for, by tool call id, so a re-render never refetches twice. */
const refreshed = new Set<string>();

function RefreshAfterWrite({ toolCallId }: { toolCallId: string }) {
  const client = useQueryClient();
  useEffect(() => {
    if (refreshed.has(toolCallId)) return;
    refreshed.add(toolCallId);
    void client.invalidateQueries();
  }, [toolCallId, client]);
  return null;
}

export function ToolStatusLine({
  name,
  status,
  result,
}: {
  name: string;
  status: string;
  result?: string;
}) {
  const refusal = status === "complete" ? refusalOf(result) : null;
  const icon =
    status !== "complete" ? (
      <Loader2 className="size-3.5 animate-spin" />
    ) : refusal ? (
      <CircleAlert className="size-3.5 text-destructive" />
    ) : (
      <Check className="size-3.5 text-primary" />
    );
  return (
    <div className="my-1 flex items-start gap-1.5 text-muted-foreground text-xs">
      <span className="mt-px">{icon}</span>
      <span>
        {LABELS[name] ?? name}
        {refusal ? ` — ${refusal}` : null}
      </span>
    </div>
  );
}

export function StyleComparison({ styles }: { styles: ComparedStyle[] }) {
  return (
    <div
      className="my-2 grid gap-2"
      style={{ gridTemplateColumns: `repeat(${styles.length}, minmax(0, 1fr))` }}
    >
      {styles.map((style) => (
        <section key={style.id} className="min-w-0 rounded-lg border bg-card p-2 text-xs">
          <h4 className="font-medium text-card-foreground text-sm">{style.name}</h4>
          <p className="mt-0.5 text-muted-foreground">{style.summary}</p>
          {style.checked_by ? (
            <p className="mt-1 text-muted-foreground">Checked by: {style.checked_by}</p>
          ) : null}
          {style.examples?.slice(0, 1).map((example) => (
            <div key={example.prompt} className="mt-2 rounded-md bg-muted p-1.5">
              <QuestionBody
                prompt={example.prompt}
                figure={example.figure}
                className="space-y-2"
                promptClassName="space-y-1 leading-normal"
              />
              {example.code ? (
                <pre className="mt-1 overflow-x-auto font-mono text-[11px]">{example.code}</pre>
              ) : null}
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}

type DraftedExample = StyleSample & {
  options?: { text: string; correct?: boolean }[];
  lines?: string[];
  answer?: string | null;
};

export type DraftedStyle = {
  id: string;
  name: string;
  summary: string;
  question_type: string;
  difficulty_range: string[];
  checked_by: string;
  examples: DraftedExample[];
};

/** A style `draft_style` wrote, with both examples and answer keys, as the professor approves it. */
export function DraftedStyleCard({ style, problems }: { style: DraftedStyle; problems: string[] }) {
  return (
    <section className="my-2 rounded-lg border bg-card p-3 text-xs">
      <div className="flex items-baseline justify-between gap-2">
        <h4 className="font-medium text-card-foreground text-sm">{style.name}</h4>
        <span className="shrink-0 text-muted-foreground">
          {style.question_type.replaceAll("_", " ")} · {style.difficulty_range.join(", ")}
        </span>
      </div>
      <p className="mt-0.5 text-muted-foreground">{style.summary}</p>
      <p className="mt-1 text-muted-foreground">Checked by: {style.checked_by}</p>
      {style.examples.map((example) => (
        <div key={example.prompt} className="mt-2 rounded-md bg-muted p-2">
          <QuestionBody
                prompt={example.prompt}
                figure={example.figure}
                className="space-y-2"
                promptClassName="space-y-1 leading-normal"
              />
          {example.code ? (
            <pre className="mt-1 overflow-x-auto font-mono text-[11px]">{example.code}</pre>
          ) : null}
          {example.lines?.length ? (
            <pre className="mt-1 overflow-x-auto font-mono text-[11px]">
              {example.lines.join("\n")}
            </pre>
          ) : null}
          {example.options?.length ? (
            <ul className="mt-1 space-y-0.5">
              {example.options.map((option) => (
                <li key={option.text} className="flex items-start gap-1">
                  {option.correct ? (
                    <Check className="mt-px size-3.5 shrink-0 text-primary" aria-label="Correct" />
                  ) : (
                    <span className="size-3.5 shrink-0" />
                  )}
                  <span className={option.correct ? "font-medium" : undefined}>{option.text}</span>
                </li>
              ))}
            </ul>
          ) : null}
          {example.answer && !example.options?.length ? (
            <p className="mt-1">
              <span className="text-muted-foreground">Answer:</span> {example.answer}
            </p>
          ) : null}
        </div>
      ))}
      {problems.length ? (
        <ul className="mt-2 list-disc space-y-0.5 pl-4 text-destructive">
          {problems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

/** The design card, with follow-ups sent through the course chat when there is one. */
type ChatMessage = {
  role?: string;
  content?: unknown;
  toolCallId?: string;
  toolCalls?: { id: string; function: { name: string } }[];
};

/** Whether a later `show_design` result in the chat shows the same design again. */
export function isSuperseded(messages: ChatMessage[], toolCallId: string, designId: string) {
  const showCalls = new Set(
    messages.flatMap((m) =>
      (m.toolCalls ?? []).filter((c) => c.function.name === "show_design").map((c) => c.id),
    ),
  );
  const own = messages.findIndex((m) => m.role === "tool" && m.toolCallId === toolCallId);
  if (own < 0) return false;
  return messages
    .slice(own + 1)
    .some(
      (m) =>
        m.role === "tool" &&
        showCalls.has(m.toolCallId ?? "") &&
        typeof m.content === "string" &&
        parse<{ design_id?: string }>(m.content)?.design_id === designId,
    );
}

function ProposedDesign({ design, toolCallId }: { design: CourseDesign; toolCallId: string }) {
  const { agent } = useAgent();
  const superseded = isSuperseded(agent.messages as ChatMessage[], toolCallId, design.design_id);
  return <DesignCard design={design} ask={useChatAsk()} superseded={superseded} />;
}

export function useAgentToolRenderers() {
  useRenderTool(
    {
      name: "show_design",
      parameters: z.object({}).passthrough(),
      render: ({ status, result, toolCallId }) => {
        const design = status === "complete" ? parse<CourseDesign>(result) : null;
        if (design?.design_id && Array.isArray(design.styles))
          return <ProposedDesign design={design} toolCallId={toolCallId} />;
        return <ToolStatusLine name="show_design" status={status} result={result} />;
      },
    },
    [],
  );
  useRenderTool(
    {
      name: "preview_styles",
      parameters: z.object({ style_ids: z.array(z.string()).nullish() }),
      render: ({ status, result }) => {
        const styles =
          status === "complete" ? parse<{ styles?: ComparedStyle[] }>(result)?.styles : null;
        if (styles?.some((style) => style.examples?.length))
          return <StyleComparison styles={styles} />;
        return <ToolStatusLine name="preview_styles" status={status} result={result} />;
      },
    },
    [],
  );
  useRenderTool(
    {
      name: "draft_style",
      parameters: z.object({ description: z.string(), current_yaml: z.string().nullish() }),
      render: ({ status, result }) => {
        const draft =
          status === "complete"
            ? parse<{ style?: DraftedStyle | null; problems?: string[] }>(result)
            : null;
        if (draft?.style)
          return <DraftedStyleCard style={draft.style} problems={draft.problems ?? []} />;
        return <ToolStatusLine name="draft_style" status={status} result={result} />;
      },
    },
    [],
  );
  useRenderTool(
    {
      name: "*",
      render: ({
        name,
        status,
        result,
        toolCallId,
      }: {
        name: string;
        status: string;
        result?: string;
        toolCallId: string;
      }) => (
        <>
          {status === "complete" && WRITES.has(name) && !refusalOf(result) ? (
            <RefreshAfterWrite toolCallId={toolCallId} />
          ) : null}
          <ToolStatusLine name={name} status={status} result={result} />
        </>
      ),
    },
    [],
  );
}
