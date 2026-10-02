"use client";

/**
 * One topic's deck: five short cards, one idea each. Card 1 has an "I know this" jump to the check;
 * card 3 is the simulator; card 5 is the faded completion. Nothing forces the scaffold: prediction
 * can be switched off, the deck can be skipped to its check, and any card is one tap away.
 *
 * Each card fits the screen. The slide is the only surface that may scroll (on a very short
 * phone), never the page. Arrow keys page the cards, except on the simulator card, where they step
 * the trace instead.
 */

import { ArrowLeft, ArrowRight, FastForward } from "lucide-react";
import { Fragment, type Ref, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { type Card, exampleById, type Topic } from "../mock-data";
import type { Example } from "../traces.generated";
import { CodeView } from "./code-view";
import { FadedParsons, FadedPick, FadedType } from "./faded";
import { TraceLab } from "./trace-lab";

/** Arrow keys belong to text fields and selects. */
function isTypingTarget(target: EventTarget | null) {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
  );
}

/** `code` spans only. */
function Inline({ text }: { text: string }) {
  const parts = text.split(/(`[^`]+`)/g).filter(Boolean);
  return (
    <>
      {parts.map((part, index) => {
        const key = `${index}:${part}`;
        return part.startsWith("`") ? (
          <code
            key={key}
            className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.86em] text-foreground"
          >
            {part.slice(1, -1)}
          </code>
        ) : (
          <Fragment key={key}>{part}</Fragment>
        );
      })}
    </>
  );
}

function ExampleBlock({ example }: { example: Example }) {
  return (
    <figure className="min-w-0 overflow-hidden rounded-lg bg-muted/50 dark:bg-muted/30">
      <CodeView label="Example code" code={example.code} />
      <figcaption className="border-border border-t px-4 py-2">
        <span className="block font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest">
          Output
        </span>
        <fieldset aria-label="Example output" className="m-0 min-w-0 border-0 p-0 font-mono text-sm leading-6">
          {example.output.map((line, index) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: an endless loop repeats the same line
            <div key={index}>{line}</div>
          ))}
          {example.endless ? (
            <span className="font-sans text-muted-foreground text-xs">
              and on, forever: this loop never stops
            </span>
          ) : null}
        </fieldset>
      </figcaption>
    </figure>
  );
}

function CardHeading({
  headline,
  small,
  headingRef,
}: {
  headline: string;
  small?: boolean;
  headingRef: Ref<HTMLHeadingElement>;
}) {
  return (
    <h2
      ref={headingRef}
      tabIndex={-1}
      className={cn(
        "font-heading font-semibold text-foreground leading-tight tracking-tight outline-none",
        small ? "text-xl sm:text-2xl" : "text-2xl sm:text-3xl",
      )}
    >
      {headline}
    </h2>
  );
}

