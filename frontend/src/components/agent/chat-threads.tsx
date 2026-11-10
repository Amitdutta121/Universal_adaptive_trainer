"use client";

/**
 * Saved chats for the course assistant (ADR-075).
 *
 * The chat keeps its conversation as AG-UI messages on the agent. After every run the whole list
 * is saved under the agent's thread id (`PUT /api/agent/threads/{id}`); opening a saved chat puts
 * its messages back on the agent. CopilotKit's own thread list needs its paid cloud service, so
 * the threads live in the app's database instead, and the chat is never given a `threadId` prop
 * (that would make it try to reconnect to a server-side thread the relay does not keep).
 */

import type { AbstractAgent, Message } from "@ag-ui/client";
import { History, SquarePen, Trash2 } from "lucide-react";
import {
  createContext,
  type ReactElement,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { toast } from "sonner";
import {
  fetchAgentThread,
  useAgentThreads,
  useDeleteAgentThread,
  useSaveAgentThread,
} from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { ChatMaterialsButton, MaterialsPanel } from "./chat-materials";

type ThreadSummary = Schemas["AgentThreadSummary"];

/**
 * The messages of a saved chat that can be sent again. A run that stopped for an approval leaves
 * a tool call without a result; after a reload that approval card is gone, and a model refuses a
 * history with an unanswered call, so such calls are dropped (the agent asks again if needed).
 */
export function resumableMessages(messages: Message[]): Message[] {
  const answered = new Set(
    messages.flatMap((message) => (message.role === "tool" ? [message.toolCallId] : [])),
  );
  return messages.flatMap((message): Message[] => {
    if (message.role !== "assistant" || !message.toolCalls?.length) return [message];
    const toolCalls = message.toolCalls.filter((call) => answered.has(call.id));
    if (toolCalls.length === message.toolCalls.length) return [message];
    if (toolCalls.length === 0 && !message.content) return [];
    return [{ ...message, toolCalls: toolCalls.length ? toolCalls : undefined }];
  });
}

type ChatThreads = {
  threads: ThreadSummary[];
  currentId: string | null;
  open: (threadId: string) => void;
  newChat: () => void;
  remove: (threadId: string) => void;
};

const ChatThreadsContext = createContext<ChatThreads | null>(null);

/**
 * Saves the agent's conversation after each run, reopens the latest chat when the course
 * opens with none, and switches between chats. Mounted once per course (`AgentProvider`), so the
 * side panel and the assistant page share one conversation.
 */
export function useChatThreads(courseId: number, agent: AbstractAgent): ChatThreads {
  const list = useAgentThreads(courseId);
  const save = useSaveAgentThread(courseId);
  const deletion = useDeleteAgentThread(courseId);
  const [currentId, setCurrentId] = useState<string | null>(null);
  // The id the conversation on the agent is saved under. Kept here, not read off the agent:
  // each chat view (side panel, assistant page) gives the agent a fresh thread id when it
  // mounts, which would split one conversation into two saved chats.
  const threadRef = useRef<string | null>(null);
  const saveRef = useRef(save.mutate);
  saveRef.current = save.mutate;

  useEffect(() => {
    const subscription = agent.subscribe({
      onRunFinalized: () => {
        if (agent.messages.length === 0) return;
        const threadId = threadRef.current ?? agent.threadId;
        threadRef.current = threadId;
        setCurrentId(threadId);
        saveRef.current(
          { threadId, messages: agent.messages },
          { onError: () => toast.error("This chat could not be saved.") },
        );
      },
    });
    return () => subscription.unsubscribe();
  }, [agent]);

  const open = useCallback(
    (threadId: string) => {
      if (agent.isRunning) {
        toast.info("The assistant is still answering. Switch chats when it is done.");
        return;
      }
      fetchAgentThread(courseId, threadId).then(
        (thread) => {
          agent.setMessages(resumableMessages(thread.messages as unknown as Message[]));
          agent.threadId = thread.id;
          threadRef.current = thread.id;
          setCurrentId(thread.id);
        },
        () => toast.error("This chat could not be opened."),
      );
    },
    [agent, courseId],
  );

  const newChat = useCallback(() => {
    if (agent.isRunning) {
      toast.info("The assistant is still answering. Start a new chat when it is done.");
      return;
    }
    agent.setMessages([]);
    agent.threadId = crypto.randomUUID();
    threadRef.current = null;
    setCurrentId(null);
  }, [agent]);

  const remove = useCallback(
    (threadId: string) => {
      deletion.mutate(threadId, {
        onError: () => toast.error("This chat could not be deleted."),
      });
      if (threadId === (threadRef.current ?? agent.threadId)) newChat();
    },
    [agent, deletion, newChat],
  );

  // The panel opens on the latest chat, so setting a course up can continue where it stopped.
  const resumed = useRef(false);
  useEffect(() => {
    if (resumed.current || !list.data) return;
    resumed.current = true;
    const latest = list.data.threads[0];
    if (latest && agent.messages.length === 0) open(latest.id);
  }, [list.data, agent, open]);

  return { threads: list.data?.threads ?? [], currentId, open, newChat, remove };
}

export const ChatThreadsProvider = ChatThreadsContext.Provider;

/** The course's saved chats and the actions on them; `null` outside `AgentProvider`. */
export function useChatThreadList(): ChatThreads | null {
  return useContext(ChatThreadsContext);
}

/** When a chat was last used: the time today, the date before. */
export function chatTime(iso: string): string {
  return when(iso);
}

function when(iso: string): string {
  const date = new Date(iso);
  const sameDay = date.toDateString() === new Date().toDateString();
  return sameDay
    ? date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })
    : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

