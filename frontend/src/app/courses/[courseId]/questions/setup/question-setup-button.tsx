"use client";

/**
 * The Questions page start card that opens the setup modal. Setup is per subtopic of the
 * approved taxonomy, so without one the card's button is disabled and the card says why.
 * Once a setup exists the button reads "Edit setup".
 */

import { ListChecks } from "lucide-react";
import { useState } from "react";
import { StartCard } from "@/components/start-card";
import { useApprovedCurriculum, useCurrentSetup } from "@/lib/api/queries";
import { QuestionSetupDialog } from "./question-setup-dialog";

const NO_TAXONOMY_HINT = "Approve a taxonomy first: questions are set up per subtopic.";
const DESCRIPTION =
  "Choose which question types and styles each subtopic uses and how many questions to aim for.";

export function QuestionSetupButton() {
  const curriculum = useApprovedCurriculum();
  // A failed read (e.g. not implemented yet) is treated as "no setup yet": the modal still opens.
  const current = useCurrentSetup(curriculum.data?.version.id);
  const [open, setOpen] = useState(false);
  // A new number each opening. The suggestion query uses it so a remount of this
  // opening shares one request, and the next opening asks again.
  const [suggestionSession, setSuggestionSession] = useState(0);

  const existing = current.data?.setup ?? null;
  const label = existing ? "Edit setup" : "Set up questions";
  const card = {
    icon: <ListChecks className="size-4" />,
    title: "Question setup",
    action: label,
  };

  if (!curriculum.data) {
    return (
      <StartCard
        {...card}
        description={curriculum.isPending ? DESCRIPTION : NO_TAXONOMY_HINT}
        onClick={() => {}}
        disabled
      />
    );
  }

  return (
    <>
      <StartCard
        {...card}
        description={DESCRIPTION}
        onClick={() => {
          setSuggestionSession((session) => session + 1);
          setOpen(true);
        }}
      />
      {open ? (
        <QuestionSetupDialog
          curriculum={curriculum.data}
          currentSetup={existing}
          suggestionSession={suggestionSession}
          onOpenChange={setOpen}
        />
      ) : null}
    </>
  );
}
