/**
 * Flow tests for the practice-first prototype (variant G): wrong answer -> rung 1 -> second attempt
 * -> rung 2 simulator -> rung 3 faded completion; the Parsons question; editing code in the simulator
 * and re-running; the next question chosen from the missed topic; and the accessibility promises
 * (live regions, focus, no autoplay).
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BANK, MISCONCEPTIONS, type ParsonsQuestion } from "./mock-data";
import { parsonsSolution } from "./practice-logic";
import { TutorialsPracticeExperience } from "./tutorials-practice-experience";

// A few flows click through a whole set; give a slow machine room.
vi.setConfig({ testTimeout: 30_000 });

type User = ReturnType<typeof userEvent.setup>;

/** The radio whose option text is exactly `text` (the label also holds a letter and a status word). */
const radio = (text: string): HTMLInputElement => {
  const wanted = text.replace(/\s+/g, " ");
  const found = screen.getAllByRole("radio").find((input) => {
    const shown = input.closest("label")?.querySelector(".flex-1")?.textContent ?? "";
    return shown.replace(/\s+/g, " ") === wanted;
  });
  if (!found) throw new Error(`no option "${text}"`);
  return found as HTMLInputElement;
};

async function check(user: User, text: string) {
  await user.click(radio(text));
  await user.click(screen.getByRole("button", { name: /Check answer/i }));
}

const words = (text: string) => text.trim().split(/\s+/).length;

const heading = (n: number) =>
  screen.getByRole("heading", { name: `Question ${n} of ${BANK.length}` });

/** Reorder the ordering question into `target` (line ids) using the Move up buttons. */
async function arrange(user: User, target: string[]) {
  const list = screen.getByRole("list", { name: /Lines of the program/ });
  for (let i = 0; i < target.length; i++) {
    const current = () => Array.from(list.children).map((li) => li.getAttribute("data-line-id"));
    let at = current().indexOf(target[i]);
    while (at > i) {
      const item = list.children[at] as HTMLElement;
      const up = item.querySelector<HTMLButtonElement>('[data-dir="up"]');
      if (!up) throw new Error("no move up button");
      await user.click(up);
      at = current().indexOf(target[i]);
    }
  }
}

/** Miss the first (conditionals) question twice and land on the next one. */
async function missFirstTwice(user: User) {
  await check(user, "good");
  await check(user, "pass good");
}

/** Answer the question showing correctly on the first try (valid while nothing has steered the order). */
async function answerCorrectly(user: User) {
  const title = screen.getByRole("heading", { name: /^Question \d+ of/ }).textContent ?? "";
  const q = BANK[Number(/Question (\d+)/.exec(title)?.[1]) - 1];
  if (q.kind === "choice") {
    const right = q.options.find((o) => o.misconception === null);
    if (!right) throw new Error("no correct option");
    await check(user, right.text);
  } else {
    await arrange(user, parsonsSolution(q));
    await user.click(screen.getByRole("button", { name: /Check order/i }));
  }
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("frame", () => {
  it("renders standalone with the prototype label, console link and mock note", () => {
    render(<TutorialsPracticeExperience />);
    expect(screen.getByText("Design prototype")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Console/i })).toHaveAttribute("href", "/dashboard");
    expect(screen.getByText(/Mock data/)).toBeInTheDocument();
    expect(screen.getByText(/Prototype\./)).toBeInTheDocument();
    expect(heading(1)).toBeInTheDocument();
    // Practice first: no help is on screen until the student answers, and there is no tutorial text.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Show me what happens/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/Worked example/)).not.toBeInTheDocument();
  });

  it("locks the check button until an option is picked", async () => {
    const user = userEvent.setup();
    render(<TutorialsPracticeExperience />);
    expect(screen.getByRole("button", { name: /Check answer/i })).toBeDisabled();
    await user.click(radio("pass"));
    expect(screen.getByRole("button", { name: /Check answer/i })).toBeEnabled();
  });

  it("shows a quiet per-topic strip with one dot per question, described in text", async () => {
    const user = userEvent.setup();
    render(<TutorialsPracticeExperience />);
    const strip = screen.getByRole("list", { name: "Progress by topic" });
    expect(within(strip).getAllByRole("listitem")).toHaveLength(5);
    expect(within(strip).getByText("Conditionals: nothing answered yet")).toBeInTheDocument();
    await check(user, "pass");
    await user.click(screen.getByRole("button", { name: /Next question/ }));
    expect(within(strip).getByText("Conditionals: right")).toBeInTheDocument();
  });
});

