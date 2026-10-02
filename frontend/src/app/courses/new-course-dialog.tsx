"use client";

/**
 * The "New course" modal on My courses: create a course in two steps (ADR-054, design "option D"):
 *   1. Subject — a preset, described by the question types it gives.
 *   2. Question types — pre-ticked from the subject, each with an example in that subject's terms.
 *
 * The professor picks what students will do; the graders (capabilities) are worked out from the
 * chosen types on the server and never shown as a choice. Everything here comes from
 * `GET /api/courses/catalog`: only types the app can actually generate and grade can be ticked;
 * the rest are listed as "Coming soon". Groups the subject uses are open; the others sit under
 * "More question types".
 */

import { ArrowLeftIcon, ArrowRightIcon, CheckIcon, ChevronDownIcon, InfoIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { QueryError } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useAssessmentCatalog, useCreateCourse } from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/types";
import { coursePath } from "@/lib/course";
import { cn } from "@/lib/utils";

type Catalog = Schemas["AssessmentCatalogResponse"];
type QuestionTypeOut = Schemas["QuestionTypeOut"];
type SubjectPresetOut = Schemas["SubjectPresetOut"];

function TypeCheckbox({
  type,
  example,
  checked,
  recommended,
  onChange,
}: {
  type: QuestionTypeOut;
  example: string;
  checked: boolean;
  recommended: boolean;
  onChange: (next: boolean) => void;
}) {
  const inputId = `type-${type.id}`;
  return (
    <label
      htmlFor={inputId}
      className={cn(
        "flex items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors",
        type.offerable ? "cursor-pointer hover:bg-muted/40" : "cursor-not-allowed opacity-60",
        checked && "border-primary/50 bg-[var(--accent-wash)]/40",
      )}
    >
      <input
        id={inputId}
        type="checkbox"
        className="mt-0.5 size-4 accent-[var(--accent-solid)]"
        checked={checked}
        disabled={!type.offerable}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-sm">{type.label}</span>
          {!type.offerable ? (
            <Badge variant="outline" className="font-normal text-[11px]">
              Coming soon
            </Badge>
          ) : recommended ? (
            <Badge variant="secondary" className="font-normal text-[11px]">
              Recommended
            </Badge>
          ) : null}
          {type.ai_graded ? (
            <span
              className="rounded px-1.5 py-0.5 font-medium text-[11px]"
              style={{ background: "var(--warn-wash)", color: "var(--warn-solid)" }}
            >
              AI-graded · practice only, never counts toward mastery
            </span>
          ) : null}
        </span>
        <span className="mt-0.5 block text-muted-foreground text-xs">
          Students answer with {type.widget}
        </span>
        {example ? (
          <span className="mt-1 block text-muted-foreground text-xs italic">{example}</span>
        ) : null}
      </span>
    </label>
  );
}

