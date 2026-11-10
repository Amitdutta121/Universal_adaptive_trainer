"use client";

/**
 * The card a professor clicks to let the agent write or spend (Task 33/35).
 *
 * The backend ends a run at every approval-required tool call with an AG-UI interrupt
 * (`app/agent/approvals.py`). The card shows what that call would do, read from the call's own
 * arguments, and resumes the run with `{ approved: true }` or `{ approved: false }`. Nothing
 * else approves: the backend denies any other payload.
 */

import { type Interrupt, useAgent, useInterrupt } from "@copilotkit/react-core/v2";
import { Check, ShieldCheck, X } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { type DraftedStyle, DraftedStyleCard } from "./tool-renderers";

export type PendingCall = { name: string; args: Record<string, unknown> };

type Topic = { name?: string; subtopics?: unknown[] };

/** A design tool's result (`CourseDesignView`), as far as the card reads it. */
type DesignView = {
  design_id?: string;
  title?: string;
  topic_count?: number;
  subtopic_count?: number;
  styles?: { name: string; new: boolean }[];
  recipes?: { name: string; new: boolean }[];
};

function topicLines(topics: unknown): string[] {
  if (!Array.isArray(topics)) return [];
  return (topics as Topic[]).map(
    (topic) => `${topic.name ?? "Untitled"} (${topic.subtopics?.length ?? 0} subtopics)`,
  );
}

