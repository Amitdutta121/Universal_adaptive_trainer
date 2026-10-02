"use client";

import { ArrowRight } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { type Refresher, SOURCE_LINE } from "../mock-data";
import { SnippetBlock } from "./snippet-block";

const ORDINAL = ["", "first", "second", "third", "fourth"];

function RefresherBody({ refresher, count }: { refresher: Refresher; count: number }) {
  // Resets on every open: the sheet content unmounts when it closes.
  const [fuller, setFuller] = useState(false);
  const repeated = count >= 2;

  return (
    <>
      <SheetHeader className="pr-12">
        <SheetTitle>{refresher.title}</SheetTitle>
        {repeated ? (
          <p className="text-muted-foreground text-sm">
            This is the {ORDINAL[Math.min(count, 4)]} time you have picked this kind of answer.
          </p>
        ) : null}
      </SheetHeader>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4">
        <SheetDescription asChild>
          <div className="space-y-1.5 text-foreground leading-6">
            {(fuller ? refresher.full : refresher.short).map((line) => (
              <p key={line}>{line}</p>
            ))}
          </div>
        </SheetDescription>
        <SnippetBlock
          code={fuller ? refresher.fullSnippet.code : refresher.shortSnippet.code}
          output={fuller ? refresher.fullSnippet.output : refresher.shortSnippet.output}
        />
        {repeated && !fuller ? (
          <Button type="button" variant="outline" size="sm" onClick={() => setFuller(true)}>
            Show the fuller version (6 lines)
          </Button>
        ) : null}
        {/* TODO(real): the page comes from the retrieval chunk the question was generated from. */}
        <p className="pb-1 text-muted-foreground text-xs">
          Why you&rsquo;re seeing this: generated from {SOURCE_LINE}
        </p>
      </div>
    </>
  );
}

/**
 * The 30-second refresher, as a bottom sheet (the Sheet primitive; on wide screens it is a centred
 * panel docked to the bottom so it never covers the whole page).
 *
 * The trigger lives here so Radix returns focus to it on a plain close (Escape, X, overlay). On
 * "Got it" the trigger unmounts together with the old result, so the parent moves focus to the new
 * question heading instead.
 */
export function RefresherSheet({
  open,
  onOpenChange,
  refresher,
  count,
  isLastQuestion,
  onGotIt,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  refresher: Refresher;
  /** How many times this misconception has now been picked (1 = first time). */
  count: number;
  isLastQuestion: boolean;
  onGotIt: () => void;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetTrigger asChild>
        <Button type="button" variant="outline">
          Need a refresher? 30 seconds
        </Button>
      </SheetTrigger>
      <SheetContent
        side="bottom"
        className="mx-auto max-h-[85dvh] sm:max-w-xl sm:rounded-t-xl sm:border-x"
      >
        <RefresherBody refresher={refresher} count={count} />
        <SheetFooter>
          <Button type="button" onClick={onGotIt}>
            {isLastQuestion ? "Got it, finish" : "Got it, try another"}
            <ArrowRight />
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
