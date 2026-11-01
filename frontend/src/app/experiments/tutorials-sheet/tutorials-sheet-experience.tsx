"use client";

/**
 * Variant D — a one-screen cheat sheet for `for` loops and `range()`. Mock data only; see
 * `mock-data.ts`. The card is the whole lesson (about 90 words); the longer explanation is
 * folded away. Prints on one page: everything interactive is `print:hidden`, and the tokens are
 * pinned to a light palette in print so a dark-theme student still gets dark ink on white paper.
 */

import { BookOpen, Bookmark, ChevronDown, Home, Printer } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Inline } from "../tutorials/components/tutorial-blocks";
import { NumberLine } from "./components/number-line";
import { PatternList } from "./components/pattern-list";
import { Stepper } from "./components/stepper";
import {
  DEFAULT_START,
  DEFAULT_STOP,
  LINE_MAX,
  LINE_MIN,
  PATTERNS,
  pyListRepr,
  pyRange,
  SAVED_KEY,
  WATCH_OUT,
  WHY_TEXT,
} from "./mock-data";

const PRINT_PALETTE =
  "print:[--background:#fff] print:[--card:#fff] print:[--foreground:#111] print:[--card-foreground:#111] print:[--muted:#f1f1f1] print:[--muted-foreground:#444] print:[--border:#bbb]";

function readSaved(): boolean {
  try {
    return window.localStorage.getItem(SAVED_KEY) === "1";
  } catch {
    return false;
  }
}