export function Deck({
  topic,
  index,
  onIndex,
  done,
  onSolved,
  predictOn,
  setPredictOn,
  nextTopic,
  onNextTopic,
}: {
  topic: Topic;
  index: number;
  onIndex: (index: number) => void;
  done: boolean;
  onSolved: () => void;
  predictOn: boolean;
  setPredictOn: (on: boolean) => void;
  nextTopic?: Topic;
  onNextTopic: () => void;
}) {
  const total = topic.cards.length;
  const card: Card = topic.cards[index] ?? topic.cards[0];
  const headingRef = useRef<HTMLHeadingElement>(null);
  const first = useRef(true);
  const go = (next: number) => onIndex(Math.min(total - 1, Math.max(0, next)));

  // The simulator card owns the arrow keys (they step the trace); other cards page with them.
  const isSim = card.kind === "sim";
  useEffect(() => {
    if (isSim) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      if (isTypingTarget(event.target)) return;
      if (event.key === "ArrowRight") onIndex(Math.min(total - 1, index + 1));
      else if (event.key === "ArrowLeft") onIndex(Math.max(0, index - 1));
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isSim, index, total, onIndex]);

  // If the control that had focus went away with the card, land on the heading, not the page top.
  // biome-ignore lint/correctness/useExhaustiveDependencies: runs when the card changes
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    if (document.activeElement === document.body) headingRef.current?.focus();
  }, [index]);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 sm:gap-3">
      <nav aria-label={`${topic.label} progress`}>
        <ol className="flex gap-1.5">
          {topic.cards.map((item, position) => (
            <li key={item.id} className="flex-1">
              <button
                type="button"
                aria-label={`Go to card ${position + 1} of ${total}`}
                aria-current={position === index ? "step" : undefined}
                onClick={() => go(position)}
                className="group flex h-5 w-full items-center rounded-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                <span
                  className={cn(
                    "block h-1.5 w-full rounded-full",
                    position <= index ? "bg-primary" : "bg-muted group-hover:bg-border",
                  )}
                />
              </button>
            </li>
          ))}
        </ol>
      </nav>

      <p role="status" aria-live="polite" className="sr-only">
        {`${topic.label}, card ${index + 1} of ${total}: ${card.headline}`}
      </p>

      <section
        aria-label={`${topic.label}, card ${index + 1} of ${total}`}
        className="flex min-h-0 flex-1 flex-col overflow-y-auto rounded-xl border border-border bg-card p-4 sm:p-6"
      >
        <div className="my-auto grid gap-3 sm:gap-4">
          {card.kind === "idea" ? (
            <div
              className={cn(
                "grid gap-4 md:items-center md:gap-8",
                card.example && "md:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]",
              )}
            >
              <div className="grid content-start gap-3">
                <CardHeading headline={card.headline} headingRef={headingRef} />
                <p className="max-w-prose text-base text-foreground/85 leading-relaxed sm:text-lg">
                  <Inline text={card.body} />
                </p>
                {index === 0 ? (
                  <div>
                    <Button type="button" variant="ghost" onClick={() => go(total - 1)}>
                      <FastForward aria-hidden="true" />
                      I know this, skip to the check
                    </Button>
                  </div>
                ) : null}
              </div>
              {card.example ? <ExampleBlock example={exampleById(card.example)} /> : null}
            </div>
          ) : null}

          {card.kind === "sim" ? (
            <>
              <div>
                <CardHeading small headline={card.headline} headingRef={headingRef} />
                <p className="mt-1 text-muted-foreground text-sm sm:text-base">{card.body}</p>
              </div>
              <TraceLab
                key={card.id}
                traceIds={card.traces}
                predictOn={predictOn}
                setPredictOn={setPredictOn}
              />
            </>
          ) : null}

          {card.kind === "faded" ? (
            <>
              <div>
                <CardHeading small headline={card.headline} headingRef={headingRef} />
                <p className="mt-1 text-muted-foreground text-sm sm:text-base">{card.body}</p>
              </div>
              {card.task.kind === "pick" ? (
                <FadedPick key={card.id} task={card.task} onSolved={onSolved} />
              ) : null}
              {card.task.kind === "type" ? (
                <FadedType key={card.id} task={card.task} onSolved={onSolved} />
              ) : null}
              {card.task.kind === "parsons" ? (
                <FadedParsons key={card.id} task={card.task} onSolved={onSolved} />
              ) : null}
            </>
          ) : null}
        </div>
      </section>

      <div className="flex shrink-0 items-center justify-between gap-3">
        <Button type="button" variant="outline" disabled={index === 0} onClick={() => go(index - 1)}>
          <ArrowLeft aria-hidden="true" />
          Back
        </Button>
        <span className="hidden text-muted-foreground text-xs sm:block">
          {isSim ? "Arrow keys step the trace." : "Left and right arrow keys change card."}
        </span>
        {index < total - 1 ? (
          <Button type="button" onClick={() => go(index + 1)}>
            Next
            <ArrowRight aria-hidden="true" />
          </Button>
        ) : done && nextTopic ? (
          <Button type="button" onClick={onNextTopic}>
            Next topic: {nextTopic.label}
            <ArrowRight aria-hidden="true" />
          </Button>
        ) : (
          <Button type="button" disabled>
            {done ? "Deck done" : "Next"}
          </Button>
        )}
      </div>
    </div>
  );
}
