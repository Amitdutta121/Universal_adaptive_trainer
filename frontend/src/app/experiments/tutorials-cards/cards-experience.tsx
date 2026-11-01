"use client";

/**
 * Variant A, micro-card stepper. One idea per screen; Next/Back and the arrow keys move between
 * cards; the last card is a one-question check and the way into practice. Each card fits the
 * viewport (no page scroll), so the shell is a fixed-height column: header, card, controls.
 *
 * Mock data only. See `mock-data.ts`.
 */

import { ArrowLeft, ArrowRight, BookOpen, Home } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CardText } from "./components/card-body";
import { CheckQuestion } from "./components/check-question";
import { CodeSnippet } from "./components/code-snippet";
import { SegmentedProgress } from "./components/segmented-progress";
import { CARDS, MISSED, PRACTICE_HREF } from "./mock-data";

/** Arrow keys belong to text fields; everything else (including buttons) lets them page the cards. */
function isTypingTarget(target: EventTarget | null) {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
  );
}

export function CardsExperience() {
  const [index, setIndex] = useState(0);
  const [chosenId, setChosenId] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const firstRender = useRef(true);

  const total = CARDS.length;
  const card = CARDS[index];
  const isLast = index === total - 1;

  const go = (next: number) => setIndex(Math.min(total - 1, Math.max(0, next)));

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      if (isTypingTarget(event.target)) return;
      if (event.key === "ArrowRight") setIndex((value) => Math.min(total - 1, value + 1));
      else if (event.key === "ArrowLeft") setIndex((value) => Math.max(0, value - 1));
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  // If the focused control disappeared with the card (Next on the last card), land on the heading
  // instead of dropping focus to the page top.
  // biome-ignore lint/correctness/useExhaustiveDependencies: runs when the card changes
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    if (document.activeElement === document.body) headingRef.current?.focus();
  }, [index]);

  const answered = card.kind === "check" && chosenId !== null;

  return (
    <div className="flex h-dvh flex-col bg-background text-foreground">
      <header className="shrink-0 border-border border-b bg-card/60">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-2 sm:px-6">
          <div className="flex items-center gap-2.5">
            <span className="flex size-7 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <BookOpen className="size-3.5" aria-hidden="true" />
            </span>
            <span>
              <span className="block font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest">
                Design prototype
              </span>
              <span className="block font-heading font-semibold text-foreground text-sm">
                Tutorial cards
              </span>
            </span>
          </div>
          <a
            href="/dashboard"
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-muted-foreground text-sm outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <Home className="size-3.5" aria-hidden="true" />
            Console
          </a>
        </div>
      </header>

      <div className="mx-auto w-full max-w-3xl shrink-0 px-4 pt-2 sm:px-6">
        {/* TODO(real): drop this note once the cards come from the approved book content. */}
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-amber-800 text-xs sm:text-sm dark:text-amber-200">
          <strong className="font-medium">Prototype.</strong> Mock data: the cards are hand-written, and
          nothing here calls a server or a model.
        </p>
      </div>

      <main className="mx-auto flex min-h-0 w-full max-w-3xl flex-1 flex-col gap-2 px-4 pt-2 pb-3 sm:px-6 sm:pt-4 sm:pb-5">
        <SegmentedProgress total={total} index={index} onJump={go} />

        <section
          aria-labelledby="card-heading"
          className="flex min-h-0 flex-1 flex-col justify-center gap-4 overflow-y-auto rounded-xl border border-border bg-card p-5 sm:gap-6 sm:p-10"
        >
          <div className="flex items-center gap-2">
            <Badge variant="secondary" className="capitalize">
              {MISSED.topic}
            </Badge>
            <span className="font-mono text-muted-foreground text-xs">
              {index + 1} / {total}
            </span>
          </div>

          <h1
            id="card-heading"
            ref={headingRef}
            tabIndex={-1}
            className="font-heading font-semibold text-2xl text-foreground leading-tight tracking-tight outline-none sm:text-4xl"
          >
            {card.headline}
          </h1>

          {card.kind === "lesson" ? (
            <>
              <p className="max-w-prose text-base text-foreground/85 leading-relaxed sm:text-lg">
                <CardText text={card.body} />
              </p>
              {card.snippet ? <CodeSnippet snippet={card.snippet} /> : null}
            </>
          ) : (
            <CheckQuestion card={card} chosenId={chosenId} onChoose={setChosenId} />
          )}
        </section>

        <div className="flex shrink-0 items-center justify-between gap-3">
          <Button
            type="button"
            variant="outline"
            className="h-10 px-4 text-sm"
            disabled={index === 0}
            onClick={() => go(index - 1)}
          >
            <ArrowLeft aria-hidden="true" />
            Back
          </Button>

          <span className="hidden text-muted-foreground text-xs sm:block">
            Use the left and right arrow keys
          </span>

          {isLast ? (
            answered ? (
              <Button asChild className="h-10 px-4 text-sm">
                <Link href={PRACTICE_HREF}>
                  Practice for loops
                  <ArrowRight aria-hidden="true" />
                </Link>
              </Button>
            ) : (
              <span className="text-muted-foreground text-sm">Pick an answer</span>
            )
          ) : (
            <Button type="button" className="h-10 px-5 text-sm" onClick={() => go(index + 1)}>
              Next
              <ArrowRight aria-hidden="true" />
            </Button>
          )}
        </div>
      </main>

      {/* Announces the card that just came up; the card itself is not a live region. */}
      <p className="sr-only" aria-live="polite">
        Card {index + 1} of {total}: {card.headline}
      </p>
    </div>
  );
}
