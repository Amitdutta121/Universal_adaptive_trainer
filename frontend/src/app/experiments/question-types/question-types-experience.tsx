"use client";

/**
 * Type-first question setup for a new Intro Python course, every screen of it. The bar on top
 * jumps to any screen (`?screen=`, or `[` / `]`); below it is the dialog as the professor sees
 * it, fully clickable.
 *
 * Flow: Set up questions opens on the whole course with every type allowed and every style on
 * -> optionally adjust one subtopic -> turning a style off (or back on) asks what happens to its
 * existing questions -> targets -> approve. Course settings, reached separately, blocks or allows
 * types; setup greys a blocked type and can allow it again.
 *
 * Styles are the real library (library-python.ts). TODO(real): AI fit, question counts and
 * targets are stand-ins (setup-model.ts).
 */

import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { parseAsStringLiteral, useQueryState } from "nuqs";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { DIFFICULTIES } from "../question-setup/mock-types";
import { PYTHON_COURSE } from "./course-python";
import { SettingsStep } from "./settings-step";
import {
  COURSE,
  type Course,
  covers,
  effective,
  existingCount,
  hiddenCount,
  initialState,
  type LibraryStyle,
  resetSubtopic,
  type Scope,
  type SetupState,
  setAllowed,
  subtopics,
  targetsFor,
  turnOff,
  turnOn,
  typeGroups,
} from "./setup-model";
import { StylesStep } from "./step-styles";
import { TargetsStep } from "./step-targets";
import { type PendingToggle, ToggleDialog } from "./toggle-dialog";

const SCREENS = ["course", "subtopic", "turn-off", "turn-on", "targets", "settings"] as const;
type Screen = (typeof SCREENS)[number];
const SCREEN_LABEL: Record<Screen, string> = {
  course: "Types for the course",
  subtopic: "Adjust one subtopic",
  "turn-off": "Turn off a style",
  "turn-on": "Turn a style back on",
  targets: "Targets",
  settings: "Course settings",
};

export function QuestionTypesExperience() {
  const [screen, setScreen] = useQueryState(
    "screen",
    parseAsStringLiteral(SCREENS).withDefault("course"),
  );
  // Bumped on every jump from the prototype bar, so the dialog starts that screen fresh.
  const [jump, setJump] = useState(0);

  const go = useCallback(
    (next: Screen) => {
      void setScreen(next);
      setJump((value) => value + 1);
    },
    [setScreen],
  );

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (
        event.target instanceof HTMLElement &&
        event.target.closest("input, textarea, [role=dialog]")
      )
        return;
      const index = SCREENS.indexOf(screen);
      if (event.key === "]" && index < SCREENS.length - 1) go(SCREENS[index + 1]);
      if (event.key === "[" && index > 0) go(SCREENS[index - 1]);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [screen, go]);

  const index = SCREENS.indexOf(screen);

  return (
    <div className="min-h-screen bg-muted/40">
      <header className="sticky top-0 z-20 border-b bg-background">
        <div className="mx-auto flex w-full max-w-[1280px] flex-wrap items-center gap-3 px-6 py-2.5">
          <div className="mr-4">
            <div className="font-semibold text-sm">Question setup — prototype</div>
            <div className="text-muted-foreground text-xs">
              New course · [ and ] step through screens
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Previous screen"
            disabled={index === 0}
            onClick={() => go(SCREENS[index - 1])}
          >
            <ChevronLeft />
          </Button>
          <div role="tablist" aria-label="Screen" className="flex flex-wrap gap-1">
            {SCREENS.map((entry, position) => (
              <button
                key={entry}
                type="button"
                role="tab"
                aria-selected={screen === entry}
                onClick={() => go(entry)}
                className="flex items-center gap-2 rounded-md border px-2.5 py-1 text-xs aria-selected:border-primary aria-selected:bg-primary aria-selected:text-primary-foreground"
              >
                <span className="tabular-nums opacity-70">{position + 1}</span>
                {SCREEN_LABEL[entry]}
              </button>
            ))}
          </div>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Next screen"
            disabled={index === SCREENS.length - 1}
            onClick={() => go(SCREENS[index + 1])}
          >
            <ChevronRight />
          </Button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1280px] px-6 py-6">
        <SetupDialogFrame
          key={jump}
          course={PYTHON_COURSE}
          screen={screen}
          onScreen={(next) => void setScreen(next)}
        />
      </main>
    </div>
  );
}

