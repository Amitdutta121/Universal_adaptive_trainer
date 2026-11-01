/**
 * Stand-in content for `/experiments/tutorials-deck`: five topics, five cards each. The card copy
 * is hand-written (headline at most 8 words, body at most 20). Everything that is a fact about
 * Python (outputs, traces, the right answers, what a wrong choice really does) comes from
 * `traces.generated.ts`, which `record_traces.py` produced by running the snippets.
 *
 * TODO(real): in the product a tutorial is generated from a book section, the validator records
 * the traces and the check answers, and the professor approves it. The topics and their order
 * would come from the student's measured mastery, not from this list.
 */

import { EXAMPLES, FADED, TRACES, type Trace } from "./traces.generated";

export { EXAMPLES, FADED, TRACES };

export type FadedTask =
  | {
      kind: "pick";
      /** Code shown; a `____` line is filled with the chosen value. */
      code: string;
      ask: string;
      choices: { value: string; why: string; result?: string }[];
      answer: string;
    }
  | {
      kind: "type";
      code: string;
      ask: string;
      answer: string;
      why: string;
      retry: string;
    }
  | {
      kind: "parsons";
      ask: string;
      lines: string[];
      shuffled: number[];
      orders: Record<string, { ok: boolean; text: string }>;
      output: string[];
      why: string;
    };

export type IdeaCard = {
  id: string;
  kind: "idea";
  headline: string;
  body: string;
  /** Key into `EXAMPLES`. */
  example?: string;
};
export type SimCard = {
  id: string;
  kind: "sim";
  headline: string;
  body: string;
  /** Keys into `TRACES`; more than one shows a small switch between snippets. */
  traces: string[];
};
export type FadedCard = {
  id: string;
  kind: "faded";
  headline: string;
  body: string;
  task: FadedTask;
};
export type Card = IdeaCard | SimCard | FadedCard;

export type Topic = {
  id: string;
  label: string;
  cards: Card[];
};

const whileResult = (choice: (typeof FADED.while.choices)[number]) =>
  choice.terminates
    ? `Result: prints ${choice.output.join(" ")} and stops.`
    : "Result: it never stops. Python was cut off at the step limit.";

const WHILE_WHY: Record<string, string> = {
  "i = i + 1": "i grows 1, 2, 3, 4, so i <= 3 finally turns false.",
  "i = 1": "i goes back to 1 on every pass, so the test stays true.",
  "total = 0": "Nothing changes i, so the test stays true.",
};

