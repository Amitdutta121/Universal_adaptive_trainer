import type { AbstractAgent, AgentSubscriber, Message } from "@ag-ui/client";
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { resumableMessages, useChatThreads } from "./chat-threads";

const save = vi.fn();
const remove = vi.fn();
const fetchThread = vi.fn();
let saved: { id: string; title: string; updated_at: string }[] = [];

vi.mock("@/lib/api/queries", () => ({
  useAgentThreads: () => ({ data: { threads: saved } }),
  useSaveAgentThread: () => ({ mutate: save }),
  useDeleteAgentThread: () => ({ mutate: remove }),
  fetchAgentThread: (...args: unknown[]) => fetchThread(...args),
}));

/** The agent surface the hook uses: messages, thread id, and run subscriptions. */
function fakeAgent() {
  const subscribers: AgentSubscriber[] = [];
  const agent = {
    messages: [] as Message[],
    threadId: "chat-own-id",
    isRunning: false,
    setMessages(messages: Message[]) {
      agent.messages = messages;
    },
    subscribe(subscriber: AgentSubscriber) {
      subscribers.push(subscriber);
      return { unsubscribe: () => subscribers.splice(subscribers.indexOf(subscriber), 1) };
    },
    finishRun() {
      for (const subscriber of subscribers) subscriber.onRunFinalized?.({} as never);
    },
  };
  return agent;
}

const hello: Message = { id: "m1", role: "user", content: "Hello" };

describe("resumableMessages", () => {
  it("drops a tool call left waiting for an approval, keeping answered ones", () => {
    const messages: Message[] = [
      hello,
      {
        id: "m2",
        role: "assistant",
        content: "",
        toolCalls: [
          { id: "a", type: "function", function: { name: "course_overview", arguments: "{}" } },
        ],
      },
      { id: "m3", role: "tool", toolCallId: "a", content: "{}" },
      {
        id: "m4",
        role: "assistant",
        content: "",
        toolCalls: [
          { id: "b", type: "function", function: { name: "save_style", arguments: "{}" } },
        ],
      },
    ];
    expect(resumableMessages(messages).map((message) => message.id)).toEqual(["m1", "m2", "m3"]);
  });
});

describe("useChatThreads", () => {
  beforeEach(() => {
    save.mockReset();
    remove.mockReset();
    fetchThread.mockReset();
    saved = [];
  });

  it("saves the whole conversation under the agent's thread id after each run", () => {
    const agent = fakeAgent();
    const { result } = renderHook(() => useChatThreads(7, agent as unknown as AbstractAgent));
    agent.messages = [hello];
    act(() => agent.finishRun());
    expect(save).toHaveBeenCalledWith(
      { threadId: "chat-own-id", messages: [hello] },
      expect.anything(),
    );
    expect(result.current.currentId).toBe("chat-own-id");
  });

  it("reopens the latest chat when the panel starts empty", async () => {
    saved = [{ id: "t1", title: "Hello", updated_at: "2026-11-09T10:00:00Z" }];
    fetchThread.mockResolvedValue({ id: "t1", messages: [hello] });
    const agent = fakeAgent();
    const { result } = renderHook(() => useChatThreads(7, agent as unknown as AbstractAgent));
    await waitFor(() => expect(result.current.currentId).toBe("t1"));
    expect(fetchThread).toHaveBeenCalledWith(7, "t1");
    expect(agent.threadId).toBe("t1");
    expect(agent.messages).toEqual([hello]);
  });

  it("starts a new chat, and deleting the open chat starts one too", () => {
    const agent = fakeAgent();
    agent.messages = [hello];
    const { result } = renderHook(() => useChatThreads(7, agent as unknown as AbstractAgent));
    act(() => result.current.remove("chat-own-id"));
    expect(remove).toHaveBeenCalledWith("chat-own-id", expect.anything());
    expect(agent.messages).toEqual([]);
    expect(agent.threadId).not.toBe("chat-own-id");
  });
});