export function TutorialsSheetExperience() {
  const [start, setStart] = useState(DEFAULT_START);
  const [stop, setStop] = useState(DEFAULT_STOP);
  const [saved, setSaved] = useState(false);
  const [whyOpen, setWhyOpen] = useState(false);
  const resultId = useId();

  // Read after mount so the server and first client render agree.
  useEffect(() => {
    setSaved(readSaved());
  }, []);

  const toggleSaved = () => {
    const next = !saved;
    setSaved(next);
    try {
      if (next) window.localStorage.setItem(SAVED_KEY, "1");
      else window.localStorage.removeItem(SAVED_KEY);
    } catch {
      // Notes are a convenience; a blocked or full store must not break the sheet.
    }
  };

  const values = pyRange(start, stop);
  const empty = values.length === 0;

  return (
    <div className="min-h-screen bg-background text-foreground print:min-h-0">
      <a
        href="#sheet-main"
        className="sr-only rounded-md bg-primary px-3 py-2 font-medium text-primary-foreground text-sm focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50"
      >
        Skip to content
      </a>

      <header className="border-border border-b bg-card/60 print:hidden">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-2.5">
            <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <BookOpen className="size-4" aria-hidden="true" />
            </span>
            <span>
              <span className="block font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest">
                Design prototype
              </span>
              <span className="block font-heading font-semibold text-foreground text-sm">
                Tutorial: cheat sheet
              </span>
            </span>
          </div>
          <a
            href="/dashboard"
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-muted-foreground text-sm hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Home className="size-3.5" aria-hidden="true" />
            Console
          </a>
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-4 py-3 sm:px-6 print:hidden">
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-amber-800 text-sm dark:text-amber-200">
          <strong className="font-medium">Prototype.</strong> Mock data: the patterns and text are
          hand-written. Nothing here calls a server or a model.
        </p>
      </div>

      <main
        id="sheet-main"
        tabIndex={-1}
        className={`mx-auto max-w-5xl px-4 pb-16 text-foreground sm:px-6 print:max-w-none print:p-0 ${PRINT_PALETTE}`}
      >
        <article
          aria-labelledby="sheet-title"
          className="rounded-xl border border-border bg-card p-4 ring-1 ring-foreground/5 sm:p-6 print:rounded-none print:ring-0"
        >
          <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
            <div className="min-w-0">
              <h1
                id="sheet-title"
                className="font-heading font-semibold text-foreground text-xl tracking-tight sm:text-2xl"
              >
                for loops and <span className="font-mono">range()</span>
              </h1>
              <p className="mt-1 text-muted-foreground text-sm">
                <Inline text="`range()` counts from start up to, but not including, stop." />
              </p>
            </div>
            <div className="flex items-center gap-2 print:hidden">
              {saved ? (
                <span role="status" className="text-muted-foreground text-xs">
                  Saved on this device
                </span>
              ) : null}
              <Button
                type="button"
                variant={saved ? "secondary" : "outline"}
                size="sm"
                aria-pressed={saved}
                onClick={toggleSaved}
              >
                <Bookmark className={saved ? "fill-current" : undefined} aria-hidden="true" />
                Save to my notes
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label="Print this sheet"
                onClick={() => window.print()}
              >
                <Printer aria-hidden="true" />
              </Button>
            </div>
          </div>

          <div className="mt-5 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-8 print:grid-cols-2 print:gap-6">
            <PatternList patterns={PATTERNS} />

            <section aria-labelledby="try-title" className="min-w-0">
              <h2
                id="try-title"
                className="font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest"
              >
                Try it
              </h2>
              <div className="mt-2 flex flex-wrap gap-x-6 gap-y-2 print:hidden">
                <Stepper
                  name="start"
                  value={start}
                  min={LINE_MIN}
                  max={LINE_MAX}
                  onChange={setStart}
                />
                <Stepper
                  name="stop"
                  value={stop}
                  min={LINE_MIN}
                  max={LINE_MAX}
                  onChange={setStop}
                />
              </div>

              {/* The text alternative for the number line, and the live announcement. */}
              <div id={resultId} role="status" aria-live="polite" className="mt-3 min-h-14 text-sm">
                <p className="font-medium font-mono text-foreground">
                  <span data-testid="range-call">{`list(range(${start}, ${stop}))`}</span>
                  <span aria-hidden="true"> → </span>
                  <span className="sr-only"> gives </span>
                  <span data-testid="range-list">{pyListRepr(values)}</span>
                </p>
                <p className="mt-0.5 text-muted-foreground" data-testid="range-note">
                  {empty
                    ? "Nothing to loop over: stop must be bigger than start."
                    : `Last number is ${stop - 1}, not ${stop}.`}
                </p>
              </div>

              <div className="mt-2">
                <NumberLine start={start} stop={stop} values={values} describedBy={resultId} />
              </div>
              <p className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-muted-foreground text-xs">
                <span className="inline-flex items-center gap-1.5">
                  <span className="size-2.5 rounded-full bg-primary" aria-hidden="true" />
                  in the list
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span
                    className="size-2.5 rounded-full border-2 border-foreground bg-background"
                    aria-hidden="true"
                  />
                  stops before
                </span>
              </p>
            </section>
          </div>

          <aside
            aria-label="Watch out"
            className="mt-6 border-amber-500 border-l-2 bg-amber-500/10 py-2 pr-3 pl-3"
          >
            <p className="text-foreground text-sm leading-6">
              <span className="mr-2 font-mono text-[0.68rem] text-amber-700 uppercase tracking-widest dark:text-amber-400">
                Watch out
              </span>
              <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.86em]">
                {WATCH_OUT.code}
              </code>{" "}
              {WATCH_OUT.text}{" "}
              <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.86em]">
                {WATCH_OUT.fixCode}
              </code>
              .
            </p>
          </aside>
        </article>

        <Collapsible open={whyOpen} onOpenChange={setWhyOpen} className="mt-3 print:hidden">
          <CollapsibleTrigger asChild>
            <Button type="button" variant="ghost" size="sm" className="group">
              Show me why
              <ChevronDown
                className="transition-transform group-data-[state=open]:rotate-180"
                aria-hidden="true"
              />
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <p className="mt-2 max-w-prose border-border border-l-2 pl-4 text-foreground/90 text-sm leading-7">
              <Inline text={WHY_TEXT} />
            </p>
          </CollapsibleContent>
        </Collapsible>
      </main>
    </div>
  );
}
