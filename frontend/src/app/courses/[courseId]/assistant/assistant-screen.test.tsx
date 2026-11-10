import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AssistantScreen, STEP_PROMPTS } from "./assistant-screen";

const ask = vi.fn();
const open = vi.fn();
const newChat = vi.fn();

vi.mock("@copilotkit/react-core/v2", () => ({
  CopilotChat: () => <div data-testid="chat" />,
  useConfigureSuggestions: () => {},
  useAgent: () => ({ agent: { messages: [] } }),
}));
vi.mock("@/components/agent/agent-panel", () => ({
  CHAT_LABELS: {},
  useCourseChat: () => ({ courseId: 3, ask, toolsMenu: [], attachments: { enabled: true } }),
}));
vi.mock("@/components/agent/chat-threads", () => ({
  chatTime: () => "10:00",
  useChatThreadList: () => ({
    threads: [{ id: "t1", title: "Set up Python", updated_at: "2026-11-09T10:00:00Z" }],
    currentId: "t1",
    open,
    newChat,
    remove: vi.fn(),
  }),
}));
vi.mock("@/components/agent/chat-materials", () => ({
  ChatMaterialsButton: () => null,
  MaterialsPanel: () => null,
}));
vi.mock("@/lib/api/queries", () => ({
  useCourse: () => ({ data: { name: "CS 135" } }),
}));
vi.mock("@/lib/course-setup", () => ({
  useCourseSetup: () => ({
    error: null,
    setup: {
      done: 1,
      total: 5,
      steps: [
        { key: "content", title: "Add content", state: "done", detail: "1 book", path: "/books" },
        {
          key: "curriculum",
          title: "Build the curriculum",
          state: "next",
          detail: "Draft it with AI",
          path: "/curriculum",
        },
        {
          key: "questions",
          title: "Choose question types",
          state: "blocked",
          detail: "Needs an approved curriculum",
          path: "/questions",
        },
      ],
      next: null,
    },
  }),
}));

describe("AssistantScreen", () => {
  beforeEach(() => {
    ask.mockReset();
    open.mockReset();
    newChat.mockReset();
  });

  it("hands a setup step to the assistant, and opens its page", async () => {
    const user = userEvent.setup();
    render(<AssistantScreen />);

    const curriculum = screen.getByText("Build the curriculum").closest("li") as HTMLElement;
    await user.click(within(curriculum).getByRole("button", { name: "Ask the assistant" }));
    expect(ask).toHaveBeenCalledWith(STEP_PROMPTS.curriculum);
    expect(within(curriculum).getByRole("link", { name: /Open page/ })).toHaveAttribute(
      "href",
      "/courses/3/curriculum",
    );

    // A done step only links to its page; a blocked one offers nothing to do yet.
    const content = screen.getByText("Add content").closest("li") as HTMLElement;
    expect(within(content).queryByRole("button")).not.toBeInTheDocument();
    const questions = screen.getByText("Choose question types").closest("li") as HTMLElement;
    expect(within(questions).queryByRole("button")).not.toBeInTheDocument();
  });

  it("lists the saved chats and switches between them", async () => {
    const user = userEvent.setup();
    render(<AssistantScreen />);

    const list = screen.getByRole("list", { name: "Saved chats" });
    await user.click(within(list).getByRole("button", { name: /^Set up Python/ }));
    expect(open).toHaveBeenCalledWith("t1");
    await user.click(screen.getAllByRole("button", { name: "New chat" })[0]);
    expect(newChat).toHaveBeenCalled();
    expect(screen.getByTestId("chat")).toBeInTheDocument();
    expect(screen.getByText("CS 135")).toBeInTheDocument();
  });
});
