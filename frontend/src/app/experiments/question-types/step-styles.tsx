"use client";

/**
 * Step 2. Left: scope, the whole course (default) or one subtopic. Middle: every question type
 * the subject offers, with an on/off switch; a type blocked in course Settings is greyed and can
 * be allowed from here. Right: the selected type's styles, which difficulties each one writes,
 * and a switch per style.
 */

import { RotateCcw } from "lucide-react";
import { StyleRow, type StyleRowStyle } from "@/components/question-setup/style-row";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { DIFFICULTIES, DIFFICULTY_LABEL } from "../question-setup/mock-types";
import {
  aiFit,
  COURSE,
  type Course,
  covers,
  effective,
  isCustom,
  type LibraryStyle,
  liveCourseOn,
  onIn,
  type Scope,
  type SetupState,
  type SubtopicRef,
  subtopics,
  targetsFor,
  type TypeGroup,
  typeAllowed,
} from "./setup-model";

export function StylesStep({
  course,
  groups,
  state,
  scope,
  onScope,
  typeId,
  onType,
  onToggle,
  onReset,
  onAllow,
}: {
  course: Course;
  groups: readonly TypeGroup[];
  state: SetupState;
  scope: Scope;
  onScope(scope: Scope): void;
  typeId: string;
  onType(typeId: string): void;
  onToggle(styles: readonly LibraryStyle[], on: boolean, label: string): void;
  onReset(subtopicId: string): void;
  /** Allow a type blocked in course Settings. */
  onAllow(typeId: string): void;
}) {
  const refs = subtopics(course);
  const ref = refs.find((entry) => entry.subtopic.id === scope) ?? null;
  const on = onIn(state, course, scope);
  const group = groups.find((entry) => entry.id === typeId) ?? groups[0];

  return (
    <div className="grid min-h-0 flex-1 grid-cols-[230px_230px_1fr]">
      <ScopeRail course={course} refs={refs} state={state} scope={scope} onScope={onScope} />

      <nav aria-label="Question types" className="min-h-0 overflow-y-auto border-r p-2">
        <ul className="flex flex-col gap-0.5">
          {groups.map((entry) => {
            const usable = usableIn(entry, state, scope);
            const count = entry.styles.filter((style) => on.has(style.id)).length;
            const active = entry.id === group?.id;
            const allowed = typeAllowed(state, entry.id);
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
                  disabled={usable.length === 0}
                  onCheckedChange={(value) => {
                    onType(entry.id);
                    onToggle(
                      value ? usable : usable.filter((s) => on.has(s.id)),
                      value,
                      entry.label,
                    );
                  }}
                  aria-label={`Use ${entry.label}`}
                />
                <button
                  type="button"
                  onClick={() => onType(entry.id)}
                  aria-current={active ? "true" : undefined}
                  className={cn("min-w-0 flex-1 text-left", count === 0 && "text-muted-foreground")}
                >
                  <div className="truncate font-medium text-sm">{entry.label}</div>
                  <div className="flex items-center gap-2 text-muted-foreground text-xs">
                    {allowed ? (
                      <>
                        {count} of {entry.styles.length}
                        <LevelDots group={entry} on={on} />
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

      <div className="min-h-0 overflow-y-auto px-5 py-4">
        {ref ? (
          <SubtopicHeader course={course} refEntry={ref} state={state} onReset={onReset} />
        ) : null}
        <Coverage course={course} groups={groups} state={state} refEntry={ref} />
        {group ? (
          <TypeDetail
            course={course}
            group={group}
            state={state}
            scope={scope}
            refEntry={ref}
            onToggle={onToggle}
            onAllow={onAllow}
          />
        ) : null}
      </div>
    </div>
  );
}

/** Only allowed types; and a subtopic can only use styles the course has on. */
function usableIn(group: TypeGroup, state: SetupState, scope: Scope): LibraryStyle[] {
  if (!typeAllowed(state, group.id)) return [];
  return scope === COURSE
    ? group.styles
    : group.styles.filter((style) => state.courseOn.has(style.id));
}

function ScopeRail({
  course,
  refs,
  state,
  scope,
  onScope,
}: {
  course: Course;
  refs: readonly SubtopicRef[];
  state: SetupState;
  scope: Scope;
  onScope(scope: Scope): void;
}) {
  const custom = refs.filter((entry) => isCustom(state, entry.subtopic.id)).length;
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
          {liveCourseOn(state, course).size} styles on
          {custom > 0 ? ` · ${custom} custom ${custom === 1 ? "subtopic" : "subtopics"}` : ""}
        </div>
      </button>

      <div className="mt-4 px-2.5 pb-1 font-medium text-muted-foreground text-xs">
        Adjust one subtopic
      </div>
      {course.topics.map((topic) => (
        <div key={topic.id} className="mt-2">
          <div className="truncate px-2.5 py-1 text-muted-foreground text-xs">{topic.name}</div>
          <ul>
            {topic.subtopics.map((subtopic) => {
              const active = scope === subtopic.id;
              return (
                <li key={subtopic.id}>
                  <button
                    type="button"
                    onClick={() => onScope(subtopic.id)}
                    aria-current={active ? "true" : undefined}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm",
                      active ? "bg-background shadow-xs ring-1 ring-border" : "hover:bg-muted/60",
                    )}
                  >
                    <span className="min-w-0 flex-1 truncate">{subtopic.name}</span>
                    {isCustom(state, subtopic.id) ? (
                      <Badge variant="outline" className="h-5 px-1.5 text-[11px]">
                        Custom
                      </Badge>
                    ) : null}
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

function SubtopicHeader({
  course,
  refEntry,
  state,
  onReset,
}: {
  course: Course;
  refEntry: SubtopicRef;
  state: SetupState;
  onReset(subtopicId: string): void;
}) {
  const custom = isCustom(state, refEntry.subtopic.id);
  const count = effective(state, course, refEntry).size;
  return (
    <div className="mb-4 flex items-start gap-3 border-b pb-3">
      <div className="min-w-0 flex-1">
        <div className="text-muted-foreground text-xs">{refEntry.topicName}</div>
        <h3 className="font-semibold text-base">{refEntry.subtopic.name}</h3>
        <div className="text-muted-foreground text-xs">
          {count} styles · {custom ? "Custom" : "Follows the course"}
        </div>
      </div>
      {custom ? (
        <Button variant="outline" size="sm" onClick={() => onReset(refEntry.subtopic.id)}>
          <RotateCcw data-icon="inline-start" />
          Reset to course
        </Button>
      ) : null}
    </div>
  );
}

function Coverage({
  course,
  groups,
  state,
  refEntry,
}: {
  course: Course;
  groups: readonly TypeGroup[];
  state: SetupState;
  refEntry: SubtopicRef | null;
}) {
  const on = refEntry ? effective(state, course, refEntry) : liveCourseOn(state, course);
  const targets = refEntry ? targetsFor(refEntry.subtopic) : null;
  return (
    <ul aria-label="Difficulty coverage" className="mb-5 grid grid-cols-3 gap-2">
      {DIFFICULTIES.map((difficulty) => {
        const covering = groups.filter((group) =>
          group.styles.some((style) => covers(style, difficulty) && on.has(style.id)),
        );
        const target = targets?.[difficulty] ?? null;
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

function asRowStyle(style: LibraryStyle): StyleRowStyle {
  return {
    name: style.name,
    summary: style.summary,
    question_type: style.questionType as StyleRowStyle["question_type"],
    difficulty_range: style.difficulties,
    checked_by: style.checkedBy,
    examples: style.examples,
  };
}

function TypeDetail({
  course,
  group,
  state,
  scope,
  refEntry,
  onToggle,
  onAllow,
}: {
  course: Course;
  group: TypeGroup;
  state: SetupState;
  scope: Scope;
  refEntry: SubtopicRef | null;
  onToggle(styles: readonly LibraryStyle[], on: boolean, label: string): void;
  onAllow(typeId: string): void;
}) {
  const on = onIn(state, course, scope);
  const allowed = typeAllowed(state, group.id);
  const fit = refEntry ? aiFit(course, refEntry) : null;

  return (
    <section aria-label={group.label} className="flex flex-col gap-4">
      <h2 className="font-semibold text-lg">{group.label}</h2>
      {!allowed ? (
        <div className="flex items-center gap-3 rounded-md border border-dashed px-3 py-2.5">
          <p className="mr-auto text-sm">Not allowed in this course.</p>
          <Button size="sm" variant="outline" onClick={() => onAllow(group.id)}>
            Allow for this course
          </Button>
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
              const styles = group.styles.filter((style) => covers(style, difficulty));
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

      {group.styles.length === 0 ? (
        <p className="text-muted-foreground text-sm">No styles for this type yet.</p>
      ) : (
        <ul className="divide-y rounded-lg border">
          {group.styles.map((style) => {
            const courseOff = !allowed || (scope !== COURSE && !state.courseOn.has(style.id));
            const isOn = on.has(style.id);
            return (
              <StyleRow
                key={style.id}
                style={asRowStyle(style)}
                muted={!isOn}
                controls={
                  <div className="flex items-center gap-2">
                    {courseOff ? (
                      <span className="text-muted-foreground text-xs">
                        {allowed ? "Off for the course" : "Type not allowed"}
                      </span>
                    ) : fit?.has(style.id) ? (
                      <Badge variant="outline">Suggested</Badge>
                    ) : null}
                    <Switch
                      checked={isOn}
                      disabled={courseOff}
                      onCheckedChange={(value) => onToggle([style], value, style.name)}
                      aria-label={`Use ${style.name}`}
                    />
                  </div>
                }
              />
            );
          })}
        </ul>
      )}
    </section>
  );
}

function LevelDots({ group, on }: { group: TypeGroup; on: ReadonlySet<string> }) {
  return (
    <span className="flex items-center gap-0.5" aria-hidden>
      {DIFFICULTIES.map((difficulty) => (
        <span
          key={difficulty}
          className={cn(
            "h-1.5 w-3 rounded-[1px]",
            group.styles.some((s) => covers(s, difficulty) && on.has(s.id))
              ? "bg-[var(--accent-solid)]"
              : "bg-border",
          )}
        />
      ))}
    </span>
  );
}
