"use client";

import type React from "react";
import {
  MissingField,
  ReviewChip,
  statusTone,
} from "@/app/courses/[courseId]/review/components/review-primitives";
import { checkByName, presentText } from "@/app/courses/[courseId]/review/review-utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type {
  AnswerInputProps,
  AuthoringReviewProps,
  QuestionContent,
  QuestionTypeUI,
  ReviewContentProps,
} from "./registry";
import { ExplanationPanel } from "./review-panels";

const ANSWER_LABEL = "Your answer";

/**
 * The answer is one string, number first and unit after ("9.81 m/s^2"): the form the
 * `quantity.units` grader reads. The two fields are views onto it, split at the first space,
 * so the parent keeps owning the value and a reset to "" clears both.
 */
export function splitAnswer(value: string): { number: string; unit: string } {
  const space = value.indexOf(" ");
  if (space === -1) return { number: value, unit: "" };
  return { number: value.slice(0, space), unit: value.slice(space + 1) };
}

export function joinAnswer(number: string, unit: string): string {
  return unit === "" ? number : `${number} ${unit}`;
}

function NumericResponseAnswerInput({ question, value, onChange, onSubmit }: AnswerInputProps) {
  const { number, unit } = splitAnswer(value);
  const id = `answer-${question.attempt_id}`;
  const submitOnEnter = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      if (number !== "") onSubmit?.();
    }
  };

  return (
    <fieldset className="space-y-2">
      <legend className="font-medium text-foreground text-sm">{ANSWER_LABEL}</legend>
      <div className="flex max-w-md items-center gap-2">
        <Input
          id={id}
          aria-label="Number"
          inputMode="decimal"
          autoComplete="off"
          spellCheck={false}
          value={number}
          // A number never contains a space; dropping it keeps the split unambiguous.
          onChange={(event) => onChange(joinAnswer(event.target.value.replace(/\s/g, ""), unit))}
          onKeyDown={submitOnEnter}
          placeholder="Number"
          className="h-10 flex-[3] font-mono"
        />
        <Input
          aria-label="Unit"
          autoComplete="off"
          spellCheck={false}
          value={unit}
          onChange={(event) => onChange(joinAnswer(number, event.target.value))}
          onKeyDown={submitOnEnter}
          placeholder="Unit"
          className="h-10 flex-[2] font-mono"
        />
      </div>
      <p className="text-muted-foreground text-xs">
        {question.answer_hint ? `${question.answer_hint} ` : null}
        Use a decimal point; write powers with ^, e.g. m^3.
      </p>
    </fieldset>
  );
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** "9.81 m/s^2", or null when the stored key has no number. */
export function formatQuantity(content: QuestionContent): string | null {
  const value = finiteNumber(content.value);
  if (value === null) return null;
  const unit = typeof content.unit === "string" ? content.unit.trim() : "";
  return unit ? `${value} ${unit}` : String(value);
}

/** "within 1%", "within ±0.5 m/s^2", "within 1% or ±0.5 m/s^2"; null when unset. */
export function formatTolerance(content: QuestionContent): string | null {
  const relative = finiteNumber(content.relative_tolerance);
  const absolute = finiteNumber(content.absolute_tolerance);
  const unit = typeof content.unit === "string" ? content.unit.trim() : "";
  const parts: string[] = [];
  if (relative !== null && relative > 0) parts.push(`${Number((relative * 100).toPrecision(6))}%`);
  if (absolute !== null && absolute > 0) parts.push(`±${absolute}${unit ? ` ${unit}` : ""}`);
  return parts.length ? `within ${parts.join(" or ")}` : null;
}

function acceptedUnits(content: QuestionContent): string[] | null {
  const units = content.accepted_units;
  return Array.isArray(units) && units.length && units.every((unit) => typeof unit === "string")
    ? (units as string[])
    : null;
}

// The key and how close an answer had to be. The explanation is shown by the session screen
// itself (it is the scorer's feedback), so it is not repeated here.
function NumericResponseReview({ content, submittedAnswer }: ReviewContentProps) {
  const expected = formatQuantity(content);
  if (expected === null) return null;
  const tolerance = formatTolerance(content);
  const submitted = submittedAnswer?.trim();

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <Badge variant="secondary">Correct answer: {expected}</Badge>
      {submitted ? <Badge variant="outline">Your answer: {submitted}</Badge> : null}
      {tolerance ? (
        <span className="text-muted-foreground text-xs">Accepted {tolerance}.</span>
      ) : null}
    </div>
  );
}

function KeyRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[8rem_minmax(0,1fr)] gap-3 py-2 text-sm">
      <dt className="text-[var(--review-muted)]">{label}</dt>
      <dd className="min-w-0 text-[var(--review-foreground)]">{children}</dd>
    </div>
  );
}

function NumericResponseAuthoringReview({ detail }: AuthoringReviewProps) {
  const checks = detail.validation_checks;
  const content = detail.content ?? {};
  const value = finiteNumber(content.value);
  const unit = presentText(content.unit);
  const tolerance = formatTolerance(content);
  const accepted = acceptedUnits(content);
  const sigFigs = finiteNumber(content.sig_figs);
  const notGivenAway = checkByName(checks, "numeric_value_not_in_prompt");

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_20rem]">
      <Card className="review-panel border">
        <CardHeader>
          <CardTitle>Answer key</CardTitle>
          <CardDescription>
            Marked by converting the student's unit and comparing within the tolerance.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {value === null ? (
            <MissingField label="Value is missing." />
          ) : (
            <dl className="divide-y divide-[var(--review-border)]">
              <KeyRow label="Value">
                <span className="font-mono">{value}</span>
              </KeyRow>
              <KeyRow label="Unit">
                <span className="font-mono">{unit ?? "none (a pure number)"}</span>
              </KeyRow>
              <KeyRow label="Tolerance">{tolerance ?? "default (1%)"}</KeyRow>
              <KeyRow label="Accepted units">
                {accepted ? (
                  <span className="font-mono">{accepted.join(", ")}</span>
                ) : (
                  "any unit of the same quantity"
                )}
              </KeyRow>
              {sigFigs !== null ? (
                <KeyRow label="Significant figures">at least {sigFigs}</KeyRow>
              ) : null}
            </dl>
          )}
        </CardContent>
      </Card>
      <div className="space-y-4">
        {notGivenAway ? (
          <Card className="review-panel border">
            <CardHeader>
              <CardTitle>Prompt check</CardTitle>
              <CardDescription>{notGivenAway.evidence ?? notGivenAway.detail}</CardDescription>
            </CardHeader>
            <CardContent>
              <ReviewChip tone={statusTone(notGivenAway.passed)}>
                {notGivenAway.passed ? "answer not stated" : "prompt states the answer"}
              </ReviewChip>
            </CardContent>
          </Card>
        ) : null}
        <ExplanationPanel detail={detail} />
      </div>
    </div>
  );
}

export const numericResponse: QuestionTypeUI = {
  kind: "discrete",
  label: "Numeric response",
  shortLabel: "Numeric",
  answerLabel: ANSWER_LABEL,
  AnswerInput: NumericResponseAnswerInput,
  ReviewContent: NumericResponseReview,
  AuthoringReview: NumericResponseAuthoringReview,
};
