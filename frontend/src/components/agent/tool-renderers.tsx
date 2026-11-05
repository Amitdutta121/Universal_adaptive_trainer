"use client";

/**
 * How the agent's tool calls show in the chat (Task 35).
 *
 * `preview_styles` renders the compared styles side by side with their worked examples,
 * `open_view` navigates the Studio to the page it names, and every other tool shows one
 * status line, with the app's refusal when it refused.
 */

import { useRenderTool } from "@copilotkit/react-core/v2";
import { Check, CircleAlert, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { z } from "zod";
import { coursePath } from "@/lib/course";
import { PromptText } from "@/components/prompt-text";

export type StyleSample = {
  prompt: string;
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
  open_view: "Open a page",
};

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
              <PromptText text={example.prompt} className="space-y-1 leading-normal" />
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

/** Navigations already made, by tool call id, so a re-render never navigates twice. */
const opened = new Set<string>();

function OpenView({
  toolCallId,
  path,
  courseId,
}: {
  toolCallId: string;
  path: string;
  courseId: number;
}) {
  const router = useRouter();
  useEffect(() => {
    if (opened.has(toolCallId)) return;
    opened.add(toolCallId);
    router.push(coursePath(courseId, path));
  }, [toolCallId, path, courseId, router]);
  return <ToolStatusLine name="open_view" status="complete" />;
}

export function useAgentToolRenderers(courseId: number) {
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
      name: "open_view",
      parameters: z.object({ view: z.string(), id: z.number().nullish() }),
      render: ({ status, result, toolCallId }) => {
        const path = status === "complete" ? parse<{ path?: string }>(result)?.path : undefined;
        if (path) return <OpenView toolCallId={toolCallId} path={path} courseId={courseId} />;
        return <ToolStatusLine name="open_view" status={status} result={result} />;
      },
    },
    [courseId],
  );
  useRenderTool(
    {
      name: "*",
      render: ({ name, status, result }: { name: string; status: string; result?: string }) => (
        <ToolStatusLine name={name} status={status} result={result} />
      ),
    },
    [],
  );
}
