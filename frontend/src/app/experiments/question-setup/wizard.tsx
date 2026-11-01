"use client";

/**
 * The question setup wizard for one course, shown after the book is imported and the taxonomy
 * approved:
 *   1. Read the book   — mining runs, findings shown, optional wishes.
 *   2. Question styles — approve or skip suggested templates, two examples each.
 *   3. Your styles     — the approved list, and rules taken from skips.
 *   4. Plan            — the subtopic x difficulty blueprint, then generate.
 * State lives here only; nothing is saved and no LLM is called.
 */

import { ArrowLeftIcon, ArrowRightIcon, CheckIcon } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { StepMining } from "./components/step-mining";
import { StepPlan } from "./components/step-plan";
import { StepStyles } from "./components/step-styles";
import { StepSummary } from "./components/step-summary";
import { DIFFICULTIES, type Difficulty, type Domain } from "./mock-types";
import { approvedByDifficulty, approvedIds, buildPlan, type Decision, deckFor } from "./plan";

const STEPS = [
  { title: "Read the book", description: "Find the practice material in your book and learn its level." },
  { title: "Question styles", description: "Choose the kinds of questions you want. Each card shows two examples." },
  { title: "Your styles", description: "The styles the generator will use, and what it learned from your skips." },
  { title: "Plan", description: "What will be generated so every subtopic has questions at every difficulty." },
] as const;

