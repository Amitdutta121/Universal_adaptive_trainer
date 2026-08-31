"use client";

import { AlertTriangle, ArrowRight, CheckCircle2, Clock3 } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import type { CoverageReport, TopicCoverage } from "@/lib/api/types";
import { sortTopicsForReadability, topicGapCount } from "../coverage-display";

function decisionFor(report: CoverageReport, prioritizedTopics: readonly TopicCoverage[]) {
  if (report.empty_cells > 0) {
    const top = prioritizedTopics.slice(0, 3).map((topic) => topic.topic_name);
    return {
      title: "Students should not train from this bank yet",
      detail:
        top.length > 0
          ? `Start by fixing ${new Intl.ListFormat("en", { style: "long", type: "conjunction" }).format(top)} before freezing or assigning this bank.`
          : "Some topic and difficulty combinations still have no usable questions.",
      tone: "danger" as const,
      icon: <AlertTriangle className="size-4" />,
    };
  }
  if (report.thin_cells > 0) {
    return {
      title: "Students can train, but some areas are too thin",
      detail: "Top up the thinnest topics before freezing a new set for a larger cohort.",
      tone: "warn" as const,
      icon: <Clock3 className="size-4" />,
    };
  }
  return {
    title: "This bank is ready for students",
    detail: "Every topic and difficulty combination has enough approved questions to assign safely.",
    tone: "success" as const,
    icon: <CheckCircle2 className="size-4" />,
  };
}

export function ReadinessSummaryCard({
  report,
  scopeLabel,
}: {
  report: CoverageReport;
  scopeLabel: string;
}) {
  const prioritizedTopics = sortTopicsForReadability(report.topics ?? []);
  const decision = decisionFor(report, prioritizedTopics);
  const worstTopic = prioritizedTopics[0] ?? null;

  return (
    <Card className="overflow-hidden border-border/70">
      <CardContent className="grid gap-0 p-0 lg:grid-cols-[1.6fr_0.8fr]">
        <div className="space-y-4 p-6">
          <div className="flex items-center gap-2 text-muted-foreground text-xs uppercase tracking-[0.18em]">
            {decision.icon}
            Decision
          </div>
          <div>
            <h2 className="font-semibold text-2xl tracking-tight">{decision.title}</h2>
            <p className="mt-2 max-w-3xl text-muted-foreground text-sm leading-6">
              {decision.detail}
            </p>
          </div>
          <div className="flex flex-wrap gap-2 text-sm">
            <span className="rounded-full bg-muted px-3 py-1">
              {report.question_count} approved questions
            </span>
            <span className="rounded-full bg-muted px-3 py-1">
              {report.empty_cells + report.thin_cells} places still need work
            </span>
            <span className="rounded-full bg-muted px-3 py-1">
              {report.total_cells - report.empty_cells - report.thin_cells} places ready now
            </span>
          </div>
        </div>

        <div className="border-border/70 border-t bg-muted/20 p-6 lg:border-t-0 lg:border-l">
          <div className="flex items-center gap-2 text-muted-foreground text-xs uppercase tracking-[0.18em]">
            <ArrowRight className="size-4" />
            Next step
          </div>
          <div className="mt-3 font-medium leading-6">
            {worstTopic
              ? `Open ${worstTopic.topic_name} first. It still has ${topicGapCount(worstTopic)} places that need work.`
              : "Review this snapshot and freeze a set when you are ready to assign it."}
          </div>
          <p className="mt-2 text-muted-foreground text-sm leading-6">
            {scopeLabel === "Live bank"
              ? "Fix the top gaps, then freeze a set."
              : "This frozen set is fixed. Use this page only to inspect what it contains."}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
