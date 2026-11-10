"use client";

/**
 * The course assistant's own page: where a new course lands, and where a professor sets a course
 * up by chatting (ADR-074).
 *
 * Three columns on a wide screen: the course's saved chats, the conversation, and the setup
 * steps with their real state (`lib/course-setup.ts`). The conversation is the one the side panel
 * shows on every other page (`AgentProvider`), so leaving and coming back keeps it. Each step can
 * be handed to the assistant as a message, or opened on its own page.
 */

import { CopilotChat, useAgent, useConfigureSuggestions } from "@copilotkit/react-core/v2";
import {
  ArrowUpRight,
  CheckCircle2,
  Circle,
  CircleDashed,
  Loader2,
  MessageSquarePlus,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { CHAT_LABELS, useCourseChat } from "@/components/agent/agent-panel";
import { ChatMaterialsButton, MaterialsPanel } from "@/components/agent/chat-materials";
import { chatTime, useChatThreadList } from "@/components/agent/chat-threads";
import { QueryError } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCourse } from "@/lib/api/queries";
import { coursePath } from "@/lib/course";
import { type SetupStep, type StepKey, useCourseSetup } from "@/lib/course-setup";
import { cn } from "@/lib/utils";

/** What to ask the assistant to do each setup step, in the professor's words. */
export const STEP_PROMPTS: Record<StepKey, string> = {
  content: "Help me add my course material. What can I upload?",
  curriculum: "Draft a curriculum from my material, aimed at my students.",
  questions: "Suggest question styles for each subtopic, and draft any style the course lacks.",
  review: "What is waiting in the review queue?",
  tutorials: "Which tutorial recipes suit this course? Draft one if none fit.",
  share: "Publish the approved questions so students can join.",
};

/** The side panel's wording, with a welcome short enough to read as a page heading. */
const PAGE_LABELS = {
  ...CHAT_LABELS,
  welcomeMessageText: "What are you teaching, and to whom?",
};

/** Shown in a chat that has no message yet. */
const STARTERS = [
  {
    title: "Set up a new course",
    message:
      "I'm setting up a new course. Ask me what I teach and to whom, then set the subject and draft a curriculum.",
  },
  { title: "Where am I?", message: "What is done in this course, and what should I do next?" },
  {
    title: "Make a question style",
    message: "Draft a question style that checks understanding, not recall.",
  },
];

function StepIcon({ step }: { step: SetupStep }) {
  if (step.state === "done") return <CheckCircle2 className="size-4 text-[var(--ok-solid)]" />;
  if (step.state === "running")
    return <Loader2 className="size-4 animate-spin text-[var(--warn-solid)]" />;
  if (step.state === "next") return <Circle className="size-4 text-primary" strokeWidth={2.5} />;
  return <CircleDashed className="size-4 text-muted-foreground" />;
}

