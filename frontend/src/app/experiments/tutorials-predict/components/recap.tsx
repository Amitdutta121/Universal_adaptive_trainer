"use client";

/**
 * The end: only the predictions the student got wrong, each as its snippet with what happened and
 * what they said, plus the one-line insight. If nothing surprised them there is nothing to review.
 */

import { RotateCcw } from "lucide-react";
import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { type Answer, type Experiment, outcomeComment } from "../mock-data";
import { CodeBox, Inline } from "./parts";

export function Recap({
  wrong,
  answers,
  onRestart,
}: {
  wrong: Experiment[];
  answers: Readonly<Record<string, Answer>>;
  onRestart: () => void;
}) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  return (
    <div className="grid gap-4">
      <h2
        ref={headingRef}
        tabIndex={-1}
        className="rounded font-heading font-semibold text-xl outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        Recap
      </h2>

      {wrong.length === 0 ? (
        <p>No surprises. You already had this.</p>
      ) : (
        <>
          <p>
            {wrong.length} {wrong.length === 1 ? "surprise" : "surprises"}. Those are the ones worth
            remembering.
          </p>
          <ul className="grid gap-4">
            {wrong.map((experiment) => (
              <li key={experiment.id} className="grid gap-2">
                <CodeBox
                  code={`${experiment.code}\n${outcomeComment(experiment, answers[experiment.id]?.guess ?? "")}`}
                  label="Python snippet"
                />
                <p>
                  <Inline text={experiment.insight} />
                </p>
              </li>
            ))}
          </ul>
        </>
      )}

      <div>
        <Button type="button" variant="outline" onClick={onRestart}>
          <RotateCcw aria-hidden="true" />
          Start over
        </Button>
      </div>
    </div>
  );
}
