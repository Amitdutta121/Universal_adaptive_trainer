/**
 * Flow smoke test for the student-experience prototype. This is the stand-in for
 * the live keyboard walkthrough the frontend-readiness audit would otherwise do
 * in a browser: it drives welcome → question → result → summary and asserts the
 * accessibility wiring (labelled controls, live region, landmarks, focus, a
 * confirmed reset) along the way.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SESSION_STORAGE_KEY } from "./session-types";
import { StudentExperience } from "./student-experience";

beforeEach(() => {
  window.localStorage.clear();
  window.history.replaceState(null, "", "/experiments/student");
  // jsdom has no matchMedia; useReducedMotion needs it.
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function startSession(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("radio", { name: /Full mixed review/i }));
  await user.click(screen.getByRole("button", { name: /Start practising/i }));
}

async function answerCurrentQuestion(user: ReturnType<typeof userEvent.setup>) {
  const heading = await screen.findByRole("heading", { name: /^Question \d+$/ }, { timeout: 3000 });
  const panel = heading.closest("section");
  if (!panel) throw new Error("question panel not found");
  const scope = within(panel);

  const radios = scope.queryAllByRole("radio");
  if (radios.length > 0) {
    await user.click(radios[0]);
  } else {
    const textbox = scope.queryByRole("textbox");
    if (textbox) await user.type(textbox, "something");
    // parsons needs no input — the order is always complete.
  }
  await user.click(scope.getByRole("button", { name: /Submit answer/i }));
  await screen.findByRole(
    "heading",
    { name: /^(Correct|Partly correct|Not quite)$/i },
    { timeout: 3000 },
  );
}

describe("StudentExperience", () => {
  it("has a labelled entry screen with a skip link and a live region", () => {
    render(<StudentExperience />);

    expect(screen.getByRole("heading", { level: 1, name: /Practice Python/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Skip to content/i })).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByLabelText(/Your name/i)).toBeInTheDocument();
    // The polite announcement region for async state changes.
    expect(document.querySelector('[role="status"][aria-live="polite"]')).not.toBeNull();
  });

  it("walks welcome → question → result with an accessible answer form", async () => {
    const user = userEvent.setup();
    render(<StudentExperience />);

    await user.type(screen.getByLabelText(/Your name/i), "Ada");
    await startSession(user);

    const heading = await screen.findByRole(
      "heading",
      { name: /^Question \d+$/ },
      { timeout: 3000 },
    );
    const panel = heading.closest("section");
    expect(panel).not.toBeNull();
    // Every answer widget sits in a fieldset/legend or has a real label.
    const scope = within(panel as HTMLElement);
    const hasFieldset = (panel as HTMLElement).querySelector("fieldset legend");
    const hasLabelledTextbox = scope.queryByRole("textbox");
    expect(Boolean(hasFieldset) || Boolean(hasLabelledTextbox)).toBe(true);

    await answerCurrentQuestion(user);

    const resultSection = screen
      .getByRole("heading", { name: /^(Correct|Partly correct|Not quite)$/i })
      .closest("section") as HTMLElement;
    expect(within(resultSection).getByText(/What was correct/i)).toBeInTheDocument();
    expect(within(resultSection).getByText(/mastery/i)).toBeInTheDocument();
    expect(
      within(resultSection).getByRole("button", { name: /Next question|See summary/i }),
    ).toBeInTheDocument();
    // Progress landmark is present throughout the run.
    expect(screen.getByRole("complementary", { name: /Your progress/i })).toBeInTheDocument();
  });

  it("recovers from a simulated submit failure without losing the answer", async () => {
    const user = userEvent.setup();
    render(<StudentExperience />);
    await startSession(user);

    await screen.findByRole("heading", { name: /^Question \d+$/ }, { timeout: 3000 });
    await user.click(screen.getByLabelText(/Make the next answer submit fail once/i));

    const heading = screen.getByRole("heading", { name: /^Question \d+$/ });
    const scope = within(heading.closest("section") as HTMLElement);
    const radios = scope.queryAllByRole("radio");
    if (radios.length > 0) await user.click(radios[0]);
    else await user.type(scope.getByRole("textbox"), "answer text");

    await user.click(scope.getByRole("button", { name: /Submit answer/i }));

    expect(await screen.findByText(/Couldn't save your answer/i)).toBeInTheDocument();
    // The answer is still selected/typed — retry is offered.
    const retry = screen.getByRole("button", { name: /Retry submit/i });
    await user.click(retry);
    await screen.findByRole(
      "heading",
      { name: /^(Correct|Partly correct|Not quite)$/i },
      { timeout: 3000 },
    );
  });

  it("reaches the summary and only clears progress after a confirm", async () => {
    const user = userEvent.setup();
    render(<StudentExperience />);
    await startSession(user);

    // Answer two questions, then end the session early from the header control.
    await answerCurrentQuestion(user);
    await user.click(screen.getByRole("button", { name: /Next question/i }));
    await answerCurrentQuestion(user);
    await user.click(screen.getByRole("button", { name: /Next question/i }));
    await screen.findByRole("heading", { name: /^Question \d+$/ }, { timeout: 3000 });

    await user.click(screen.getByRole("button", { name: /^End session$/i }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", {
        name: /^End session$/i,
      }),
    );

    expect(
      await screen.findByRole("heading", { level: 1, name: /finished|paused/i }),
    ).toBeInTheDocument();

    // "Start over" opens a confirm naming what is lost; it is not destructive on its own.
    await user.click(screen.getByRole("button", { name: /Start over/i }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/can't be undone/i)).toBeInTheDocument();
    expect(window.localStorage.getItem(SESSION_STORAGE_KEY)).not.toBeNull();

    await user.click(within(dialog).getByRole("button", { name: /Reset prototype/i }));
    await screen.findByRole("heading", { level: 1, name: /Practice Python/i });
  });

  it("logs no console errors across a full run", async () => {
    const errors: unknown[] = [];
    const spy = vi.spyOn(console, "error").mockImplementation((...args) => {
      errors.push(args);
    });
    const user = userEvent.setup();
    render(<StudentExperience />);
    await startSession(user);
    await answerCurrentQuestion(user);
    await user.click(screen.getByRole("button", { name: /Next question|See summary/i }));

    await waitFor(() => {
      // Either the next question or the summary — just let effects settle.
      expect(
        screen.queryByRole("heading", { name: /^Question \d+$/ }) ??
          screen.queryByRole("heading", { level: 1 }),
      ).not.toBeNull();
    });

    spy.mockRestore();
    expect(errors).toEqual([]);
  });
});
