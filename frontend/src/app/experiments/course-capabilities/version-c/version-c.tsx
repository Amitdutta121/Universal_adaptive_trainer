"use client";

/**
 * Version C · Settings table.
 *
 * The capability setup as it would sit in an existing course's Settings, on a "Grading" tab: a
 * subject-preset select with "Reset to preset", a capabilities table grouped by family with an
 * on/off switch per row, and a derived question-types table whose switches only work for types
 * something enabled can grade. Edits are held as a draft; a sticky bar lists the diff against the
 * saved state and warns, calmly, when switching a capability off stops existing questions from
 * being served. The saved state is the "Intro programming (Python)" preset.
 */

import { RotateCcw, TriangleAlert } from "lucide-react";
import { type ReactNode, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import {
  CAPABILITIES,
  CAPABILITIES_BY_ID,
  type Capability,
  type CapabilityFamily,
  FAMILY_LABEL,
  isSelectable,
  SUBJECT_PRESETS,
  type TypeAvailability,
  typeAvailability,
} from "../mock-capabilities";
import { Toggle } from "./toggle";

interface GradingSettings {
  presetId: string;
  enabled: ReadonlySet<string>;
  /** Question types the professor switched off although they are possible. */
  switchedOff: ReadonlySet<string>;
}

// TODO(real): load the course's saved grading settings (G3) instead of this fixed state.
const SAVED: GradingSettings = {
  presetId: "intro_python",
  enabled: new Set(presetCapabilities("intro_python")),
  switchedOff: new Set(),
};

const FAMILIES = Object.keys(FAMILY_LABEL) as CapabilityFamily[];

function presetCapabilities(presetId: string): readonly string[] {
  return SUBJECT_PRESETS.find((preset) => preset.id === presetId)?.capabilities ?? [];
}

function minus<T>(a: ReadonlySet<T>, b: ReadonlySet<T>): T[] {
  return [...a].filter((item) => !b.has(item));
}

function capLabel(id: string): string {
  return CAPABILITIES_BY_ID[id]?.label ?? id;
}

function joinLabels(labels: string[]): string {
  return labels.join(", ");
}

export function VersionC() {
  const [draft, setDraft] = useState<GradingSettings>(SAVED);
  const [saveAttempted, setSaveAttempted] = useState(false);

  const savedTypes = useMemo(() => typeAvailability(SAVED.enabled, SAVED.switchedOff), []);
  const draftTypes = useMemo(
    () => typeAvailability(draft.enabled, draft.switchedOff),
    [draft.enabled, draft.switchedOff],
  );

  const diff = useMemo(
    () => computeDiff(draft, draftTypes, savedTypes),
    [draft, draftTypes, savedTypes],
  );

  function update(next: Partial<GradingSettings>) {
    setDraft((current) => ({ ...current, ...next }));
    setSaveAttempted(false);
  }

  function setCapability(id: string, on: boolean) {
    const enabled = new Set(draft.enabled);
    if (on) enabled.add(id);
    else enabled.delete(id);
    update({ enabled });
  }

  function setTypeAllowed(id: string, allowed: boolean) {
    const switchedOff = new Set(draft.switchedOff);
    if (allowed) switchedOff.delete(id);
    else switchedOff.add(id);
    update({ switchedOff });
  }

  function resetToPreset() {
    update({ enabled: new Set(presetCapabilities(draft.presetId)), switchedOff: new Set() });
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        {/* TODO(real): course name and code come from the course record. */}
        <p className="text-muted-foreground text-xs">CS 101 · Introduction to Programming</p>
        <h1 className="font-semibold text-xl tracking-tight">Course settings</h1>
      </div>

      <Tabs defaultValue="grading">
        <TabsList variant="line" className="border-b pb-1">
          <TabsTrigger value="general" disabled>
            General
          </TabsTrigger>
          <TabsTrigger value="grading">Grading</TabsTrigger>
          <TabsTrigger value="members" disabled>
            Members
          </TabsTrigger>
        </TabsList>

        <TabsContent value="grading" className="flex flex-col gap-8 pt-4">
          <PresetSection
            presetId={draft.presetId}
            enabled={draft.enabled}
            onPresetChange={(presetId) => update({ presetId })}
            onReset={resetToPreset}
          />
          <CapabilitiesSection enabled={draft.enabled} onToggle={setCapability} />
          <QuestionTypesSection types={draftTypes} onToggle={setTypeAllowed} />

          {diff.dirty ? (
            <UnsavedBar
              diff={diff}
              saveAttempted={saveAttempted}
              onDiscard={() => {
                setDraft(SAVED);
                setSaveAttempted(false);
              }}
              onSave={() => {
                // TODO(real): PUT the course's grading settings, then refresh the saved state.
                setSaveAttempted(true);
              }}
            />
          ) : null}
        </TabsContent>
      </Tabs>
    </div>
  );
}

/* ------------------------------------------------------------------------------------------ */

function SectionHeading({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <h2 id={id} className="font-semibold text-base">
        {title}
      </h2>
      {children ? <p className="max-w-3xl text-muted-foreground text-sm">{children}</p> : null}
    </div>
  );
}

function PresetSection({
  presetId,
  enabled,
  onPresetChange,
  onReset,
}: {
  presetId: string;
  enabled: ReadonlySet<string>;
  onPresetChange: (presetId: string) => void;
  onReset: () => void;
}) {
  const preset = SUBJECT_PRESETS.find((item) => item.id === presetId);
  const presetSet = new Set(presetCapabilities(presetId));
  const added = minus(enabled, presetSet).map(capLabel);
  const removed = minus(presetSet, enabled).map(capLabel);
  const matches = added.length === 0 && removed.length === 0;

  return (
    <section aria-labelledby="preset-heading" className="flex flex-col gap-3">
      <SectionHeading id="preset-heading" title="Subject preset">
        The preset is the starting set of capabilities for this kind of course. You can change
        capabilities below without changing the preset.
      </SectionHeading>
      <div className="flex flex-wrap items-center gap-2">
        <Select value={presetId} onValueChange={onPresetChange}>
          <SelectTrigger className="w-72" aria-label="Subject preset">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SUBJECT_PRESETS.map((item) => (
              <SelectItem key={item.id} value={item.id}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button variant="outline" onClick={onReset} disabled={matches}>
          <RotateCcw data-icon="inline-start" />
          Reset to preset
        </Button>
      </div>
      <div className="text-muted-foreground text-xs" aria-live="polite">
        {preset ? <span>{preset.blurb} </span> : null}
        {matches ? (
          <span>Capabilities match this preset.</span>
        ) : (
          <span>
            Differs from preset
            {added.length > 0 ? ` · added ${joinLabels(added)}` : ""}
            {removed.length > 0 ? ` · removed ${joinLabels(removed)}` : ""}.
          </span>
        )}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------------------------------ */

function KindBadge({ capability }: { capability: Capability }) {
  if (capability.deterministic) {
    return <Badge variant="outline">Deterministic</Badge>;
  }
  return (
    <div className="flex flex-col items-start gap-0.5">
      <Badge className="bg-[var(--warn-wash)] text-[var(--warn-solid)]">
        AI-graded · practice only
      </Badge>
      <span className="text-[11px] text-muted-foreground">Never counts toward mastery</span>
    </div>
  );
}

function StatusLabel({ capability }: { capability: Capability }) {
  if (isSelectable(capability)) {
    return <span className="text-sm">Available</span>;
  }
  return <span className="text-muted-foreground text-sm">Not built yet</span>;
}

function ChangedDot({ changed }: { changed: boolean }) {
  if (!changed) return null;
  return (
    <>
      <span aria-hidden className="inline-block size-1.5 rounded-full bg-[var(--warn-solid)]" />
      <span className="sr-only">(unsaved change)</span>
    </>
  );
}

function CapabilitiesSection({
  enabled,
  onToggle,
}: {
  enabled: ReadonlySet<string>;
  onToggle: (id: string, on: boolean) => void;
}) {
  const onCount = CAPABILITIES.filter((capability) => enabled.has(capability.id)).length;

  return (
    <section aria-labelledby="capabilities-heading" className="flex flex-col gap-3">
      <div className="flex items-end justify-between gap-4">
        <SectionHeading id="capabilities-heading" title="Grading capabilities">
          What this course can check. The AI only writes questions that an enabled capability can
          grade. Turning one off keeps existing questions; the ones that need it stop being served.
        </SectionHeading>
        <span className="shrink-0 text-muted-foreground text-xs">
          {onCount} of {CAPABILITIES.length} on
        </span>
      </div>

      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="pl-4">Capability</TableHead>
              <TableHead>What it checks</TableHead>
              <TableHead>Grader</TableHead>
              <TableHead>Kind</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="pr-4 text-right">On</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {FAMILIES.map((family) => {
              const rows = CAPABILITIES.filter((capability) => capability.family === family);
              if (rows.length === 0) return null;
              return [
                <TableRow key={`family-${family}`} className="bg-muted/40 hover:bg-muted/40">
                  <TableCell
                    colSpan={6}
                    className="py-1.5 pl-4 font-medium text-muted-foreground text-xs"
                  >
                    {FAMILY_LABEL[family]}
                  </TableCell>
                </TableRow>,
                ...rows.map((capability) => {
                  const on = enabled.has(capability.id);
                  const selectable = isSelectable(capability);
                  const changed = on !== SAVED.enabled.has(capability.id);
                  const reasonId = `cap-reason-${capability.id}`;
                  return (
                    <TableRow
                      key={capability.id}
                      className={cn(!selectable && "text-muted-foreground")}
                    >
                      <TableCell className="pl-4 align-top">
                        <div className="flex items-center gap-1.5 font-medium">
                          {capability.label}
                          <ChangedDot changed={changed} />
                        </div>
                        <div className="font-mono text-[11px] text-muted-foreground">
                          {capability.id}
                        </div>
                      </TableCell>
                      <TableCell className="min-w-72 max-w-md whitespace-normal align-top text-sm">
                        {capability.card}
                      </TableCell>
                      <TableCell className="align-top font-mono text-xs">
                        {capability.grader ?? <span className="text-muted-foreground">—</span>}
                      </TableCell>
                      <TableCell className="align-top">
                        <KindBadge capability={capability} />
                      </TableCell>
                      <TableCell className="align-top">
                        <span id={reasonId}>
                          <StatusLabel capability={capability} />
                        </span>
                      </TableCell>
                      <TableCell className="pr-4 text-right align-top">
                        <Toggle
                          checked={on}
                          disabled={!selectable}
                          label={capability.label}
                          describedBy={reasonId}
                          onChange={(next) => onToggle(capability.id, next)}
                        />
                      </TableCell>
                    </TableRow>
                  );
                }),
              ];
            })}
          </TableBody>
        </Table>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------------------------------ */

function TypeStatus({ availability }: { availability: TypeAvailability }) {
  if (availability.allowed) {
    const practiceOnly = availability.gradedByEnabled.every(
      (id) => CAPABILITIES_BY_ID[id]?.deterministic === false,
    );
    return (
      <div className="flex flex-col items-start gap-0.5">
        <Badge className="bg-[var(--accent-wash)] text-[var(--accent-text)]">Allowed</Badge>
        {practiceOnly ? (
          <span className="text-[11px] text-muted-foreground">Practice only · AI-graded</span>
        ) : null}
      </div>
    );
  }
  if (availability.possible) {
    return <Badge variant="outline">Off</Badge>;
  }
  return (
    <span className="whitespace-normal text-muted-foreground text-sm">
      Unavailable — needs {joinLabels(availability.missing.map(capLabel))}
    </span>
  );
}

function QuestionTypesSection({
  types,
  onToggle,
}: {
  types: TypeAvailability[];
  onToggle: (id: string, allowed: boolean) => void;
}) {
  const allowedCount = types.filter((item) => item.allowed).length;
  const savedAllowed = new Set(
    typeAvailability(SAVED.enabled, SAVED.switchedOff)
      .filter((item) => item.allowed)
      .map((item) => item.type.id),
  );

  return (
    <section aria-labelledby="types-heading" className="flex flex-col gap-3">
      <div className="flex items-end justify-between gap-4">
        <SectionHeading id="types-heading" title="Question types">
          Worked out from the capabilities above. You can switch off a type the course could use; a
          type nothing enabled can grade stays unavailable until you turn on what it needs.
        </SectionHeading>
        <span className="shrink-0 text-muted-foreground text-xs">
          {allowedCount} of {types.length} allowed
        </span>
      </div>

      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="pl-4">Type</TableHead>
              <TableHead>Answer widget</TableHead>
              <TableHead>Graded by</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="pr-4 text-right">On</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {types.map((availability) => {
              const { type } = availability;
              const changed = availability.allowed !== savedAllowed.has(type.id);
              const statusId = `type-status-${type.id}`;
              return (
                <TableRow
                  key={type.id}
                  className={cn(!availability.possible && "text-muted-foreground")}
                >
                  <TableCell className="pl-4">
                    <div className="flex items-center gap-1.5 font-medium">
                      {type.label}
                      <ChangedDot changed={changed} />
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">{type.widget}</TableCell>
                  <TableCell className="text-sm">
                    {availability.gradedByEnabled.length > 0 ? (
                      joinLabels(availability.gradedByEnabled.map(capLabel))
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell id={statusId}>
                    <TypeStatus availability={availability} />
                  </TableCell>
                  <TableCell className="pr-4 text-right">
                    <Toggle
                      checked={availability.allowed}
                      disabled={!availability.possible}
                      label={type.label}
                      describedBy={statusId}
                      onChange={(next) => onToggle(type.id, next)}
                    />
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------------------------------ */

interface SettingsDiff {
  dirty: boolean;
  presetChanged: string | null;
  turnedOn: string[];
  turnedOff: string[];
  typesSwitchedOff: string[];
  typesSwitchedOn: string[];
  /** Types allowed before that the capability change made unavailable: their questions pause. */
  typesNoLongerServed: string[];
  /** Types that become possible through a capability change. */
  typesNowPossible: string[];
}

function computeDiff(
  draft: GradingSettings,
  draftTypes: TypeAvailability[],
  savedTypes: TypeAvailability[],
): SettingsDiff {
  const turnedOn = minus(draft.enabled, SAVED.enabled);
  const turnedOff = minus(SAVED.enabled, draft.enabled);
  const savedById = new Map(savedTypes.map((item) => [item.type.id, item]));

  const typesSwitchedOff: string[] = [];
  const typesSwitchedOn: string[] = [];
  const typesNoLongerServed: string[] = [];
  const typesNowPossible: string[] = [];

  for (const now of draftTypes) {
    const before = savedById.get(now.type.id);
    if (!before) continue;
    if (before.possible && !now.possible) {
      if (before.allowed) typesNoLongerServed.push(now.type.label);
    } else if (!before.possible && now.possible) {
      if (now.allowed) typesNowPossible.push(now.type.label);
    } else if (now.possible && before.allowed !== now.allowed) {
      (now.allowed ? typesSwitchedOn : typesSwitchedOff).push(now.type.label);
    }
  }

  const presetChanged =
    draft.presetId === SAVED.presetId
      ? null
      : (SUBJECT_PRESETS.find((preset) => preset.id === draft.presetId)?.label ?? draft.presetId);

  return {
    dirty:
      presetChanged !== null ||
      turnedOn.length + turnedOff.length + typesSwitchedOff.length + typesSwitchedOn.length > 0,
    presetChanged,
    turnedOn: turnedOn.map(capLabel),
    turnedOff: turnedOff.map(capLabel),
    typesSwitchedOff,
    typesSwitchedOn,
    typesNoLongerServed,
    typesNowPossible,
  };
}

function DiffLine({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <li>
      <span className="text-muted-foreground">{label}: </span>
      {joinLabels(items)}
    </li>
  );
}

function UnsavedBar({
  diff,
  saveAttempted,
  onDiscard,
  onSave,
}: {
  diff: SettingsDiff;
  saveAttempted: boolean;
  onDiscard: () => void;
  onSave: () => void;
}) {
  return (
    <section
      aria-label="Unsaved changes"
      className="sticky bottom-4 z-10 rounded-lg border bg-card p-4 shadow-lg"
    >
      <div className="flex flex-wrap items-start gap-4">
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <h2 className="font-medium text-sm">Unsaved changes</h2>
          <ul className="flex flex-col gap-0.5 text-sm">
            {diff.presetChanged ? <DiffLine label="Preset" items={[diff.presetChanged]} /> : null}
            <DiffLine label="Turned on" items={diff.turnedOn} />
            <DiffLine label="Turned off" items={diff.turnedOff} />
            <DiffLine label="Question types switched off" items={diff.typesSwitchedOff} />
            <DiffLine label="Question types switched on" items={diff.typesSwitchedOn} />
            <DiffLine label="Newly allowed question types" items={diff.typesNowPossible} />
          </ul>
          {diff.turnedOff.length > 0 ? (
            <div className="flex gap-2 rounded-md bg-[var(--warn-wash)] px-3 py-2 text-sm">
              <TriangleAlert
                aria-hidden
                className="mt-0.5 size-4 shrink-0 text-[var(--warn-solid)]"
              />
              <p>
                {diff.typesNoLongerServed.length > 0 ? (
                  <>
                    Existing {joinLabels(diff.typesNoLongerServed)} questions will stop being served
                    to students.{" "}
                  </>
                ) : (
                  <>Questions that need {joinLabels(diff.turnedOff)} will stop being served. </>
                )}
                They are kept, not deleted, and come back if you turn{" "}
                {diff.turnedOff.length === 1 ? "it" : "them"} on again.
              </p>
            </div>
          ) : null}
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <div className="flex gap-2">
            <Button variant="outline" onClick={onDiscard}>
              Discard
            </Button>
            <Button onClick={onSave}>Save changes</Button>
          </div>
          {saveAttempted ? (
            <p role="status" className="text-muted-foreground text-xs">
              Prototype — nothing is saved
            </p>
          ) : null}
        </div>
      </div>
    </section>
  );
}
