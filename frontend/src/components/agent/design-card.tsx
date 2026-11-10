"use client";

/**
 * The course design `show_design` returned, as the professor reviews it (ADR-078), in three
 * cards: the curriculum (every subtopic with what it uses, and what stays outside the app), the
 * question styles (how students are checked) and the tutorial recipes (how they are taught).
 * A row can be changed (a short inline box) or removed, a topic changed, and the whole design
 * approved; each sends a follow-up through the chat, which the agent turns into a revision of
 * just that part or, for approval, its own approval card. Any other change is typed in the chat.
 */

import { Check, ChevronRight, Pencil, Send, X } from "lucide-react";
import { type FormEvent, type ReactNode, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type DesignItem = {
  name: string;
  summary: string;
  new: boolean;
  reused_from?: string | null;
  used_by: number;
};

export type DesignStyleRow = DesignItem & { question_type: string };
export type DesignRecipeRow = DesignItem & { form: string };

export type CourseDesign = {
  design_id: string;
  title: string;
  audience: string;
  topic_count: number;
  subtopic_count: number;
  /** False until styles are suggested for the current curriculum. */
  styles_ready: boolean;
  recipes_ready: boolean;
  styles: DesignStyleRow[];
  recipes: DesignRecipeRow[];
  topics: {
    name: string;
    subtopics: { name: string; description: string; styles: string[]; recipes: string[] }[];
  }[];
  out_of_scope: string[];
};

type Ask = ((question: string) => void) | null;

/** Asks inline what should change about one row or topic, then sends it. */
function ChangeBox({ subject, onSend }: { subject: string; onSend: (text: string) => void }) {
  const [text, setText] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (text.trim()) onSend(text.trim());
  };
  return (
    <form onSubmit={submit} className="mt-1.5 flex gap-1">
      <Input
        autoFocus
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder={`What should change about ${subject}?`}
        className="h-7 text-xs md:text-xs"
      />
      <Button type="submit" size="icon-sm" aria-label="Send change" disabled={!text.trim()}>
        <Send />
      </Button>
    </form>
  );
}

