"use client";

import { AlertCircle, CheckCircle2, ChevronDown, CircleSlash } from "lucide-react";
import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { MetricResult, QuestionDetail, ReviewOut } from "../review-types";
import { DIFFICULTY_LABEL } from "../review-types";
import { ReviewChip, statusTone } from "./review-primitives";

function ExpandableText({ text, preview = 96 }: { text: string; preview?: number }) {
  const [expanded, setExpanded] = useState(false);
  if (text.length <= preview) {
    return <p className="mt-1 text-[13px] text-[var(--review-foreground-2)] leading-6">{text}</p>;
  }

  const shortText = `${text.slice(0, preview).trimEnd()}...`;
  return (
    <p className="mt-1 text-[13px] text-[var(--review-foreground-2)] leading-6">
      {expanded ? text : shortText}{" "}
      <button
        type="button"
        className="text-[var(--review-accent)] underline-offset-2 hover:underline"
        onClick={() => setExpanded((value) => !value)}
      >
        {expanded ? "Show less" : "See more"}
      </button>
    </p>
  );
}

export function ValidationSummary({ detail }: { detail: QuestionDetail }) {
  const [isOpen, setIsOpen] = useState(false);
  const failed = detail.validation_checks.filter((check) => !check.passed);
  return (
    <Card className="review-panel border">
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="review-eyebrow">Deterministic evidence</div>
            <CardTitle>Deterministic checks</CardTitle>
            <CardDescription>Recorded validation evidence for this question.</CardDescription>
          </div>
          <button
            type="button"
            className="review-collapse-trigger"
            aria-expanded={isOpen}
            onClick={() => setIsOpen((value) => !value)}
          >
            <span>{isOpen ? "Hide" : "Show"}</span>
            <ChevronDown className={isOpen ? "size-4 rotate-180" : "size-4"} />
          </button>
        </div>
      </CardHeader>
      {isOpen ? (
        <CardContent className="space-y-3">
          {detail.validation_checks.length === 0 ? (
            <p className="text-[var(--review-muted)] text-sm">No checks were recorded.</p>
          ) : (
            detail.validation_checks.map((check) => (
              <div
                key={check.name}
                className="review-judge-row"
                data-status={statusTone(check.passed)}
              >
                <div className="min-w-0 grow">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-mono text-xs">{check.name}</p>
                    <ReviewChip tone={statusTone(check.passed)}>
                      {check.passed ? "passed" : "failed"}
                    </ReviewChip>
                  </div>
                  {check.detail ? <ExpandableText text={check.detail} /> : null}
                  {check.evidence ? (
                    <p className="mt-2 whitespace-pre-wrap font-mono text-[var(--review-muted)] text-xs">
                      {check.evidence}
                    </p>
                  ) : null}
                </div>
              </div>
            ))
          )}
          {failed.length > 0 ? (
            <div className="review-banner" data-tone="critical">
              <AlertCircle className="mt-0.5 size-4 shrink-0 text-[var(--review-critical)]" />
              <div>
                <div className="review-banner-title">Blocking defects recorded</div>
                <p className="review-banner-copy">
                  {failed.length} deterministic check{failed.length === 1 ? "" : "s"} failed on this
                  question.
                </p>
              </div>
            </div>
          ) : null}
        </CardContent>
      ) : (
        <CardContent>
          <p className="text-[var(--review-muted)] text-sm">
            Hidden by default. Open to inspect validation details.
          </p>
        </CardContent>
      )}
    </Card>
  );
}

/** One row of the judge rail: a label, a pass/fail chip, and what the judge said. */
function JudgeRow({
  label,
  passed,
  verdict,
  rationale,
}: {
  label: string;
  passed: boolean | null | undefined;
  verdict?: string | null;
  rationale?: string | null;
}) {
  return (
    <div className="review-judge-row" data-status={statusTone(passed)} data-testid="judge-row">
      <div className="min-w-0 grow">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="font-medium text-sm">{label}</p>
          <ReviewChip tone={statusTone(passed)}>
            {passed == null ? "not measured" : passed ? "pass" : "fail"}
          </ReviewChip>
        </div>
        {verdict ? <p className="mt-1 text-[var(--review-muted)] text-xs">{verdict}</p> : null}
        {rationale ? <ExpandableText text={rationale} /> : null}
      </div>
    </div>
  );
}