describe("rung 1: one line, then one more attempt", () => {
  it("names the misconception, not the answer, and keeps the other options open", async () => {
    const user = userEvent.setup();
    render(<TutorialsPracticeExperience />);
    await check(user, "good");

    const live = screen.getByRole("status", { name: "" });
    expect(live).toHaveAttribute("aria-live", "polite");
    expect(live).toHaveFocus();
    expect(live).toHaveTextContent("Not quite.");
    expect(live).toHaveTextContent(
      "Looks like you expected the elif to run. Check which condition is true first.",
    );
    // Not the answer.
    expect(live).not.toHaveTextContent(/\bpass\b/);
    // Under the ~40 word budget for a state.
    expect(words(live.textContent ?? "")).toBeLessThanOrEqual(40);

    // No help window opened by itself.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    // The wrong option is marked and locked; the others can still be picked.
    expect(radio("good")).toBeDisabled();
    expect(radio("pass")).toBeEnabled();
    // The simulator is offered quietly, not pushed.
    expect(screen.getByRole("button", { name: "Show me what happens" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Next question/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /worked example/ })).not.toBeInTheDocument();
  });

  it("a right answer on the second try counts as recovered", async () => {
    const user = userEvent.setup();
    render(<TutorialsPracticeExperience />);
    await check(user, "good");
    await check(user, "pass");
    expect(screen.getByRole("status", { name: "" })).toHaveTextContent(
      "Correct, on the second try.",
    );
    expect(radio("pass")).toBeInTheDocument();
    const strip = screen.getByRole("list", { name: "Progress by topic" });
    expect(within(strip).getByText("Conditionals: right on the second try")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Next question/ })).toBeInTheDocument();
  });

  it("a right answer on the first try goes straight on, with the simulator still on request", async () => {
    const user = userEvent.setup();
    render(<TutorialsPracticeExperience />);
    await check(user, "pass");
    expect(screen.getByRole("status", { name: "" })).toHaveTextContent("Correct.");
    await user.click(screen.getByRole("button", { name: "Show me what happens" }));
    const dialog = await screen.findByRole("dialog", { name: "What the code does" });
    // A correct answer matches the real output.
    expect(within(dialog).getByText("matches", { exact: false })).toBeInTheDocument();
  });
});

