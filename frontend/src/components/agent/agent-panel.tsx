"use client";

/**
 * The professor agent as a side panel on every course page (Phase 8, Task 35).
 *
 * CopilotKit renders the chat. Its runtime (`app/copilotkit/[[...path]]/route.ts`) relays each
 * run to the backend's AG-UI endpoint (`POST /api/agent`, Pydantic AI), sending the course in
 * `X-Course-Id` as the API client does.
 *
 * New dependencies: `@copilotkit/react-core` (chat UI, tool-call rendering, AG-UI interrupt
 * handling for approval cards), `@copilotkit/runtime` and `@ag-ui/client` (the relay).
 */

import "@copilotkit/react-core/v2/styles.css";
import { CopilotKitProvider, CopilotSidebar } from "@copilotkit/react-core/v2";
import { useMemo } from "react";
import { toast } from "sonner";
import { COURSE_HEADER } from "@/lib/api/client";
import { useApprovalCards } from "./approval-card";
import { useAgentToolRenderers } from "./tool-renderers";

/**
 * The backend's own refusal in a failed run, e.g. "This feature needs an LLM provider and API
 * key." or the unverified-email refusal; the error's text when it carries none.
 */
export function agentErrorMessage(error: Error): string {
  const json = /\{[\s\S]*\}/.exec(error.message)?.[0];
  if (json) {
    try {
      const body = JSON.parse(json) as { error?: { message?: string; detail?: string } };
      if (body.error?.message) return body.error.message;
    } catch {
      // Not the backend's envelope: fall through to the raw text.
    }
  }
  return error.message || "The assistant could not answer.";
}

function AgentRenderers({ courseId }: { courseId: number }) {
  useApprovalCards();
  useAgentToolRenderers(courseId);
  return null;
}

export function AgentPanel({ courseId }: { courseId: number }) {
  const headers = useMemo(() => ({ [COURSE_HEADER]: String(courseId) }), [courseId]);
  return (
    <CopilotKitProvider
      runtimeUrl="/copilotkit"
      headers={headers}
      showDevConsole={false}
      enableInspector={false}
      onError={({ error }) => {
        toast.error(agentErrorMessage(error));
      }}
    >
      <AgentRenderers courseId={courseId} />
      <CopilotSidebar
        // A new chat per course: a conversation never carries another course's ids.
        key={courseId}
        defaultOpen={false}
        width={420}
        labels={{
          modalHeaderTitle: "Course assistant",
          chatInputPlaceholder: "Ask about this course, or tell it what to set up",
          welcomeMessageText:
            "I can import a YouTube lecture, draft a curriculum, compare question styles, price and run generation, and publish to students. Anything that saves or spends waits for your Approve.",
          chatDisclaimerText: "",
        }}
      />
    </CopilotKitProvider>
  );
}
