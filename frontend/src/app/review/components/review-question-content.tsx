"use client";

import { AlertCircle, CheckCircle2 } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import type { QuestionDetail } from "../review-types";
import {
  checkByName,
  explanation,
  occurrenceKeys,
  presentBlocks,
  presentStringArray,
  presentTests,
  presentText,
} from "../review-utils";
import { CodeBlock, MissingField, ReviewChip, statusTone } from "./review-primitives";

type ReviewQuestionContentProps = {
  detail: QuestionDetail;
  isInlineEditing: boolean;
  promptEdit: string;
  referenceEdit: string;
  testsEdit: string;
  onPromptEdit: (value: string) => void;
  onReferenceEdit: (value: string) => void;
  onTestsEdit: (value: string) => void;
};

function ExplanationPanel({ detail }: { detail: QuestionDetail }) {
  const text = explanation(detail);
  if (!text) return null;
  return (
    <Card className="review-panel border">
      <CardHeader>
        <CardTitle>Explanation</CardTitle>
        <CardDescription>Shown to the student after answering.</CardDescription>
      </CardHeader>
      <CardContent>
        <p className="whitespace-pre-wrap text-[14px] text-[var(--review-foreground-2)] leading-7">
          {text}
        </p>
      </CardContent>
    </Card>
  );
}

function TestsPanel({
  detail,
  isInlineEditing,
  testsEdit,
  onTestsEdit,
}: {
  detail: QuestionDetail;
  isInlineEditing: boolean;
  testsEdit: string;
  onTestsEdit: (value: string) => void;
}) {
  const tests = presentTests(detail.content?.tests);
  const harness = checkByName(detail.validation_checks, "harness_valid");
  const reference = checkByName(detail.validation_checks, "reference_passes_tests");

  return (
    <Card className="review-panel border">
      <CardHeader>
        <CardTitle>Tests</CardTitle>
        <CardDescription className="flex flex-wrap items-center gap-2">
          {reference ? (
            <ReviewChip tone={statusTone(reference.passed)}>
              {reference.detail ?? (reference.passed ? "reference passes" : "reference failed")}
            </ReviewChip>
          ) : null}
          {harness ? (
            <ReviewChip tone={statusTone(harness.passed)}>
              {harness.passed ? "harness valid" : "invalid harness"}
            </ReviewChip>
          ) : null}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isInlineEditing ? (
          <Textarea
            rows={8}
            value={testsEdit}
            onChange={(event) => onTestsEdit(event.target.value)}
            className="review-textarea font-mono text-xs"
          />
        ) : !tests ? (
          <MissingField label="Tests are missing." />
        ) : (
          <TestsTable tests={tests} referencePassed={reference?.passed ?? false} />
        )}
      </CardContent>
    </Card>
  );
}

