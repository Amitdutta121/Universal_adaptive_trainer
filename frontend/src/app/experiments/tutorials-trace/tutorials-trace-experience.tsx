"use client";

/**
 * Variant B of the short tutorial: no reading, a snippet you step through. Three short traces
 * (loop a list, a running total, the off-by-one) and a predict-then-reveal at the end. Mock data
 * only (`mock-data.ts`); nothing here calls the API.
 *
 * TODO(real): the topic, the "missed 2 of 3" line and the traces come from the student's measured
 * weak subtopic and the approved tutorial, not from constants.
 */

import { Home, ListVideo } from "lucide-react";
import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TracePlayer } from "./components/trace-player";
import { TryIt } from "./components/try-it";
import { useTraceRunner } from "./components/use-trace-runner";
import { TRACES, type Trace } from "./mock-data";

function TraceSection({ trace }: { trace: Trace }) {
  const runner = useTraceRunner(trace);
  return <TracePlayer trace={trace} runner={runner} />;
}

export function TutorialsTraceExperience() {
  const [traceId, setTraceId] = useState<string>(TRACES[0]?.id ?? "");

  return (
    <div className="min-h-screen bg-background text-foreground">
      <a
        href="#tracer"
        className="sr-only rounded-md bg-primary px-3 py-2 font-medium text-primary-foreground text-sm focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50"
      >
        Skip to the tracer
      </a>

      <header className="border-border border-b bg-card/60">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-2.5">
            <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <ListVideo className="size-4" aria-hidden="true" />
            </span>
            <span>
              <span className="block font-mono text-[0.68rem] text-muted-foreground uppercase tracking-widest">
                Design prototype
              </span>
              <span className="block font-heading font-semibold text-foreground text-sm">
                Tutorial B: code tracer
              </span>
            </span>
          </div>
          <a
            href="/dashboard"
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-muted-foreground text-sm hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <Home className="size-3.5" aria-hidden="true" />
            Console
          </a>
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-4 py-3 sm:px-6">
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-amber-800 text-sm dark:text-amber-200">
          <strong className="font-medium">Prototype.</strong> Mock data. The traces were recorded by
          running the snippets once; nothing here calls a server or a model.
        </p>
      </div>

      <main id="tracer" className="mx-auto grid max-w-5xl gap-6 px-4 pt-4 pb-20 sm:px-6">
        <div>
          <h1 className="font-heading font-semibold text-2xl text-foreground">
            for loops and range()
          </h1>
          <p className="mt-1 text-muted-foreground text-sm">
            Missed 2 of 3 loop questions. Watch three short runs.
          </p>
        </div>

        <Tabs value={traceId} onValueChange={setTraceId} className="gap-4">
          <TabsList aria-label="Pick a trace" className="w-full sm:w-fit">
            {TRACES.map((trace) => (
              <TabsTrigger key={trace.id} value={trace.id} className="px-3">
                {trace.label}
              </TabsTrigger>
            ))}
          </TabsList>
          <h2 className="sr-only">Code tracer</h2>
          {TRACES.map((trace) => (
            <TabsContent key={trace.id} value={trace.id}>
              <TraceSection trace={trace} />
            </TabsContent>
          ))}
        </Tabs>

        <TryIt />
      </main>
    </div>
  );
}
