"use client";

import { AlertCircle, CheckCircle2, ChevronDown, CircleSlash } from "lucide-react";
import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { MetricResult, QuestionDetail, ReviewOut } from "../review-types";
import { METRIC_LABEL } from "../review-types";
import { labelize } from "../review-utils";
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

function MetricCard({ metric }: { metric: MetricResult }) {
  const issueCodes = metric.issue_codes ?? [];
  return (
    <div className="review-judge-row" data-status={statusTone(metric.passed)}>
      <div className="min-w-0 grow">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-medium">{METRIC_LABEL[metric.metric] ?? metric.metric}</p>
          <ReviewChip tone={statusTone(metric.passed)}>
            {metric.passed === null ? "not measured" : metric.passed ? "pass" : "fail"}
          </ReviewChip>
        </div>
        {metric.rationale ? <ExpandableText text={metric.rationale} /> : null}
        {issueCodes.length > 0 ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {issueCodes.map((code) => (
              <ReviewChip key={code}>{code}</ReviewChip>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function JudgeRail({ detail }: { detail: QuestionDetail }) {
  const [showDescription, setShowDescription] = useState(false);
  const evaluation = detail.pedagogical_eval;
  const metrics = evaluation?.metrics ?? [];
  const gateTone =
    evaluation?.gate === "approved"
      ? "ok"
      : evaluation?.gate === "needs_review"
        ? "warn"
        : evaluation?.gate
          ? "critical"
          : "muted";

  return (
    <Card className="review-panel border">
      <CardHeader>
        <div className="review-eyebrow">Panel</div>
        <CardTitle>Advisory judges</CardTitle>
        <CardDescription>
          Advisory only.
          {!showDescription ? (
            <>
              {" "}
              <button
                type="button"
                className="text-[var(--review-accent)] underline-offset-2 hover:underline"
                onClick={() => setShowDescription(true)}
              >
                See more
              </button>
            </>
          ) : (
            <>
              {" "}
              Secondary on purpose; the professor review remains the authority.{" "}
              <button
                type="button"
                className="text-[var(--review-accent)] underline-offset-2 hover:underline"
                onClick={() => setShowDescription(false)}
              >
                Show less
              </button>
            </>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {evaluation?.gate ? (
          <ReviewChip tone={gateTone}>judges: {labelize(evaluation.gate)}</ReviewChip>
        ) : null}
        {metrics.length === 0 ? (
          <p className="text-[var(--review-muted)] text-sm">
            Nothing was measured{evaluation?.skip_reason ? ` - ${evaluation.skip_reason}` : ""}.
          </p>
        ) : (
          metrics.map((metric) => <MetricCard key={metric.metric} metric={metric} />)
        )}
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