function TestsTable({
  tests,
  referencePassed,
}: {
  tests: Array<{ stdin: string; stdout?: string | null; assert?: string | null }>;
  referencePassed: boolean;
}) {
  const rowKeys = occurrenceKeys(
    tests,
    (test) => `${test.stdin}::${test.stdout ?? ""}::${test.assert ?? ""}`,
  );

  return (
    <div className="overflow-x-auto rounded-[0.8rem] border border-[var(--review-border)] bg-[var(--review-panel)]">
      <table className="w-full text-left text-sm">
        <thead className="bg-[var(--review-panel-2)] font-mono text-[10.5px] text-[var(--review-muted)] uppercase tracking-[0.12em]">
          <tr>
            <th className="px-3 py-2">stdin</th>
            <th className="px-3 py-2">expects</th>
            <th className="px-3 py-2">reference</th>
          </tr>
        </thead>
        <tbody>
          {tests.map((test, index) => (
            <tr key={rowKeys[index]} className="border-[var(--review-border)] border-t">
              <td className="whitespace-pre-wrap px-3 py-2 align-top font-mono text-xs">
                {test.stdin || "--"}
              </td>
              <td className="px-3 py-2 align-top">
                <div className="space-y-1 whitespace-pre-wrap font-mono text-xs">
                  {test.stdout ? <div>stdout: {test.stdout}</div> : null}
                  {test.assert ? <div>{test.assert}</div> : null}
                </div>
              </td>
              <td className="px-3 py-2 align-top text-[var(--review-muted)] text-xs">
                {referencePassed ? "pass" : "see summary"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReferencePanel({
  title,
  description,
  value,
  isInlineEditing,
  onChange,
  missingLabel,
}: {
  title: string;
  description: string;
  value: string;
  isInlineEditing: boolean;
  onChange: (value: string) => void;
  missingLabel: string;
}) {
  return (
    <Card className="review-panel border">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        {isInlineEditing ? (
          <Textarea
            rows={7}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            className="review-textarea font-mono text-xs"
          />
        ) : value ? (
          <CodeBlock>{value}</CodeBlock>
        ) : (
          <MissingField label={missingLabel} />
        )}
      </CardContent>
    </Card>
  );
}

function computeAddedLines(stub: string, reference: string) {
  const stubLines = stub.replace(/\r\n/g, "\n").split("\n");
  const referenceLines = reference.replace(/\r\n/g, "\n").split("\n");
  const added = new Set<number>();
  let stubIndex = 0;

  referenceLines.forEach((line, index) => {
    if (stubIndex < stubLines.length && line === stubLines[stubIndex]) {
      stubIndex += 1;
      return;
    }
    added.add(index);
  });

  return { stubLines, referenceLines, addedCount: added.size, added };
}

function CodeCompletionDiff({
  stub,
  reference,
}: {
  stub: string;
  reference: string;
}) {
  const { stubLines, referenceLines, addedCount, added } = computeAddedLines(stub, reference);

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card className="review-panel border">
        <CardHeader>
          <div className="flex items-center gap-2">
            <CardTitle>Given to the student</CardTitle>
            <ReviewChip>stub</ReviewChip>
          </div>
        </CardHeader>
        <CardContent>
          <div className="review-diff-shell">
            <pre className="review-diff-code">
              {stubLines.map((line, index) => (
                <div key={`stub-${index}`} className="review-diff-line">
                  {line || " "}
                </div>
              ))}
            </pre>
          </div>
        </CardContent>
      </Card>

      <Card className="review-panel border">
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <CardTitle>Reference solution</CardTitle>
              <ReviewChip>key</ReviewChip>
            </div>
            <span className="review-diff-meta">
              +{addedCount} {addedCount === 1 ? "line" : "lines"} over the stub
            </span>
          </div>
        </CardHeader>
        <CardContent>
          <div className="review-diff-shell">
            <pre className="review-diff-code">
              {referenceLines.map((line, index) => (
                <div
                  key={`ref-${index}`}
                  className={added.has(index) ? "review-diff-line review-diff-line-added" : "review-diff-line"}
                >
                  {line || " "}
                </div>
              ))}
            </pre>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export function ReviewQuestionSurface({
  detail,
  isInlineEditing,
  promptEdit,
  onPromptEdit,
}: Pick<
  ReviewQuestionContentProps,
  "detail" | "isInlineEditing" | "promptEdit" | "onPromptEdit"
>) {
  return (
    <Card className="review-panel border">
      <CardHeader>
        <div className="review-eyebrow">Question surface</div>
        <CardTitle className="flex flex-wrap items-center gap-2">
          <span>Question {detail.question.id}</span>
          <ReviewChip>{detail.question.difficulty}</ReviewChip>
          <ReviewChip tone="accent">{detail.question.question_type ?? detail.question.kind}</ReviewChip>
        </CardTitle>
        <CardDescription>
          {detail.taxonomy.topic} - {detail.taxonomy.subtopics.join(", ")}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {isInlineEditing ? (
          <Textarea
            rows={7}
            value={promptEdit}
            onChange={(event) => onPromptEdit(event.target.value)}
            className="review-textarea"
          />
        ) : (
          <p className="whitespace-pre-wrap text-[15px] text-[var(--review-foreground)] leading-7">
            {detail.question.prompt}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export function ReviewQuestionContent(props: ReviewQuestionContentProps) {
  const { detail, isInlineEditing, referenceEdit, onReferenceEdit } = props;
  const questionType = detail.question.question_type;
  const checks = detail.validation_checks;
  const content = detail.content ?? {};

  if (questionType === "multiple_choice") {
    const options = presentStringArray(content.options) ?? [];
    const optionKeys = occurrenceKeys(options, (option) => option);
    const correctIndex =
      typeof content.correct_option_index === "number" ? content.correct_option_index : null;
    const duplicateCheck = checkByName(checks, "mc_no_duplicate_options");
    return (
      <div className="space-y-4">
        <Card className="review-panel border">
          <CardHeader>
            <CardTitle>Options</CardTitle>
            <CardDescription className="flex flex-wrap items-center gap-2">
              <ReviewChip>{options.length} options</ReviewChip>
              {duplicateCheck ? (
                <ReviewChip tone={statusTone(duplicateCheck.passed)}>
                  {duplicateCheck.passed ? "no duplicates" : "duplicate options"}
                </ReviewChip>
              ) : null}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {options.map((option, index) => (
              <div
                key={optionKeys[index]}
                className={[
                  "flex items-start gap-3 rounded-[0.75rem] border px-3 py-3",
                  index === correctIndex
                    ? "review-panel-muted border-[var(--review-accent)]"
                    : "review-panel border",
                ].join(" ")}
              >
                <div className="pt-1 font-mono text-[var(--review-muted)] text-xs">
                  {String.fromCharCode(65 + index)}
                </div>
                <div className="grow">
                  <CodeBlock>{option}</CodeBlock>
                </div>
                {index === correctIndex ? <ReviewChip tone="accent">correct</ReviewChip> : null}
              </div>
            ))}
          </CardContent>
        </Card>
        <ExplanationPanel detail={detail} />
      </div>
    );
  }

  if (questionType === "true_false") {
    const correct = typeof content.correct_answer === "boolean" ? content.correct_answer : null;
    return (
      <div className="space-y-4">
        <Card className="review-panel border">
          <CardHeader>
            <CardTitle>Answer</CardTitle>
            <CardDescription>Compact key for the binary claim.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap items-center gap-2">
              <ReviewChip tone={correct === true ? "ok" : "muted"}>True</ReviewChip>
              <ReviewChip tone={correct === false ? "ok" : "muted"}>False</ReviewChip>
              <Separator orientation="vertical" className="hidden h-4 sm:block" />
              <span className="text-[var(--review-muted)] text-xs">
                {checkByName(checks, "tf_boolean_answer")?.passed
                  ? "boolean answer recorded"
                  : "answer missing"}
              </span>
            </div>
          </CardContent>
        </Card>
        <ExplanationPanel detail={detail} />
      </div>
    );
  }

  if (questionType === "output_prediction") {
    const source = presentText(content.code);
    const expected = presentText(content.expected_output);
    const observed = checkByName(checks, "expected_output_verified");
    return (
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <Card className="review-panel border">
          <CardHeader>
            <CardTitle>Code</CardTitle>
            <CardDescription>The student reads and reasons about this script.</CardDescription>
          </CardHeader>
          <CardContent>
            {source ? <CodeBlock>{source}</CodeBlock> : <MissingField label="Code is missing." />}
          </CardContent>
        </Card>
        <div className="space-y-4">
          <Card className="review-panel border">
            <CardHeader>
              <CardTitle>Expected output</CardTitle>
              <CardDescription>What the generator claimed.</CardDescription>
            </CardHeader>
            <CardContent>
              {expected ? <CodeBlock>{expected}</CodeBlock> : <MissingField label="Expected output is missing." />}
            </CardContent>
          </Card>
          <Card className="review-panel border">
            <CardHeader>
              <CardTitle>Observed by deterministic check</CardTitle>
              <CardDescription>
                {observed?.passed ? "Matches the claimed output." : "Interpreter evidence from validation."}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {observed?.evidence ? (
                <CodeBlock>{observed.evidence}</CodeBlock>
              ) : (
                <ReviewChip tone={statusTone(observed?.passed)}>
                  {observed?.passed ? "verified" : "no observed output recorded"}
                </ReviewChip>
              )}
            </CardContent>
          </Card>
          <ExplanationPanel detail={detail} />
        </div>
      </div>
    );
  }

  if (questionType === "code_completion") {
    const source = presentText(content.code);
    return (
      <div className="space-y-4">
        {isInlineEditing ? (
          <div className="grid gap-4 xl:grid-cols-2">
            <Card className="review-panel border">
              <CardHeader>
                <CardTitle>Given to the student</CardTitle>
                <CardDescription>The stub and its gap.</CardDescription>
              </CardHeader>
              <CardContent>
                {source ? <CodeBlock>{source}</CodeBlock> : <MissingField label="Stub is missing." />}
              </CardContent>
            </Card>
            <ReferencePanel
              title="Reference solution"
              description="The full key, read as what the stub needs."
              value={referenceEdit}
              isInlineEditing={isInlineEditing}
              onChange={onReferenceEdit}
              missingLabel="Reference solution is missing."
            />
          </div>
        ) : source && referenceEdit ? (
          <CodeCompletionDiff stub={source} reference={referenceEdit} />
        ) : (
          <div className="grid gap-4 xl:grid-cols-2">
            <Card className="review-panel border">
              <CardHeader>
                <CardTitle>Given to the student</CardTitle>
              </CardHeader>
              <CardContent>
                {source ? <CodeBlock>{source}</CodeBlock> : <MissingField label="Stub is missing." />}
              </CardContent>
            </Card>
            <ReferencePanel
              title="Reference solution"
              description="The full key, read as what the stub needs."
              value={referenceEdit}
              isInlineEditing={false}
              onChange={onReferenceEdit}
              missingLabel="Reference solution is missing."
            />
          </div>
        )}
        <TestsPanel
          detail={detail}
          isInlineEditing={isInlineEditing}
          testsEdit={props.testsEdit}
          onTestsEdit={props.onTestsEdit}
        />
        <ExplanationPanel detail={detail} />
      </div>
    );
  }

  if (questionType === "debugging") {
    const broken = presentText(content.code);
    const bugCheck = checkByName(checks, "debug_broken_exhibits_issue");
    return (
      <div className="space-y-4">
        <div className="grid gap-4 xl:grid-cols-2">
          <Card className="review-panel border">
            <CardHeader>
              <CardTitle>Broken code</CardTitle>
              <CardDescription>The student should fix this version.</CardDescription>
            </CardHeader>
            <CardContent>
              {broken ? <CodeBlock>{broken}</CodeBlock> : <MissingField label="Broken code is missing." />}
            </CardContent>
          </Card>
          <ReferencePanel
            title="Fixed reference"
            description="The stored repair."
            value={referenceEdit}
            isInlineEditing={isInlineEditing}
            onChange={onReferenceEdit}
            missingLabel="Reference solution is missing."
          />
        </div>
        <Alert variant={bugCheck?.passed ? "default" : "destructive"}>
          {bugCheck?.passed ? <CheckCircle2 /> : <AlertCircle />}
          <AlertTitle>{bugCheck?.passed ? "Bug confirmed" : "Broken code did not exhibit the issue"}</AlertTitle>
          <AlertDescription>
            {bugCheck?.evidence ? (
              <p className="whitespace-pre-wrap font-mono text-xs">{bugCheck.evidence}</p>
            ) : (
              <p>{bugCheck?.detail ?? "No deterministic evidence was recorded."}</p>
            )}
          </AlertDescription>
        </Alert>
        <TestsPanel
          detail={detail}
          isInlineEditing={isInlineEditing}
          testsEdit={props.testsEdit}
          onTestsEdit={props.onTestsEdit}
        />
        <ExplanationPanel detail={detail} />
      </div>
    );
  }

  if (questionType === "parsons") {
    const blocks = presentBlocks(content.blocks);
    const order = presentStringArray(content.correct_order) ?? [];
    const compiled = checkByName(checks, "parsons_reference_compiles");
    const assembled =
      blocks && order.length
        ? order
            .map((id) => blocks.find((block) => block.id === id))
            .filter((block): block is NonNullable<typeof block> => Boolean(block))
            .map((block) => `${" ".repeat(block.indent * 4)}${block.text}`)
            .join("\n")
        : null;
    return (
      <div className="space-y-4">
        <div className="grid gap-4 xl:grid-cols-2">
          <Card className="review-panel border">
            <CardHeader>
              <CardTitle>Blocks</CardTitle>
              <CardDescription>The student sees these shuffled.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {blocks ? (
                blocks.map((block) => (
                  <div
                    key={block.id}
                    className="review-panel-muted whitespace-pre-wrap rounded-[0.7rem] border px-3 py-2 font-mono text-xs"
                  >
                    {`${" ".repeat(block.indent * 4)}${block.text}`}
                  </div>
                ))
              ) : (
                <MissingField label="Blocks are missing." />
              )}
            </CardContent>
          </Card>
          <Card className="review-panel border">
            <CardHeader>
              <CardTitle>Assembled in canonical order</CardTitle>
              <CardDescription>
                {compiled?.passed ? "Reconstruction compiles." : "Reconstruction or compilation failed."}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {assembled ? <CodeBlock>{assembled}</CodeBlock> : <MissingField label="Correct order is missing." />}
              {compiled?.evidence ? (
                <Alert variant="destructive">
                  <AlertCircle />
                  <AlertTitle>Compile evidence</AlertTitle>
                  <AlertDescription>
                    <p className="whitespace-pre-wrap font-mono text-xs">{compiled.evidence}</p>
                  </AlertDescription>
                </Alert>
              ) : null}
            </CardContent>
          </Card>
        </div>
        <ExplanationPanel detail={detail} />
      </div>
    );
  }

  if (questionType === "coding") {
    return (
      <div className="space-y-4">
        <ReferencePanel
          title="Reference solution"
          description="The current stored answer."
          value={referenceEdit}
          isInlineEditing={isInlineEditing}
          onChange={onReferenceEdit}
          missingLabel="Reference solution is missing."
        />
        <TestsPanel
          detail={detail}
          isInlineEditing={isInlineEditing}
          testsEdit={props.testsEdit}
          onTestsEdit={props.onTestsEdit}
        />
        <ExplanationPanel detail={detail} />
      </div>
    );
  }

  return (
    <Card className="review-panel border">
      <CardHeader>
        <CardTitle>Question body</CardTitle>
        <CardDescription>This question has no specialized renderer yet.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="whitespace-pre-wrap text-[14px] leading-7">{detail.question.prompt}</p>
        {referenceEdit ? <CodeBlock>{referenceEdit}</CodeBlock> : null}
      </CardContent>
    </Card>
  );
}