/** TODO(real): the "why" lines come from the tutorial author. Which choice is right does not: it is the recorded run. */
export const TOPICS: Topic[] = [
  {
    id: "conditionals",
    label: "Conditionals",
    cards: [
      {
        id: "cond-1",
        kind: "idea",
        headline: "if picks one path",
        body: "Python tests a condition. If it is true, the indented lines run. Otherwise they are skipped.",
        example: "if-basic",
      },
      {
        id: "cond-2",
        kind: "idea",
        headline: "The first true test wins",
        body: "Tests run top to bottom. Once one is true, its lines run and every later branch is skipped.",
        example: "elif-chain",
      },
      {
        id: "cond-3",
        kind: "sim",
        headline: "Watch which branch runs",
        body: "Predict, then step. This one has a trap.",
        traces: ["cond"],
      },
      {
        id: "cond-4",
        kind: "idea",
        headline: "Strictest test goes first",
        body: "Now 95 meets the strictest test first, so it earns the distinction it deserves.",
        example: "elif-fixed",
      },
      {
        id: "cond-5",
        kind: "faded",
        headline: "Now you finish it",
        body: "Same code, new mark. Pick what it prints.",
        task: {
          kind: "pick",
          code: FADED.cond.code,
          ask: "It prints:",
          answer: FADED.cond.output.join("\n"),
          choices: [
            { value: "distinction", why: "65 fails >= 90, so the first branch is skipped." },
            { value: "pass", why: "65 fails >= 90, then passes >= 60, so the elif runs." },
            { value: "fail", why: "65 already passes >= 60, so else is never reached." },
          ],
        },
      },
    ],
  },
  {
    id: "while",
    label: "While loops",
    cards: [
      {
        id: "while-1",
        kind: "idea",
        headline: "while repeats while a test is true",
        body: "Python checks the test before every pass. When it turns false, the loop ends.",
        example: "while-countdown",
      },
      {
        id: "while-2",
        kind: "idea",
        headline: "Something inside must change the test",
        body: "If nothing changes the variable, the test never turns false and the loop never ends.",
        example: "while-stuck",
      },
      {
        id: "while-3",
        kind: "sim",
        headline: "Watch the test re-checked each pass",
        body: "Try both loops. Predict first.",
        traces: ["while-ends", "while-stuck"],
      },
      {
        id: "while-4",
        kind: "idea",
        headline: "Change the variable inside the loop",
        body: "One extra line moves count toward 3, so the test finally turns false.",
        example: "while-fixed",
      },
      {
        id: "while-5",
        kind: "faded",
        headline: "Which line ends the loop?",
        body: "Pick the missing line so the loop stops and prints the total.",
        task: {
          kind: "pick",
          code: FADED.while.template,
          ask: "The missing line is:",
          answer: FADED.while.choices.find((choice) => choice.terminates)?.value ?? "",
          choices: FADED.while.choices.map((choice) => ({
            value: choice.value,
            why: WHILE_WHY[choice.value] ?? "",
            result: whileResult(choice),
          })),
        },
      },
    ],
  },
  {
    id: "functions",
    label: "Functions",
    cards: [
      {
        id: "fn-1",
        kind: "idea",
        headline: "Parameters receive arguments",
        body: "Parameters are the names in def. Arguments are the values you pass when you call.",
        example: "fn-greet",
      },
      {
        id: "fn-2",
        kind: "idea",
        headline: "return hands a value back",
        body: "The call is replaced by the returned value, so the caller can keep it.",
        example: "fn-square",
      },
      {
        id: "fn-3",
        kind: "sim",
        headline: "Watch the call and the return",
        body: "Compare a function that returns with one that only prints.",
        traces: ["fn-return", "fn-print"],
      },
      {
        id: "fn-4",
        kind: "idea",
        headline: "print shows, return keeps",
        body: "total_price returns its result, so cost can hold it. Print alone would leave None.",
        example: "fn-worked",
      },
      {
        id: "fn-5",
        kind: "faded",
        headline: "Put the lines in order",
        body: `Tap the lines in the order Python needs. It should print ${FADED.fn.output.join(" ")}.`,
        task: {
          kind: "parsons",
          ask: "Your program:",
          lines: FADED.fn.lines,
          shuffled: FADED.fn.shuffled,
          orders: FADED.fn.orders,
          output: FADED.fn.output,
          why: "Define the function, call it, then print what came back.",
        },
      },
    ],
  },
  {
    id: "lists",
    label: "Lists",
    cards: [
      {
        id: "list-1",
        kind: "idea",
        headline: "Indexes start at 0",
        body: "The first item is `a[0]`. Negative indexes count from the end, so `a[-1]` is the last.",
        example: "list-index",
      },
      {
        id: "list-2",
        kind: "idea",
        headline: "append changes the list itself",
        body: "append adds to the end, in place. It returns nothing, and len counts the items.",
        example: "list-append",
      },
      {
        id: "list-3",
        kind: "sim",
        headline: "Two names, one list",
        body: "Watch what the names point at. Predict first.",
        traces: ["list-alias"],
      },
      {
        id: "list-4",
        kind: "idea",
        headline: "copy() makes a separate list",
        body: "`b = a.copy()` builds a new list, so b.append leaves a alone.",
        example: "list-copy",
      },
      {
        id: "list-5",
        kind: "faded",
        headline: "Predict the shared list",
        body: "Same shape as before. Type what print(a) shows.",
        task: {
          kind: "type",
          code: FADED.list.code,
          ask: "print(a) shows:",
          answer: FADED.list.output.join("\n"),
          why: "b = a shares one list, so b.append(3) changes a too.",
          retry: "Remember: b = a makes no copy.",
        },
      },
    ],
  },
  {
    id: "recursion",
    label: "Recursion",
    cards: [
      {
        id: "rec-1",
        kind: "idea",
        headline: "A function can call itself",
        body: "Each call gets its own frame. Calls stack up until one can answer without calling again.",
        example: "rec-countdown",
      },
      {
        id: "rec-2",
        kind: "idea",
        headline: "The base case stops the calls",
        body: "`if n == 1: return 1` answers without calling again. Without it, frames pile up forever.",
      },
      {
        id: "rec-3",
        kind: "sim",
        headline: "Watch the call stack grow",
        body: "Frames stack up, then answers unwind. Predict first.",
        traces: ["rec-fact"],
      },
      {
        id: "rec-4",
        kind: "idea",
        headline: "Answers flow back as frames close",
        body: "factorial(1) is 1, then 2 * 1, then 3 * 2. Each result feeds the next.",
        example: "rec-unwind",
      },
      {
        id: "rec-5",
        kind: "faded",
        headline: "Finish the chain",
        body: "One more call: factorial(4). Type what the last line prints.",
        task: {
          kind: "type",
          code: FADED.rec.code,
          ask: "The last print shows:",
          answer: FADED.rec.output.at(-1) ?? "",
          why: "factorial(4) is 4 * factorial(3), which is 4 * 6.",
          retry: "Each answer feeds the next: 1, 2, 6, and then?",
        },
      },
    ],
  },
];

export function traceById(id: string): Trace {
  const trace = TRACES[id];
  if (!trace) throw new Error(`unknown trace ${id}`);
  return trace;
}

export function exampleById(id: string) {
  const example = EXAMPLES[id];
  if (!example) throw new Error(`unknown example ${id}`);
  return example;
}
