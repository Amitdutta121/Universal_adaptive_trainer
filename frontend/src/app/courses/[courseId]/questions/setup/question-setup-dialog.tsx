"use client";

/**
 * "Set up questions": a large modal opened from the Questions page header
 * (docs/QUESTION_SETUP_PLAN.md, agent D).
 *
 *   1. Suggest — on open the AI suggests library styles per subtopic and a target per
 *      subtopic x difficulty cell.
 *   2. Styles  — one subtopic at a time, picked from a rail that shows every subtopic's state.
 *      The whole library is shown, grouped by what the student does, in the same order for
 *      every subtopic; the AI's picks start selected and the professor deselects or adds.
 *      Every subtopic needs at least one selected style.
 *   3. Targets — the AI's counts, read-only, and the total. Approve saves the setup; the backend
 *      starts round 1 in the background and the professor lands on the review queue.
 *
 * Mount it only while open (`{open ? <QuestionSetupDialog … /> : null}`) so each opening asks
 * for a fresh suggestion and starts from clean choices.
 */

import {
  Check,
  ChevronLeft,
  ChevronRight,
  Eye,
  LoaderCircle,
  TriangleAlert,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { type ReactNode, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { QueryError } from "@/components/query-state";
import { DifficultyBadge } from "@/components/question-setup/badges";
import { ExampleQuestionView } from "@/components/question-setup/example-question";
import { DIFFICULTIES, DIFFICULTY_LABEL, type Difficulty } from "@/components/question-setup/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import type { StyleRowStyle } from "@/components/question-setup/style-row";
import type { CurriculumVersionDetail, QuestionSetup, SetupSuggestion } from "@/lib/api/types";
import { useCoursePath } from "@/lib/use-course";
import { cn } from "@/lib/utils";
import { CustomRules } from "./custom-rules";
import {
  approvedStyleIds,
  FIRST_ROUND_SIZE,
  initialChoices,
  rowTotal,
  type SetupChoices,
  type SetupSubtopic,
  type SetupTopic,
  saveRequest,
  setupTopics,
  subtopicsWithoutStyle,
  targetsBySubtopic,
  toggleStyle,
  uncoveredDifficulties,
  withKnownStyles,
} from "./setup-state";
import { groupStyles } from "./style-groups";

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
            writes. Its suggestions start selected; click any style to change that.
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
  const { topics, dropped } = useMemo(
    () =>
      withKnownStyles(
        setupTopics(curriculum, suggestion),
        new Set(library.map((style) => style.id)),
      ),
    [curriculum, suggestion, library],
  );
  const [choices, setChoices] = useState<SetupChoices>(() => initialChoices(topics, currentSetup));
  const [step, setStep] = useState<Step>("styles");

  const missing = subtopicsWithoutStyle(choices, topics);
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

  const extras = (
    <>
      <CustomRules curriculumVersionId={curriculum.version.id} />
      {save.error ? (
        <div className="mt-4">
          <QueryError error={save.error} />
        </div>
      ) : null}
    </>
  );

  return (
    <>
      {step === "styles" ? (
        <StylesStep
          topics={topics}
          choices={choices}
          onChoices={setChoices}
          library={library}
          cellTargets={suggestion.cell_targets}
          droppedSuggestions={dropped}
        >
          {extras}
        </StylesStep>
      ) : (
        <div className="flex-1 overflow-y-auto px-6 py-5">
          <TargetsStep topics={topics} choices={choices} suggestion={suggestion} />
          {extras}
        </div>
      )}

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
              {missingMessage(missing)} Select at least one style for each before approving.
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

type Health = "ok" | "gap" | "none";

/**
 * Step 2: one subtopic at a time. The rail lists every subtopic with its state; the main pane
 * shows the whole library for the chosen subtopic, grouped by what the student does, in the
 * same order and place for every subtopic. The AI's picks start selected.
 */
function StylesStep({
  topics,
  choices,
  onChoices,
  library,
  cellTargets,
  droppedSuggestions,
  children,
}: {
  topics: readonly SetupTopic[];
  choices: SetupChoices;
  onChoices(update: (choices: SetupChoices) => SetupChoices): void;
  library: readonly QuestionStyle[];
  cellTargets: SetupSuggestion["cell_targets"];
  droppedSuggestions: number;
  children: ReactNode;
}) {
  const subtopics = useMemo(() => topics.flatMap((topic) => topic.subtopics), [topics]);
  const groups = useMemo(() => groupStyles(library), [library]);
  const styleById = useMemo(() => new Map(library.map((style) => [style.id, style])), [library]);
  const targets = useMemo(() => targetsBySubtopic(cellTargets), [cellTargets]);
  const [selectedId, setSelectedId] = useState(() => subtopics[0]?.id);
  const scrollRef = useRef<HTMLDivElement>(null);

  const index = Math.max(
    0,
    subtopics.findIndex((subtopic) => subtopic.id === selectedId),
  );
  const subtopic = subtopics[index];
  const topic = topics.find((entry) => entry.subtopics.includes(subtopic));
  const next = subtopics[index + 1];
  const previous = subtopics[index - 1];

  function select(id: number) {
    setSelectedId(id);
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
  }

  function selectedStyles(entry: SetupSubtopic): QuestionStyle[] {
    return approvedStyleIds(choices, entry)
      .map((id) => styleById.get(id))
      .filter((style): style is QuestionStyle => style !== undefined);
  }

  function health(entry: SetupSubtopic): Health {
    if (approvedStyleIds(choices, entry).length === 0) return "none";
    return uncoveredDifficulties(selectedStyles(entry), targets.get(entry.id)).length > 0
      ? "gap"
      : "ok";
  }

  return (
    <div className="flex min-h-0 flex-1">
      <nav
        aria-label="Subtopics"
        className="hidden w-72 shrink-0 overflow-y-auto border-r bg-muted/30 p-2 md:block"
      >
        {topics.map((entry) => (
          <div key={entry.id} className="pb-2">
            <p className="px-2 pt-2 pb-1 font-medium text-muted-foreground text-xs">{entry.name}</p>
            <ul>
              {entry.subtopics.map((item) => {
                const count = approvedStyleIds(choices, item).length;
                const current = item.id === subtopic?.id;
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      aria-current={current ? "true" : undefined}
                      title={item.name}
                      onClick={() => select(item.id)}
                      className={cn(
                        "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted",
                        current && "bg-background font-medium ring-1 ring-border",
                      )}
                    >
                      <HealthIcon health={health(item)} />
                      <span className="min-w-0 flex-1 truncate">{item.name}</span>
                      <span className="text-muted-foreground text-xs tabular-nums">
                        {count}
                        <span className="sr-only"> selected</span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="flex min-w-0 flex-1 flex-col">
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-5">
          <select
            aria-label="Subtopic"
            value={subtopic?.id}
            onChange={(event) => select(Number(event.target.value))}
            className="mb-4 h-9 w-full rounded-md border bg-background px-2 text-sm md:hidden"
          >
            {subtopics.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
          {droppedSuggestions > 0 ? (
            <p className="mb-4 text-muted-foreground text-xs">
              {droppedSuggestions} suggested {droppedSuggestions === 1 ? "style is" : "styles are"}{" "}
              no longer in the library and {droppedSuggestions === 1 ? "was" : "were"} left out.
            </p>
          ) : null}
          {subtopic && topic ? (
            <SubtopicPicker
              key={subtopic.id}
              topicName={topic.name}
              position={index + 1}
              total={subtopics.length}
              subtopic={subtopic}
              selected={approvedStyleIds(choices, subtopic)}
              selectedStyles={selectedStyles(subtopic)}
              groups={groups}
              targets={targets.get(subtopic.id)}
              onToggle={(styleId) =>
                onChoices((current) => toggleStyle(current, subtopic, styleId))
              }
            />
          ) : (
            <p className="text-muted-foreground text-sm">
              This taxonomy has no subtopics to set up.
            </p>
          )}
          {children}
        </div>
        {subtopic ? (
          <div className="flex items-center gap-2 border-t px-6 py-2.5">
            <Button
              variant="ghost"
              size="sm"
              disabled={!previous}
              onClick={() => previous && select(previous.id)}
            >
              <ChevronLeft data-icon="inline-start" />
              Previous
            </Button>
            <span className="ml-auto" />
            {next ? (
              <Button variant="outline" size="sm" onClick={() => select(next.id)}>
                Next: {next.name}
                <ChevronRight data-icon="inline-end" />
              </Button>
            ) : (
              <span className="text-muted-foreground text-xs">
                Last subtopic. Review the targets when you are ready.
              </span>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function HealthIcon({ health }: { health: Health }) {
  if (health === "ok") {
    return <Check className="size-3.5 shrink-0 text-[var(--accent-solid)]" aria-hidden />;
  }
  return (
    <span className="flex shrink-0">
      <TriangleAlert className="size-3.5 text-[var(--warn-solid)]" aria-hidden />
      <span className="sr-only">
        {health === "none" ? "No style selected." : "A difficulty has no style."}
      </span>
    </span>
  );
}

function SubtopicPicker({
  topicName,
  position,
  total,
  subtopic,
  selected,
  selectedStyles,
  groups,
  targets,
  onToggle,
}: {
  topicName: string;
  position: number;
  total: number;
  subtopic: SetupSubtopic;
  selected: readonly string[];
  selectedStyles: readonly QuestionStyle[];
  groups: readonly { title: string; description: string; styles: QuestionStyle[] }[];
  targets: Record<Difficulty, number | null> | undefined;
  onToggle(styleId: string): void;
}) {
  const [showReason, setShowReason] = useState(false);
  const [openStyleId, setOpenStyleId] = useState<string | null>(null);
  const suggested = new Set(subtopic.suggestion?.style_ids ?? []);
  const reason = subtopic.suggestion?.reason;

  return (
    <section aria-label={subtopic.name} className="flex flex-col gap-5">
      <header className="flex flex-col gap-1">
        <p className="text-muted-foreground text-xs">
          {topicName} · subtopic {position} of {total}
        </p>
        <h3 className="font-heading font-semibold text-lg">{subtopic.name}</h3>
        {reason ? (
          <div>
            <button
              type="button"
              aria-expanded={showReason}
              onClick={() => setShowReason((open) => !open)}
              className="text-muted-foreground text-xs underline decoration-dotted underline-offset-4 hover:text-foreground"
            >
              Why the AI suggested these
            </button>
            {showReason ? (
              <p className="mt-1.5 max-w-prose rounded-md bg-muted px-2.5 py-1.5 text-sm">
                {reason}
              </p>
            ) : null}
          </div>
        ) : (
          <p className="text-muted-foreground text-xs">
            The AI made no suggestion for this subtopic. Select at least one style.
          </p>
        )}
      </header>

      <DifficultyCoverage targets={targets} selectedStyles={selectedStyles} />

      {groups.map((group) => {
        const count = group.styles.filter((style) => selected.includes(style.id)).length;
        const open = group.styles.find((style) => style.id === openStyleId);
        return (
          <section key={group.title} aria-label={group.title} className="flex flex-col gap-2">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
              <h4 className="font-medium text-sm">{group.title}</h4>
              <span className="text-muted-foreground text-xs">{group.description}</span>
              {count > 0 ? (
                <span className="text-muted-foreground text-xs tabular-nums">{count} selected</span>
              ) : null}
            </div>
            <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {group.styles.map((style) => (
                <StyleTile
                  key={style.id}
                  style={style}
                  selected={selected.includes(style.id)}
                  suggested={suggested.has(style.id)}
                  examplesOpen={openStyleId === style.id}
                  onToggle={() => onToggle(style.id)}
                  onExamples={() => setOpenStyleId((id) => (id === style.id ? null : style.id))}
                />
              ))}
            </ul>
            {open ? <StyleExamples style={open} onClose={() => setOpenStyleId(null)} /> : null}
          </section>
        );
      })}
    </section>
  );
}

/** Per difficulty: the AI's target and how many selected styles can be written at it. */
function DifficultyCoverage({
  targets,
  selectedStyles,
}: {
  targets: Record<Difficulty, number | null> | undefined;
  selectedStyles: readonly QuestionStyle[];
}) {
  return (
    <ul aria-label="Questions planned per difficulty" className="grid gap-2 sm:grid-cols-3">
      {DIFFICULTIES.map((difficulty) => {
        const target = targets?.[difficulty] ?? 0;
        const styles = selectedStyles.filter((style) =>
          style.difficulty_range.includes(difficulty),
        ).length;
        const gap = target > 0 && styles === 0;
        return (
          <li
            key={difficulty}
            className={cn(
              "flex min-h-14 flex-col justify-center gap-1 rounded-md border px-3 py-2",
              target === 0 && "border-dashed",
              target > 0 && !gap && "bg-muted/40",
              gap && "border-[var(--warn-solid)]/50 bg-[var(--warn-wash)]",
            )}
          >
            <span className="font-medium text-sm">{DIFFICULTY_LABEL[difficulty]}</span>
            <span
              className={cn(
                "text-xs",
                gap ? "font-medium text-[var(--warn-solid)]" : "text-muted-foreground",
              )}
            >
              {target === 0
                ? "No questions planned"
                : `${target} ${target === 1 ? "question" : "questions"} planned · ${
                    gap
                      ? "no selected style writes these"
                      : `${styles} selected ${styles === 1 ? "style writes" : "styles write"} these`
                  }`}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function StyleTile({
  style,
  selected,
  suggested,
  examplesOpen,
  onToggle,
  onExamples,
}: {
  style: QuestionStyle;
  selected: boolean;
  suggested: boolean;
  examplesOpen: boolean;
  onToggle(): void;
  onExamples(): void;
}) {
  return (
    <li
      className={cn(
        "relative rounded-lg border bg-card transition-colors",
        selected &&
          "border-[var(--accent-solid)] bg-[var(--accent-wash)]/40 ring-1 ring-[var(--accent-solid)]",
        examplesOpen && "outline-2 outline-[var(--accent-solid)] outline-offset-2",
      )}
    >
      <button
        type="button"
        aria-pressed={selected}
        title={style.summary}
        onClick={onToggle}
        className="flex w-full items-start gap-2.5 rounded-lg py-2.5 pr-10 pl-3 text-left"
      >
        <span
          aria-hidden
          className={cn(
            "mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-[4px] border",
            selected
              ? "border-[var(--accent-solid)] bg-[var(--accent-solid)] text-primary-foreground"
              : "border-input bg-background",
          )}
        >
          {selected ? <Check className="size-3" /> : null}
        </span>
        <span className="flex min-w-0 flex-col gap-1">
          <span className="font-medium text-sm leading-snug">{style.name}</span>
          <span className="flex flex-wrap items-center gap-1.5 text-muted-foreground text-xs">
            {suggested ? (
              <span className="rounded border border-[var(--accent-solid)]/50 px-1 font-medium text-[var(--accent-text)]">
                Suggested
              </span>
            ) : null}
            <span>
              {style.difficulty_range.map((difficulty) => DIFFICULTY_LABEL[difficulty]).join(", ")}
            </span>
          </span>
        </span>
      </button>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="absolute top-1.5 right-1.5 size-7"
        aria-label={`Examples for ${style.name}`}
        aria-expanded={examplesOpen}
        title="Show two example questions"
        onClick={onExamples}
      >
        <Eye />
      </Button>
    </li>
  );
}

function StyleExamples({ style, onClose }: { style: QuestionStyle; onClose(): void }) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border bg-muted/30 p-3.5">
      <div className="flex items-start gap-3">
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <p className="font-medium text-sm">{style.name}</p>
          <p className="text-muted-foreground text-xs">
            {style.summary} Checked by: {style.checked_by}.
          </p>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="size-7"
          aria-label="Close examples"
          onClick={onClose}
        >
          <X />
        </Button>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {style.examples.map((example, index) => (
          <ExampleQuestionView
            key={example.prompt}
            example={example}
            label={`Example ${index + 1}`}
          />
        ))}
      </div>
    </div>
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