function TypeGroups({
  catalog,
  subject,
  chosen,
  setType,
}: {
  catalog: Catalog;
  subject: SubjectPresetOut;
  chosen: ReadonlySet<string>;
  setType: (id: string, on: boolean) => void;
}) {
  const [showMore, setShowMore] = useState(false);
  const recommended = new Set([...subject.default_types, ...subject.coming_soon_types]);
  const primary = catalog.groups.filter((group) => subject.primary_groups.includes(group.id));
  const others = catalog.groups.filter((group) => !subject.primary_groups.includes(group.id));

  const renderGroup = (group: Catalog["groups"][number]) => {
    const types = catalog.question_types.filter((type) => type.group === group.id);
    if (types.length === 0) return null;
    return (
      <section key={group.id} className="space-y-2">
        <div className="flex items-baseline gap-2">
          <h3 className="font-medium text-sm">{group.title}</h3>
          <span className="text-muted-foreground text-xs">{group.hint}</span>
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          {types.map((type) => (
            <TypeCheckbox
              key={type.id}
              type={type}
              example={subject.examples[type.id] ?? ""}
              checked={chosen.has(type.id)}
              recommended={recommended.has(type.id)}
              onChange={(next) => setType(type.id, next)}
            />
          ))}
        </div>
      </section>
    );
  };

  return (
    <div className="space-y-5">
      {primary.map(renderGroup)}
      {others.length > 0 ? (
        <div className="rounded-lg border">
          <button
            type="button"
            aria-expanded={showMore}
            onClick={() => setShowMore((open) => !open)}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm"
          >
            More question types
            <span className="text-muted-foreground text-xs">
              {others.map((group) => group.title).join(" · ")}
            </span>
            <ChevronDownIcon
              className={cn("ml-auto size-4 transition-transform", showMore && "rotate-180")}
            />
          </button>
          {showMore ? (
            <div className="space-y-5 border-t px-3 py-3">{others.map(renderGroup)}</div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/** How the chosen types will be graded, in plain words. Mirrors the server's derivation. */
function gradingNote(catalog: Catalog, chosen: ReadonlySet<string>) {
  const built = new Set(catalog.capabilities.filter((cap) => cap.built).map((cap) => cap.id));
  const needed = new Set<string>();
  for (const type of catalog.question_types) {
    if (!chosen.has(type.id)) continue;
    const grader = type.graded_by.find((id) => built.has(id));
    if (grader) needed.add(grader);
    for (const need of type.also_needs) needed.add(need);
  }
  return catalog.capabilities.filter((cap) => needed.has(cap.id));
}

export function NewCourseDialog({ onOpenChange }: { onOpenChange: (open: boolean) => void }) {
  const catalog = useAssessmentCatalog();
  const createCourse = useCreateCourse();
  const [step, setStep] = useState<0 | 1>(0);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [subjectId, setSubjectId] = useState<string | null>(null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [showHow, setShowHow] = useState(false);

  const subject = catalog.data?.subjects.find((entry) => entry.id === subjectId) ?? null;
  const labels = useMemo(
    () => new Map((catalog.data?.question_types ?? []).map((type) => [type.id, type.label])),
    [catalog.data],
  );
  const grading = catalog.data ? gradingNote(catalog.data, chosen) : [];

  function pickSubject(next: SubjectPresetOut) {
    setSubjectId(next.id);
    setChosen(new Set(next.default_types));
  }

  function setType(id: string, on: boolean) {
    setChosen((previous) => {
      const next = new Set(previous);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  async function create() {
    if (!subject || !name.trim() || chosen.size === 0) return;
    try {
      const course = await createCourse.mutateAsync({
        name: name.trim(),
        description: description.trim() || null,
        subject: subject.id,
        question_types: [...chosen],
      });
      // A full load into the new course: query keys do not name a course (see courses-screen).
      window.location.assign(coursePath(course.id, "/dashboard"));
    } catch {
      // Rendered below with the backend's own wording.
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !createCourse.isPending && onOpenChange(next)}>
      <DialogContent className="flex max-h-[90vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-4xl">
        <DialogHeader className="gap-3 border-b px-6 pt-5 pb-4">
          <div>
            <DialogTitle className="text-lg">New course</DialogTitle>
            <DialogDescription>
              Choose the subject, then the kinds of questions students will answer.
            </DialogDescription>
          </div>
          <ol className="flex items-center gap-3 text-sm" aria-label="Steps">
            {["Subject", "Question types"].map((title, index) => (
              <li
                key={title}
                aria-current={step === index ? "step" : undefined}
                className="flex items-center gap-2"
              >
                <span
                  className={cn(
                    "flex size-6 items-center justify-center rounded-full border text-xs",
                    step === index && "border-primary bg-primary text-primary-foreground",
                    step > index && "border-primary text-primary",
                  )}
                >
                  {step > index ? <CheckIcon className="size-3.5" /> : index + 1}
                </span>
                <span className={step === index ? "font-medium" : "text-muted-foreground"}>
                  {title}
                </span>
                {index === 0 ? <span className="mx-2 h-px w-16 bg-border" aria-hidden /> : null}
              </li>
            ))}
          </ol>
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          {catalog.isError ? <QueryError error={catalog.error} /> : null}
          {catalog.isPending ? <Skeleton className="h-96" /> : null}

          {catalog.data ? (
            step === 0 ? (
              <div className="space-y-5">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="new-course-name">Course name</Label>
                    <Input
                      id="new-course-name"
                      value={name}
                      maxLength={200}
                      placeholder="e.g. CS 135 · Intro to Programming"
                      onChange={(event) => setName(event.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="new-course-description">
                      Description <span className="text-muted-foreground">(optional)</span>
                    </Label>
                    <Textarea
                      id="new-course-description"
                      value={description}
                      maxLength={2000}
                      className="h-[2.4rem] min-h-0"
                      placeholder="Term, section, who it is for…"
                      onChange={(event) => setDescription(event.target.value)}
                    />
                  </div>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  {catalog.data.subjects.map((entry) => {
                    const selected = entry.id === subjectId;
                    const given = entry.default_types.map((id) => labels.get(id) ?? id);
                    const soon = entry.coming_soon_types.map((id) => labels.get(id) ?? id);
                    return (
                      <button
                        key={entry.id}
                        type="button"
                        aria-pressed={selected}
                        onClick={() => pickSubject(entry)}
                        className={cn(
                          "rounded-xl border p-4 text-left transition-colors hover:bg-muted/40",
                          selected && "border-primary ring-1 ring-primary",
                        )}
                      >
                        <div className="font-medium text-sm">{entry.label}</div>
                        <div className="mt-1 text-muted-foreground text-xs">
                          {given.join(" · ")}
                        </div>
                        {soon.length > 0 ? (
                          <div className="mt-1 text-muted-foreground text-xs">
                            Coming soon: {soon.join(" · ")}
                          </div>
                        ) : null}
                      </button>
                    );
                  })}
                </div>
                <p className="text-muted-foreground text-xs">
                  The subject decides which question types are ticked to start with.
                </p>
              </div>
            ) : subject ? (
              <div className="space-y-5">
                <p className="text-muted-foreground text-sm">
                  Ticked for {subject.label}. The AI only writes questions of the ticked types.
                </p>
                <TypeGroups
                  catalog={catalog.data}
                  subject={subject}
                  chosen={chosen}
                  setType={setType}
                />
                <div className="rounded-lg border bg-muted/30">
                  <button
                    type="button"
                    aria-expanded={showHow}
                    onClick={() => setShowHow((open) => !open)}
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-muted-foreground text-xs"
                  >
                    <InfoIcon className="size-3.5" />
                    How these are graded
                    <ChevronDownIcon
                      className={cn(
                        "ml-auto size-3.5 transition-transform",
                        showHow && "rotate-180",
                      )}
                    />
                  </button>
                  {showHow ? (
                    <ul className="space-y-1 border-t px-3 py-2 text-xs">
                      {grading.map((cap) => (
                        <li key={cap.id}>
                          <span className="font-medium">{cap.label}:</span>{" "}
                          <span className="text-muted-foreground">{cap.description}</span>
                        </li>
                      ))}
                      {grading.length === 0 ? (
                        <li className="text-muted-foreground">
                          Tick a question type to see how it is graded.
                        </li>
                      ) : null}
                    </ul>
                  ) : null}
                </div>
              </div>
            ) : null
          ) : null}
        </div>

        {createCourse.error ? (
          <div className="border-t px-6 py-3">
            <QueryError error={createCourse.error} />
          </div>
        ) : null}
        <div className="flex flex-wrap items-center gap-3 border-t px-6 py-4">
          {step === 0 ? (
            <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
          ) : (
            <Button variant="outline" size="sm" onClick={() => setStep(0)}>
              <ArrowLeftIcon />
              Back
            </Button>
          )}
          <span className="text-muted-foreground text-sm">
            {step === 0
              ? !name.trim()
                ? "Name the course and pick a subject."
                : subject
                  ? `${chosen.size} question types ticked`
                  : "Pick a subject to continue."
              : `${chosen.size} question types`}
          </span>
          <div className="ml-auto flex items-center gap-3">
            {step === 0 ? (
              <Button size="sm" disabled={!subject || !name.trim()} onClick={() => setStep(1)}>
                Next
                <ArrowRightIcon />
              </Button>
            ) : (
              <Button
                size="sm"
                disabled={chosen.size === 0 || createCourse.isPending}
                onClick={() => void create()}
              >
                {createCourse.isPending ? "Creating…" : "Create course"}
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
