import { describe, expect, it, vi } from "vitest";
import { QUICK_QUESTIONS, quickActions } from "./agent-panel";

describe("quickActions", () => {
  it("gives the + menu items, so CopilotKit enables the button", () => {
    const handlers = { onUpload: vi.fn(), onCreateRecipe: vi.fn(), onAsk: vi.fn() };
    const menu = quickActions(handlers);

    expect(menu.map((item) => item.label)).toEqual([
      "Upload content…",
      "Create a recipe…",
      "Ask",
    ]);
    menu[0].action?.();
    menu[1].action?.();
    expect(handlers.onUpload).toHaveBeenCalledOnce();
    expect(handlers.onCreateRecipe).toHaveBeenCalledOnce();
  });

  it("sends each quick question exactly as written", () => {
    const onAsk = vi.fn();
    const [, , ask] = quickActions({ onUpload: vi.fn(), onCreateRecipe: vi.fn(), onAsk });

    expect(ask.items?.map((item) => item.label)).toEqual([...QUICK_QUESTIONS]);
    ask.items?.[1].action?.();
    expect(onAsk).toHaveBeenCalledWith(QUICK_QUESTIONS[1]);
  });
});