interface View {
  state: SetupState;
  step: "settings" | "styles" | "targets";
  scope: Scope;
  typeId: string;
  pending: PendingToggle | null;
}

/** The view a screen opens on, so each one can be reached directly. */
function viewFor(screen: Screen, course: Course): View {
  const groups = typeGroups(course);
  const refs = subtopics(course);
  let state = initialState(course);
  const base: View = {
    state,
    step: "styles",
    scope: COURSE,
    typeId: groups[0]?.id ?? "",
    pending: null,
  };
  if (screen === "settings") return { ...base, step: "settings" };
  if (screen === "targets") return { ...base, step: "targets" };
  if (screen === "subtopic") return { ...base, scope: refs[1]?.subtopic.id ?? COURSE };

  // The last style of the type with the most styles: it has questions behind it.
  const sample =
    [...groups].sort((a, b) => b.styles.length - a.styles.length)[0]?.styles.at(-1) ??
    course.library[0];
  const count = existingCount(sample, COURSE);
  const shared = {
    label: sample.name,
    styleIds: [sample.id],
    scopeLabel: "the whole course",
    count,
    perStyle: { [sample.id]: count },
    slotsBelowTarget: slotsBelowTarget(state, course, COURSE, [sample]),
  };
  const typeId = sample.questionType;
  if (screen === "turn-off") return { ...base, typeId, pending: { mode: "off", ...shared } };
  if (screen === "turn-on") {
    state = turnOff(state, COURSE, [sample.id], { [sample.id]: count });
    return { ...base, state, typeId, pending: { mode: "on", ...shared } };
  }
  return base;
}

/** Capped by the questions hidden: each hidden question can empty at most one level. */
function slotsBelowTarget(
  state: SetupState,
  course: Course,
  scope: Scope,
  styles: readonly LibraryStyle[],
): number {
  let slots = 0;
  for (const ref of subtopics(course)) {
    if (scope !== COURSE && ref.subtopic.id !== scope) continue;
    const on = effective(state, course, ref);
    const targets = targetsFor(ref.subtopic);
    for (const difficulty of DIFFICULTIES) {
      const hit = styles.some((s) => covers(s, difficulty) && on.has(s.id));
      if (hit && targets[difficulty] > 0) slots++;
    }
  }
  const hiding = styles.reduce((sum, style) => sum + existingCount(style, scope), 0);
  return Math.min(slots, hiding);
}

