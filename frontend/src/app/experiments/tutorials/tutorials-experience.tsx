"use client";

/**
 * The student's view of a tutorial: a course outline on the left, the tutorial in a reading column,
 * and a page outline on the right. Mock data only (see `mock-tutorials.ts`); nothing here calls the
 * API. Reading progress is kept in this browser.
 *
 * TODO(real): the seeded "already done" tutorials, the recommendation banner, and the reviewed date
 * are mock. Real ones come from the student's measured weak subtopics and the professor's approval.
 */

import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  CircleCheck,
  FlaskConical,
  Home,
  Target,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { BlockView, blockKey } from "./components/tutorial-blocks";
import {
  COURSE,
  countChecks,
  TUTORIAL_TOPICS,
  TUTORIALS,
  type Tutorial,
  tutorialById,
} from "./mock-tutorials";

const STORAGE_KEY = "adaptive-trainer:tutorial-progress:v1";
/** TODO(real): mock. A brand-new student would start with none done. */
const SEEDED_DONE = ["variables-and-types", "if-elif-else"];
const DEFAULT_TUTORIAL = "for-loops";

function loadDone(): string[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === null) return SEEDED_DONE;
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === "string") : SEEDED_DONE;
  } catch {
    return SEEDED_DONE;
  }
}

function saveDone(done: string[]) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(done));
  } catch {
    // Progress just is not kept; reading still works.
  }
}

// ---- course outline ---------------------------------------------------------------------------------