function yamlField(yaml: unknown, field: string): string | null {
  if (typeof yaml !== "string") return null;
  return (
    new RegExp(`^${field}:\\s*(.+)$`, "m").exec(yaml)?.[1]?.replace(/^['"]|['"]$/g, "") ?? null
  );
}

/** What approving ``call`` does, in the professor's terms. */
export function describeCall(call: PendingCall): { title: string; lines: string[] } {
  const { args } = call;
  switch (call.name) {
    case "approve_curriculum": {
      // The document's own fields: Pydantic AI flattens a tool whose only parameter is a model.
      const document = args as { label?: string; topics?: unknown };
      return {
        title: `Save the curriculum "${document.label ?? "Untitled"}"`,
        lines: ["It becomes this course's approved curriculum.", ...topicLines(document.topics)],
      };
    }
    case "approve_course_design": {
      const design = args.design as DesignView | undefined;
      if (!design) {
        return {
          title: "Save the course design",
          lines: ["Saves the curriculum and makes its new styles and recipes."],
        };
      }
      const newStyles = (design.styles ?? []).filter((s) => s.new);
      const newRecipes = (design.recipes ?? []).filter((r) => r.new);
      const calls = newStyles.length + newRecipes.length;
      return {
        title: `Save the course design "${design.title ?? "Untitled"}"`,
        lines: [
          `${design.topic_count ?? 0} topics · ${design.subtopic_count ?? 0} subtopics become this course's approved curriculum.`,
          ...newStyles.map((s) => `New question style: ${s.name} (you review its examples next)`),
          ...newRecipes.map((r) => `New tutorial recipe: ${r.name}`),
          calls
            ? `Making them takes about ${calls} model calls (more if a draft needs a retry).`
            : "It reuses the course's existing styles and recipes.",
          "Its tutorial recipes are approved for students.",
        ],
      };
    }
    case "edit_curriculum": {
      const update = (args.update ?? {}) as { label?: string; topics?: unknown };
      return {
        title: `Change curriculum version ${String(args.version_id)}`,
        lines: [
          `Label: ${update.label ?? ""}`,
          "Rows left out are hidden. Students see the change right away.",
          ...topicLines(update.topics),
        ],
      };
    }
    case "save_style":
      return {
        title: `Add the style "${yamlField(args.yaml, "name") ?? yamlField(args.yaml, "id") ?? "?"}"`,
        lines: [
          args.draft
            ? "Questions for its subtopics are written like these examples."
            : `Id: ${yamlField(args.yaml, "id") ?? "?"}`,
          "Only this course will see it.",
        ],
      };
    case "set_course_subject": {
      const labels = (args.labels ?? {}) as Record<string, string>;
      const types = Array.isArray(args.question_types)
        ? args.question_types.map((id) => labels[String(id)] ?? String(id))
        : null;
      return {
        title: `Set the course's subject to ${labels[String(args.subject)] ?? String(args.subject)}`,
        lines: [
          types
            ? `Question types: ${types.join(", ")}`
            : "With the subject's default question types.",
          "It decides the wording the AI uses and where what it learns is kept.",
        ],
      };
    }
    case "publish_set":
      return {
        title: "Publish the approved questions to students",
        lines: [
          `Freezes the approved questions of curriculum version ${String(args.curriculum_version_id)} and points its classroom link at them.`,
          "Students already in a run keep the set they started on.",
        ],
      };
    case "run_generation":
      return {
        title: "Start generating questions",
        lines: [
          `Spends about ${String(args.model_calls)} model calls, as priced in the plan above.`,
        ],
      };
    case "import_material":
      return {
        title: "Import a YouTube video",
        lines: [
          String(args.url ?? ""),
          args.transcript
            ? "From the transcript you pasted."
            : "Its transcript becomes course material; the video stays on YouTube.",
        ],
      };
    case "save_recipe":
      return {
        title: `Save the recipe "${yamlField(args.yaml, "name") ?? yamlField(args.yaml, "id") ?? "?"}"`,
        lines: [
          `Id: ${yamlField(args.yaml, "id") ?? "?"}`,
          "Saved to this course. Students see it only once it is approved for a taxonomy.",
          "Saving over a recipe hides the blocks written from its old wording.",
        ],
      };
    case "decide_recipe":
      return args.approved
        ? {
            title: `Approve the recipe ${String(args.recipe_id)} for students`,
            lines: [
              `Curriculum version ${String(args.curriculum_version_id)}: its blocks are shown, and missing ones written as students need them.`,
            ],
          }
        : {
            title: `Stop using the recipe ${String(args.recipe_id)}`,
            lines: [
              `Curriculum version ${String(args.curriculum_version_id)}: its blocks are hidden from students.`,
            ],
          };
    default:
      return { title: `Run ${call.name}`, lines: [JSON.stringify(args)] };
  }
}

export function ApprovalCardView({
  call,
  onDecide,
}: {
  call: PendingCall;
  onDecide: (approved: boolean) => void;
}) {
  const [decision, setDecision] = useState<boolean | null>(null);
  const { title, lines } = describeCall(call);
  const decide = (approved: boolean) => {
    setDecision(approved);
    onDecide(approved);
  };
  return (
    <div className="my-2 rounded-lg border bg-card p-3 text-card-foreground text-sm">
      <div className="flex items-center gap-2 font-medium">
        <ShieldCheck className="size-4 text-primary" />
        {title}
      </div>
      <ul className="mt-2 space-y-0.5 text-muted-foreground">
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      {call.name === "save_style" && call.args.draft ? (
        <DraftedStyleCard style={call.args.draft as DraftedStyle} problems={[]} />
      ) : null}
      {decision === null ? (
        <div className="mt-3 flex gap-2">
          <Button size="sm" onClick={() => decide(true)}>
            <Check /> Approve
          </Button>
          <Button size="sm" variant="outline" onClick={() => decide(false)}>
            <X /> Reject
          </Button>
        </div>
      ) : (
        <p className="mt-3 text-muted-foreground text-xs">{decision ? "Approved" : "Rejected"}</p>
      )}
    </div>
  );
}

type ToolCallMessage = {
  role?: string;
  content?: unknown;
  toolCalls?: { id: string; function: { name: string; arguments: string } }[];
};

/** The latest state of design ``designId``, from the newest design tool result in the chat. */
function proposedDesign(messages: ToolCallMessage[], designId: unknown): DesignView | undefined {
  for (const message of [...messages].reverse()) {
    if (message.role !== "tool" || typeof message.content !== "string") continue;
    const view = parse<DesignView>(message.content);
    if (view && view.design_id === designId) return view;
  }
  return undefined;
}

type StyleHolder = { style?: DraftedStyle | null; style_drafts?: { style?: DraftedStyle }[] };

/** The drafted style with ``styleId`` that a `draft_style` or `approve_course_design` result in
 * the chat holds, so its approval card can show the examples being approved. */
function draftedStyle(
  messages: ToolCallMessage[],
  styleId: string | null,
): DraftedStyle | undefined {
  if (!styleId) return undefined;
  for (const message of [...messages].reverse()) {
    if (message.role !== "tool" || typeof message.content !== "string") continue;
    const held = parse<StyleHolder>(message.content);
    const styles = [held?.style, ...(held?.style_drafts ?? []).map((d) => d.style)];
    const found = styles.find((style) => style?.id === styleId);
    if (found) return found;
  }
  return undefined;
}

/** Subject and question type labels by id, from the newest `subject_options` result. */
function optionLabels(messages: ToolCallMessage[]): Record<string, string> {
  for (const message of [...messages].reverse()) {
    if (message.role !== "tool" || typeof message.content !== "string") continue;
    const options = parse<{
      subjects?: { id: string; label: string }[];
      question_types?: { id: string; label: string }[];
    }>(message.content);
    if (!options?.subjects) continue;
    return Object.fromEntries(
      [...options.subjects, ...(options.question_types ?? [])].map((o) => [o.id, o.label]),
    );
  }
  return {};
}

/** The call an interrupt is about, found in the chat's own messages by its tool call id. */
export function findCall(messages: ToolCallMessage[], interrupt: Interrupt): PendingCall | null {
  for (const message of messages) {
    for (const call of message.toolCalls ?? []) {
      if (call.id !== interrupt.toolCallId) continue;
      const args = parse<Record<string, unknown>>(call.function.arguments || "{}") ?? {};
      if (call.function.name === "approve_course_design") {
        args.design = proposedDesign(messages, args.design_id);
      }
      if (call.function.name === "set_course_subject") args.labels = optionLabels(messages);
      if (call.function.name === "save_style") {
        const draft = draftedStyle(messages, yamlField(args.yaml, "id"));
        if (draft) args.draft = draft;
      }
      return { name: call.function.name, args };
    }
  }
  return null;
}

function parse<T>(text: string): T | null {
  try {
    return JSON.parse(text) as T;
  } catch {
    return null;
  }
}

function InterruptApproval({
  interrupt,
  resolve,
}: {
  interrupt: Interrupt;
  resolve: (payload: unknown, interruptId?: string) => unknown;
}) {
  const { agent } = useAgent();
  const call = findCall(agent.messages as ToolCallMessage[], interrupt) ?? {
    name: "unknown",
    args: { request: interrupt.message ?? "" },
  };
  return (
    <ApprovalCardView
      call={call}
      onDecide={(approved) =>
        resolve(
          approved ? { approved: true } : { approved: false, reason: "The professor rejected it." },
          interrupt.id,
        )
      }
    />
  );
}

/** Renders one approval card per open interrupt, inside the chat. */
export function useApprovalCards() {
  useInterrupt({
    render: ({ interrupts, resolve }) => (
      <>
        {interrupts.map((interrupt) => (
          <InterruptApproval key={interrupt.id} interrupt={interrupt} resolve={resolve} />
        ))}
      </>
    ),
  });
}