function SetupSteps({ courseId }: { courseId: number }) {
  const { setup, error } = useCourseSetup(courseId);
  const { ask } = useCourseChat();

  if (error) return <QueryError error={error} />;
  if (!setup) return <Skeleton className="h-80 w-full rounded-xl" />;

  return (
    <div className="flex min-h-0 flex-col">
      <div className="space-y-2 border-b px-4 py-3">
        <div className="flex items-baseline justify-between gap-2">
          <h2 className="font-medium text-sm">Course setup</h2>
          <span className="text-muted-foreground text-xs">
            {setup.done} of {setup.total}
          </span>
        </div>
        <div className="flex gap-1" aria-hidden="true">
          {setup.steps
            .filter((step) => !step.optional)
            .map((step) => (
              <span
                key={step.key}
                className={cn(
                  "h-1 flex-1 rounded-full bg-muted",
                  step.state === "done" && "bg-[var(--ok-solid)]",
                  step === setup.next && "bg-primary",
                )}
              />
            ))}
        </div>
      </div>
      <ol className="min-h-0 overflow-y-auto">
        {setup.steps.map((step) => {
          const isNext = step === setup.next;
          return (
            <li
              key={step.key}
              data-step={step.key}
              data-state={step.state}
              className={cn("border-b px-4 py-3 last:border-b-0", isNext && "bg-accent/50")}
            >
              <div className="flex items-start gap-2.5">
                <span className="mt-0.5 shrink-0">
                  <StepIcon step={step} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span
                      className={cn(
                        "font-medium text-sm",
                        step.state === "blocked" && "text-muted-foreground",
                      )}
                    >
                      {step.title}
                    </span>
                    {step.optional ? (
                      <span className="text-muted-foreground text-xs">optional</span>
                    ) : null}
                  </div>
                  <p className="mt-0.5 line-clamp-2 text-muted-foreground text-xs">{step.detail}</p>
                  {step.state === "done" || step.state === "blocked" ? null : (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <Button
                        size="sm"
                        variant={isNext ? "default" : "outline"}
                        className="h-7 px-2.5 text-xs"
                        onClick={() => ask(STEP_PROMPTS[step.key])}
                      >
                        Ask the assistant
                      </Button>
                      <Button asChild size="sm" variant="ghost" className="h-7 px-2 text-xs">
                        <Link href={coursePath(courseId, step.path)}>
                          Open page
                          <ArrowUpRight className="size-3" />
                        </Link>
                      </Button>
                    </div>
                  )}
                </div>
                {step.state === "done" ? (
                  <Link
                    href={coursePath(courseId, step.path)}
                    className="shrink-0 text-muted-foreground text-xs hover:text-foreground"
                  >
                    Open
                  </Link>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function ChatList() {
  const threads = useChatThreadList();
  if (!threads) return null;
  return (
    <div className="flex min-h-0 flex-col">
      <div className="border-b p-3">
        <Button
          variant="outline"
          size="sm"
          className="w-full justify-start"
          onClick={threads.newChat}
        >
          <MessageSquarePlus className="size-4" />
          New chat
        </Button>
      </div>
      {threads.threads.length === 0 ? (
        <p className="px-4 py-3 text-muted-foreground text-xs">Chats are saved here.</p>
      ) : (
        <ul className="min-h-0 overflow-y-auto p-1.5" aria-label="Saved chats">
          {threads.threads.map((thread) => {
            const current = thread.id === threads.currentId;
            return (
              <li key={thread.id} className="group relative">
                <button
                  type="button"
                  aria-current={current ? "true" : undefined}
                  className={cn(
                    "flex w-full flex-col rounded-md px-2.5 py-2 pr-8 text-left hover:bg-muted",
                    current && "bg-muted",
                  )}
                  onClick={() => threads.open(thread.id)}
                >
                  <span className={cn("truncate text-sm", current && "font-medium")}>
                    {thread.title}
                  </span>
                  <span className="text-muted-foreground text-xs">
                    {chatTime(thread.updated_at)}
                  </span>
                </button>
                <button
                  type="button"
                  aria-label={`Delete chat: ${thread.title}`}
                  title="Delete chat"
                  className="absolute top-2 right-1.5 inline-flex size-6 items-center justify-center rounded text-muted-foreground opacity-0 hover:bg-background hover:text-foreground focus-visible:opacity-100 group-hover:opacity-100"
                  onClick={() => threads.remove(thread.id)}
                >
                  <Trash2 className="size-3.5" />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export function AssistantScreen() {
  const { courseId, toolsMenu, attachments } = useCourseChat();
  const course = useCourse(courseId);
  // Only in an empty chat: a reopened chat already has messages, which CopilotKit's own
  // "before-first-message" does not notice.
  const { agent } = useAgent();
  const empty = agent.messages.length === 0;
  const [files, setFiles] = useState(false);
  useConfigureSuggestions(
    empty ? { suggestions: STARTERS, available: "before-first-message" } : null,
    [empty],
  );

  return (
    <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,1fr)_19rem] xl:grid-cols-[14rem_minmax(0,1fr)_19rem]">
      <aside className="hidden min-h-0 flex-col overflow-hidden rounded-xl border bg-card xl:flex">
        <ChatList />
      </aside>
      <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border bg-card">
        <header className="relative flex items-center gap-3 border-b px-4 py-3">
          <div className="min-w-0 flex-1">
            <h1 className="truncate font-semibold text-base">Course assistant</h1>
            <p className="truncate text-muted-foreground text-xs">{course.data?.name ?? " "}</p>
          </div>
          <ChatHeaderNewChat />
          <ChatMaterialsButton open={files} onToggle={() => setFiles((value) => !value)} />
          {files ? <MaterialsPanel onClose={() => setFiles(false)} /> : null}
        </header>
        <div className="min-h-0 flex-1">
          <CopilotChat
            className="h-full"
            input={{ toolsMenu }}
            attachments={attachments}
            labels={PAGE_LABELS}
          />
        </div>
      </section>
      <aside className="hidden min-h-0 flex-col overflow-hidden rounded-xl border bg-card lg:flex">
        <SetupSteps courseId={courseId} />
      </aside>
    </div>
  );
}

/** "New chat" in the conversation's header, where the chat list column is hidden. */
function ChatHeaderNewChat() {
  const threads = useChatThreadList();
  if (!threads) return null;
  return (
    <Button variant="ghost" size="sm" className="xl:hidden" onClick={threads.newChat}>
      <MessageSquarePlus className="size-4" />
      New chat
    </Button>
  );
}
