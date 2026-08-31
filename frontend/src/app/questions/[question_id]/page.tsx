/**
 * One question, with everything that was decided about it.
 *
 * A server component with async `params` (Next 16 removed synchronous access). It
 * shows the deterministic checks and the four advisory judges side by side, because
 * they answer different questions: validation is a gate, the panel is advice, and
 * the professor's review is the authority.
 */

import { notFound } from "next/navigation";
import { PageHeader } from "@/components/page-header";
import { QueryError } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError, api, readApiError, unwrap } from "@/lib/api/client";
import { forwardedCookieHeader } from "@/lib/api/server-request";
import type { QuestionDetail } from "@/lib/api/types";

export const dynamic = "force-dynamic";

const GATE_VARIANT = {
  approved: "default",
  needs_review: "secondary",
  reject: "destructive",
} as const;

const METRIC_LABELS = {
  issues: "Issues",
  subtopic: "Subtopic",
  difficulty: "Difficulty",
  generatability: "Generatability",
} as const;

function CodeBlock({ children }: { children: string }) {
  return (
    <pre className="overflow-x-auto rounded-md bg-muted p-3 font-mono text-xs leading-relaxed">
      <code>{children}</code>
    </pre>
  );
}

export default async function QuestionDetailPage(props: PageProps<"/questions/[question_id]">) {
  const { question_id } = await props.params;
  const id = Number(question_id);
  if (!Number.isInteger(id)) notFound();

  let detail: QuestionDetail;
  try {
    detail = await unwrap(
      api.GET("/api/questions/{question_id}", {
        params: { path: { question_id: id } },
        headers: await forwardedCookieHeader(),
      }),
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    return (
      <>
        <PageHeader title={`Question ${id}`} />
        <QueryError error={readApiError(error)} />
      </>
    );
  }

  const { question, taxonomy, validation_checks, pedagogical_eval } = detail;
  const gate = pedagogical_eval?.gate ?? null;
  // Fields with a Pydantic default are optional in the generated types, not required.
  const metrics = pedagogical_eval?.metrics ?? [];

  return (
    <>
      <PageHeader
        title={`Question ${question.id}`}
        summary={`${taxonomy.topic} - ${taxonomy.subtopics.join(", ") || "no subtopics"}`}
        actions={
          <>
            <Badge variant="outline">{question.difficulty}</Badge>
            <Badge variant={detail.validation_passed ? "secondary" : "destructive"}>
              {question.status.replace(/_/g, " ")}
            </Badge>
            {gate ? <Badge variant={GATE_VARIANT[gate]}>judges: {gate}</Badge> : null}
          </>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Prompt</CardTitle>
          <CardDescription>
            {question.question_type ?? "unclassified"} - {question.kind}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="whitespace-pre-wrap text-sm">{question.prompt}</p>
          {detail.reference_solution ? (
            <>
              <Separator />
              <div className="space-y-2">
                <p className="font-medium text-sm">Reference solution</p>
                <CodeBlock>{detail.reference_solution}</CodeBlock>
              </div>
            </>
          ) : null}
          {detail.tests ? (
            <div className="space-y-2">
              <p className="font-medium text-sm">Tests</p>
              <CodeBlock>{detail.tests}</CodeBlock>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Deterministic checks</CardTitle>
            <CardDescription>
              These decide whether the question reaches the review queue at all.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {validation_checks.length === 0 ? (
              <p className="text-muted-foreground text-sm">No checks were recorded.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Check</TableHead>
                    <TableHead>Detail</TableHead>
                    <TableHead className="w-28">Result</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {validation_checks.map((check) => (
                    <TableRow key={check.name}>
                      <TableCell className="font-mono text-xs">{check.name}</TableCell>
                      <TableCell className="max-w-80 whitespace-normal text-muted-foreground text-xs">
                        {check.detail ?? "-"}
                      </TableCell>
                      <TableCell>
                        <Badge variant={check.passed ? "secondary" : "destructive"}>
                          {check.passed ? "passed" : "failed"}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Advisory judges</CardTitle>
            <CardDescription>
              Four metrics, each compared with what the generator claimed. Advisory only.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {metrics.length === 0 ? (
              // Never render this as "all clear": an absent judge is an absent
              // measurement, not a passing verdict.
              <p className="text-muted-foreground text-sm">
                Nothing was measured{" "}
                {pedagogical_eval?.skip_reason ? `- ${pedagogical_eval.skip_reason}` : ""}.
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Metric</TableHead>
                    <TableHead className="w-28">Result</TableHead>
                    <TableHead>Rationale</TableHead>
                    <TableHead>Issue codes</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {metrics.map((metric) => (
                    <TableRow key={metric.metric}>
                      <TableCell className="font-mono text-xs">
                        {METRIC_LABELS[metric.metric]}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            metric.passed === null
                              ? "outline"
                              : metric.passed
                                ? "secondary"
                                : "destructive"
                          }
                        >
                          {metric.passed === null
                            ? "not measured"
                            : metric.passed
                              ? "pass"
                              : "fail"}
                        </Badge>
                      </TableCell>
                      <TableCell className="max-w-80 whitespace-normal text-muted-foreground text-xs">
                        {metric.rationale ?? metric.error_detail ?? "-"}
                      </TableCell>
                      <TableCell className="max-w-64 whitespace-normal">
                        {(metric.issue_codes ?? []).length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {(metric.issue_codes ?? []).map((code) => (
                              <Badge key={code} variant="outline" className="text-[10px]">
                                {code}
                              </Badge>
                            ))}
                          </div>
                        ) : (
                          <span className="text-muted-foreground text-xs">-</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