describe("rung 2: the simulator", () => {
  it("opens after the second miss, with code central and the answer pinned next to the output", async () => {
    const user = userEvent.setup();
    render(<TutorialsPracticeExperience />);
    await missFirstTwice(user);

    const live = screen.getByRole("status", { name: "" });
    expect(live).toHaveTextContent("Not this time.");
    expect(live).toHaveTextContent("The correct answer is marked.");
    expect(radio("pass")).toBeInTheDocument();
    // The simulator is now the primary action; the next question is also there, but secondary.
    const trigger = screen.getByRole("button", { name: "Show me what happens" });
    expect(screen.getByRole("button", { name: /Next question/ })).toBeInTheDocument();

    await user.click(trigger);
    const dialog = await screen.findByRole("dialog", { name: "What the code does" });
    expect(dialog).toHaveAttribute("data-side", "bottom"); // phone-first: a bottom sheet by default

    // Pinned comparison: the chosen (wrong) answer beside what it really prints.
    expect(within(dialog).getByText("Your answer")).toBeInTheDocument();
    expect(within(dialog).getByText("Actual output")).toBeInTheDocument();
    expect(within(dialog).getByText("does not match")).toBeInTheDocument();
    const pre = within(dialog)
      .getAllByText(/pass/)
      .map((el) => el.tagName);
    expect(pre.length).toBeGreaterThan(0);

    // Source stays central: numbered lines, the first one marked as the line that runs first.
    const codeRegion = within(dialog).getByRole("region", { name: "Code" });
    expect(within(codeRegion).getAllByRole("listitem")).toHaveLength(7);
    expect(codeRegion.querySelector('[aria-current="step"]')).toHaveTextContent("score = 85");
    expect(within(dialog).getByText("Line 1 runs first.")).toBeInTheDocument();

    // Step: the marked line advances, the variable appears, and the caption says what happened.
    await user.click(within(dialog).getByRole("button", { name: /^Step$/ }));
    expect(codeRegion.querySelector('[aria-current="step"]')).toHaveTextContent("if score >= 60:");
    expect(within(dialog).getByRole("term")).toHaveTextContent("score");
    expect(within(dialog).getByRole("definition")).toHaveTextContent("85");
    const caption = within(dialog).getByText(/is now 85/);
    expect(caption.closest('[aria-live="polite"]')).not.toBeNull();

    await user.click(within(dialog).getByRole("button", { name: /^Step$/ }));
    expect(within(dialog).getByText(/is True: run this block/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: /^Step$/ }));
    expect(within(dialog).getByText(/Printed: pass/)).toBeInTheDocument();

    // Back and reset work, and nothing advanced on its own.
    await user.click(within(dialog).getByRole("button", { name: "Back" }));
    expect(within(dialog).getByText("3 / 4")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "To the end" }));
    expect(within(dialog).getByText("The program finished.", { exact: false })).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Reset" }));
    expect(within(dialog).getByText("1 / 4")).toBeInTheDocument();
  });

  it("is also offered by a click after the FIRST miss, and closing returns focus to the button", async () => {
    const user = userEvent.setup();
    render(<TutorialsPracticeExperience />);
    await check(user, "pass good");
    const trigger = screen.getByRole("button", { name: "Show me what happens" });
    await user.click(trigger);
    await screen.findByRole("dialog", { name: "What the code does" });
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
    // The student is still on the same question with one attempt left.
    expect(radio("pass")).toBeEnabled();
  });

  it("uses a side panel on wide screens", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query.includes("min-width"),
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
    const user = userEvent.setup();
    render(<TutorialsPracticeExperience />);
    await check(user, "pass good");
    await user.click(screen.getByRole("button", { name: "Show me what happens" }));
    expect(await screen.findByRole("dialog", { name: "What the code does" })).toHaveAttribute(
      "data-side",
      "right",
    );
  });

  it("simulates the never-ending loop and ends with the plain-words step cap message", async () => {
    const user = userEvent.setup();
    render(<TutorialsPracticeExperience />);
    await check(user, "pass");
    await user.click(screen.getByRole("button", { name: /Next question/ }));
    expect(heading(2)).toBeInTheDocument();
    await check(user, "0 1 2");
    await user.click(screen.getByRole("button", { name: "Show me what happens" }));
    const dialog = await screen.findByRole("dialog", { name: "What the code does" });
    await user.click(within(dialog).getByRole("button", { name: "To the end" }));
    const messages = within(dialog).getAllByText(
      "Stopped after 300 steps. This loop may never end.",
    );
    expect(messages.length).toBeGreaterThan(0);
    // The printed output is condensed instead of 300 lines of zeros.
    expect(within(dialog).getAllByText(/0 \(x\d+\)/).length).toBeGreaterThan(0);
  });

  it("try it yourself: edit the code, run it, and step through the new version", async () => {
    const user = userEvent.setup();
    render(<TutorialsPracticeExperience />);
    await check(user, "good");
    await user.click(screen.getByRole("button", { name: "Show me what happens" }));
    const dialog = await screen.findByRole("dialog", { name: "What the code does" });
    expect(within(dialog).getByText("does not match")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: /Try it yourself/ }));
    const editor = within(dialog).getByRole("textbox", { name: /Python code/ });
    expect(editor).toHaveValue(BANK[0].kind === "choice" ? BANK[0].code : "");

    // Modify the condition so the elif becomes the branch that runs.
    await user.clear(editor);
    await user.type(
      editor,
      'score = 85{Enter}if score >= 90:{Enter}    print("pass"){Enter}elif score >= 80:{Enter}    print("good"){Enter}',
    );
    await user.click(within(dialog).getByRole("button", { name: /^Run$/ }));

    // Back in watch mode on the NEW code; the pinned answer ("good") now matches what it prints.
    const codeRegion = within(dialog).getByRole("region", { name: "Code" });
    expect(codeRegion).toHaveTextContent("if score >= 90:");
    expect(within(dialog).getByText("matches")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "To the end" }));
    expect(within(dialog).getByText("Printed: good", { exact: false })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Restore original" })).toBeInTheDocument();

    // Restore the original snippet.
    await user.click(within(dialog).getByRole("button", { name: "Restore original" }));
    expect(codeRegion).toHaveTextContent("if score >= 60:");
    expect(within(dialog).getByText("does not match")).toBeInTheDocument();
  });

  it("try it yourself: unsupported and invalid code get a plain-words message, never a crash", async () => {
    const user = userEvent.setup();
    render(<TutorialsPracticeExperience />);
    await check(user, "good");
    await user.click(screen.getByRole("button", { name: "Show me what happens" }));
    const dialog = await screen.findByRole("dialog", { name: "What the code does" });
    await user.click(within(dialog).getByRole("button", { name: /Try it yourself/ }));
    const editor = within(dialog).getByRole("textbox", { name: /Python code/ });

    await user.clear(editor);
    await user.type(editor, "import os");
    await user.click(within(dialog).getByRole("button", { name: /^Run$/ }));
    expect(
      within(dialog).getByText("This mini-runner doesn't support import yet."),
    ).toBeInTheDocument();

    await user.clear(editor);
    await user.type(editor, "if x{Enter}    y = 1");
    await user.click(within(dialog).getByRole("button", { name: /^Run$/ }));
    expect(within(dialog).getByText(/SyntaxError: invalid syntax \(line 1\)/)).toBeInTheDocument();

    // A runtime error is simulated, not refused: it becomes a step with the error and a plain line.
    await user.clear(editor);
    await user.type(editor, "a = [[1, 2]{Enter}print(a[[5])");
    await user.click(within(dialog).getByRole("button", { name: /^Run$/ }));
    await user.click(within(dialog).getByRole("button", { name: "To the end" }));
    expect(
      within(dialog).getAllByText("IndexError: list index out of range").length,
    ).toBeGreaterThan(0);
    expect(within(dialog).getByText(/The list has 2 items/)).toBeInTheDocument();
  });

  it("shows two names holding one list as the same list, so aliasing is visible", async () => {
    const user = userEvent.setup();
    render(<TutorialsPracticeExperience />);
    // Reach the aliasing question (9th) by answering everything before it correctly.
    for (let n = 1; n <= 8; n++) {
      await answerCorrectly(user);
      await user.click(screen.getByRole("button", { name: /Next question|See summary/ }));
    }
    expect(heading(9)).toBeInTheDocument();
    await check(user, "[1, 2, 3]");
    await user.click(screen.getByRole("button", { name: "Show me what happens" }));
    const dialog = await screen.findByRole("dialog", { name: "What the code does" });
    await user.click(within(dialog).getByRole("button", { name: "To the end" }));
    expect(within(dialog).getAllByText("same list #1")).toHaveLength(2);
  });
});