const iconButton =
  "inline-flex size-8 items-center justify-center rounded-full text-muted-foreground transition hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/**
 * The chat panel's header: past chats and a new chat on the left, the title, then close. The
 * list opens inside the panel, since the Studio's popovers sit under it (z-50 against z-1200).
 * Passed as the sidebar's `header={{ children: chatHeader }}`: the slot takes props, not a
 * component.
 */
export function chatHeader({
  titleContent,
  closeButton,
}: {
  titleContent: ReactElement;
  closeButton: ReactElement;
}) {
  return <ChatHeader titleContent={titleContent} closeButton={closeButton} />;
}

function ChatHeader({
  titleContent,
  closeButton,
}: {
  titleContent: ReactElement;
  closeButton: ReactElement;
}) {
  const threads = useContext(ChatThreadsContext);
  const [listing, setListing] = useState(false);
  const [files, setFiles] = useState(false);
  return (
    <header className="relative border-b bg-background px-3 py-3">
      <div className="flex items-center gap-1">
        {threads ? (
          <>
            <button
              type="button"
              className={cn(iconButton, listing && "bg-muted text-foreground")}
              aria-label="Past chats"
              aria-expanded={listing}
              title="Past chats"
              onClick={() => {
                setFiles(false);
                setListing((value) => !value);
              }}
            >
              <History className="size-4" />
            </button>
            <button
              type="button"
              className={iconButton}
              aria-label="New chat"
              title="New chat"
              onClick={() => {
                setListing(false);
                threads.newChat();
              }}
            >
              <SquarePen className="size-4" />
            </button>
          </>
        ) : null}
        <div className="min-w-0 flex-1 px-1 text-center">{titleContent}</div>
        <ChatMaterialsButton
          open={files}
          onToggle={() => {
            setListing(false);
            setFiles((value) => !value);
          }}
        />
        {closeButton}
      </div>
      {files ? <MaterialsPanel onClose={() => setFiles(false)} /> : null}
      {threads && listing ? (
        <div className="absolute inset-x-0 top-full z-10 max-h-80 overflow-y-auto border-b bg-background shadow-sm">
          {threads.threads.length === 0 ? (
            <p className="px-4 py-3 text-muted-foreground text-sm">No saved chats yet.</p>
          ) : (
            <ul className="py-1">
              {threads.threads.map((thread) => (
                <li key={thread.id} className="group flex items-center gap-1 px-2">
                  <button
                    type="button"
                    className={cn(
                      "flex min-w-0 flex-1 items-baseline gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted",
                      thread.id === threads.currentId && "bg-muted font-medium",
                    )}
                    onClick={() => {
                      setListing(false);
                      threads.open(thread.id);
                    }}
                  >
                    <span className="min-w-0 flex-1 truncate">{thread.title}</span>
                    <span className="shrink-0 text-muted-foreground text-xs">
                      {when(thread.updated_at)}
                    </span>
                  </button>
                  <button
                    type="button"
                    className={cn(iconButton, "size-7 shrink-0")}
                    aria-label={`Delete chat: ${thread.title}`}
                    title="Delete chat"
                    onClick={() => threads.remove(thread.id)}
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </header>
  );
}
