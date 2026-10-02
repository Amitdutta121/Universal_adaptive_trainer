"use client";

/**
 * Version B · Live matrix.
 *
 * One screen where cause and effect are visible together: capabilities (grouped by family) on the
 * left, the question types they make possible on the right. Every toggle on the left re-derives
 * the tiles on the right immediately. Hovering or focusing a capability marks the question types
 * it grades or is needed by; hovering or focusing a type marks the capabilities it uses. A save
 * bar at the bottom says what would change, including questions that would stop being served.
 *
 * All data comes from `../mock-capabilities.ts`; nothing is loaded or saved.
 */

import { AlertTriangle, Bot, Lock } from "lucide-react";
import { useMemo, useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import {
  CAPABILITIES,
  CAPABILITIES_BY_ID,
  type Capability,
  type CapabilityFamily,
  FAMILY_LABEL,
  isSelectable,
  QUESTION_TYPES,
  type QuestionType,
  SUBJECT_PRESETS,
  type TypeAvailability,
  typeAvailability,
} from "../mock-capabilities";
import { Toggle } from "./toggle";

// TODO(real): the course name, its saved preset and its enabled set come from the course settings
// endpoint (G3). Here the "saved" state is the Intro programming preset.
const COURSE_NAME = "Default course";
const SAVED_PRESET_ID = "intro_python";

type Focus = { kind: "capability"; id: string } | { kind: "type"; id: string } | null;

const FAMILIES = Object.keys(FAMILY_LABEL) as CapabilityFamily[];

function presetCapabilities(presetId: string): Set<string> {
  const preset = SUBJECT_PRESETS.find((p) => p.id === presetId);
  // Planned capabilities have no grader, so a preset can only switch on the built ones.
  return new Set(
    (preset?.capabilities ?? []).filter((id) => {
      const capability = CAPABILITIES_BY_ID[id];
      return capability !== undefined && isSelectable(capability);
    }),
  );
}

/** Capabilities a preset lists that cannot be switched on yet. */
function presetPlanned(presetId: string): string[] {
  const preset = SUBJECT_PRESETS.find((p) => p.id === presetId);
  return (preset?.capabilities ?? []).filter((id) => {
    const capability = CAPABILITIES_BY_ID[id];
    return capability !== undefined && !isSelectable(capability);
  });
}

function capLabel(id: string): string {
  return CAPABILITIES_BY_ID[id]?.label ?? id;
}

function joinLabels(labels: string[], last: "and" | "or"): string {
  if (labels.length <= 1) return labels[0] ?? "";
  return `${labels.slice(0, -1).join(", ")} ${last} ${labels[labels.length - 1]}`;
}

/** How a capability relates to a question type, if at all. */
function relation(type: QuestionType, capabilityId: string): "grades" | "needed" | null {
  if (type.gradedBy.includes(capabilityId)) return "grades";
  if (type.alsoNeeds.includes(capabilityId)) return "needed";
  return null;
}

/** Plain-language reason a type is unavailable. */
function unavailableReason(row: TypeAvailability, enabled: ReadonlySet<string>): string {
  const parts: string[] = [];
  if (row.gradedByEnabled.length === 0) {
    const graders = row.type.gradedBy.map((id) => {
      const capability = CAPABILITIES_BY_ID[id];
      return capability && !isSelectable(capability)
        ? `${capability.label} (not built yet)`
        : capLabel(id);
    });
    parts.push(
      graders.length > 1 ? `one of ${joinLabels(graders, "or")}` : (graders[0] ?? "a grader"),
    );
  }
  const needs = row.type.alsoNeeds.filter((id) => !enabled.has(id)).map(capLabel);
  if (needs.length > 0) parts.push(joinLabels(needs, "and"));
  return `Needs ${parts.join(", plus ")}`;
}

const SAVED_ENABLED = presetCapabilities(SAVED_PRESET_ID);
const SAVED_POSSIBLE = new Set(
  typeAvailability(SAVED_ENABLED)
    .filter((row) => row.possible)
    .map((row) => row.type.id),
);

export function VersionB() {
  const [presetId, setPresetId] = useState(SAVED_PRESET_ID);
  const [enabled, setEnabled] = useState<Set<string>>(() => new Set(SAVED_ENABLED));
  const [switchedOff, setSwitchedOff] = useState<Set<string>>(() => new Set());
  const [focus, setFocus] = useState<Focus>(null);
  const [saveClicked, setSaveClicked] = useState(false);

  const rows = useMemo(() => typeAvailability(enabled, switchedOff), [enabled, switchedOff]);
  const allowedCount = rows.filter((row) => row.allowed).length;
  const offCount = rows.filter((row) => row.possible && !row.allowed).length;

  // Capabilities the saved course had on that are now off, and the types that stop being served.
  const turnedOff = [...SAVED_ENABLED].filter((id) => !enabled.has(id));
  const stopServing = rows.filter((row) => SAVED_POSSIBLE.has(row.type.id) && !row.possible);
  const dirty =
    presetId !== SAVED_PRESET_ID ||
    turnedOff.length > 0 ||
    [...enabled].some((id) => !SAVED_ENABLED.has(id)) ||
    switchedOff.size > 0;

  function choosePreset(next: string) {
    setPresetId(next);
    setEnabled(presetCapabilities(next));
    setSwitchedOff(new Set());
    setSaveClicked(false);
  }

  function setCapability(id: string, on: boolean) {
    setEnabled((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
    setSaveClicked(false);
  }

  function setTypeAllowed(id: string, allowed: boolean) {
    setSwitchedOff((prev) => {
      const next = new Set(prev);
      if (allowed) next.delete(id);
      else next.add(id);
      return next;
    });
    setSaveClicked(false);
  }

  function discard() {
    choosePreset(SAVED_PRESET_ID);
  }

  const focusedType =
    focus?.kind === "type" ? QUESTION_TYPES.find((t) => t.id === focus.id) : undefined;
  const preset = SUBJECT_PRESETS.find((p) => p.id === presetId);

  return (
    <div className="flex flex-col gap-5 pb-24">
      {/* Top bar */}
      <div className="flex flex-wrap items-end gap-x-6 gap-y-3 border-b pb-4">
        <div className="mr-auto">
          <div className="text-muted-foreground text-xs">Course</div>
          <h1 className="font-semibold text-lg">{COURSE_NAME}</h1>
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="b-preset" className="text-muted-foreground text-xs">
            Subject preset
          </Label>
          <Select value={presetId} onValueChange={choosePreset}>
            <SelectTrigger id="b-preset" className="w-64">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SUBJECT_PRESETS.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <output aria-live="polite" className="pb-1.5 text-sm tabular-nums">
          <span className="font-medium">{enabled.size}</span>{" "}
          <span className="text-muted-foreground">
            {enabled.size === 1 ? "capability" : "capabilities"} on ·
          </span>{" "}
          <span className="font-medium">{allowedCount}</span>{" "}
          <span className="text-muted-foreground">
            question {allowedCount === 1 ? "type" : "types"} allowed
          </span>
          {offCount > 0 ? (
            <span className="text-muted-foreground"> · {offCount} switched off</span>
          ) : null}
        </output>
      </div>
      {preset ? (
        <p className="-mt-2 text-muted-foreground text-sm">
          {preset.blurb} Changing the preset resets the capabilities below.
          {presetPlanned(preset.id).length > 0
            ? ` This preset also expects ${joinLabels(presetPlanned(preset.id).map(capLabel), "and")}, which ${presetPlanned(preset.id).length === 1 ? "is" : "are"} not built yet and stay${presetPlanned(preset.id).length === 1 ? "s" : ""} off.`
            : null}
        </p>
      ) : null}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        {/* Left: capabilities */}
        <section aria-labelledby="b-caps-heading" className="flex flex-col gap-3">
          <div className="flex items-baseline justify-between">
            <h2 id="b-caps-heading" className="font-medium text-sm">
              Capabilities
            </h2>
            <span className="text-muted-foreground text-xs">What the course can check</span>
          </div>
          <div className="divide-y rounded-lg border bg-card">
            {FAMILIES.map((family) => {
              const members = CAPABILITIES.filter((c) => c.family === family);
              if (members.length === 0) return null;
              return (
                <div key={family} className="py-1">
                  <h3 className="px-3 pt-2 pb-1 font-medium text-muted-foreground text-xs">
                    {FAMILY_LABEL[family]}
                  </h3>
                  <ul>
                    {members.map((capability) => (
                      <CapabilityRow
                        key={capability.id}
                        capability={capability}
                        on={enabled.has(capability.id)}
                        onChange={(on) => setCapability(capability.id, on)}
                        focus={focus}
                        setFocus={setFocus}
                        link={focusedType ? relation(focusedType, capability.id) : null}
                      />
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        </section>

        {/* Right: question types */}
        <section aria-labelledby="b-types-heading" className="flex flex-col gap-3">
          <div className="flex items-baseline justify-between">
            <h2 id="b-types-heading" className="font-medium text-sm">
              Question types
            </h2>
            <span className="text-muted-foreground text-xs">
              What the AI may generate for this course
            </span>
          </div>
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {rows.map((row) => (
              <TypeTile
                key={row.type.id}
                row={row}
                enabled={enabled}
                onAllowedChange={(allowed) => setTypeAllowed(row.type.id, allowed)}
                focus={focus}
                setFocus={setFocus}
                link={focus?.kind === "capability" ? relation(row.type, focus.id) : null}
              />
            ))}
          </ul>
          <p className="text-muted-foreground text-xs">
            A type is possible when an enabled capability can grade it and everything it needs is
            on. You can switch off a possible type; you cannot turn on one nothing can grade.
          </p>
        </section>
      </div>

      {/* Save bar */}
      <div className="sticky bottom-0 z-10 -mx-6 border-t bg-background/95 px-6 py-3 backdrop-blur">
        <div className="flex flex-col gap-3">
          {turnedOff.length > 0 ? (
            <Alert className="border-[var(--warn-solid)]/40 bg-[var(--warn-wash)]">
              <AlertTriangle className="text-[var(--warn-solid)]" />
              <AlertTitle>
                {joinLabels(turnedOff.map(capLabel), "and")}{" "}
                {turnedOff.length === 1 ? "was" : "were"} on for this course
              </AlertTitle>
              <AlertDescription className="text-foreground/80">
                {stopServing.length > 0
                  ? `Existing ${joinLabels(
                      stopServing.map((row) => row.type.label),
                      "and",
                    )} questions will stop being served to students. `
                  : "Existing questions that need it will stop being served to students. "}
                They are kept, not deleted, and come back if you turn it on again.
              </AlertDescription>
            </Alert>
          ) : null}
          <div className="flex flex-wrap items-center justify-end gap-3">
            <span className="mr-auto text-muted-foreground text-xs">
              {saveClicked
                ? "Prototype — nothing is saved. In the app this would update the course."
                : dirty
                  ? "Unsaved changes · Prototype — nothing is saved"
                  : "No changes · Prototype — nothing is saved"}
            </span>
            <Button variant="ghost" size="sm" onClick={discard} disabled={!dirty}>
              Discard changes
            </Button>
            <Button
              size="sm"
              disabled={!dirty}
              onClick={() => {
                // TODO(real): PUT the course's preset, enabled capabilities and switched-off types.
                setSaveClicked(true);
              }}
            >
              Save
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

interface CapabilityRowProps {
  capability: Capability;
  on: boolean;
  onChange: (on: boolean) => void;
  focus: Focus;
  setFocus: (focus: Focus) => void;
  /** Set when a question type is hovered: how this capability relates to it. */
  link: "grades" | "needed" | null;
}

function CapabilityRow({ capability, on, onChange, focus, setFocus, link }: CapabilityRowProps) {
  const selectable = isSelectable(capability);
  const self = focus?.kind === "capability" && focus.id === capability.id;
  const typeFocused = focus?.kind === "type";
  const usedBy = QUESTION_TYPES.filter((t) => relation(t, capability.id) !== null).length;
  const cardId = `b-cap-${capability.id}`;

  return (
    <li
      onMouseEnter={() => setFocus({ kind: "capability", id: capability.id })}
      onMouseLeave={() => setFocus(null)}
      onFocus={() => setFocus({ kind: "capability", id: capability.id })}
      onBlur={() => setFocus(null)}
      className={cn(
        "flex gap-3 border-transparent border-l-2 px-3 py-2 transition-colors",
        self && "bg-muted/60",
        link && "border-l-[var(--accent-solid)] bg-[var(--accent-wash)]/50",
        typeFocused && !link && "opacity-55",
      )}
    >
      <div className="pt-0.5">
        <Toggle
          checked={on}
          onCheckedChange={onChange}
          disabled={!selectable}
          label={capability.label}
          describedBy={cardId}
        />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={cn("font-medium text-sm", !selectable && "text-muted-foreground")}>
            {capability.label}
          </span>
          {!selectable ? (
            <Badge variant="outline" className="text-muted-foreground">
              <Lock /> Not built yet
            </Badge>
          ) : null}
          {!capability.deterministic ? (
            <Badge className="bg-[var(--warn-wash)] text-[var(--warn-solid)]">
              <Bot /> AI-graded · practice only
            </Badge>
          ) : null}
          {link ? (
            <span className="ml-auto text-[var(--accent-text)] text-xs">
              {link === "grades" ? "grades it" : "needed"}
            </span>
          ) : null}
        </div>
        <p id={cardId} className="mt-0.5 text-muted-foreground text-xs leading-relaxed">
          {capability.card}
          {!capability.deterministic ? " Never counts toward mastery." : null}
        </p>
        <p className="mt-0.5 font-mono text-[11px] text-muted-foreground/80">
          {capability.id}
          {capability.grader ? ` · ${capability.grader}` : ""} · used by {usedBy}{" "}
          {usedBy === 1 ? "type" : "types"}
        </p>
      </div>
    </li>
  );
}

interface TypeTileProps {
  row: TypeAvailability;
  enabled: ReadonlySet<string>;
  onAllowedChange: (allowed: boolean) => void;
  focus: Focus;
  setFocus: (focus: Focus) => void;
  /** Set when a capability is hovered: how it relates to this type. */
  link: "grades" | "needed" | null;
}

function TypeTile({ row, enabled, onAllowedChange, focus, setFocus, link }: TypeTileProps) {
  const { type, possible, allowed, gradedByEnabled } = row;
  const self = focus?.kind === "type" && focus.id === type.id;
  const capabilityFocused = focus?.kind === "capability";
  const status = allowed ? "allowed" : possible ? "off" : "unavailable";
  const reasonId = `b-type-${type.id}`;
  const aiGraded = gradedByEnabled.some((id) => CAPABILITIES_BY_ID[id]?.deterministic === false);

  return (
    <li
      onMouseEnter={() => setFocus({ kind: "type", id: type.id })}
      onMouseLeave={() => setFocus(null)}
      onFocus={() => setFocus({ kind: "type", id: type.id })}
      onBlur={() => setFocus(null)}
      className={cn(
        "flex flex-col gap-1 rounded-lg border px-3 py-2.5 transition-colors",
        status === "unavailable" ? "bg-muted/40" : "bg-card",
        self && "border-foreground/25",
        link && "border-[var(--accent-solid)] ring-1 ring-[var(--accent-solid)]/30",
        capabilityFocused && !link && "opacity-55",
      )}
    >
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <div
            className={cn(
              "font-medium text-sm",
              status === "unavailable" && "text-muted-foreground",
              status === "off" &&
                "text-muted-foreground line-through decoration-muted-foreground/50",
            )}
          >
            {type.label}
          </div>
          <div className="text-muted-foreground text-xs">
            {type.widget}
            {link ? (
              <span className="text-[var(--accent-text)]">
                {link === "grades" ? " · graded by it" : " · needs it"}
              </span>
            ) : null}
          </div>
        </div>
        <StatusChip status={status} />
        {possible ? (
          <Toggle
            size="sm"
            checked={allowed}
            onCheckedChange={onAllowedChange}
            label={`Allow ${type.label}`}
            describedBy={reasonId}
          />
        ) : null}
      </div>
      <p
        id={reasonId}
        className={cn(
          "text-xs",
          status === "allowed" ? "text-foreground/80" : "text-muted-foreground",
        )}
      >
        {status === "unavailable"
          ? unavailableReason(row, enabled)
          : status === "off"
            ? "Switched off for this course. No new questions of this type."
            : `Graded by ${joinLabels(gradedByEnabled.map(capLabel), "or")}${
                type.alsoNeeds.length > 0
                  ? ` · uses ${joinLabels(type.alsoNeeds.map(capLabel), "and")}`
                  : ""
              }`}
      </p>
      {status === "allowed" && aiGraded ? (
        <p className="text-[var(--warn-solid)] text-xs">
          AI-graded · practice only — never counts toward mastery
        </p>
      ) : null}
    </li>
  );
}

function StatusChip({ status }: { status: "allowed" | "off" | "unavailable" }) {
  if (status === "allowed") {
    return <Badge className="bg-[var(--accent-wash)] text-[var(--accent-text)]">Allowed</Badge>;
  }
  if (status === "off") {
    return (
      <Badge variant="outline" className="text-muted-foreground">
        Switched off
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="border-dashed text-muted-foreground">
      Unavailable
    </Badge>
  );
}