describe("rung 3: worked example, then a faded one", () => {
  it("full ladder: two misses -> simulator -> worked example -> faded completion -> steered next question", async () => {
    const user = userEvent.setup();
    render(<TutorialsPracticeExperience />);
    await missFirstTwice(user);

    await user.click(screen.getByRole("button", { name: "Show me what happens" }));
    const dialog = await screen.findByRole("dialog", { name: "What the code does" });
    // Rung 3 is offered from inside the simulator...
    await user.click(
      within(dialog).getByRole("button", { name: "Explain it like a worked example" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    // ...and lands on the worked example, with focus moved to its heading.
    const worked = screen.getByRole("heading", { name: "Worked example" });
    await waitFor(() => expect(worked).toHaveFocus());
    const misconception = MISCONCEPTIONS.all_branches; // the LAST wrong pick was "pass\ngood"
    expect(screen.getByRole("figure", { name: "Worked example" })).toHaveTextContent('print("A")');
    expect(
      screen.getByText(/Only the first true branch runs|only the first true branch runs/),
    ).toBeInTheDocument();
    expect(screen.getByText("Output")).toBeInTheDocument();

    // The faded version: same idea, last line blank. A wrong line gets one short line of feedback.
    expect(screen.getByText(/Now you finish one/)).toBeInTheDocument();
    const input = screen.getByRole("textbox", { name: "The last line of the program" });
    await user.type(input, 'print("B")');
    await user.click(screen.getByRole("button", { name: "Check" }));
    expect(screen.getByText("That prints B. The goal is A.")).toBeInTheDocument();

    // Any correct line passes, not only the one in the answer key.
    await user.clear(input);
    await user.type(input, "print(label)");
    await user.click(screen.getByRole("button", { name: "Check" }));
    expect(screen.getByText("That prints A.")).toBeInTheDocument();
    expect(misconception.faded.answer).toBe("print(label)");

    // Try another: two misses on conditionals steer the next question to conditionals (the Parsons one).
    await user.click(screen.getByRole("button", { name: "Try another" }));
    expect(heading(2)).toBeInTheDocument();
    expect(screen.getAllByText("Conditionals")).toHaveLength(2); // the strip and the question
    expect(screen.getByText(/More on conditionals/)).toBeInTheDocument();
    expect(
      screen.getByText("Put the lines in order so the program prints warm."),
    ).toBeInTheDocument();
    expect(heading(2)).toHaveFocus();
  });

  it("rung 3 also appears on the page once the simulator has been seen, and the line can be shown", async () => {
    const user = userEvent.setup();
    render(<TutorialsPracticeExperience />);
    await check(user, "good");
    // Not before the simulator was opened.
    expect(
      screen.queryByRole("button", { name: "Explain it like a worked example" }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show me what happens" }));
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Explain it like a worked example" }));
    // This student picked "good": the elif misconception.
    expect(screen.getByText(/The first true one wins/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show the line" }));
    expect(screen.getByRole("textbox", { name: "The last line of the program" })).toHaveValue(
      "print(grade)",
    );
    expect(screen.getByText("The last line was shown above.")).toBeInTheDocument();
    // "Try another" is never gated.
    await user.click(screen.getByRole("button", { name: "Try another" }));
    expect(heading(2)).toBeInTheDocument();
  });

  it("an indented blank (inside a loop) is part of the check", async () => {
    const user = userEvent.setup();
    render(<TutorialsPracticeExperience />);
    await answerCorrectly(user);
    await user.click(screen.getByRole("button", { name: /Next question/ }));
    await check(user, "0 1 2");
    await user.click(screen.getByRole("button", { name: "Show me what happens" }));
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Explain it like a worked example" }));
    const input = screen.getByRole("textbox", { name: "The last line of the program" });
    await user.type(input, "print(i)");
    await user.click(screen.getByRole("button", { name: "Check" }));
    expect(screen.getByText(/That never stops/)).toBeInTheDocument();
    await user.clear(input);
    await user.type(input, "i = i + 1{Enter}");
    expect(screen.getByText("That prints x, x.")).toBeInTheDocument();
  });
});

describe("Parsons question", () => {
  async function reachParsons(user: User) {
    await missFirstTwice(user);
    await user.click(screen.getByRole("button", { name: /Next question/ }));
    expect(heading(2)).toBeInTheDocument();
  }

  it("orders lines with move buttons, keeps focus on the pressed button, and announces the move", async () => {
    const user = userEvent.setup();
    render(<TutorialsPracticeExperience />);
    await reachParsons(user);

    const list = screen.getByRole("list", { name: /Lines of the program/ });
    const first = list.children[0] as HTMLElement;
    const id = first.getAttribute("data-line-id");
    const down = within(first).getByRole("button", { name: /^Move down:/ });
    expect(within(first).getByRole("button", { name: /^Move up:/ })).toBeDisabled();
    await user.click(down);
    const moved = list.querySelector(`[data-line-id="${id}"]`) as HTMLElement;
    expect(list.children[1]).toBe(moved);
    await waitFor(() =>
      expect(within(moved).getByRole("button", { name: /^Move down:/ })).toHaveFocus(),
    );
    expect(screen.getByText("Moved to position 2 of 7.")).toBeInTheDocument();
  });

  it("wrong order -> hint -> fix it -> correct on the second try", async () => {
    const user = userEvent.setup();
    render(<TutorialsPracticeExperience />);
    await reachParsons(user);

    await user.click(screen.getByRole("button", { name: /Check order/i }));
    const live = screen.getByRole("status", { name: "" });
    expect(live).toHaveTextContent("Not quite.");
    expect(live).toHaveTextContent("Python runs lines from top to bottom");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    const question = BANK.find((q): q is ParsonsQuestion => q.id === "cond-parsons");
    if (!question) throw new Error("missing question");
    await arrange(user, parsonsSolution(question));
    await user.click(screen.getByRole("button", { name: /Check order/i }));
    expect(screen.getByRole("status", { name: "" })).toHaveTextContent(
      "Correct, on the second try.",
    );
    // Locked once finished.
    for (const button of screen.getAllByRole("button", { name: /^Move (up|down):/ })) {
      expect(button).toBeDisabled();
    }
  });

  it("two wrong orders show the right order, and the simulator runs the student's own ordering", async () => {
    const user = userEvent.setup();
    render(<TutorialsPracticeExperience />);
    await reachParsons(user);

    await user.click(screen.getByRole("button", { name: /Check order/i }));
    await user.click(screen.getByRole("button", { name: /Check order/i }));
    const live = screen.getByRole("status", { name: "" });
    expect(live).toHaveTextContent("Not this time.");
    expect(live).toHaveTextContent("The right order is shown.");
    const list = screen.getByRole("list", { name: /Lines of the program/ });
    expect(Array.from(list.children).map((li) => li.getAttribute("data-line-id"))).toEqual([
      "l0",
      "l1",
      "l2",
      "l3",
      "l4",
      "l5",
      "l6",
    ]);

    await user.click(screen.getByRole("button", { name: "Show me what happens" }));
    const dialog = await screen.findByRole("dialog", { name: "What the code does" });
    expect(within(dialog).getByText("You wanted")).toBeInTheDocument();
    expect(within(dialog).getByText("Your order prints")).toBeInTheDocument();
    // The student's start order begins with `elif`, which is not valid Python: an error, not a crash.
    expect(within(dialog).getByRole("region", { name: "Code" })).toHaveTextContent(
      "elif temp > 15:",
    );
    expect(within(dialog).getByText("does not match")).toBeInTheDocument();
    expect(within(dialog).getByText("SyntaxError: invalid syntax")).toBeInTheDocument();
    expect(within(dialog).getByText(/Python can.t read this line/)).toBeInTheDocument();
    // The failing line is marked, and there is nothing to step through.
    expect(
      within(dialog).getByRole("region", { name: "Code" }).querySelector("[aria-current=step]"),
    ).toHaveTextContent("elif temp > 15:");
    expect(within(dialog).getByRole("button", { name: /^Step$/ })).toBeDisabled();
  });
});

describe("finishing a set", () => {
  it("summarises the outcome after the last question", async () => {
    const user = userEvent.setup();
    render(<TutorialsPracticeExperience />);
    for (let n = 1; n <= BANK.length; n++) {
      await answerCorrectly(user);
      await user.click(
        screen.getByRole("button", { name: n === BANK.length ? "See summary" : "Next question" }),
      );
    }
    const done = screen.getByRole("heading", { name: "Set finished" });
    expect(done).toHaveFocus();
    expect(
      screen.getByText(/10 right first time, 0 on the second try, 0 missed\./),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Start over" }));
    expect(heading(1)).toHaveFocus();
    expect(
      within(screen.getByRole("list", { name: "Progress by topic" })).getByText(
        "Lists: nothing answered yet",
      ),
    ).toBeInTheDocument();
  });
});
