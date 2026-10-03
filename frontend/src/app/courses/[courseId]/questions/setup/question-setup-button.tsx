"use client";

/**
 * The Questions page header button that opens the setup modal. Setup is per subtopic of the
 * approved taxonomy, so without one the button is disabled and says why. Once a setup exists it
 * reads "Edit setup".
 */

import { ListChecks } from "lucide-react";
import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useApprovedCurriculum, useCurrentSetup } from "@/lib/api/queries";
import { QuestionSetupDialog } from "./question-setup-dialog";

const NO_TAXONOMY_HINT = "Approve a taxonomy first: questions are set up per subtopic.";

export function QuestionSetupButton() {
  const curriculum = useApprovedCurriculum();
  // A failed read (e.g. not implemented yet) is treated as "no setup yet": the modal still opens.
  const current = useCurrentSetup(curriculum.data?.version.id);
  const [open, setOpen] = useState(false);
  const hintId = useId();

  const existing = current.data?.setup ?? null;
  const label = existing ? "Edit setup" : "Set up questions";

  if (!curriculum.data) {
    const hint = curriculum.isPending ? null : NO_TAXONOMY_HINT;
    const button = (
      <Button size="sm" className="h-9" disabled aria-describedby={hint ? hintId : undefined}>
        <ListChecks data-icon="inline-start" />
        {label}
      </Button>
    );
    if (!hint) return button;
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          {/* A disabled button gets no pointer events; the wrapper carries the tooltip. */}
          {/* biome-ignore lint/a11y/noNoninteractiveTabindex: focus target for the tooltip of a disabled button */}
          <span tabIndex={0} className="inline-flex rounded-lg">
            {button}
            <span id={hintId} className="sr-only">
              {hint}
            </span>
          </span>
        </TooltipTrigger>
        <TooltipContent>{hint}</TooltipContent>
      </Tooltip>
    );
  }

  return (
    <>
      <Button size="sm" className="h-9" onClick={() => setOpen(true)}>
        <ListChecks data-icon="inline-start" />
        {label}
      </Button>
      {open ? (
        <QuestionSetupDialog
          curriculum={curriculum.data}
          currentSetup={existing}
          onOpenChange={setOpen}
        />
      ) : null}
    </>
  );
}