function answerCheck(detail: QuestionDetail) {
  const checks = detail.validation_checks;
  const failed = checks.filter((check) => !check.passed);
  const passed = checks.length > 0 ? failed.length === 0 : detail.validation_passed;
  const verdict =
    failed.length > 0
      ? `Failed: ${failed.map((check) => check.name).join(", ")}`
      : checks.length > 0
        ? `${checks.length} check${checks.length === 1 ? "" : "s"} passed`
        : null;
  return { passed, verdict };
}

function metricOf(detail: QuestionDetail, id: MetricResult["metric"]) {
  return detail.pedagogical_eval?.metrics?.find((metric) => metric.metric === id) ?? null;
}

/**
 * The judges a professor weighs a question against: the deterministic answer check, the
 * difficulty and topic judges, and one row per custom rule. Issues and generatability are
 * not shown even when an older question still carries them.
 */
export function JudgeRail({
  detail,
  subtopicNames,
}: {
  detail: QuestionDetail;
  /** Taxonomy subtopic id → name, to spell out the topic judge's proposal. */
  subtopicNames?: ReadonlyMap<number, string>;
}) {
  const evaluation = detail.pedagogical_eval;
  const answer = answerCheck(detail);
  const difficulty = metricOf(detail, "difficulty");
  const subtopic = metricOf(detail, "subtopic");
  const customResults = detail.custom_results ?? [];

  const proposedSubtopics = (subtopic?.proposed_subtopic_ids ?? []).map(
    (id) => subtopicNames?.get(id) ?? `#${id}`,
  );

  return (
    <Card className="review-panel border">
      <CardHeader>
        <div className="review-eyebrow">Panel</div>
        <CardTitle>Judges</CardTitle>
        <CardDescription>Advisory only; your verdict below is what counts.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <JudgeRow label="Answer check" passed={answer.passed} verdict={answer.verdict} />
        <JudgeRow
          label="Difficulty"
          passed={difficulty?.passed}
          verdict={
            difficulty?.proposed_difficulty
              ? `Judge says ${DIFFICULTY_LABEL[difficulty.proposed_difficulty]}`
              : null
          }
          rationale={difficulty?.rationale ?? difficulty?.error_detail}
        />
        <JudgeRow
          label="Topic"
          passed={subtopic?.passed}
          verdict={
            proposedSubtopics.length > 0 ? `Judge says ${proposedSubtopics.join(", ")}` : null
          }
          rationale={subtopic?.rationale ?? subtopic?.error_detail}
        />
        {customResults.map((result) => (
          <JudgeRow
            key={result.judge_id}
            label={result.rule_text}
            passed={result.passed}
            verdict={result.kind === "pattern" ? "Custom rule - pattern" : "Custom rule"}
            rationale={result.reason}
          />
        ))}
        {!difficulty && !subtopic && evaluation?.skip_reason ? (
          <p className="text-[var(--review-muted)] text-xs">
            Judges did not run - {evaluation.skip_reason}.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function OutcomeBanner({ review }: { review: ReviewOut }) {
  const outcome = review.outcome;
  if (!outcome) {
    return (
      <div className="review-banner" data-tone="muted">
        <CircleSlash className="mt-0.5 size-4 shrink-0 text-[var(--review-muted)]" />
        <div>
          <div className="review-banner-title">Review saved - nothing was measured</div>
          <p className="review-banner-copy">
            The verdict landed, but this question had no completed judge outcome to compare against.
          </p>
        </div>
      </div>
    );
  }

  const destructive = outcome.cell === "missed" || outcome.cell === "confirmed_bad";
  return (
    <div className="review-banner" data-tone={destructive ? "critical" : "ok"}>
      {destructive ? (
        <AlertCircle className="mt-0.5 size-4 shrink-0 text-[var(--review-critical)]" />
      ) : (
        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-[var(--review-ok)]" />
      )}
      <div className="min-w-0 grow">
        <div className="review-banner-title">{outcome.cell.replace(/_/g, " ")}</div>
        <div className="review-banner-copy space-y-1">
          <p>{outcome.action}</p>
          {outcome.attributed_labels.length > 0 ? (
            <p>Judges named at fault: {outcome.attributed_labels.join(", ")}.</p>
          ) : null}
          {outcome.refresh_error ? <p>{outcome.refresh_error}</p> : null}
        </div>
      </div>
    </div>
  );
}
