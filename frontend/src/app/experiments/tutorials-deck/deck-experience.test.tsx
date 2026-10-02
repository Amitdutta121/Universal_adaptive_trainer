/**
 * Flow tests for the trace-lesson deck (variant F): the copy budget, the recorded data, topic
 * switching, predict-first (right, wrong, "Just show me"), stepping every trace to the end and
 * comparing with what Python printed, Back / Reset, the faded completions (right and wrong), the
 * skip button, the keyboard, and that "done" persists.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DONE_KEY } from "./components/use-done-topics";
import { DeckExperience } from "./deck-experience";
import { EXAMPLES, FADED, TOPICS, TRACES, traceById } from "./mock-data";

type User = ReturnType<typeof userEvent.setup>;

const words = (text: string) => text.trim().split(/\s+/).length;

beforeEach(() => {
  window.localStorage.clear();
});
afterEach(() => {
  vi.restoreAllMocks();
});

// ---- helpers ---------------------------------------------------------------------------------

const topicButton = (label: string) => screen.getByRole("button", { name: new RegExp(`^${label}`) });
const cardButton = (n: number) => screen.getByRole("button", { name: `Go to card ${n} of 5` });
const stepButton = () => screen.getByRole("button", { name: /^Step$/ });

async function openTopic(user: User, label: string) {
  await user.click(topicButton(label));
}

async function openSim(user: User, label: string) {
  await openTopic(user, label);
  await user.click(cardButton(3));
}

async function predictOff(user: User) {
  await user.click(screen.getByRole("button", { name: /Predict first: on/ }));
}

async function stepTimes(user: User, times: number) {
  for (let count = 0; count < times; count += 1) await user.click(stepButton());
}

async function stepToEnd(user: User) {
  while (!(stepButton() as HTMLButtonElement).disabled) await user.click(stepButton());
}

const outputLines = () =>
  within(screen.getByRole("group", { name: "Program output" }))
    .queryAllByTestId("output-line")
    .map((node) => node.textContent);

const currentLine = () => document.querySelector("li[aria-current=step]")?.textContent ?? "";
const prediction = () => screen.queryByRole("group", { name: /^Prediction:/ });

// ---- data ------------------------------------------------------------------------------------

describe("the deck content", () => {
  it("has exactly five topics of five cards: idea, idea, simulator, worked example, faded check", () => {
    expect(TOPICS.map((topic) => topic.label)).toEqual([
      "Conditionals",
      "While loops",
      "Functions",
      "Lists",
      "Recursion",
    ]);
    for (const topic of TOPICS) {
      expect(topic.cards.map((card) => card.kind), topic.id).toEqual([
        "idea",
        "idea",
        "sim",
        "idea",
        "faded",
      ]);
    }
  });

  it("keeps every headline to 8 words and every body to 20", () => {
    for (const topic of TOPICS) {
      for (const card of topic.cards) {
        expect(words(card.headline), card.id).toBeLessThanOrEqual(8);
        expect(words(card.body), card.id).toBeLessThanOrEqual(20);
      }
    }
  });

  it("points every card at recorded data that exists", () => {
    for (const topic of TOPICS) {
      for (const card of topic.cards) {
        if (card.kind === "idea" && card.example) expect(EXAMPLES[card.example], card.id).toBeDefined();
        if (card.kind === "sim") for (const id of card.traces) expect(TRACES[id], id).toBeDefined();
      }
    }
  });

  it("was recorded from real runs: each trace ends on the output an untraced run printed", () => {
    for (const trace of Object.values(TRACES)) {
      const last = trace.steps.at(-1);
      expect(last?.output, trace.id).toEqual(trace.expectedOutput);
      expect(trace.steps[0].line, trace.id).toBeNull();
      for (const step of trace.steps) {
        expect(words(step.caption), `${trace.id}: ${step.caption}`).toBeLessThanOrEqual(16);
      }
      for (const p of trace.predictions) {
        expect(p.answer).toBeGreaterThanOrEqual(0);
        expect(p.answer).toBeLessThan(p.choices.length);
        expect(p.atStep).toBeGreaterThanOrEqual(1);
        expect(p.atStep).toBeLessThan(trace.steps.length);
      }
    }
    expect(TRACES["while-stuck"].endless).toBe(true);
    expect(TRACES["while-stuck"].steps.at(-1)?.kind).toBe("cap");
    // Spot checks against what Python is known to print for these snippets.
    expect(TRACES.cond.expectedOutput).toEqual(["pass"]);
    expect(TRACES["fn-print"].expectedOutput).toEqual(["5", "None"]);
    expect(TRACES["list-alias"].expectedOutput).toEqual(["10", "30", "[10, 20, 30, 40]"]);
    expect(TRACES["rec-fact"].expectedOutput).toEqual(["6"]);
  });

  it("recorded the call stack growing to depth 4 and shared lists by id()", () => {
    const depths = TRACES["rec-fact"].steps.map((step) => step.frames.length);
    expect(Math.max(...depths)).toBe(4);
    expect(depths.at(-1)).toBe(1);
    const shared = TRACES["list-alias"].steps.find((step) => step.heap?.some((o) => o.names.length === 2));
    expect(shared?.heap?.[0]?.names).toEqual(["a", "b"]);
  });
});

// ---- shell and topic switching ---------------------------------------------------------------

describe("DeckExperience", () => {
  it("renders standalone with the prototype label, console link and mock note", () => {
    render(<DeckExperience />);
    expect(screen.getByText("Design prototype")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Console/i })).toHaveAttribute("href", "/dashboard");
    expect(screen.getByText(/Mock data/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "if picks one path" })).toBeInTheDocument();
  });

  it("switches topic from the picker and remembers where each deck was", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);

    await user.click(cardButton(2));
    expect(screen.getByRole("heading", { level: 2, name: "The first true test wins" })).toBeInTheDocument();

    await openTopic(user, "While loops");
    expect(screen.getByRole("heading", { level: 2, name: TOPICS[1].cards[0].headline })).toBeInTheDocument();
    expect(topicButton("While loops")).toHaveAttribute("aria-current", "true");

    await openTopic(user, "Conditionals");
    expect(screen.getByRole("heading", { level: 2, name: "The first true test wins" })).toBeInTheDocument();
  });

  it("switches topic from the phone select too", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await user.selectOptions(screen.getByLabelText("Topic"), "Recursion");
    expect(screen.getByRole("heading", { level: 2, name: "A function can call itself" })).toBeInTheDocument();
  });

  it("shows the progress of a deck and jumps between cards", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    expect(cardButton(1)).toHaveAttribute("aria-current", "step");
    await user.click(screen.getByRole("button", { name: /^Next$/ }));
    expect(cardButton(2)).toHaveAttribute("aria-current", "step");
    await user.click(screen.getByRole("button", { name: /^Back$/ }));
    expect(cardButton(1)).toHaveAttribute("aria-current", "step");
  });
});

// ---- skip ------------------------------------------------------------------------------------

describe("skip to the check", () => {
  it("is offered on the first card of every deck and jumps to the faded card", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    for (const topic of TOPICS) {
      await openTopic(user, topic.label);
      await user.click(cardButton(1));
      await user.click(screen.getByRole("button", { name: "I know this, skip to the check" }));
      expect(cardButton(5)).toHaveAttribute("aria-current", "step");
      expect(screen.getByRole("heading", { level: 2, name: topic.cards[4].headline })).toBeInTheDocument();
    }
  });

  it("is not on the other cards", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await user.click(cardButton(2));
    expect(screen.queryByRole("button", { name: /skip to the check/ })).not.toBeInTheDocument();
  });
});

// ---- predict first ---------------------------------------------------------------------------

describe("predict first", () => {
  it("asks before the first step and reveals it on a right answer", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await openSim(user, "Conditionals");

    expect(screen.getByText("Nothing has run yet. Press Step.")).toBeInTheDocument();
    await user.click(stepButton());
    const question = within(prediction() as HTMLElement);
    expect(screen.getByText("Which grade will print?")).toBeInTheDocument();
    expect(stepButton()).toBeDisabled();

    await user.click(question.getByRole("button", { name: "pass" }));
    expect(prediction()).not.toBeInTheDocument();
    expect(screen.getByText("Right.")).toBeInTheDocument();
    expect(screen.getByText("mark is 95.")).toBeInTheDocument();
    expect(currentLine()).toContain("mark = 95");
  });

  it("explains a wrong answer with the real one, then goes on", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await openSim(user, "Conditionals");

    await user.click(stepButton());
    await user.click(within(prediction() as HTMLElement).getByRole("button", { name: "distinction" }));
    expect(screen.getByText("Not quite: it is pass.")).toBeInTheDocument();
    expect(screen.getByText(/The first true test wins/)).toBeInTheDocument();
    expect(screen.getByText("mark is 95.")).toBeInTheDocument();
  });

  it("asks once more at the key moment, and the branch is greyed out on reveal", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await openSim(user, "Conditionals");

    await user.click(stepButton());
    await user.click(within(prediction() as HTMLElement).getByRole("button", { name: "pass" }));
    await user.click(stepButton());
    expect(screen.getByText("The if test is True. Does Python test the elif next?")).toBeInTheDocument();
    await user.click(within(prediction() as HTMLElement).getByRole("button", { name: "No, it skips it" }));

    expect(screen.getAllByText("Right.").length).toBeGreaterThan(0);
    expect(document.querySelectorAll('[data-state="skipped"]')).toHaveLength(2);
    expect(document.querySelectorAll('[data-state="taken"]')).toHaveLength(1);
    expect(document.querySelectorAll('[data-dim="true"]').length).toBeGreaterThan(0);
    // The elif line is on screen but greyed out.
    expect(screen.getByText(/elif/, { selector: "li[data-dim=true] *" })).toBeInTheDocument();
  });

  it('"Just show me" turns prediction off for good, including the key moment', async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await openSim(user, "Conditionals");

    await user.click(stepButton());
    await user.click(screen.getByRole("button", { name: "Just show me" }));
    expect(prediction()).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Predict first: off" })).toBeInTheDocument();
    expect(screen.getByText("mark is 95.")).toBeInTheDocument();

    await user.click(stepButton());
    expect(prediction()).not.toBeInTheDocument();
    expect(screen.getByText("mark >= 60 is True: take this branch and skip the rest.")).toBeInTheDocument();
  });

  it("can be switched on again, and is shared between decks", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await openSim(user, "Conditionals");
    await predictOff(user);

    await openSim(user, "While loops");
    expect(screen.getByRole("button", { name: "Predict first: off" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Predict first: off" }));
    await user.click(stepButton());
    expect(screen.getByText("What will this print?")).toBeInTheDocument();
  });

  it("asks at the key moment of a stuck loop and shows the cap in plain words", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await openSim(user, "While loops");
    await user.click(screen.getByRole("button", { name: "Stuck loop" }));

    await user.click(stepButton());
    await user.click(within(prediction() as HTMLElement).getByRole("button", { name: "Forever" }));
    await stepTimes(user, 2);
    await user.click(stepButton());
    expect(
      screen.getByText("The body ran once. count is still 0. Is the test True again?"),
    ).toBeInTheDocument();
    await user.click(
      within(prediction() as HTMLElement).getByRole("button", { name: "Yes, nothing changed count" }),
    );
    await stepToEnd(user);
    expect(screen.getByText(/this would go on forever/)).toBeInTheDocument();
    expect(screen.getByText("and on, forever")).toBeInTheDocument();
  });
});

// ---- stepping every trace to the end ---------------------------------------------------------

const SIMS = TOPICS.flatMap((topic) =>
  topic.cards.flatMap((card) =>
    card.kind === "sim" ? card.traces.map((id) => ({ topic: topic.label, id })) : [],
  ),
);

describe("stepping to the end", () => {
  it.each(SIMS)("$topic / $id prints what Python printed", async ({ topic, id }) => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await openSim(user, topic);
    const trace = traceById(id);
    const variants = TOPICS.find((t) => t.label === topic)?.cards[2];
    if (variants?.kind === "sim" && variants.traces.length > 1) {
      await user.click(screen.getByRole("button", { name: trace.label }));
    }
    await predictOff(user);

    expect(outputLines()).toEqual([]);
    await stepToEnd(user);

    expect(outputLines()).toEqual(trace.expectedOutput);
    expect(screen.getByText(`step ${trace.steps.length - 1} / ${trace.steps.length - 1}`)).toBeInTheDocument();
    expect(screen.getByText(trace.takeaway)).toBeInTheDocument();
  });
});

// ---- the topic-specific views ----------------------------------------------------------------

describe("the simulator views", () => {
  it("functions: the call jumps into add, shows its locals, then the value comes back", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await openSim(user, "Functions");
    await predictOff(user);

    await stepTimes(user, 2);
    expect(currentLine()).toContain("def add");
    const stack = within(screen.getByRole("heading", { name: "Call stack" }).closest("section") as HTMLElement);
    expect(stack.getByText("add(2, 3)")).toBeInTheDocument();
    expect(stack.getByText("global")).toBeInTheDocument();

    await stepTimes(user, 2);
    expect(stack.getByText("returns 5")).toBeInTheDocument();
    await user.click(stepButton());
    expect(screen.getByText("5 comes back: result is 5.")).toBeInTheDocument();
    expect(stack.queryByText("add(2, 3)")).not.toBeInTheDocument();
  });

  it("functions: a function that only prints gives back None", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await openSim(user, "Functions");
    await user.click(screen.getByRole("button", { name: "Only prints" }));
    await predictOff(user);
    await stepToEnd(user);
    expect(screen.getAllByText(/None/).length).toBeGreaterThan(0);
    expect(outputLines()).toEqual(["5", "None"]);
  });

  it("lists: two names point at one list and both grow", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await openSim(user, "Lists");
    await predictOff(user);

    await stepTimes(user, 3);
    expect(document.querySelector('[data-focused="true"]')?.textContent).toContain("30");
    await stepTimes(user, 1);
    expect(screen.getByText("a and b are two names for the same list.")).toBeInTheDocument();
    await user.click(stepButton());
    expect(screen.getByText("append adds 40. a and b are one list: both grow.")).toBeInTheDocument();
    const memory = within(screen.getByRole("heading", { name: "Memory" }).closest("section") as HTMLElement);
    expect(memory.getAllByRole("listitem", { name: /List 1, named a and b/ })).toHaveLength(1);
    expect(memory.getByText("40")).toBeInTheDocument();
  });

  it("recursion: the stack grows to three factorial frames and then unwinds", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await openSim(user, "Recursion");
    await predictOff(user);

    const stack = () =>
      within(screen.getByRole("heading", { name: "Call stack" }).closest("section") as HTMLElement);
    await stepTimes(user, 7);
    for (const label of ["factorial(3)", "factorial(2)", "factorial(1)", "global"]) {
      expect(stack().getByText(label)).toBeInTheDocument();
    }
    await user.click(stepButton());
    expect(stack().getByText("returns 1")).toBeInTheDocument();
    await stepToEnd(user);
    expect(stack().queryByText("factorial(3)")).not.toBeInTheDocument();
    expect(outputLines()).toEqual(["6"]);
  });

  it("while: the test result is logged on every pass", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await openSim(user, "While loops");
    await predictOff(user);
    await stepToEnd(user);
    const chips = within(screen.getByRole("list", { name: "Results so far" })).getAllByRole("listitem");
    expect(chips.map((chip) => chip.textContent)).toEqual([
      "1: True",
      "2: True",
      "3: True",
      "4: False",
    ]);
  });
});

// ---- back / reset ----------------------------------------------------------------------------

describe("Back and Reset", () => {
  it("Back undoes a step (output shrinks) and Reset starts over", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await openSim(user, "While loops");
    await predictOff(user);

    expect(screen.getAllByRole("button", { name: "Back" })[0]).toBeDisabled();
    await stepTimes(user, 3);
    expect(outputLines()).toEqual(["3"]);
    const backButtons = screen.getAllByRole("button", { name: /^Back$/ });
    await user.click(backButtons[0]);
    expect(outputLines()).toEqual([]);
    expect(screen.getByText("step 2 / 11")).toBeInTheDocument();

    await stepTimes(user, 4);
    await user.click(screen.getByRole("button", { name: "Reset" }));
    expect(screen.getByText("step 0 / 11")).toBeInTheDocument();
    expect(outputLines()).toEqual([]);
    expect(screen.getByText("Nothing has run yet. Press Step.")).toBeInTheDocument();
  });

  it("Reset makes the predictions ask again", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await openSim(user, "Conditionals");
    await user.click(stepButton());
    await user.click(within(prediction() as HTMLElement).getByRole("button", { name: "pass" }));
    await user.click(screen.getByRole("button", { name: "Reset" }));
    await user.click(stepButton());
    expect(prediction()).toBeInTheDocument();
  });
});

// ---- keyboard --------------------------------------------------------------------------------

describe("keyboard", () => {
  it("Space and the right arrow step the trace, the left arrow goes back", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await openSim(user, "While loops");
    await predictOff(user);
    await user.click(document.body);

    await user.keyboard(" ");
    expect(screen.getByText("step 1 / 11")).toBeInTheDocument();
    await user.keyboard("{ArrowRight}{ArrowRight}");
    expect(screen.getByText("step 3 / 11")).toBeInTheDocument();
    expect(outputLines()).toEqual(["3"]);
    await user.keyboard("{ArrowLeft}");
    expect(screen.getByText("step 2 / 11")).toBeInTheDocument();
    expect(outputLines()).toEqual([]);
  });

  it("the arrow keys page the cards where there is no simulator", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await user.keyboard("{ArrowRight}");
    expect(cardButton(2)).toHaveAttribute("aria-current", "step");
    await user.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(cardButton(1)).toHaveAttribute("aria-current", "step");
  });

  it("the arrow keys stay with a text field", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await openTopic(user, "Lists");
    await user.click(cardButton(5));
    await user.type(screen.getByLabelText("print(a) shows:"), "[[1{ArrowLeft}{ArrowRight}");
    expect(cardButton(5)).toHaveAttribute("aria-current", "step");
  });
});

// ---- faded completions -----------------------------------------------------------------------

describe("faded completion", () => {
  it("conditionals: a wrong pick gets a one-line reason, the right one finishes the deck", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await user.click(cardButton(5));

    await user.click(screen.getByRole("button", { name: "distinction" }));
    expect(screen.getByText("Not quite.")).toBeInTheDocument();
    expect(screen.getByText("65 fails >= 90, so the first branch is skipped.")).toBeInTheDocument();
    expect(window.localStorage.getItem(DONE_KEY)).toBeNull();

    await user.click(screen.getByRole("button", { name: "pass" }));
    expect(screen.getByText("Right.")).toBeInTheDocument();
    expect(FADED.cond.output).toEqual(["pass"]);
    expect(topicButton("Conditionals")).toHaveTextContent("Conditionals");
    expect(within(topicButton("Conditionals")).getByText(/done/)).toBeInTheDocument();
  });

  it("while: the real result of the chosen line is shown", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await openTopic(user, "While loops");
    await user.click(cardButton(5));

    await user.click(screen.getByRole("button", { name: "i = 1" }));
    expect(screen.getByText(/it never stops/)).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Code with a missing part" })).toHaveTextContent("i = 1");
    await user.click(screen.getByRole("button", { name: "i = i + 1" }));
    expect(screen.getByText("Result: prints 6 and stops.")).toBeInTheDocument();
  });

  it("functions: shuffled lines, a wrong order shows Python's real error, the right order passes", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await openTopic(user, "Functions");
    await user.click(cardButton(5));

    const line = (index: number) =>
      screen.getByRole("button", { name: FADED.fn.lines[index].trim() });
    for (const index of [3, 2, 1, 0]) await user.click(line(index));
    expect(screen.getByText(/Not yet\./)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(FADED.fn.orders["3,2,1,0"].text.slice(0, 20)))).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Start over" }));
    for (const index of [0, 1, 2, 3]) await user.click(line(index));
    expect(screen.getByText("Right.")).toBeInTheDocument();
    expect(screen.getByText(/It prints 15\./)).toBeInTheDocument();
  });

  it("lists: typing the wrong value hints, twice reveals the answer, the right one passes", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await openTopic(user, "Lists");
    await user.click(cardButton(5));

    const field = screen.getByLabelText("print(a) shows:");
    await user.type(field, "[[1, 2]{Enter}");
    expect(screen.getByText("Remember: b = a makes no copy.")).toBeInTheDocument();
    expect(screen.queryByText(/The answer is/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Check" }));
    expect(screen.getByText(/The answer is/)).toBeInTheDocument();

    await user.clear(field);
    await user.type(field, "[[1,2,3]{Enter}");
    expect(screen.getByText("Right.")).toBeInTheDocument();
  });

  it("recursion: typing 24 finishes the last deck", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await openTopic(user, "Recursion");
    await user.click(cardButton(5));
    expect(FADED.rec.output.at(-1)).toBe("24");

    await user.type(screen.getByLabelText("The last print shows:"), "6{Enter}");
    expect(screen.getByText("Not quite.")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("The last print shows:"));
    await user.type(screen.getByLabelText("The last print shows:"), "24{Enter}");
    expect(screen.getByText("Right.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Deck done" })).toBeDisabled();
  });

  it("offers the next topic once a deck is done", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    await user.click(cardButton(5));
    expect(screen.getByRole("button", { name: /^Next$/ })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "pass" }));
    await user.click(screen.getByRole("button", { name: "Next topic: While loops" }));
    expect(screen.getByRole("heading", { level: 2, name: TOPICS[1].cards[0].headline })).toBeInTheDocument();
  });
});

// ---- persistence -----------------------------------------------------------------------------

describe("done persists", () => {
  it("writes the finished deck to localStorage and ticks the picker", async () => {
    const user = userEvent.setup();
    render(<DeckExperience />);
    expect(within(topicButton("Conditionals")).queryByText(/done/)).not.toBeInTheDocument();
    await user.click(cardButton(5));
    await user.click(screen.getByRole("button", { name: "pass" }));

    expect(JSON.parse(window.localStorage.getItem(DONE_KEY) ?? "[]")).toEqual(["conditionals"]);
    expect(within(topicButton("Conditionals")).getByText(/done/)).toBeInTheDocument();
  });

  it("restores the tick after a reload", async () => {
    window.localStorage.setItem(DONE_KEY, JSON.stringify(["lists", "recursion"]));
    render(<DeckExperience />);
    await waitFor(() => expect(within(topicButton("Lists")).getByText(/done/)).toBeInTheDocument());
    expect(within(topicButton("Recursion")).getByText(/done/)).toBeInTheDocument();
    expect(within(topicButton("Functions")).queryByText(/done/)).not.toBeInTheDocument();
  });

  it("ignores junk in storage and still works when storage throws", async () => {
    window.localStorage.setItem(DONE_KEY, "{not json");
    const user = userEvent.setup();
    render(<DeckExperience />);
    expect(screen.getByRole("heading", { level: 2, name: "if picks one path" })).toBeInTheDocument();

    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    await user.click(cardButton(5));
    await user.click(screen.getByRole("button", { name: "pass" }));
    expect(within(topicButton("Conditionals")).getByText(/done/)).toBeInTheDocument();
  });
});