function ItemTable({
  kind,
  rows,
  ask,
}: {
  kind: "style" | "recipe";
  rows: (DesignItem & { label: string })[];
  ask: Ask;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  return (
    <table className="mt-2 w-full border-collapse text-xs">
      <thead>
        <tr className="border-b text-left text-muted-foreground">
          <th className="py-1 pr-2 font-normal">{kind === "style" ? "Style" : "Recipe"}</th>
          <th className="py-1 pr-2 font-normal">{kind === "style" ? "Type" : "Form"}</th>
          <th className="py-1 text-right font-normal">Subtopics</th>
          {ask ? <th className="w-14" aria-label="Actions" /> : null}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.name} className="border-b align-top last:border-0">
            <td className="py-1.5 pr-2">
              <div className="flex flex-wrap items-center gap-1 font-medium text-card-foreground">
                {row.name}
                {row.new ? <Badge variant="secondary">New</Badge> : null}
              </div>
              <p className="text-muted-foreground">{row.summary}</p>
              {row.reused_from ? (
                <p className="text-muted-foreground italic">Reused: {row.reused_from}</p>
              ) : null}
              {ask && editing === row.name ? (
                <ChangeBox
                  subject={`"${row.name}"`}
                  onSend={(text) => {
                    setEditing(null);
                    ask(`Change the ${kind} "${row.name}": ${text}`);
                  }}
                />
              ) : null}
            </td>
            <td className="py-1.5 pr-2 text-muted-foreground">{row.label}</td>
            <td className="py-1.5 text-right tabular-nums">{row.used_by}</td>
            {ask ? (
              <td className="whitespace-nowrap py-1 text-right">
                <Button
                  variant="ghost"
                  size="icon-xs"
                  aria-label={`Change ${row.name}`}
                  onClick={() => setEditing(editing === row.name ? null : row.name)}
                >
                  <Pencil />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-xs"
                  aria-label={`Remove ${row.name}`}
                  onClick={() => ask(`Remove the ${kind} "${row.name}" from the design.`)}
                >
                  <X />
                </Button>
              </td>
            ) : null}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function NotYet({ what }: { what: string }) {
  return (
    <p className="mt-2 text-muted-foreground">{what} are not suggested for this curriculum yet.</p>
  );
}

function Chips({ names, label }: { names: string[]; label: string }): ReactNode {
  if (!names.length) return null;
  return (
    <p className="text-muted-foreground">
      <span className="text-card-foreground/70">{label}:</span> {names.join(", ")}
    </p>
  );
}

/** One of the design's three cards. */
function Panel({ title, meta, children }: { title: string; meta: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-lg border bg-card p-3 text-xs">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="font-medium text-card-foreground text-sm">{title}</h3>
        <span className="shrink-0 text-muted-foreground">{meta}</span>
      </div>
      {children}
    </section>
  );
}

function Curriculum({ topics, ask }: { topics: CourseDesign["topics"]; ask: Ask }) {
  const [editing, setEditing] = useState<string | null>(null);
  return (
    <ol className="mt-2 space-y-1">
      {topics.map((topic, t) => (
        <li key={topic.name}>
          <details open={t === 0} className="group rounded-md border px-2 py-1">
            <summary className="flex cursor-pointer list-none items-center gap-1 font-medium text-card-foreground">
              <ChevronRight className="size-3.5 shrink-0 transition-transform group-open:rotate-90" />
              <span className="flex-1">
                {t + 1}. {topic.name}
              </span>
              <span className="font-normal text-muted-foreground">{topic.subtopics.length}</span>
              {ask ? (
                <Button
                  variant="ghost"
                  size="icon-xs"
                  aria-label={`Change ${topic.name}`}
                  onClick={(event) => {
                    event.preventDefault();
                    setEditing(editing === topic.name ? null : topic.name);
                  }}
                >
                  <Pencil />
                </Button>
              ) : null}
            </summary>
            {ask && editing === topic.name ? (
              <ChangeBox
                subject={`the topic "${topic.name}"`}
                onSend={(text) => {
                  setEditing(null);
                  ask(`Change the topic "${topic.name}": ${text}`);
                }}
              />
            ) : null}
            <ul className="mt-1 space-y-1.5 pb-1 pl-5">
              {topic.subtopics.map((sub) => (
                <li key={sub.name}>
                  <p className="text-card-foreground">{sub.name}</p>
                  <Chips label="Checked by" names={sub.styles} />
                  <Chips label="Taught by" names={sub.recipes} />
                </li>
              ))}
            </ul>
          </details>
        </li>
      ))}
    </ol>
  );
}

/**
 * The design as three cards: the curriculum, the question styles and the tutorial recipes.
 * ``superseded``: a newer version of this design is further down the chat, so this one shows
 * as a single line instead of a second copy of every card.
 */
export function DesignCard({
  design,
  ask,
  superseded = false,
}: {
  design: CourseDesign;
  /** Sends a follow-up through the chat; ``null`` shows the design without buttons. */
  ask: Ask;
  superseded?: boolean;
}) {
  if (superseded) {
    return (
      <p className="my-1 text-muted-foreground text-xs">
        An earlier version of the course design; the current one is further down.
      </p>
    );
  }
  const newStyles = design.styles.filter((s) => s.new).length;
  const newRecipes = design.recipes.filter((r) => r.new).length;
  return (
    <div className="my-2 space-y-2">
      <Panel
        title="Curriculum"
        meta={`${design.topic_count} topics · ${design.subtopic_count} subtopics`}
      >
        <p className="mt-0.5 font-medium text-card-foreground">{design.title}</p>
        {design.audience ? <p className="text-muted-foreground">{design.audience}</p> : null}
        <Curriculum topics={design.topics} ask={ask} />
        {design.out_of_scope.length ? (
          <>
            <h4 className="mt-3 font-medium text-card-foreground">Left outside the app</h4>
            <ul className="mt-1 list-disc space-y-0.5 pl-4 text-muted-foreground">
              {design.out_of_scope.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </>
        ) : null}
      </Panel>
      <Panel
        title="Question styles"
        meta={design.styles_ready ? `${design.styles.length} · ${newStyles} new` : "not yet"}
      >
        <p className="mt-0.5 text-muted-foreground">How students are checked.</p>
        {design.styles_ready ? (
          <ItemTable
            kind="style"
            rows={design.styles.map((s) => ({ ...s, label: s.question_type }))}
            ask={ask}
          />
        ) : (
          <NotYet what="Question styles" />
        )}
      </Panel>
      <Panel
        title="Tutorial recipes"
        meta={design.recipes_ready ? `${design.recipes.length} · ${newRecipes} new` : "not yet"}
      >
        <p className="mt-0.5 text-muted-foreground">How students are taught.</p>
        {design.recipes_ready ? (
          <ItemTable
            kind="recipe"
            rows={design.recipes.map((r) => ({ ...r, label: r.form }))}
            ask={ask}
          />
        ) : (
          <NotYet what="Tutorial recipes" />
        )}
      </Panel>
      {ask && design.styles_ready && design.recipes_ready ? (
        <div className="flex justify-end">
          <Button size="sm" onClick={() => ask("Approve this design.")}>
            <Check /> Approve design
          </Button>
        </div>
      ) : null}
    </div>
  );
}
