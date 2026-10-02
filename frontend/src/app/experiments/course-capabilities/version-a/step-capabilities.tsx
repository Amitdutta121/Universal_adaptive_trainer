"use client";

import {
  CAPABILITIES,
  type Capability,
  type CapabilityFamily,
  FAMILY_LABEL,
  isSelectable,
  QUESTION_TYPES,
} from "../mock-capabilities";
import { AiGradedBadge, PlannedBadge } from "./badges";
import { Toggle } from "./toggle";

const FAMILIES = Object.keys(FAMILY_LABEL) as CapabilityFamily[];

/** Question types this capability can grade (by label), for the "Grades" line. */
function gradesLabels(capability: Capability): string[] {
  return QUESTION_TYPES.filter((type) => type.gradedBy.includes(capability.id)).map(
    (type) => type.label,
  );
}

/** Question types that need this capability as a prerequisite, not as a grader. */
function supportsLabels(capability: Capability): string[] {
  return QUESTION_TYPES.filter((type) => type.alsoNeeds.includes(capability.id)).map(
    (type) => type.label,
  );
}

export function StepCapabilities({
  enabled,
  onToggle,
}: {
  enabled: ReadonlySet<string>;
  onToggle: (id: string, on: boolean) => void;
}) {
  return (
    <div className="flex flex-col gap-6">
      <p className="text-muted-foreground text-sm">
        Each capability is a grader the system can run on student answers. Question types become
        available in the next step based on what you turn on here. You can change this later in
        course settings; turning a capability off keeps its questions but stops serving them.
      </p>

      {FAMILIES.map((family) => {
        const caps = CAPABILITIES.filter((cap) => cap.family === family);
        if (caps.length === 0) return null;
        const headingId = `family-${family}`;
        return (
          <section key={family} aria-labelledby={headingId} className="flex flex-col gap-2">
            <h3
              id={headingId}
              className="font-medium text-muted-foreground text-xs uppercase tracking-wide"
            >
              {FAMILY_LABEL[family]}
            </h3>
            <ul className="divide-y rounded-lg border bg-card">
              {caps.map((cap) => {
                const selectable = isSelectable(cap);
                const on = selectable && enabled.has(cap.id);
                const grades = gradesLabels(cap);
                const supports = supportsLabels(cap);
                const toggleId = `cap-${cap.id}`;
                return (
                  <li key={cap.id} className="flex items-start gap-4 px-4 py-3">
                    <div className="pt-0.5">
                      <Toggle
                        id={toggleId}
                        checked={on}
                        disabled={!selectable}
                        label={selectable ? cap.label : `${cap.label} (not built yet)`}
                        onChange={(next) => onToggle(cap.id, next)}
                      />
                    </div>
                    <div className="flex min-w-0 flex-1 flex-col gap-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <label
                          htmlFor={toggleId}
                          className={
                            selectable
                              ? "cursor-pointer font-medium text-sm"
                              : "font-medium text-muted-foreground text-sm"
                          }
                        >
                          {cap.label}
                        </label>
                        {selectable ? null : <PlannedBadge />}
                        {cap.deterministic ? null : <AiGradedBadge />}
                      </div>
                      <p className="text-sm">{cap.card}</p>
                      <p className="text-muted-foreground text-xs italic">{cap.example}</p>
                      {cap.deterministic ? null : (
                        <p className="text-[var(--warn-solid)] text-xs">
                          AI-graded · practice only — never counts toward mastery.
                        </p>
                      )}
                      <p className="text-muted-foreground text-xs">
                        {grades.length > 0 ? <>Grades: {grades.join(", ")}</> : null}
                        {grades.length > 0 && supports.length > 0 ? " · " : null}
                        {supports.length > 0 ? <>Required for: {supports.join(", ")}</> : null}
                      </p>
                    </div>
                    <code className="hidden shrink-0 pt-0.5 font-mono text-muted-foreground text-xs md:block">
                      {cap.grader ?? "no grader"}
                    </code>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
