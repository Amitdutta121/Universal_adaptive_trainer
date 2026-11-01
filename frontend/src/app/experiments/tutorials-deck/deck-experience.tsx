"use client";

/**
 * Variant F, the trace-lesson deck: a topic picker (conditionals, while loops, functions, lists,
 * recursion) over one short deck per topic. Cards are one idea each; the third is a step-through
 * simulator of a real recorded snippet; the fifth is a faded completion.
 *
 * Prediction and stepping are optional by design: a 2026 study of AI-generated traces found they
 * helped low- and high-engagement students and slightly hurt mid-engagement ones, so nothing here
 * is forced ("Just show me", "I know this, skip to the check").
 *
 * TODO(real): which topic opens first, and whether the scaffold is on, would come from the
 * student's measured mastery (see DESIGN_NOTES.md). Here every deck is open and prediction starts on.
 */

import { Home, ListVideo } from "lucide-react";
import { useState } from "react";
import { Deck } from "./components/deck";
import { TopicPicker } from "./components/topic-picker";
import { useDoneTopics } from "./components/use-done-topics";
import { TOPICS } from "./mock-data";

export function DeckExperience() {
  const [topicId, setTopicId] = useState(TOPICS[0].id);
  const [positions, setPositions] = useState<Record<string, number>>({});
  const [predictOn, setPredictOn] = useState(true);
  const { done, markDone } = useDoneTopics();

  const topicIndex = Math.max(
    0,
    TOPICS.findIndex((topic) => topic.id === topicId),
  );
  const topic = TOPICS[topicIndex];
  const nextTopic = TOPICS[topicIndex + 1];

  return (
    <div className="flex h-dvh flex-col bg-background text-foreground">
      <header className="shrink-0 border-border border-b bg-card/60">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-4 py-2 sm:px-6">
          <div className="flex items-center gap-2.5">
            <span className="flex size-7 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <ListVideo className="size-3.5" aria-hidden="true" />
            </span>
            <span>
              <span className="block font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest">
                Design prototype
              </span>
              <span className="block font-heading font-semibold text-foreground text-sm">
                Tutorial F: trace-lesson deck
              </span>
            </span>
          </div>
          <a
            href="/dashboard"
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-muted-foreground text-sm outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <Home className="size-3.5" aria-hidden="true" />
            Console
          </a>
        </div>
      </header>

      <div className="mx-auto w-full max-w-5xl shrink-0 px-4 pt-2 sm:px-6">
        {/* TODO(real): drop this note once decks come from approved book content. */}
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-amber-800 text-xs sm:text-sm dark:text-amber-200">
          <strong className="font-medium">Prototype.</strong> Mock data. Traces were recorded from real
          Python; nothing here calls a server or a model.
        </p>
      </div>

      <main className="mx-auto flex min-h-0 w-full max-w-5xl flex-1 flex-col gap-2 px-4 pt-2 pb-3 sm:gap-3 sm:px-6 sm:pt-3 sm:pb-5">
        <h1 className="sr-only">Tutorial: {topic.label}</h1>
        <TopicPicker topics={TOPICS} activeId={topicId} done={done} onSelect={setTopicId} />
        <Deck
          key={topic.id}
          topic={topic}
          index={positions[topic.id] ?? 0}
          onIndex={(next) => setPositions((current) => ({ ...current, [topic.id]: next }))}
          done={done.includes(topic.id)}
          onSolved={() => markDone(topic.id)}
          predictOn={predictOn}
          setPredictOn={setPredictOn}
          nextTopic={nextTopic}
          onNextTopic={() => nextTopic && setTopicId(nextTopic.id)}
        />
      </main>
    </div>
  );
}
