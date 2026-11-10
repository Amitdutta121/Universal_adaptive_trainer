"use client";

/**
 * The professor agent: one conversation per course, shown in a side panel on every course page
 * (Phase 8, Task 35) and full-page on the assistant page (`app/courses/[courseId]/assistant`).
 * `AgentProvider` holds it, with its saved chats and the "+" menu's dialogs, so moving between the
 * two views keeps the conversation.
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
import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from "react";
import { toast } from "sonner";
import { RecipeEditorDialog } from "@/app/experimental_tutorial/recipe-builder";
import { COURSE_HEADER } from "@/lib/api/client";
import { useApprovalCards } from "./approval-card";
import { ChatAskContext } from "./chat-ask";
import { type ChatAttachments, useChatAttachments } from "./chat-attachments";
import { ChatThreadsProvider, chatHeader, useChatThreads } from "./chat-threads";
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

function AgentRenderers() {
  useApprovalCards();
  useAgentToolRenderers();
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
 * The "+" menu of the chat input, after CopilotKit's own "Attach files" (attachments, ADR-076).
 * The recipe editor is the Studio's own dialog, opened over the page.
 */
export function quickActions(handlers: {
  onCreateRecipe: () => void;
  onAsk: (question: string) => void;
}): ToolsMenuItem[] {
  return [
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

export type ToolsMenuItem = { label: string } & (
  | { action: () => void; items?: never }
  | { action?: never; items: ToolsMenuItem[] }
);

/** The chat's wording, the same in the side panel and on the assistant page. */
export const CHAT_LABELS = {
  modalHeaderTitle: "Course assistant",
  chatInputPlaceholder: "Ask about this course, or tell it what to set up",
  // Also the "+" menu's attach item, which CopilotKit adds first.
  chatInputToolbarAddButtonLabel: "Attach files",
  welcomeMessageText:
    "Tell me what you teach and to whom, and I'll set the course up: subject, curriculum, question styles and tutorial recipes. Drop your material here or attach it with +. Anything that saves or spends waits for your Approve.",
  chatDisclaimerText: "",
};

type CourseChat = {
  courseId: number;
  /** Sends a message as the professor would, the way the chat input submits one. */
  ask: (question: string) => void;
  toolsMenu: ToolsMenuItem[];
  attachments: ChatAttachments;
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
};

const CourseChatContext = createContext<CourseChat | null>(null);

/** The course's conversation and its actions; only inside `AgentProvider`. */
export function useCourseChat(): CourseChat {
  const chat = useContext(CourseChatContext);
  if (!chat) throw new Error("useCourseChat needs an AgentProvider.");
  return chat;
}

function CourseChatRoot({ courseId, children }: { courseId: number; children: ReactNode }) {
  const { agent } = useAgent();
  const { copilotkit } = useCopilotKit();
  const threads = useChatThreads(courseId, agent);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const attachments = useChatAttachments(courseId);
  const [creatingRecipe, setCreatingRecipe] = useState(false);

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
      // The Studio's dialogs sit under the side panel (z-50 against its z-1200), so the panel
      // closes while one is open; the conversation is kept and returns when it reopens.
      quickActions({
        onCreateRecipe: () => {
          setSidebarOpen(false);
          setCreatingRecipe(true);
        },
        onAsk: ask,
      }),
    [ask],
  );

  const chat = useMemo(
    () => ({ courseId, ask, toolsMenu, attachments, sidebarOpen, setSidebarOpen }),
    [courseId, ask, toolsMenu, attachments, sidebarOpen],
  );

  return (
    <ChatThreadsProvider value={threads}>
      <CourseChatContext.Provider value={chat}>
        <ChatAskContext.Provider value={ask}>{children}</ChatAskContext.Provider>
        {creatingRecipe ? (
          <RecipeEditorDialog
            courseId={courseId}
            recipe={null}
            onClose={() => setCreatingRecipe(false)}
          />
        ) : null}
      </CourseChatContext.Provider>
    </ChatThreadsProvider>
  );
}

/** The side panel, on every course page but the assistant page. */
export function AgentSidebar() {
  const { toolsMenu, attachments, sidebarOpen, setSidebarOpen } = useCourseChat();
  return (
    <CopilotSidebar
      open={sidebarOpen}
      onOpenChange={setSidebarOpen}
      width={420}
      header={{ children: chatHeader }}
      input={{ toolsMenu }}
      attachments={attachments}
      labels={CHAT_LABELS}
    />
  );
}

/**
 * The agent for one course, around the course's pages. Keyed by course, so a conversation never
 * carries another course's ids into the next one.
 */
export function AgentProvider({ courseId, children }: { courseId: number; children: ReactNode }) {
  const headers = useMemo(() => ({ [COURSE_HEADER]: String(courseId) }), [courseId]);
  return (
    <CopilotKitProvider
      key={courseId}
      runtimeUrl="/copilotkit"
      headers={headers}
      showDevConsole={false}
      enableInspector={false}
      onError={({ error }) => {
        toast.error(agentErrorMessage(error));
      }}
    >
      <AgentRenderers />
      <CourseChatRoot courseId={courseId}>{children}</CourseChatRoot>
    </CopilotKitProvider>
  );
}