export function Wizard({ domain }: { domain: Domain }) {
  const [step, setStep] = useState(0);
  const [reached, setReached] = useState(0);
  const [mined, setMined] = useState(false);
  const [wishes, setWishes] = useState<Set<string>>(new Set());
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [cursor, setCursor] = useState(0);
  const [addedReserve, setAddedReserve] = useState<string[]>([]);
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [generated, setGenerated] = useState(false);

  const deck = useMemo(() => {
    const reserve = domain.reserve.filter((template) => addedReserve.includes(template.id));
    return [...deckFor(domain, wishes), ...reserve];
  }, [domain, wishes, addedReserve]);

  const reserveLeft = useMemo(() => {
    const left: Record<Difficulty, number> = { easy: 0, medium: 0, hard: 0 };
    for (const template of domain.reserve) {
      if (!addedReserve.includes(template.id)) left[template.difficulty] += 1;
    }
    return left;
  }, [domain, addedReserve]);

  const approved = useMemo(() => approvedIds(decisions), [decisions]);
  const perDifficulty = approvedByDifficulty(deck, decisions);
  const reviewedAll = deck.every((template) => decisions[template.id]);
  const plan = useMemo(() => buildPlan(domain, deck, approved, excluded), [domain, deck, approved, excluded]);

  const onMined = useCallback(() => setMined(true), []);

  function go(next: number) {
    setStep(next);
    setReached((value) => Math.max(value, next));
    window.scrollTo({ top: 0 });
  }

  function decide(templateId: string, decision: Decision) {
    setDecisions((prev) => ({ ...prev, [templateId]: decision }));
    setGenerated(false);
    if (step === 1) {
      // Move to the next card nobody has decided yet, or past the end.
      const index = deck.findIndex((template) => template.id === templateId);
      const open = (template: (typeof deck)[number], i: number) => i !== index && !decisions[template.id];
      const after = deck.findIndex((template, i) => i > index && open(template, i));
      const anywhere = deck.findIndex(open);
      setCursor(after !== -1 ? after : anywhere !== -1 ? anywhere : deck.length);
    }
  }

  function addReserve(difficulty: Difficulty) {
    const extra = domain.reserve
      .filter((template) => template.difficulty === difficulty && !addedReserve.includes(template.id))
      .map((template) => template.id);
    setAddedReserve((prev) => [...prev, ...extra]);
    setCursor(deck.length);
  }

  function toggleWish(wish: string) {
    setWishes((prev) => {
      const next = new Set(prev);
      if (next.has(wish)) next.delete(wish);
      else next.add(wish);
      return next;
    });
  }

  function toggleExcluded(subtopicId: string) {
    setExcluded((prev) => {
      const next = new Set(prev);
      if (next.has(subtopicId)) next.delete(subtopicId);
      else next.add(subtopicId);
      return next;
    });
    setGenerated(false);
  }

  const canAdvance = step === 0 ? mined : step === 1 ? reviewedAll && approved.size > 0 : step === 2 ? approved.size > 0 : true;
  const current = STEPS[step] ?? STEPS[0];
  const chosenCount = deck.filter((template) => approved.has(template.id)).length;

  const footerNote =
    step === 0
      ? mined
        ? `${domain.mining.itemsFound} items from ${domain.mining.sectionsRouted} sections`
        : "Reading the book…"
      : step === 1
        ? reviewedAll
          ? `${chosenCount} of ${deck.length} styles chosen`
          : `${deck.filter((t) => decisions[t.id]).length} of ${deck.length} reviewed`
        : step === 2
          ? DIFFICULTIES.map((d) => `${perDifficulty[d]} ${d}`).join(" · ")
          : `${plan.totalAdd} questions · ${plan.drafts} drafts`;

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-5">
      <div className="flex flex-col gap-1">
        <p className="text-muted-foreground text-xs">
          {domain.course} · Book imported · Taxonomy approved ({domain.taxonomy.topics} topics,{" "}
          {domain.taxonomy.subtopics} subtopics)
        </p>
        <h1 className="font-semibold text-lg">Set up questions</h1>
        <p className="text-muted-foreground text-sm">
          A few minutes here decides what kind of questions the AI writes for this course. You only approve or skip.
        </p>
      </div>

      <nav aria-label="Setup steps">
        <ol className="flex flex-wrap items-center gap-2">
          {STEPS.map((entry, index) => {
            const done = index < reached || (index === reached && index < step);
            const active = index === step;
            return (
              <li key={entry.title} className="flex flex-1 items-center gap-2">
                <button
                  type="button"
                  onClick={() => go(index)}
                  disabled={index > reached}
                  aria-current={active ? "step" : undefined}
                  className={cn(
                    "flex items-center gap-2 whitespace-nowrap rounded-md py-1 pr-2 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed",
                    active ? "font-medium text-foreground" : "text-muted-foreground",
                  )}
                >
                  <span
                    aria-hidden
                    className={cn(
                      "flex size-6 shrink-0 items-center justify-center rounded-full border text-xs tabular-nums",
                      active && "border-[var(--accent-solid)] bg-[var(--accent-solid)] text-white",
                      done && !active && "border-[var(--accent-solid)] text-[var(--accent-text)]",
                    )}
                  >
                    {done && !active ? <CheckIcon className="size-3.5" /> : index + 1}
                  </span>
                  <span>
                    <span className="sr-only">Step {index + 1}: </span>
                    {entry.title}
                  </span>
                </button>
                {index < STEPS.length - 1 ? (
                  <span aria-hidden className={cn("hidden h-px flex-1 bg-border sm:block", done && "bg-[var(--accent-solid)]")} />
                ) : null}
              </li>
            );
          })}
        </ol>
      </nav>

      <Card>
        <CardHeader className="border-b">
          <CardTitle>
            {step + 1}. {current.title}
          </CardTitle>
          <CardDescription>{current.description}</CardDescription>
        </CardHeader>
        <CardContent>
          {step === 0 ? (
            <StepMining domain={domain} done={mined} onDone={onMined} wishes={wishes} onToggleWish={toggleWish} />
          ) : step === 1 ? (
            <StepStyles
              domain={domain}
              deck={deck}
              cursor={cursor}
              onCursor={setCursor}
              decisions={decisions}
              onDecide={decide}
              wishes={wishes}
              reserveLeft={reserveLeft}
              onAddReserve={addReserve}
            />
          ) : step === 2 ? (
            <StepSummary domain={domain} deck={deck} decisions={decisions} onDecide={decide} />
          ) : (
            <StepPlan
              domain={domain}
              deck={deck}
              plan={plan}
              excluded={excluded}
              onToggleExcluded={toggleExcluded}
              generated={generated}
            />
          )}
        </CardContent>
        <Separator />
        <div className="flex flex-wrap items-center gap-3 px-4">
          <Button variant="outline" onClick={() => go(Math.max(0, step - 1))} disabled={step === 0}>
            <ArrowLeftIcon data-icon="inline-start" />
            Back
          </Button>
          <p className="mr-auto text-muted-foreground text-sm" aria-live="polite">
            {footerNote}
          </p>
          {step < STEPS.length - 1 ? (
            <Button onClick={() => go(step + 1)} disabled={!canAdvance}>
              {step === 0 ? "Choose question styles" : step === 1 ? "Review my styles" : "See the plan"}
              <ArrowRightIcon data-icon="inline-end" />
            </Button>
          ) : (
            <Button onClick={() => setGenerated(true)} disabled={plan.totalAdd === 0}>
              Generate {plan.totalAdd} questions
            </Button>
          )}
        </div>
      </Card>
    </div>
  );
}
