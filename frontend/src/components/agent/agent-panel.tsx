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
import {
  CopilotKitProvider,
  CopilotSidebar,
  useAgent,
  useCopilotKit,
} from "@copilotkit/react-core/v2";
import { useCallback, useMemo, useState } from "react";
import { toast } from "sonner";
import { BookImportDialog } from "@/app/courses/[courseId]/books/components/book-import-dialog";
import { RecipeEditorDialog } from "@/app/experimental_tutorial/recipe-builder";
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

/** Questions the "+" menu sends as they are: each one a read tool answers in the chat. */
export const QUICK_QUESTIONS = [
  "How many students do I have, and how are they doing?",
  "Which students are weakest, counting only those with enough answers?",
  "Which subtopics still need questions?",
  "What is waiting in the review queue?",
  "Which tutorial recipes do students get?",
] as const;

/**
 * The "+" menu of the chat input. CopilotKit enables the button only when it has items, so
 * without these it showed disabled. The dialogs are the Studio's own, opened over the page.
 */
export function quickActions(handlers: {
  onUpload: () => void;
  onCreateRecipe: () => void;
  onAsk: (question: string) => void;
}): ToolsMenuItem[] {
  return [
    { label: "Upload content…", action: handlers.onUpload },
    { label: "Create a recipe…", action: handlers.onCreateRecipe },
    {
      label: "Ask",
      items: QUICK_QUESTIONS.map((question) => ({
        label: question,
        action: () => handlers.onAsk(question),
      })),
    },
  ];
}

type ToolsMenuItem = { label: string } & (
  | { action: () => void; items?: never }
  | { action?: never; items: ToolsMenuItem[] }
);

function AgentSidebar({ courseId }: { courseId: number }) {
  const { agent } = useAgent();
  const { copilotkit } = useCopilotKit();
  const [open, setOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [creatingRecipe, setCreatingRecipe] = useState(false);

  // Sends a question as the professor would, the way the chat input submits one.
  const ask = useCallback(
    (question: string) => {
      if (agent.isRunning) {
        toast.info("The assistant is still answering. Ask again when it is done.");
        return;
      }
      agent.addMessage({ id: crypto.randomUUID(), role: "user", content: question });
      void copilotkit.runAgent({ agent }).catch((error: Error) => {
        toast.error(agentErrorMessage(error));
      });
    },
    [agent, copilotkit],
  );

  const toolsMenu = useMemo(
    () =>
      // The Studio's dialogs sit under the chat panel (z-50 against its z-1200), so the panel
      // closes while one is open; the conversation is kept and returns when it reopens.
      quickActions({
        onUpload: () => {
          setOpen(false);
          setUploading(true);
        },
        onCreateRecipe: () => {
          setOpen(false);
          setCreatingRecipe(true);
        },
        onAsk: ask,
      }),
    [ask],
  );

  return (
    <>
      <CopilotSidebar
        open={open}
        onOpenChange={setOpen}
        width={420}
        input={{ toolsMenu }}
        labels={{
          modalHeaderTitle: "Course assistant",
          chatInputPlaceholder: "Ask about this course, or tell it what to set up",
          chatInputToolbarAddButtonLabel: "Upload, create or ask",
          welcomeMessageText:
            "Ask about your students, coverage or review queue, or have me draft a curriculum or a tutorial recipe. Use + to upload content or create a recipe. Anything that saves or spends waits for your Approve.",
          chatDisclaimerText: "",
        }}
      />
      <BookImportDialog open={uploading} onOpenChange={setUploading} />
      {creatingRecipe ? (
        <RecipeEditorDialog
          courseId={courseId}
          recipe={null}
          onClose={() => setCreatingRecipe(false)}
        />
      ) : null}
    </>
  );
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
      {/* A new chat per course: a conversation never carries another course's ids. */}
      <AgentSidebar key={courseId} courseId={courseId} />
    </CopilotKitProvider>
  );
}
