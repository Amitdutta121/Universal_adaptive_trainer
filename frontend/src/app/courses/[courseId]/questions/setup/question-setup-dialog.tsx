"use client";

/**
 * "Set up questions": a large modal opened from the Questions page header
 * (docs/QUESTION_SETUP_PLAN.md, agent D).
 *
 *   1. Suggest — on open the AI suggests library styles per subtopic and a target per
 *      subtopic x difficulty cell.
 *   2. Styles  — per topic and subtopic the professor uses or skips each suggested style and
 *      can add others from the library. Every subtopic needs at least one approved style.
 *   3. Targets — the AI's counts, read-only, and the total. Approve saves the setup; the backend
 *      starts round 1 in the background and the professor lands on the review queue.
 *
 * Mount it only while open (`{open ? <QuestionSetupDialog … /> : null}`) so each opening asks
 * for a fresh suggestion and starts from clean choices.
 */

import { Check, LoaderCircle, Plus, TriangleAlert, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { QueryError } from "@/components/query-state";
import { DifficultyBadge } from "@/components/question-setup/badges";
import { StyleRow, type StyleRowStyle } from "@/components/question-setup/style-row";
import { DIFFICULTIES } from "@/components/question-setup/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useSaveSetup, useSetupSuggestion, useStyles } from "@/lib/api/queries";
import type { CurriculumVersionDetail, QuestionSetup, SetupSuggestion } from "@/lib/api/types";
import { useCoursePath } from "@/lib/use-course";
import { cn } from "@/lib/utils";
import { CustomRules } from "./custom-rules";
import {
  addStyle,
  approveAllUndecided,
  approvedStyleIds,
  decide,
  FIRST_ROUND_SIZE,
  initialChoices,
  removeStyle,
  rowTotal,
  type SetupChoices,
  type SetupSubtopic,
  type SetupTopic,
  saveRequest,
  setupTopics,
  subtopicsWithoutStyle,
  targetsBySubtopic,
  undecidedCount,
} from "./setup-state";

/** A library style as the API client returns it. */
type QuestionStyle = StyleRowStyle & { id: string };

type Step = "styles" | "targets";

export function QuestionSetupDialog({
  curriculum,
  currentSetup,
  suggestionSession,
  onOpenChange,
}: {
  curriculum: CurriculumVersionDetail;
  currentSetup: QuestionSetup | null;
  /** Changes each time the dialog opens, so that opening asks for a new suggestion. */
  suggestionSession: number;
  onOpenChange(open: boolean): void;
}) {
  const curriculumVersionId = curriculum.version.id;
  const suggest = useSetupSuggestion(curriculumVersionId, suggestionSession);
  const styles = useStyles();

  const failed = suggest.error ?? styles.error;
  const ready = suggest.data && styles.data;

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[92vh] w-[96vw] max-w-none flex-col gap-0 overflow-hidden p-0 sm:max-w-[min(96vw,1200px)]">
        <DialogHeader className="border-b px-6 py-4">
          <DialogTitle>{currentSetup ? "Edit question setup" : "Set up questions"}</DialogTitle>
          <DialogDescription>
            For each subtopic of {curriculum.version.label}, choose the kinds of questions the AI
            writes. It suggests styles from the library and how many questions each difficulty
            needs; you approve or skip.
          </DialogDescription>
        </DialogHeader>

        {failed ? (
          <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-6 py-5">
            <QueryError error={failed} />
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Close
              </Button>
              <Button
                onClick={() => {
                  if (suggest.error) void suggest.refetch();
                  if (styles.error) void styles.refetch();
                }}
              >
                Try again
              </Button>
            </div>
          </div>
        ) : ready ? (
          <SetupSteps
            curriculum={curriculum}
            currentSetup={currentSetup}
            suggestion={suggest.data}
            library={styles.data.styles}
            onOpenChange={onOpenChange}
          />
        ) : (
          <div
            role="status"
            className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center"
          >
            <LoaderCircle className="size-5 animate-spin text-muted-foreground" aria-hidden />
            <p className="text-sm">Suggesting question styles for your taxonomy…</p>
            <p className="max-w-sm text-muted-foreground text-xs">
              The AI reads each subtopic against the style library. This takes a few seconds.
            </p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function SetupSteps({
  curriculum,
  currentSetup,
  suggestion,
  library,
  onOpenChange,
}: {
  curriculum: CurriculumVersionDetail;
  currentSetup: QuestionSetup | null;
  suggestion: SetupSuggestion;
  library: readonly QuestionStyle[];
  onOpenChange(open: boolean): void;
}) {
  const router = useRouter();
  const toCourse = useCoursePath();
  const save = useSaveSetup();
  const topics = useMemo(() => setupTopics(curriculum, suggestion), [curriculum, suggestion]);
  const [choices, setChoices] = useState<SetupChoices>(() => initialChoices(topics, currentSetup));
  const [step, setStep] = useState<Step>("styles");
  const styleById = useMemo(() => new Map(library.map((style) => [style.id, style])), [library]);

  const missing = subtopicsWithoutStyle(choices, topics);
  const undecided = undecidedCount(choices, topics);
  const subtopicCount = topics.reduce((sum, topic) => sum + topic.subtopics.length, 0);

  function approve() {
    save.mutate(saveRequest(curriculum.version.id, choices, topics, suggestion.cell_targets), {
      onSuccess: (result) => {
        toast.success("Setup saved", {
          description: `Round 1 (${FIRST_ROUND_SIZE} questions) is generating. They arrive in the review queue.`,
          id: `setup-${result.setup_id}`,
        });
        onOpenChange(false);
        router.push(toCourse("/review"));
      },
    });
  }

  return (
    <>
      <div className="flex-1 overflow-y-auto px-6 py-5">
        {step === "styles" ? (
          <StylesStep
            topics={topics}
            choices={choices}
            onChoices={setChoices}
            styleById={styleById}
            library={library}
            undecided={undecided}
          />
        ) : (
          <TargetsStep topics={topics} choices={choices} suggestion={suggestion} />
        )}
        <CustomRules curriculumVersionId={curriculum.version.id} />
        {save.error ? (
          <div className="mt-4">
            <QueryError error={save.error} />
          </div>
        ) : null}
      </div>

      <div className="flex flex-col gap-3 border-t px-6 py-3 sm:flex-row sm:items-center">
        <p className="text-muted-foreground text-xs tabular-nums">
          Step {step === "styles" ? 2 : 3} of 3 · {subtopicCount - missing.length} of{" "}
          {subtopicCount} subtopics have a style
        </p>
        {missing.length > 0 ? (
          <p
            role="alert"
            className="flex items-start gap-1.5 text-[var(--warn-solid)] text-sm sm:mr-auto"
          >
            <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
            <span>
              {missingMessage(missing)} Use or add at least one style for each before approving.
            </span>
          </p>
        ) : (
          <span className="sm:mr-auto" />
        )}
        <div className="flex items-center gap-2">
          {step === "styles" ? (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button onClick={() => setStep("targets")}>Review targets</Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={() => setStep("styles")} disabled={save.isPending}>
                Back
              </Button>
              <Button onClick={approve} disabled={missing.length > 0 || save.isPending}>
                {save.isPending ? (
                  <LoaderCircle data-icon="inline-start" className="animate-spin" />
                ) : null}
                Approve and generate round 1
              </Button>
            </>
          )}
        </div>
      </div>
    </>
  );
}

function missingMessage(missing: readonly SetupSubtopic[]): string {
  const names = missing.slice(0, 3).map((subtopic) => subtopic.name);
  const more = missing.length - names.length;
  const list = more > 0 ? `${names.join(", ")} and ${more} more` : names.join(", ");
  return missing.length === 1
    ? `${list} has no style.`
    : `${missing.length} subtopics have no style: ${list}.`;
}

function StylesStep({
  topics,
  choices,
  onChoices,
  styleById,
  library,
  undecided,
}: {
  topics: readonly SetupTopic[];
  choices: SetupChoices;
  onChoices(update: (choices: SetupChoices) => SetupChoices): void;
  styleById: ReadonlyMap<string, QuestionStyle>;
  library: readonly QuestionStyle[];
  undecided: number;
}) {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-3">
        <p className="mr-auto text-muted-foreground text-sm">
          {undecided > 0
            ? `${undecided} suggested ${undecided === 1 ? "style is" : "styles are"} waiting for a decision. Open Examples to see two questions written in a style.`
            : "Every suggestion has a decision. You can still change any of them."}
        </p>
        {undecided > 0 ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => onChoices((current) => approveAllUndecided(current, topics))}
          >
            Use all remaining suggestions
          </Button>
        ) : null}
      </div>

      {topics.map((topic) => (
        <section
          key={topic.id}
          aria-labelledby={`setup-topic-${topic.id}`}
          className="flex flex-col gap-3"
        >
          <h3 id={`setup-topic-${topic.id}`} className="font-semibold text-sm">
            {topic.name}
          </h3>
          {topic.subtopics.map((subtopic) => (
            <SubtopicStyles
              key={subtopic.id}
              subtopic={subtopic}
              choices={choices}
              onChoices={onChoices}
              styleById={styleById}
              library={library}
            />
          ))}
        </section>
      ))}
    </div>
  );
}

function SubtopicStyles({
  subtopic,
  choices,
  onChoices,
  styleById,
  library,
}: {
  subtopic: SetupSubtopic;
  choices: SetupChoices;
  onChoices(update: (choices: SetupChoices) => SetupChoices): void;
  styleById: ReadonlyMap<string, QuestionStyle>;
  library: readonly QuestionStyle[];
}) {
  const suggested = subtopic.suggestion?.style_ids ?? [];
  const added = (choices.added[subtopic.id] ?? []).filter((id) => !suggested.includes(id));
  const approvedCount = approvedStyleIds(choices, subtopic).length;
  const addable = library.filter(
    (style) => !suggested.includes(style.id) && !added.includes(style.id),
  );
  const verdicts = choices.verdicts[subtopic.id] ?? {};

  return (
    <article
      aria-label={subtopic.name}
      className={cn("rounded-lg border", approvedCount === 0 && "border-[var(--warn-solid)]/50")}
    >
      <header className="flex flex-col gap-1 border-b px-3 py-2.5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h4 className="font-medium text-sm">{subtopic.name}</h4>
          <span
            className={cn(
              "text-xs tabular-nums",
              approvedCount === 0 ? "text-[var(--warn-solid)]" : "text-muted-foreground",
            )}
          >
            {approvedCount === 0
              ? "No style yet"
              : `${approvedCount} ${approvedCount === 1 ? "style" : "styles"} in use`}
          </span>
        </div>
        <p className="text-muted-foreground text-xs">
          {subtopic.suggestion?.reason
            ? `Why these: ${subtopic.suggestion.reason}`
            : "The AI made no suggestion for this subtopic. Add a style from the library."}
        </p>
      </header>

      {suggested.length + added.length > 0 ? (
        <ul className="divide-y">
          {suggested.map((styleId) => {
            const style = styleById.get(styleId);
            const verdict = verdicts[styleId];
            if (!style) return <UnknownStyle key={styleId} styleId={styleId} />;
            return (
              <StyleRow
                key={styleId}
                style={style}
                muted={verdict === "skipped"}
                controls={
                  <div className="flex items-center gap-1">
                    <Button
                      size="sm"
                      variant={verdict === "skipped" ? "secondary" : "outline"}
                      aria-pressed={verdict === "skipped"}
                      onClick={() =>
                        onChoices((current) => decide(current, subtopic.id, styleId, "skipped"))
                      }
                    >
                      <X data-icon="inline-start" />
                      Skip
                    </Button>
                    <Button
                      size="sm"
                      variant={verdict === "approved" ? "default" : "outline"}
                      aria-pressed={verdict === "approved"}
                      onClick={() =>
                        onChoices((current) => decide(current, subtopic.id, styleId, "approved"))
                      }
                    >
                      <Check data-icon="inline-start" />
                      Use
                    </Button>
                  </div>
                }
              />
            );
          })}
          {added.map((styleId) => {
            const style = styleById.get(styleId);
            if (!style) return <UnknownStyle key={styleId} styleId={styleId} />;
            return (
              <StyleRow
                key={styleId}
                style={style}
                controls={
                  <>
                    <span className="text-muted-foreground text-xs">Added by you</span>
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={`Remove ${style.name}`}
                      onClick={() =>
                        onChoices((current) => removeStyle(current, subtopic.id, styleId))
                      }
                    >
                      Remove
                    </Button>
                  </>
                }
              />
            );
          })}
        </ul>
      ) : null}

      {addable.length > 0 ? (
        <div className="border-t px-3 py-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="sm" variant="ghost">
                <Plus data-icon="inline-start" />
                Add a style from the library
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="max-h-80 w-80 overflow-y-auto">
              <DropdownMenuLabel>Library styles</DropdownMenuLabel>
              {addable.map((style) => (
                <DropdownMenuItem
                  key={style.id}
                  onSelect={() => onChoices((current) => addStyle(current, subtopic.id, style.id))}
                  className="flex flex-col items-start gap-0.5"
                >
                  <span className="text-sm">{style.name}</span>
                  <span className="text-muted-foreground text-xs">{style.summary}</span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      ) : null}
    </article>
  );
}

/** A style id the library does not know, e.g. after a library change. It cannot be approved. */
function UnknownStyle({ styleId }: { styleId: string }) {
  return (
    <li className="px-3 py-2.5 text-muted-foreground text-xs">
      Suggested style <span className="font-mono">{styleId}</span> is not in the library and is left
      out.
    </li>
  );
}

function TargetsStep({
  topics,
  choices,
  suggestion,
}: {
  topics: readonly SetupTopic[];
  choices: SetupChoices;
  suggestion: SetupSuggestion;
}) {
  const targets = targetsBySubtopic(suggestion.cell_targets);
  const columnTotals = Object.fromEntries(
    DIFFICULTIES.map((difficulty) => [
      difficulty,
      suggestion.cell_targets
        .filter((cell) => cell.difficulty === difficulty)
        .reduce((sum, cell) => sum + cell.target, 0),
    ]),
  );
  const total = suggestion.cell_targets.reduce((sum, cell) => sum + cell.target, 0);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h3 className="font-semibold text-sm">
          Target: {total} approved {total === 1 ? "question" : "questions"}
        </h3>
        <p className="text-muted-foreground text-sm">
          The AI set how many approved questions each subtopic needs at each difficulty. Approving
          saves your styles and generates the first {FIRST_ROUND_SIZE} questions; you review them,
          then ask for the next round until every target is met.
        </p>
      </div>

      <div className="overflow-hidden rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Subtopic</TableHead>
              <TableHead className="text-right">Styles</TableHead>
              {DIFFICULTIES.map((difficulty) => (
                <TableHead key={difficulty} className="text-right">
                  <span className="inline-flex justify-end">
                    <DifficultyBadge difficulty={difficulty} />
                  </span>
                </TableHead>
              ))}
              <TableHead className="text-right">Total</TableHead>
            </TableRow>
          </TableHeader>
          {topics.map((topic) => (
            <TableBody key={topic.id}>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableCell colSpan={DIFFICULTIES.length + 3} className="font-medium text-xs">
                  {topic.name}
                </TableCell>
              </TableRow>
              {topic.subtopics.map((subtopic) => {
                const row = targets.get(subtopic.id);
                return (
                  <TableRow key={subtopic.id}>
                    <TableCell className="pl-5">{subtopic.name}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {approvedStyleIds(choices, subtopic).length}
                    </TableCell>
                    {DIFFICULTIES.map((difficulty) => (
                      <TableCell key={difficulty} className="text-right tabular-nums">
                        {row?.[difficulty] ?? <span className="text-muted-foreground">–</span>}
                      </TableCell>
                    ))}
                    <TableCell className="text-right font-medium tabular-nums">
                      {rowTotal(row)}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          ))}
          <TableFooter>
            <TableRow>
              <TableCell colSpan={2}>Total</TableCell>
              {DIFFICULTIES.map((difficulty) => (
                <TableCell key={difficulty} className="text-right tabular-nums">
                  {columnTotals[difficulty]}
                </TableCell>
              ))}
              <TableCell className="text-right tabular-nums" data-testid="setup-total">
                {total}
              </TableCell>
            </TableRow>
          </TableFooter>
        </Table>
      </div>
    </div>
  );
}