function CourseOutline({
  currentId,
  done,
  onOpen,
}: {
  currentId: string;
  done: ReadonlySet<string>;
  onOpen: (id: string) => void;
}) {
  const finished = TUTORIALS.filter((tutorial) => done.has(tutorial.id)).length;
  return (
    <nav aria-label="Course outline" className="text-sm">
      <p className="font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest">Course</p>
      <p className="mt-1 font-heading font-semibold text-base text-foreground">{COURSE.title}</p>
      <div className="mt-3 flex items-center gap-3">
        <Progress
          value={(finished / TUTORIALS.length) * 100}
          aria-label="Tutorials finished"
          className="h-1.5 flex-1"
        />
        <span className="shrink-0 font-mono text-muted-foreground text-xs">
          {finished}/{TUTORIALS.length}
        </span>
      </div>

      <div className="mt-5 grid gap-5">
        {TUTORIAL_TOPICS.map((topic) => (
          <section key={topic}>
            <h2 className="mb-1.5 px-2 font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest">
              {topic}
            </h2>
            <ul className="grid gap-0.5">
              {TUTORIALS.filter((tutorial) => tutorial.topic === topic).map((tutorial) => {
                const current = tutorial.id === currentId;
                const complete = done.has(tutorial.id);
                return (
                  <li key={tutorial.id}>
                    <button
                      type="button"
                      onClick={() => onOpen(tutorial.id)}
                      aria-current={current ? "page" : undefined}
                      className={cn(
                        "flex w-full items-start gap-2.5 rounded-md px-2 py-2 text-left transition-colors",
                        "focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
                        current ? "bg-accent text-foreground" : "text-foreground/80 hover:bg-muted",
                      )}
                    >
                      <span className="mt-0.5 shrink-0" aria-hidden="true">
                        {complete ? (
                          <CircleCheck className="size-4 text-primary" />
                        ) : (
                          <span
                            className={cn(
                              "block size-4 rounded-full border",
                              current ? "border-primary" : "border-border",
                            )}
                          />
                        )}
                      </span>
                      <span className="min-w-0">
                        <span className={cn("block leading-5", current && "font-medium")}>
                          {tutorial.title}
                        </span>
                        <span className="block text-muted-foreground text-xs">
                          {tutorial.minutes} min
                          {complete ? " · done" : ""}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
    </nav>
  );
}

// ---- the page outline (scroll spy) ---------------------------------------------------------------------

function useActiveSection(ids: string[], resetKey: string) {
  const [active, setActive] = useState(ids[0] ?? "");
  // biome-ignore lint/correctness/useExhaustiveDependencies: `resetKey` re-arms the observer for a new tutorial; `ids` is derived from it.
  useEffect(() => {
    setActive(ids[0] ?? "");
    if (typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((entry) => entry.isIntersecting);
        if (visible.length > 0) {
          const top = visible.reduce((a, b) => (a.boundingClientRect.top < b.boundingClientRect.top ? a : b));
          setActive(top.target.id);
        }
      },
      { rootMargin: "-10% 0px -70% 0px" },
    );
    for (const id of ids) {
      const element = document.getElementById(id);
      if (element) observer.observe(element);
    }
    return () => observer.disconnect();
  }, [resetKey]);
  return active;
}

function PageOutline({ tutorial, active }: { tutorial: Tutorial; active: string }) {
  const items = [
    ...tutorial.sections.map((section) => ({ id: section.id, title: section.title })),
    { id: "sources", title: "Sources" },
  ];
  return (
    <nav aria-label="On this page" className="text-sm">
      <p className="font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest">On this page</p>
      <ul className="mt-3 grid gap-0.5 border-border border-l">
        {items.map((item) => (
          <li key={item.id}>
            <a
              href={`#${item.id}`}
              aria-current={active === item.id ? "location" : undefined}
              className={cn(
                "-ml-px block border-l py-1 pl-3 leading-5 transition-colors",
                active === item.id
                  ? "border-primary font-medium text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {item.title}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

// ---- the tutorial ---------------------------------------------------------------------------------------

function TutorialArticle({
  tutorial,
  complete,
  onToggleDone,
  onOpen,
  headingRef,
}: {
  tutorial: Tutorial;
  complete: boolean;
  onToggleDone: () => void;
  onOpen: (id: string) => void;
  headingRef: React.RefObject<HTMLHeadingElement | null>;
}) {
  const [highlighted, setHighlighted] = useState<number | null>(null);
  /** Each check's latest answer. Kept here, so it starts empty whenever a tutorial is opened. */
  const [results, setResults] = useState<Record<string, boolean>>({});
  const index = TUTORIALS.findIndex((candidate) => candidate.id === tutorial.id);
  const previous = TUTORIALS[index - 1];
  const next = TUTORIALS[index + 1];
  const checks = countChecks(tutorial);
  const answered = Object.keys(results).length;
  const right = Object.values(results).filter(Boolean).length;

  const jumpToSource = (n: number) => {
    setHighlighted(n);
    document.getElementById("sources")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <article aria-labelledby="tutorial-title" className="min-w-0">
      <header>
        <p className="font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest">
          {tutorial.topic}
        </p>
        <h1
          id="tutorial-title"
          ref={headingRef}
          tabIndex={-1}
          className="mt-1.5 font-heading font-semibold text-3xl text-foreground leading-tight tracking-tight outline-none sm:text-[2.1rem]"
        >
          {tutorial.title}
        </h1>
        <p className="mt-3 max-w-[60ch] text-lg text-muted-foreground leading-8">{tutorial.summary}</p>
        <p className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-muted-foreground text-sm">
          <Badge variant="outline">{tutorial.level}</Badge>
          <span>{tutorial.minutes} min read</span>
          <span>
            {checks} quick {checks === 1 ? "check" : "checks"}
          </span>
          <span>Reviewed by your instructor, {tutorial.reviewedOn}</span>
        </p>
      </header>

      {tutorial.recommendedBecause ? (
        <aside
          className="mt-6 flex items-start gap-3 border-primary border-l-2 bg-accent/60 py-3 pr-4 pl-4"
          aria-label="Why this tutorial"
        >
          <Target className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
          <p className="text-sm leading-6">
            <strong className="font-semibold text-foreground">Recommended for you.</strong>{" "}
            <span className="text-muted-foreground">
              You missed {tutorial.recommendedBecause.misses} of your last{" "}
              {tutorial.recommendedBecause.attempts} <em>{tutorial.recommendedBecause.subtopic}</em>{" "}
              questions. Read this, then try more.
            </span>
          </p>
        </aside>
      ) : null}

      <div className="mt-8 max-w-[68ch]">
        {tutorial.sections.map((section) => (
          <section key={section.id} id={section.id} className="scroll-mt-6 pb-2" aria-labelledby={`${section.id}-h`}>
            <h2
              id={`${section.id}-h`}
              className="mt-10 mb-1 font-heading font-semibold text-foreground text-xl tracking-tight first:mt-0"
            >
              {section.title}
            </h2>
            {section.blocks.map((block) => (
              <BlockView
                key={blockKey(block)}
                block={block}
                onChecked={(checkId, correct) => setResults((current) => ({ ...current, [checkId]: correct }))}
                onCite={jumpToSource}
              />
            ))}
          </section>
        ))}

        <section
          aria-labelledby="finish-h"
          className="mt-12 flex flex-wrap items-center justify-between gap-4 border-border border-y py-5"
        >
          <div>
            <h2 id="finish-h" className="font-heading font-semibold text-foreground">
              {complete ? "You have finished this tutorial" : "Finished reading?"}
            </h2>
            <p className="mt-0.5 text-muted-foreground text-sm">
              {checks > 0
                ? `${right} of ${checks} ${checks === 1 ? "check" : "checks"} right${
                    answered < checks ? ` · ${checks - answered} not tried` : ""
                  }.`
                : "No checks in this one."}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant={complete ? "outline" : "default"} onClick={onToggleDone}>
              <CircleCheck aria-hidden="true" />
              {complete ? "Marked as done" : "Mark as done"}
            </Button>
            <Button asChild variant="outline">
              <a href="/experiments/student">
                <FlaskConical aria-hidden="true" />
                Practice {tutorial.subtopics[0]}
              </a>
            </Button>
          </div>
        </section>

        <section id="sources" aria-labelledby="sources-h" className="scroll-mt-6 pt-8">
          <h2 id="sources-h" className="font-heading font-semibold text-foreground text-xl tracking-tight">
            Sources
          </h2>
          <p className="mt-1 text-muted-foreground text-sm leading-6">
            This tutorial was written from the course books below, and every numbered note in the text
            points at one of them.
          </p>
          <ol className="mt-4 grid gap-2">
            {tutorial.sources.map((source, sourceIndex) => {
              const n = sourceIndex + 1;
              return (
                <li
                  key={`${source.book}:${source.pages}`}
                  className={cn(
                    "flex gap-3 rounded-md border px-3 py-2.5 transition-colors",
                    highlighted === n ? "border-primary bg-accent" : "border-border bg-card",
                  )}
                >
                  <span className="mt-0.5 font-mono text-primary text-xs">[{n}]</span>
                  <span className="min-w-0 text-sm leading-6">
                    <span className="flex items-center gap-1.5 font-medium text-foreground">
                      <BookOpen className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
                      {source.book}
                    </span>
                    <span className="block text-muted-foreground">
                      {source.chapter} · {source.pages}
                    </span>
                  </span>
                </li>
              );
            })}
          </ol>
        </section>

        <nav aria-label="Tutorial navigation" className="mt-10 grid gap-3 sm:grid-cols-2">
          {previous ? (
            <button
              type="button"
              onClick={() => onOpen(previous.id)}
              className="group flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-3 text-left transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              <ArrowLeft className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <span className="min-w-0">
                <span className="block font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest">
                  Previous
                </span>
                <span className="block truncate font-medium text-foreground text-sm">{previous.title}</span>
              </span>
            </button>
          ) : (
            <span />
          )}
          {next ? (
            <button
              type="button"
              onClick={() => onOpen(next.id)}
              className="group flex items-center justify-between gap-3 rounded-lg border border-border bg-card px-4 py-3 text-left transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50 sm:col-start-2"
            >
              <span className="min-w-0">
                <span className="block font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest">
                  Next
                </span>
                <span className="block truncate font-medium text-foreground text-sm">{next.title}</span>
              </span>
              <ArrowRight className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            </button>
          ) : null}
        </nav>
      </div>
    </article>
  );
}

// ---- the page --------------------------------------------------------------------------------------------

export function TutorialsExperience() {
  const [currentId, setCurrentId] = useState(DEFAULT_TUTORIAL);
  const [done, setDone] = useState<string[]>(SEEDED_DONE);
  const [outlineOpen, setOutlineOpen] = useState(false);
  const headingRef = useRef<HTMLHeadingElement | null>(null);
  const opened = useRef(false);

  // Read the saved progress and the tutorial named in the address after mounting, so the first
  // paint matches what the server sent.
  useEffect(() => {
    setDone(loadDone());
    const fromAddress = window.location.hash.replace(/^#/, "");
    if (tutorialById(fromAddress)) setCurrentId(fromAddress);
  }, []);

  const tutorial = useMemo(() => tutorialById(currentId) ?? TUTORIALS[0], [currentId]);
  const doneSet = useMemo(() => new Set(done), [done]);
  const sectionIds = useMemo(() => [...tutorial.sections.map((section) => section.id), "sources"], [tutorial]);
  const active = useActiveSection(sectionIds, tutorial.id);

  const open = useCallback((id: string) => {
    setCurrentId(id);
    setOutlineOpen(false);
    window.history.replaceState(null, "", `#${id}`);
    opened.current = true;
  }, []);

  // Moving to another tutorial starts at its top with focus on its title, like a page change.
  // biome-ignore lint/correctness/useExhaustiveDependencies: `currentId` is the trigger; the body reads only refs.
  useEffect(() => {
    if (!opened.current) return;
    window.scrollTo({ top: 0 });
    headingRef.current?.focus({ preventScroll: true });
  }, [currentId]);

  const toggleDone = () => {
    setDone((current) => {
      const next = current.includes(tutorial.id)
        ? current.filter((id) => id !== tutorial.id)
        : [...current, tutorial.id];
      saveDone(next);
      return next;
    });
  };

  const finished = TUTORIALS.filter((candidate) => doneSet.has(candidate.id)).length;

  return (
    <div className="min-h-screen bg-background text-foreground">
      <a
        href="#tutorial-title"
        className="sr-only rounded-md bg-primary px-3 py-2 font-medium text-primary-foreground text-sm focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50"
      >
        Skip to the tutorial
      </a>

      <header className="border-border border-b bg-card/60">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-2.5">
            <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <BookOpen className="size-4" aria-hidden="true" />
            </span>
            <span>
              <span className="block font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest">
                Design prototype
              </span>
              <span className="block font-heading font-semibold text-foreground text-sm">Tutorials</span>
            </span>
          </div>
          <a
            href="/dashboard"
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-muted-foreground text-sm hover:text-foreground"
          >
            <Home className="size-3.5" aria-hidden="true" />
            Console
          </a>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-4 py-3 sm:px-6">
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-amber-800 text-sm dark:text-amber-200">
          <strong className="font-medium">Prototype.</strong> The tutorials, code outputs, book pages and the
          recommendation are mock data written by hand. Nothing here calls a server or a model. It exists to
          review what a student would see.
        </p>
      </div>

      <div className="mx-auto grid max-w-7xl gap-8 px-4 pt-4 pb-20 sm:px-6 lg:grid-cols-[15rem_minmax(0,1fr)] xl:grid-cols-[15rem_minmax(0,1fr)_12rem]">
        {/* The outline is a sidebar from `lg`; below that it folds into one line above the article. */}
        <aside className="lg:sticky lg:top-6 lg:max-h-[calc(100dvh-3rem)] lg:self-start lg:overflow-y-auto">
          <Collapsible open={outlineOpen} onOpenChange={setOutlineOpen} className="lg:hidden">
            <CollapsibleTrigger asChild>
              <Button type="button" variant="outline" className="w-full justify-between">
                <span>
                  {COURSE.title} · {finished}/{TUTORIALS.length} done
                </span>
                <span className="text-muted-foreground text-xs">{outlineOpen ? "Hide" : "All tutorials"}</span>
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="pt-4">
              <CourseOutline currentId={tutorial.id} done={doneSet} onOpen={open} />
            </CollapsibleContent>
          </Collapsible>
          <div className="hidden lg:block">
            <CourseOutline currentId={tutorial.id} done={doneSet} onOpen={open} />
          </div>
        </aside>

        <main id="tutorial-main" className="min-w-0">
          <TutorialArticle
            key={tutorial.id}
            tutorial={tutorial}
            complete={doneSet.has(tutorial.id)}
            onToggleDone={toggleDone}
            onOpen={open}
            headingRef={headingRef}
          />
        </main>

        <aside className="hidden xl:sticky xl:top-6 xl:block xl:self-start">
          <PageOutline tutorial={tutorial} active={active} />
        </aside>
      </div>
    </div>
  );
}
