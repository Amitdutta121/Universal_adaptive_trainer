"use client";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { CAPABILITIES_BY_ID, type TypeAvailability } from "../mock-capabilities";
import { AiGradedBadge } from "./badges";
import { Toggle } from "./toggle";

function capLabel(id: string): string {
  return CAPABILITIES_BY_ID[id]?.label ?? id;
}

/** "needs Numeric with units (not built yet)" style reason for an unavailable type. */
function missingReason(missing: readonly string[]): string {
  const parts = missing.map((id) => {
    const cap = CAPABILITIES_BY_ID[id];
    if (!cap) return id;
    return cap.status === "planned" ? `${cap.label} (not built yet)` : cap.label;
  });
  return `Needs ${parts.join(" and ")}`;
}

function isAiGraded(gradedByEnabled: readonly string[]): boolean {
  return (
    gradedByEnabled.length > 0 &&
    gradedByEnabled.every((id) => CAPABILITIES_BY_ID[id]?.deterministic === false)
  );
}

export function StepReview({
  courseName,
  presetLabel,
  enabledCount,
  availability,
  onSwitch,
}: {
  courseName: string;
  presetLabel: string | null;
  enabledCount: number;
  availability: readonly TypeAvailability[];
  onSwitch: (typeId: string, on: boolean) => void;
}) {
  const possible = availability.filter((entry) => entry.possible);
  const unavailable = availability.filter((entry) => !entry.possible);
  const allowedCount = possible.filter((entry) => entry.allowed).length;

  return (
    <div className="flex flex-col gap-6">
      <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1 text-sm">
        <dt className="text-muted-foreground">Course</dt>
        <dd>
          {courseName.trim() || <span className="text-muted-foreground">Untitled course</span>}
        </dd>
        <dt className="text-muted-foreground">Subject</dt>
        <dd>{presetLabel ?? "—"}</dd>
        <dt className="text-muted-foreground">Allows</dt>
        <dd className="font-medium">
          {allowedCount} question {allowedCount === 1 ? "type" : "types"} · {enabledCount}{" "}
          {enabledCount === 1 ? "capability" : "capabilities"}
        </dd>
      </dl>

      <section aria-labelledby="review-allowed" className="flex flex-col gap-2">
        <div>
          <h3 id="review-allowed" className="font-medium text-sm">
            Question types the AI may generate
          </h3>
          <p className="text-muted-foreground text-sm">
            These can be graded by what you enabled. Switch one off to keep it out of this course.
          </p>
        </div>
        {possible.length === 0 ? (
          <p className="rounded-lg border border-dashed px-4 py-3 text-muted-foreground text-sm">
            Nothing can be graded yet. Go back and enable at least one capability.
          </p>
        ) : (
          <div className="rounded-lg border bg-card">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="w-14 pl-4">
                    <span className="sr-only">Use in this course</span>
                  </TableHead>
                  <TableHead className="text-muted-foreground text-xs">Question type</TableHead>
                  <TableHead className="text-muted-foreground text-xs">
                    Student answers with
                  </TableHead>
                  <TableHead className="text-muted-foreground text-xs">Graded by</TableHead>
                  <TableHead className="pr-4 text-muted-foreground text-xs">Also uses</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {possible.map(({ type, allowed, gradedByEnabled }) => (
                  <TableRow key={type.id} className={allowed ? undefined : "text-muted-foreground"}>
                    <TableCell className="pl-4">
                      <Toggle
                        checked={allowed}
                        label={`Use ${type.label} in this course`}
                        onChange={(next) => onSwitch(type.id, next)}
                      />
                    </TableCell>
                    <TableCell>
                      <span className={allowed ? "font-medium" : "line-through"}>{type.label}</span>
                      {allowed ? null : <span className="ml-2 text-xs">Switched off</span>}
                    </TableCell>
                    <TableCell>{type.widget}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <span>{gradedByEnabled.map(capLabel).join(" or ")}</span>
                        {isAiGraded(gradedByEnabled) ? <AiGradedBadge /> : null}
                      </div>
                    </TableCell>
                    <TableCell className="pr-4 text-muted-foreground">
                      {type.alsoNeeds.length > 0 ? type.alsoNeeds.map(capLabel).join(", ") : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        {possible.some(({ gradedByEnabled }) => isAiGraded(gradedByEnabled)) ? (
          <p className="text-[var(--warn-solid)] text-xs">
            AI-graded types are practice only — their scores never count toward mastery.
          </p>
        ) : null}
      </section>

      {unavailable.length > 0 ? (
        <section aria-labelledby="review-unavailable" className="flex flex-col gap-2">
          <div>
            <h3 id="review-unavailable" className="font-medium text-sm">
              Not available for this course
            </h3>
            <p className="text-muted-foreground text-sm">
              Nothing you enabled can grade these. Enable the capability it needs, or wait for it to
              be built.
            </p>
          </div>
          <ul className="divide-y rounded-lg border">
            {unavailable.map(({ type, missing }) => (
              <li
                key={type.id}
                className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-0.5 px-4 py-2 text-sm"
              >
                <span className="text-muted-foreground">
                  {type.label} <span className="text-xs">· {type.widget}</span>
                </span>
                <span className="text-muted-foreground text-xs">{missingReason(missing)}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
