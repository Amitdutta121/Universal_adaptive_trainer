"use client";

/**
 * The tutorial blocks a student's run shows (Phase 6): pre-teaching above the first question of
 * a topic, and on the result card after an answer. The backend composes them from the blocks
 * frozen with the run's question set -- worked after a wrong answer, faded and then a cue as
 * mastery rises, none once the topic is known -- so this only draws what it is given, through
 * the trusted renderer registry. No blocks, nothing drawn: the card keeps its explanation.
 */

import { BookOpen } from "lucide-react";
import type { Schemas } from "@/lib/api/types";
import { TutorialBlockView } from "./renderer-registry";

type StudentBlock = Schemas["StudentTutorialBlockOut"];

const AFTER_HEADING: Record<StudentBlock["guidance_level"], string> = {
  worked: "Work through it",
  faded: "Finish the idea",
  cue: "Remember",
};

export function StudentTutorialBlocks({
  blocks,
  moment,
}: {
  blocks: StudentBlock[];
  moment: "before" | "after";
}) {
  if (blocks.length === 0) return null;
  const heading =
    moment === "before" ? "Before you start" : AFTER_HEADING[blocks[0].guidance_level];
  return (
    <section aria-label={heading} className="space-y-3">
      <div className="flex items-center gap-2 font-medium text-foreground text-sm">
        <BookOpen className="size-4 text-primary" />
        {heading}
      </div>
      <div className="space-y-3">
        {blocks.map((block) => (
          <div key={block.id} className="rounded-xl border border-border/70 bg-white/80 p-4">
            <TutorialBlockView renderer={block.renderer} payload={block.payload} />
          </div>
        ))}
      </div>
    </section>
  );
}
