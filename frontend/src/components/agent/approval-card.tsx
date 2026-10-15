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

export type PendingCall = { name: string; args: Record<string, unknown> };

type Topic = { name?: string; subtopics?: unknown[] };

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
      const document = (args.document ?? {}) as { label?: string; topics?: unknown };
      return {
        title: `Save the curriculum "${document.label ?? "Untitled"}"`,
        lines: ["It becomes this course's approved curriculum.", ...topicLines(document.topics)],
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
        lines: [`Id: ${yamlField(args.yaml, "id") ?? "?"}`, "Only this course will see it."],
      };
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
  toolCalls?: { id: string; function: { name: string; arguments: string } }[];
};

/** The call an interrupt is about, found in the chat's own messages by its tool call id. */
export function findCall(messages: ToolCallMessage[], interrupt: Interrupt): PendingCall | null {
  for (const message of messages) {
    for (const call of message.toolCalls ?? []) {
      if (call.id !== interrupt.toolCallId) continue;
      try {
        return { name: call.function.name, args: JSON.parse(call.function.arguments || "{}") };
      } catch {
        return { name: call.function.name, args: {} };
      }
    }
  }
  return null;
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
