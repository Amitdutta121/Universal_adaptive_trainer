"use client";

/** The one-question check on the last card. Any option can be tried again; the feedback names why. */

import { Check, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { CheckCard } from "../mock-data";

export function CheckQuestion({
  card,
  chosenId,
  onChoose,
}: {
  card: CheckCard;
  chosenId: string | null;
  onChoose: (optionId: string) => void;
}) {
  const chosen = card.options.find((option) => option.id === chosenId);
  const correct = chosen?.id === card.correctId;

  return (
    <div className="space-y-3">
      <fieldset className="m-0 min-w-0 border-0 p-0">
        <legend className="mb-3 p-0 text-base sm:text-lg">{card.question}</legend>
        <div className="grid grid-cols-2 gap-2">
          {card.options.map((option) => {
            const isChosen = option.id === chosenId;
            const isRight = isChosen && option.id === card.correctId;
            const isWrong = isChosen && !isRight;
            return (
              <button
                key={option.id}
                type="button"
                aria-pressed={isChosen}
                onClick={() => onChoose(option.id)}
                className={cn(
                  "flex min-h-11 items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left font-mono text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
                  isRight && "border-primary bg-accent text-foreground",
                  isWrong && "border-destructive bg-destructive/10 text-foreground",
                  !isChosen && "border-border bg-background hover:bg-muted",
                )}
              >
                <span>{option.code}</span>
                {isRight ? <Check className="size-4 text-primary" aria-hidden="true" /> : null}
                {isWrong ? <X className="size-4 text-destructive" aria-hidden="true" /> : null}
              </button>
            );
          })}
        </div>
      </fieldset>
      {/* Polite live region: the verdict is read out when an option is picked. */}
      <p aria-live="polite" className="min-h-10 text-muted-foreground text-sm">
        {chosen ? (
          <>
            <strong className="font-medium text-foreground">{correct ? "Correct." : "Not quite."}</strong>{" "}
            {chosen.feedback}
          </>
        ) : null}
      </p>
    </div>
  );
}
