"use client";

/**
 * "Set up questions": a large modal opened from the Questions page header
 * (docs/QUESTION_SETUP_PLAN.md, ADR-069; design: app/experiments/question-types).
 *
 *   1. Suggest — opening a new setup asks the AI for library styles per subtopic and a target
 *      per subtopic x difficulty cell. Editing a saved setup asks nothing: it opens on what was
 *      saved (its styles and its targets) and the professor toggles from there.
 *   2. Styles  — type first. The scope rail picks the whole course (default) or one subtopic;
 *      the middle column lists the question types with a switch each; the right pane shows the
 *      selected type's styles. Course changes reach every subtopic, a subtopic edit stays local
 *      (`setup-state.ts`). Only the course's question types are usable; another type can be
 *      allowed from here. Turning a style or type off where approved questions exist (or back
 *      on where some are hidden) asks whether to hide them from students or show them again
 *      (ADR-070).
 *   3. Targets — the AI's counts, read-only, and the total. Approve saves the setup; the backend
 *      starts round 1 in the background and the professor lands on the review queue.
 *
 * Mount it only while open (`{open ? <QuestionSetupDialog … /> : null}`) so each opening asks
 * for a fresh suggestion (new setup) or the saved setup (editing) and starts from clean choices.
 */

import { LoaderCircle, RotateCcw, TriangleAlert } from "lucide-react";
import { useRouter } from "next/navigation";
import { type ReactNode, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { QueryError } from "@/components/query-state";
import { DifficultyBadge } from "@/components/question-setup/badges";
import { StyleRow, type StyleRowStyle } from "@/components/question-setup/style-row";
import { type PendingToggle, ToggleDialog } from "@/components/question-setup/toggle-dialog";
import { DIFFICULTIES, DIFFICULTY_LABEL, type Difficulty } from "@/components/question-setup/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useCourse,
  useQuestionVisibility,
  useSaveSetup,
  useSetQuestionVisibility,
  useSetupSuggestion,
  useStyles,
  useUpdateCourse,
} from "@/lib/api/queries";
import type {
  CurriculumVersionDetail,
  QuestionSetup,
  Schemas,
  SetupSuggestion,
} from "@/lib/api/types";
import { BUILT_QUESTION_TYPES, questionTypeLabel } from "@/lib/question-types/registry";
import { useCourseId, useCoursePath } from "@/lib/use-course";
import { cn } from "@/lib/utils";
import { CourseStyles } from "./course-styles";
import { CustomRules } from "./custom-rules";
import {
  COURSE,
  effectiveStyleIds,
  FIRST_ROUND_SIZE,
  initialLayers,
  isCustom,
  liveCourseOn,
  type QuestionVisibility,
  questionsIn,
  resetSubtopic,
  rowTotal,
  type Scope,
  type SetupContext,
  type SetupLayers,
  type SetupSubtopic,
  type SetupTopic,
  saveRequest,
  setStyles,
  setupTopics,
  slotsBelowTarget,
  styleIdsIn,
  subtopicsWithoutStyle,
  targetsBySubtopic,
  uncoveredDifficulties,
  withKnownStyles,
} from "./setup-state";

/** A library style as the API client returns it. */
type QuestionStyle = StyleRowStyle & { id: string };