function SetupDialogFrame({
  course,
  screen,
  onScreen,
}: {
  course: Course;
  screen: Screen;
  onScreen(screen: Screen): void;
}) {
  const groups = typeGroups(course);
  const refs = subtopics(course);
  const [view, setView] = useState<View>(() => viewFor(screen, course));
  const [saved, setSaved] = useState(false);
  const { state, step, scope, typeId, pending } = view;
  const update = (patch: Partial<View>) => setView((current) => ({ ...current, ...patch }));

  const scopeLabel =
    scope === COURSE
      ? "the whole course"
      : (refs.find((r) => r.subtopic.id === scope)?.subtopic.name ?? "");

  function requestToggle(styles: readonly LibraryStyle[], on: boolean, label: string) {
    const ids = styles.map((style) => style.id);
    if (ids.length === 0) return;
    if (on) {
      const count = hiddenCount(state, scope, ids);
      if (count === 0) return update({ state: turnOn(state, course, scope, ids, false) });
      return update({
        pending: {
          mode: "on",
          styleIds: ids,
          label,
          scopeLabel,
          count,
          perStyle: {},
          slotsBelowTarget: 0,
        },
      });
    }
    const perStyle = Object.fromEntries(
      styles.map((style) => [style.id, existingCount(style, scope)]),
    );
    const count = Object.values(perStyle).reduce((sum, value) => sum + value, 0);
    if (count === 0) return update({ state: turnOff(state, scope, ids, null) });
    update({
      pending: {
        mode: "off",
        styleIds: ids,
        label,
        scopeLabel,
        count,
        perStyle,
        slotsBelowTarget: slotsBelowTarget(state, course, scope, styles),
      },
    });
  }

  function confirm(withQuestions: boolean) {
    if (!pending) return;
    const next =
      pending.mode === "off"
        ? turnOff(state, scope, pending.styleIds, withQuestions ? pending.perStyle : null)
        : turnOn(state, course, scope, pending.styleIds, withQuestions);
    update({ state: next, pending: null });
  }

  function toStyles(nextScope: Scope = scope) {
    update({ step: "styles", scope: nextScope });
    onScreen(nextScope === COURSE ? "course" : "subtopic");
  }

  const empty = refs.filter((ref) => effective(state, course, ref).size === 0).length;

  return (
    <div className="flex h-[min(860px,calc(100vh-130px))] min-h-[560px] flex-col overflow-hidden rounded-xl border bg-background shadow-sm">
      <div className="flex items-start gap-4 border-b px-6 py-4">
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold text-lg">
            {step === "settings" ? "Course settings" : "Set up questions"}
          </h2>
          <p className="text-muted-foreground text-sm">
            {step === "settings" ? course.name : course.taxonomyLabel}
          </p>
        </div>
        <X className="size-4 text-muted-foreground" aria-hidden />
      </div>

      {step === "settings" ? (
        <SettingsStep
          groups={groups}
          state={state}
          onAllowed={(id, allowed) => update({ state: setAllowed(state, id, allowed) })}
        />
      ) : step === "styles" ? (
        <StylesStep
          course={course}
          groups={groups}
          state={state}
          scope={scope}
          onScope={toStyles}
          typeId={typeId}
          onType={(next) => update({ typeId: next })}
          onToggle={requestToggle}
          onReset={(id) => update({ state: resetSubtopic(state, id) })}
          onAllow={(id) => update({ state: setAllowed(state, id, true) })}
        />
      ) : (
        <TargetsStep course={course} state={state} onAdjust={(id) => toStyles(id)} />
      )}

      <div className="flex items-center gap-3 border-t px-6 py-3">
        {step === "settings" ? (
          <>
            <span className="mr-auto" />
            <Button onClick={() => toStyles(COURSE)}>Set up questions</Button>
          </>
        ) : (
          <>
            <p
              className={cn(
                "mr-auto text-xs tabular-nums",
                empty > 0 ? "text-[var(--warn-solid)]" : "text-muted-foreground",
              )}
            >
              Step {step === "styles" ? 2 : 3} of 3 ·{" "}
              {step === "styles"
                ? `Editing ${scopeLabel}`
                : `${refs.length - empty} of ${refs.length} subtopics have a style`}
              {saved ? " · Saved (prototype, nothing sent)" : ""}
            </p>
            {step === "styles" ? (
              <>
                <Button variant="outline">Cancel</Button>
                <Button
                  onClick={() => {
                    update({ step: "targets" });
                    onScreen("targets");
                  }}
                >
                  Review targets
                </Button>
              </>
            ) : (
              <>
                <Button variant="outline" onClick={() => toStyles()}>
                  Back
                </Button>
                <Button disabled={empty > 0} onClick={() => setSaved(true)}>
                  Approve and generate round 1
                </Button>
              </>
            )}
          </>
        )}
      </div>

      <ToggleDialog
        pending={pending}
        onCancel={() => update({ pending: null })}
        onConfirm={confirm}
      />
    </div>
  );
}