/** One question type and its library styles. */
interface TypeGroup {
  id: string;
  label: string;
  styles: QuestionStyle[];
}

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
  const editing = currentSetup !== null;
  // Session 0 disables the query: editing opens on the saved setup without an AI call.
  const suggest = useSetupSuggestion(curriculumVersionId, editing ? 0 : suggestionSession);
  const styles = useStyles();
  const courseId = useCourseId();
  const course = useCourse(courseId);
  const visibility = useQuestionVisibility(courseId, curriculumVersionId);

  const failed =
    (editing ? null : suggest.error) ?? styles.error ?? course.error ?? visibility.error;
  const ready = (editing || suggest.data) && styles.data && course.data && visibility.data;

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[92vh] w-[96vw] max-w-none flex-col gap-0 overflow-hidden p-0 sm:max-w-[min(96vw,1280px)]">
        <DialogHeader className="border-b px-6 py-4">
          <DialogTitle>{currentSetup ? "Edit question setup" : "Set up questions"}</DialogTitle>
          <DialogDescription>{curriculum.version.label}</DialogDescription>
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
                  if (course.error) void course.refetch();
                  if (visibility.error) void visibility.refetch();
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
            suggestion={editing ? null : (suggest.data ?? null)}
            library={styles.data.styles}
            courseStyleIds={styles.data.course_style_ids ?? []}
            course={course.data}
            visibility={visibility.data}
            onOpenChange={onOpenChange}
          />
        ) : (
          <div
            role="status"
            className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center"
          >
            <LoaderCircle className="size-5 animate-spin text-muted-foreground" aria-hidden />
            <p className="text-sm">
              {editing ? "Loading your setup…" : "Suggesting question styles for your taxonomy…"}
            </p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** Every type with a style in the library, in the registry's order; unknown types last. */
function typeGroups(library: readonly QuestionStyle[]): TypeGroup[] {
  const order: readonly string[] = BUILT_QUESTION_TYPES;
  const ids = [...new Set(library.map((style) => style.question_type))].sort(
    (a, b) =>
      (order.includes(a) ? order.indexOf(a) : order.length) -
      (order.includes(b) ? order.indexOf(b) : order.length),
  );
  return ids.map((id) => ({
    id,
    label: questionTypeLabel(id),
    styles: library.filter((style) => style.question_type === id),
  }));
}

function SetupSteps({
  curriculum,
  currentSetup,
  suggestion,
  library,
  courseStyleIds,
  course,
  visibility,
  onOpenChange,
}: {
  curriculum: CurriculumVersionDetail;
  currentSetup: QuestionSetup | null;
  /** The AI's suggestion for a new setup; `null` when editing a saved one. */
  suggestion: SetupSuggestion | null;
  library: readonly QuestionStyle[];
  /** Which of `library` belong to this course only. */
  courseStyleIds: readonly string[];
  course: Schemas["CourseOut"];
  visibility: QuestionVisibility;
  onOpenChange(open: boolean): void;
}) {
  const router = useRouter();
  const toCourse = useCoursePath();
  const save = useSaveSetup();
  const updateCourse = useUpdateCourse();
  const setVisibility = useSetQuestionVisibility(course.id);
  // Types allowed from this dialog, so they are usable before the course query refetches.
  const [allowedHere, setAllowedHere] = useState<readonly string[]>([]);
  const context = useMemo<SetupContext>(
    () => ({ library, allowed: new Set([...course.question_types, ...allowedHere]) }),
    [library, course.question_types, allowedHere],
  );
  const groups = useMemo(() => typeGroups(library), [library]);
  const { topics, dropped } = useMemo(
    () =>
      withKnownStyles(
        setupTopics(curriculum, suggestion, currentSetup),
        new Set(library.map((style) => style.id)),
      ),
    [curriculum, suggestion, currentSetup, library],
  );
  const cellTargets = suggestion?.cell_targets ?? currentSetup?.cell_targets ?? [];
  const [layers, setLayers] = useState<SetupLayers>(() =>
    initialLayers(context, currentSetup),
  );
  const [step, setStep] = useState<Step>("styles");
  const [scope, setScope] = useState<Scope>(COURSE);

  const missing = subtopicsWithoutStyle(layers, context, topics);
  const subtopicCount = topics.reduce((sum, topic) => sum + topic.subtopics.length, 0);
  const scopeSubtopic =
    scope === COURSE
      ? null
      : (topics.flatMap((topic) => topic.subtopics).find((entry) => entry.id === scope) ?? null);

  function approve() {
    save.mutate(
      saveRequest(curriculum.version.id, layers, context, topics, cellTargets),
      {
        onSuccess: (result) => {
          toast.success("Setup saved", {
            description: `Round 1 (${FIRST_ROUND_SIZE} questions) is generating. They arrive in the review queue.`,
            id: `setup-${result.setup_id}`,
          });
          onOpenChange(false);
          router.push(toCourse("/review"));
        },
      },
    );
  }

  /** Add a type to the course's question types, as course Settings does. */
  function allow(typeId: string) {
    updateCourse.mutate(
      { courseId: course.id, body: { question_types: [...context.allowed, typeId] } },
      {
        onSuccess: () => {
          setAllowedHere((current) => [...current, typeId]);
          // A type never used before starts with all its styles on; a blocked one comes back as
          // it was.
          const ids = library.filter((s) => s.question_type === typeId).map((s) => s.id);
          setLayers((current) =>
            ids.some((id) => current.courseOn.has(id))
              ? current
              : setStyles(current, context, COURSE, ids, true),
          );
        },
      },
    );
  }

  /** Hide approved questions or show hidden ones, at once, as "Allow for this course" saves. */
  function setHidden(body: Schemas["SetQuestionVisibilityRequest"]) {
    setVisibility.mutate(body, {
      onSuccess: ({ changed }) => {
        const plural = changed === 1 ? "question" : "questions";
        toast.success(
          body.hidden
            ? `${changed} ${plural} hidden from students`
            : `${changed} ${plural} shown to students again`,
        );
      },
      onError: (error) =>
        toast.error("Could not change which questions students see", {
          description: error instanceof Error ? error.message : undefined,
        }),
    });
  }

  function toStyles(next: Scope) {
    setScope(next);
    setStep("styles");
  }

  const extras = (
    <>
      <CourseStyles styles={library} courseStyleIds={courseStyleIds} />
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
          groups={groups}
          context={context}
          layers={layers}
          onLayers={setLayers}
          scope={scope}
          onScope={setScope}
          cellTargets={cellTargets}
          visibility={visibility}
          onSetHidden={setHidden}
          droppedSuggestions={dropped}
          onAllow={allow}
          allowing={updateCourse.isPending}
          allowError={updateCourse.error}
        >
          {extras}
        </StylesStep>
      ) : (
        <div className="flex-1 overflow-y-auto px-6 py-5">
          <TargetsStep
            topics={topics}
            context={context}
            layers={layers}
            cellTargets={cellTargets}
            onAdjust={toStyles}
          />
          {extras}
        </div>
      )}

      <div className="flex flex-col gap-3 border-t px-6 py-3 sm:flex-row sm:items-center">
        <p className="text-muted-foreground text-xs tabular-nums">
          Step {step === "styles" ? 2 : 3} of 3 ·{" "}
          {step === "styles"
            ? `Editing ${scopeSubtopic ? scopeSubtopic.name : "the whole course"}`
            : `${subtopicCount - missing.length} of ${subtopicCount} subtopics have a style`}
        </p>
        {missing.length > 0 ? (
          <p
            role="alert"
            className="flex items-start gap-1.5 text-[var(--warn-solid)] text-sm sm:mr-auto"
          >
            <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
            <span>{missingMessage(missing)}</span>
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

/**
 * Step 2. Left: scope, the whole course (default) or one subtopic. Middle: every question type
 * with a style in the library, with an on/off switch. Right: coverage per difficulty, then the
 * selected type's styles with a switch each.
 */
function StylesStep({
  topics,
  groups,
  context,
  layers,
  onLayers,
  scope,
  onScope,
  cellTargets,
  visibility,
  onSetHidden,
  droppedSuggestions,
  onAllow,
  allowing,
  allowError,
  children,
}: {
  topics: readonly SetupTopic[];
  groups: readonly TypeGroup[];
  context: SetupContext;
  layers: SetupLayers;
  onLayers(update: (layers: SetupLayers) => SetupLayers): void;
  scope: Scope;
  onScope(scope: Scope): void;
  cellTargets: SetupSuggestion["cell_targets"];
  visibility: QuestionVisibility;
  onSetHidden(body: Schemas["SetQuestionVisibilityRequest"]): void;
  droppedSuggestions: number;
  onAllow(typeId: string): void;
  allowing: boolean;
  allowError: unknown;
  children: ReactNode;
}) {
  const subtopics = useMemo(() => topics.flatMap((topic) => topic.subtopics), [topics]);
  const targets = useMemo(() => targetsBySubtopic(cellTargets), [cellTargets]);
  const [typeId, setTypeId] = useState(() => groups[0]?.id ?? "");
  const scrollRef = useRef<HTMLDivElement>(null);

  const subtopic = scope === COURSE ? null : (subtopics.find((s) => s.id === scope) ?? null);
  const topic = subtopic ? topics.find((entry) => entry.subtopics.includes(subtopic)) : null;
  const on = styleIdsIn(layers, context, subtopic);
  const live = liveCourseOn(layers, context);
  const group = groups.find((entry) => entry.id === typeId) ?? groups[0];

  function select(next: Scope) {
    onScope(next);
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
  }

  const [pending, setPending] = useState<PendingSwitch | null>(null);

  function apply(ids: readonly string[], value: boolean) {
    onLayers((current) => setStyles(current, context, subtopic ?? COURSE, ids, value));
  }

  /**
   * Switch styles on or off. When that touches existing questions -- approved ones in the
   * styles being turned off, hidden ones in the styles being turned back on -- ask first.
   */
  function toggle(styles: readonly QuestionStyle[], value: boolean, label?: string) {
    const ids = styles.map((style) => style.id);
    if (ids.length === 0) return;
    const changing = ids.filter((id) => on.has(id) !== value);
    const existing = questionsIn(visibility, scope, changing);
    const count = value ? existing.hidden : existing.approved;
    if (count === 0) return apply(ids, value);
    setPending({
      mode: value ? "on" : "off",
      label: label ?? styles[0]?.name ?? "",
      scopeLabel: subtopic ? subtopic.name : "the whole course",
      count,
      slotsBelowTarget: value ? 0 : slotsBelowTarget(visibility, cellTargets, scope, changing),
      styleIds: ids,
      changing,
      subtopicId: subtopic?.id ?? null,
    });
  }

  function confirm(withQuestions: boolean) {
    if (!pending) return;
    const value = pending.mode === "on";
    apply(pending.styleIds, value);
    if (withQuestions) {
      onSetHidden({
        hidden: !value,
        style_ids: [...pending.changing],
        subtopic_id: pending.subtopicId,
      });
    }
    setPending(null);
  }

  /** Allowed types only; and a subtopic can only use styles the course has on. */
  function usable(entry: TypeGroup): QuestionStyle[] {
    if (!context.allowed.has(entry.id)) return [];
    return subtopic ? entry.styles.filter((style) => live.has(style.id)) : entry.styles;
  }

  return (
    <div className="grid min-h-0 flex-1 grid-cols-[210px_220px_minmax(0,1fr)] lg:grid-cols-[230px_230px_minmax(0,1fr)]">
      <ScopeRail
        topics={topics}
        layers={layers}
        liveCount={live.size}
        scope={scope}
        onScope={select}
      />

      <nav aria-label="Question types" className="min-h-0 overflow-y-auto border-r p-2">
        <ul className="flex flex-col gap-0.5">
          {groups.map((entry) => {
            const styles = usable(entry);
            const count = entry.styles.filter((style) => on.has(style.id)).length;
            const active = entry.id === group?.id;
            const allowed = context.allowed.has(entry.id);
            return (
              <li
                key={entry.id}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-2.5 py-2",
                  active && "bg-muted",
                )}
              >
                <Switch
                  checked={count > 0}
                  disabled={styles.length === 0}
                  onCheckedChange={(value) => {
                    setTypeId(entry.id);
                    toggle(
                      value ? styles : styles.filter((s) => on.has(s.id)),
                      value,
                      entry.label,
                    );
                  }}
                  aria-label={`Use ${entry.label}`}
                />
                <button
                  type="button"
                  onClick={() => setTypeId(entry.id)}
                  aria-current={active ? "true" : undefined}
                  className={cn("min-w-0 flex-1 text-left", count === 0 && "text-muted-foreground")}
                >
                  <div className="truncate font-medium text-sm">{entry.label}</div>
                  <div className="flex items-center gap-2 text-muted-foreground text-xs">
                    {allowed ? (
                      <>
                        {count} of {entry.styles.length}
                        <LevelBars group={entry} on={on} />
                      </>
                    ) : (
                      "Not allowed in this course"
                    )}
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      <div ref={scrollRef} className="min-h-0 overflow-y-auto px-5 py-4">
        {droppedSuggestions > 0 ? (
          <p className="mb-4 text-muted-foreground text-xs">
            {droppedSuggestions} suggested {droppedSuggestions === 1 ? "style is" : "styles are"} no
            longer in the library and {droppedSuggestions === 1 ? "was" : "were"} left out.
          </p>
        ) : null}
        {subtopic && topic ? (
          <SubtopicHeader
            key={subtopic.id}
            topicName={topic.name}
            subtopic={subtopic}
            count={on.size}
            custom={isCustom(layers, subtopic.id)}
            onReset={() => onLayers((current) => resetSubtopic(current, subtopic.id))}
          />
        ) : null}
        <Coverage
          groups={groups}
          on={on}
          targets={subtopic ? (targets.get(subtopic.id) ?? null) : undefined}
        />
        {group ? (
          <TypeDetail
            group={group}
            on={on}
            live={live}
            allowed={context.allowed.has(group.id)}
            subtopic={subtopic}
            onToggle={toggle}
            onAllow={() => onAllow(group.id)}
            allowing={allowing}
            allowError={allowError}
          />
        ) : (
          <p className="text-muted-foreground text-sm">The style library is empty.</p>
        )}
        {children}
      </div>
      <ToggleDialog pending={pending} onCancel={() => setPending(null)} onConfirm={confirm} />
    </div>
  );
}

/** A switch waiting on the turn-off / turn-on question. */
interface PendingSwitch extends PendingToggle {
  /** Every style the switch covers. */
  styleIds: readonly string[];
  /** Those whose state actually changes, and so whose questions are hidden or shown. */
  changing: readonly string[];
  subtopicId: number | null;
}

function ScopeRail({
  topics,
  layers,
  liveCount,
  scope,
  onScope,
}: {
  topics: readonly SetupTopic[];
  layers: SetupLayers;
  liveCount: number;
  scope: Scope;
  onScope(scope: Scope): void;
}) {
  const custom = topics
    .flatMap((topic) => topic.subtopics)
    .filter((subtopic) => isCustom(layers, subtopic.id)).length;
  return (
    <nav aria-label="Scope" className="min-h-0 overflow-y-auto border-r bg-muted/20 p-2">
      <button
        type="button"
        onClick={() => onScope(COURSE)}
        aria-current={scope === COURSE ? "true" : undefined}
        className={cn(
          "w-full rounded-md px-2.5 py-2 text-left",
          scope === COURSE && "bg-background shadow-xs ring-1 ring-border",
        )}
      >
        <div className="font-medium text-sm">Whole course</div>
        <div className="text-muted-foreground text-xs">
          {liveCount} styles on
          {custom > 0 ? ` · ${custom} custom ${custom === 1 ? "subtopic" : "subtopics"}` : ""}
        </div>
      </button>

      <div className="mt-4 px-2.5 pb-1 font-medium text-muted-foreground text-xs">
        Adjust one subtopic
      </div>
      {topics.map((topic) => (
        <div key={topic.id} className="mt-2">
          <div className="truncate px-2.5 py-1 text-muted-foreground text-xs">{topic.name}</div>
          <ul>
            {topic.subtopics.map((subtopic) => {
              const active = scope === subtopic.id;
              return (
                <li key={subtopic.id}>
                  <button
                    type="button"
                    title={subtopic.name}
                    onClick={() => onScope(subtopic.id)}
                    aria-current={active ? "true" : undefined}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm",
                      active ? "bg-background shadow-xs ring-1 ring-border" : "hover:bg-muted/60",
                    )}
                  >
                    <span className="min-w-0 flex-1 truncate">{subtopic.name}</span>
                    {isCustom(layers, subtopic.id) ? <CustomBadge /> : null}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function CustomBadge({ className }: { className?: string }) {
  return (
    <Badge variant="outline" className={cn("h-5 px-1.5 text-[11px]", className)}>
      Custom
    </Badge>
  );
}

function SubtopicHeader({
  topicName,
  subtopic,
  count,
  custom,
  onReset,
}: {
  topicName: string;
  subtopic: SetupSubtopic;
  count: number;
  custom: boolean;
  onReset(): void;
}) {
  const [showReason, setShowReason] = useState(false);
  const reason = subtopic.suggestion?.reason;
  return (
    <section aria-label={subtopic.name} className="mb-4 flex items-start gap-3 border-b pb-3">
      <div className="min-w-0 flex-1">
        <div className="text-muted-foreground text-xs">{topicName}</div>
        <h3 className="font-semibold text-base">{subtopic.name}</h3>
        <div className="text-muted-foreground text-xs">
          {count} {count === 1 ? "style" : "styles"} · {custom ? "Custom" : "Follows the course"}
        </div>
        {reason ? (
          <div className="mt-1">
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
        ) : null}
      </div>
      {custom ? (
        <Button variant="outline" size="sm" onClick={onReset}>
          <RotateCcw data-icon="inline-start" />
          Reset to course
        </Button>
      ) : null}
    </section>
  );
}

/**
 * Per difficulty, which types cover it. In subtopic scope (`targets` not undefined) also the
 * questions planned there, flagged when a planned level has no style on.
 */
function Coverage({
  groups,
  on,
  targets,
}: {
  groups: readonly TypeGroup[];
  on: ReadonlySet<string>;
  targets: Record<Difficulty, number | null> | null | undefined;
}) {
  return (
    <ul aria-label="Difficulty coverage" className="mb-5 grid grid-cols-3 gap-2">
      {DIFFICULTIES.map((difficulty) => {
        const covering = groups.filter((group) =>
          group.styles.some(
            (style) => style.difficulty_range.includes(difficulty) && on.has(style.id),
          ),
        );
        const target = targets === undefined ? null : (targets?.[difficulty] ?? 0);
        const gap = covering.length === 0 && target !== 0;
        return (
          <li
            key={difficulty}
            className={cn(
              "rounded-md border px-3 py-2",
              target === 0 && "border-dashed",
              gap && "border-[var(--warn-solid)]/50 bg-[var(--warn-wash)]",
            )}
          >
            <div className="font-medium text-sm">{DIFFICULTY_LABEL[difficulty]}</div>
            <div
              className={cn(
                "text-xs",
                gap ? "font-medium text-[var(--warn-solid)]" : "text-muted-foreground",
              )}
            >
              {target !== null ? (target === 0 ? "None planned · " : `${target} planned · `) : null}
              {covering.length === 0
                ? "no style on"
                : covering.map((group) => group.label).join(", ")}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function TypeDetail({
  group,
  on,
  live,
  allowed,
  subtopic,
  onToggle,
  onAllow,
  allowing,
  allowError,
}: {
  group: TypeGroup;
  on: ReadonlySet<string>;
  /** The course's styles that are on. */
  live: ReadonlySet<string>;
  allowed: boolean;
  subtopic: SetupSubtopic | null;
  onToggle(styles: readonly QuestionStyle[], on: boolean): void;
  onAllow(): void;
  allowing: boolean;
  allowError: unknown;
}) {
  const suggested = new Set(subtopic?.suggestion?.style_ids ?? []);

  return (
    <section aria-label={group.label} className="flex flex-col gap-4">
      <h2 className="font-semibold text-lg">{group.label}</h2>
      {!allowed ? (
        <div className="flex flex-col gap-2 rounded-md border border-dashed px-3 py-2.5">
          <div className="flex items-center gap-3">
            <p className="mr-auto text-sm">Not allowed in this course.</p>
            <Button size="sm" variant="outline" disabled={allowing} onClick={onAllow}>
              {allowing ? <LoaderCircle data-icon="inline-start" className="animate-spin" /> : null}
              Allow for this course
            </Button>
          </div>
          {allowError ? <QueryError error={allowError} /> : null}
        </div>
      ) : null}

      <table className="w-full table-fixed border-collapse text-sm">
        <thead>
          <tr className="text-left text-muted-foreground text-xs">
            {DIFFICULTIES.map((difficulty) => (
              <th key={difficulty} className="border-b pb-1.5 font-medium">
                {DIFFICULTY_LABEL[difficulty]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr className="align-top">
            {DIFFICULTIES.map((difficulty) => {
              const styles = group.styles.filter((style) =>
                style.difficulty_range.includes(difficulty),
              );
              return (
                <td key={difficulty} className="py-2 pr-3">
                  {styles.length === 0 ? (
                    <span className="text-muted-foreground">—</span>
                  ) : (
                    <ul className="flex flex-col gap-1">
                      {styles.map((style) => (
                        <li
                          key={style.id}
                          className={cn(!on.has(style.id) && "text-muted-foreground line-through")}
                        >
                          {style.name}
                        </li>
                      ))}
                    </ul>
                  )}
                </td>
              );
            })}
          </tr>
        </tbody>
      </table>

      <ul className="divide-y rounded-lg border">
        {group.styles.map((style) => {
          const courseOff = !allowed || (subtopic !== null && !live.has(style.id));
          const isOn = on.has(style.id);
          return (
            <StyleRow
              key={style.id}
              style={style}
              muted={!isOn}
              controls={
                <div className="flex items-center gap-2">
                  {courseOff ? (
                    <span className="text-muted-foreground text-xs">
                      {allowed ? "Off for the course" : "Type not allowed"}
                    </span>
                  ) : suggested.has(style.id) ? (
                    <Badge variant="outline">Suggested</Badge>
                  ) : null}
                  <Switch
                    checked={isOn}
                    disabled={courseOff}
                    onCheckedChange={(value) => onToggle([style], value)}
                    aria-label={`Use ${style.name}`}
                  />
                </div>
              }
            />
          );
        })}
      </ul>
    </section>
  );
}

/** Easy / Medium / Hard: filled where a style of this type that is on covers the level. */
function LevelBars({ group, on }: { group: TypeGroup; on: ReadonlySet<string> }) {
  return (
    <span className="flex items-center gap-0.5" aria-hidden>
      {DIFFICULTIES.map((difficulty) => (
        <span
          key={difficulty}
          className={cn(
            "h-1.5 w-3 rounded-[1px]",
            group.styles.some((s) => s.difficulty_range.includes(difficulty) && on.has(s.id))
              ? "bg-[var(--accent-solid)]"
              : "bg-border",
          )}
        />
      ))}
    </span>
  );
}

function TargetsStep({
  topics,
  context,
  layers,
  cellTargets,
  onAdjust,
}: {
  topics: readonly SetupTopic[];
  context: SetupContext;
  layers: SetupLayers;
  cellTargets: SetupSuggestion["cell_targets"];
  onAdjust(subtopicId: number): void;
}) {
  const targets = targetsBySubtopic(cellTargets);
  const styleById = new Map(context.library.map((style) => [style.id, style]));
  const columnTotals = Object.fromEntries(
    DIFFICULTIES.map((difficulty) => [
      difficulty,
      cellTargets
        .filter((cell) => cell.difficulty === difficulty)
        .reduce((sum, cell) => sum + cell.target, 0),
    ]),
  );
  const total = cellTargets.reduce((sum, cell) => sum + cell.target, 0);

  return (
    <div className="flex flex-col gap-4">
      <h3 className="font-semibold text-sm">
        Target: {total} approved {total === 1 ? "question" : "questions"}
      </h3>

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
                const ids = effectiveStyleIds(layers, context, subtopic);
                const selected = ids
                  .map((id) => styleById.get(id))
                  .filter((style): style is QuestionStyle => style !== undefined);
                const gaps = new Set(uncoveredDifficulties(selected, row));
                return (
                  <TableRow key={subtopic.id}>
                    <TableCell className="pl-5">
                      <button
                        type="button"
                        onClick={() => onAdjust(subtopic.id)}
                        className="text-left underline-offset-2 hover:underline"
                      >
                        {subtopic.name}
                      </button>
                      {isCustom(layers, subtopic.id) ? <CustomBadge className="ml-2" /> : null}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{ids.length}</TableCell>
                    {DIFFICULTIES.map((difficulty) => {
                      const gap = gaps.has(difficulty);
                      return (
                        <TableCell
                          key={difficulty}
                          className={cn(
                            "text-right tabular-nums",
                            gap && "bg-[var(--warn-wash)] font-medium text-[var(--warn-solid)]",
                          )}
                          title={gap ? "No style on at this level" : undefined}
                        >
                          {row?.[difficulty] ?? <span className="text-muted-foreground">–</span>}
                          {gap ? " · no style" : null}
                        </TableCell>
                      );
                    })}
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
