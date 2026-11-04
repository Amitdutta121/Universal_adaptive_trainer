"use client";

/**
 * One tutorial style (recipe) in a modal, opened from its card on the tutorials page.
 *
 * The first view is the style itself: what students see, how it is written and a few example
 * blocks, with the on / off switch (as on its card) and Edit for a course's own style. "Show tutorials"
 * switches the same modal to the style's gallery: every block written with it across the
 * taxonomy, filterable by subtopic and guidance level, each retirable on its own.
 */

import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { QueryError, TableSkeleton } from "@/components/query-state";
import { FilterSelect } from "@/components/table-filters";
import { TutorialBlockView } from "@/components/tutorial/renderer-registry";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import {
  useRetireTutorialBlock,
  useTutorialGallery,
  useTutorialSample,
} from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/types";
import { FORMAT_LABELS, humanize, LEVEL_LABELS } from "@/lib/tutorial-labels";

type Recipe = Schemas["TutorialRecipe"];
type RecipeStats = Schemas["TutorialRecipeStatsOut"];
type Block = Schemas["TutorialBlockOut"];
type GuidanceLevel = Schemas["GuidanceLevel"];

/** Blocks drawn at once in the gallery; interactive ones are heavy, so the rest wait. */
const GALLERY_PAGE = 12;

export type StyleStatus = "in_use" | "awaiting" | "stopped";

export type BadgeVariant = "destructive" | "outline" | "secondary";

export function statusVariant(status: StyleStatus): BadgeVariant {
  return status === "stopped" ? "destructive" : status === "awaiting" ? "outline" : "secondary";
}

function errorText(error: unknown) {
  return error instanceof Error ? error.message : "";
}

export function StyleDialog({
  versionId,
  recipe,
  own,
  live,
  status,
  badge,
  stats,
  subtopicNames,
  deciding,
  onDecide,
  onEdit,
  onClose,
}: {
  versionId: number;
  recipe: Recipe;
  own: boolean;
  live: boolean;
  status: StyleStatus;
  badge: { label: string; variant: BadgeVariant };
  stats: RecipeStats | undefined;
  subtopicNames: Map<number, string>;
  deciding: boolean;
  onDecide: (approved: boolean) => void;
  /** Set only for a course's own style, which can be edited. */
  onEdit: (() => void) | null;
  onClose: () => void;
}) {
  const [view, setView] = useState<"style" | "gallery">("style");

  return (
    <Dialog open onOpenChange={(open) => (open ? null : onClose())}>
      <DialogContent className="flex max-h-[92vh] w-[96vw] max-w-none flex-col gap-0 overflow-hidden p-0 sm:max-w-[min(96vw,1100px)]">
        <DialogHeader className="border-b px-6 py-4">
          <div className="flex flex-wrap items-center gap-2 pr-8">
            {view === "gallery" ? (
              <Button
                variant="ghost"
                size="sm"
                className="-ml-2 h-7"
                onClick={() => setView("style")}
              >
                <ArrowLeft data-icon="inline-start" />
                Back
              </Button>
            ) : null}
            <DialogTitle>
              {view === "gallery" ? `Tutorials: ${recipe.name}` : recipe.name}
            </DialogTitle>
            {own ? <Badge variant="outline">made for this course</Badge> : null}
            <Badge variant={badge.variant}>{badge.label}</Badge>
          </div>
          <DialogDescription>{recipe.summary}</DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          {view === "style" ? (
            <StyleDetails versionId={versionId} recipe={recipe} stats={stats} live={live} />
          ) : (
            <StyleGallery
              versionId={versionId}
              recipe={recipe}
              live={live}
              subtopicNames={subtopicNames}
            />
          )}
        </div>

        <DialogFooter className="m-0 border-t px-6 py-3 sm:justify-between">
          <div className="flex gap-2">
            {view === "style" ? (
              <Button variant="outline" onClick={() => setView("gallery")}>
                Show tutorials
              </Button>
            ) : null}
            {onEdit ? (
              <Button variant="ghost" onClick={onEdit}>
                Edit style
              </Button>
            ) : null}
          </div>
          {/* Same switch as on the style's card. */}
          <div className="flex items-center gap-2 text-sm">
            <Switch
              id="style-on"
              checked={status === "in_use"}
              disabled={deciding}
              onCheckedChange={onDecide}
            />
            <label htmlFor="style-on">
              {status === "in_use" ? "On for students" : "Off for students"}
            </label>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="mt-0.5 text-sm">{children}</dd>
    </div>
  );
}

function StyleDetails({
  versionId,
  recipe,
  stats,
  live,
}: {
  versionId: number;
  recipe: Recipe;
  stats: RecipeStats | undefined;
  live: boolean;
}) {
  return (
    <div className="space-y-6">
      <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Fact label="Format">{FORMAT_LABELS[recipe.renderer]}</Fact>
        <Fact label="Guidance levels">
          {recipe.guidance_levels.map((level) => LEVEL_LABELS[level]).join(", ")}
        </Fact>
        <Fact label="Teaches well">{recipe.fits.map(humanize).join(", ")}</Fact>
        <Fact label="Next answer right">
          {stats && stats.outcomes > 0 ? (
            <>
              <span className="font-mono tabular-nums">
                {Math.round((stats.next_correct_rate ?? 0) * 100)}%
              </span>
              <span className="text-muted-foreground"> of {stats.outcomes} answers</span>
              {stats.weight === 0 ? (
                <span className="block text-destructive text-xs">No longer shown to students</span>
              ) : null}
            </>
          ) : (
            <span className="text-muted-foreground">No answers yet</span>
          )}
        </Fact>
      </dl>

      {recipe.prompt ? (
        <details className="rounded-md border">
          <summary className="cursor-pointer px-3 py-2 font-medium text-sm">
            How it is written
          </summary>
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap border-t px-3 py-2 text-muted-foreground text-xs">
            {recipe.prompt}
          </pre>
        </details>
      ) : null}

      <section className="space-y-3">
        <h3 className="font-medium text-sm">Examples</h3>
        <StyleExamples versionId={versionId} recipeId={recipe.id} live={live} />
      </section>
    </div>
  );
}

function emptyText(live: boolean) {
  return live ? "No tutorials yet." : "No tutorials yet. Generate them from the page.";
}

function StyleExamples({
  versionId,
  recipeId,
  live,
}: {
  versionId: number;
  recipeId: string;
  live: boolean;
}) {
  const sample = useTutorialSample(versionId, recipeId);
  if (sample.isPending) return <TableSkeleton rows={1} />;
  if (sample.isError) return <QueryError error={sample.error} />;
  const shown = sample.data.filter((block) => block.status !== "failed");
  if (shown.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        {sample.data.length > 0
          ? "The latest tutorials failed. Show tutorials for the reasons."
          : emptyText(live)}
      </p>
    );
  }
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {shown.map((block) => (
        <BlockCard key={block.id} block={block} subtopic={null} />
      ))}
    </div>
  );
}

function StyleGallery({
  versionId,
  recipe,
  live,
  subtopicNames,
}: {
  versionId: number;
  recipe: Recipe;
  live: boolean;
  subtopicNames: Map<number, string>;
}) {
  const gallery = useTutorialGallery(versionId, recipe.id);
  const [subtopic, setSubtopic] = useState("all");
  const [level, setLevel] = useState<GuidanceLevel | "all">("all");
  const [limit, setLimit] = useState(GALLERY_PAGE);

  if (gallery.isPending) return <TableSkeleton rows={3} />;
  if (gallery.isError) return <QueryError error={gallery.error} />;
  if (gallery.data.length === 0) {
    return <p className="text-muted-foreground text-sm">{emptyText(live)}</p>;
  }

  const nameOf = (id: number) => subtopicNames.get(id) ?? `Subtopic ${id}`;
  const subtopicIds = [...new Set(gallery.data.map((block) => block.subtopic_id))].sort((a, b) =>
    nameOf(a).localeCompare(nameOf(b)),
  );
  const levels = [...new Set(gallery.data.map((block) => block.guidance_level))];
  const shown = gallery.data.filter(
    (block) =>
      (subtopic === "all" || String(block.subtopic_id) === subtopic) &&
      (level === "all" || block.guidance_level === level),
  );
  const failed = shown.filter((block) => block.status === "failed").length;

  function reset(update: () => void) {
    update();
    setLimit(GALLERY_PAGE);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <FilterSelect
          label="Subtopic"
          value={subtopic}
          allValue="all"
          options={[
            { value: "all", label: "All" },
            ...subtopicIds.map((id) => ({ value: String(id), label: nameOf(id) })),
          ]}
          onChange={(value) => reset(() => setSubtopic(value))}
        />
        <FilterSelect
          label="Level"
          value={level}
          allValue="all"
          options={[
            { value: "all", label: "All" },
            ...levels.map((value) => ({ value, label: LEVEL_LABELS[value] })),
          ]}
          onChange={(value) => reset(() => setLevel(value))}
        />
        <span className="ml-auto text-muted-foreground text-sm">
          {shown.length} tutorial{shown.length === 1 ? "" : "s"}
          {failed > 0 ? ` · ${failed} failed` : ""}
          {gallery.data.length === 500 ? " (newest 500)" : ""}
        </span>
      </div>

      {shown.length === 0 ? (
        <p className="text-muted-foreground text-sm">No tutorials match this filter.</p>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {shown.slice(0, limit).map((block) => (
            <BlockCard key={block.id} block={block} subtopic={nameOf(block.subtopic_id)} retirable />
          ))}
        </div>
      )}

      {shown.length > limit ? (
        <div className="flex justify-center">
          <Button variant="outline" onClick={() => setLimit(limit + GALLERY_PAGE)}>
            Show more ({shown.length - limit} left)
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function BlockCard({
  block,
  subtopic,
  retirable = false,
}: {
  block: Block;
  subtopic: string | null;
  retirable?: boolean;
}) {
  const retire = useRetireTutorialBlock();

  // One bad block, without stopping the whole style; live, it is not written again there.
  async function handleRetire() {
    try {
      await retire.mutateAsync(block.id);
      toast.success("Tutorial retired", { description: "Students no longer see it." });
    } catch (error) {
      toast.error("Could not retire the tutorial", { description: errorText(error) });
    }
  }

  return (
    <article className="min-w-0 space-y-2 rounded-md border bg-background p-3">
      <div className="flex items-center gap-2">
        <Badge variant="outline">{LEVEL_LABELS[block.guidance_level]}</Badge>
        {subtopic ? (
          <span className="min-w-0 truncate text-muted-foreground text-xs" title={subtopic}>
            {subtopic}
          </span>
        ) : null}
        {block.status === "failed" ? (
          <Badge variant="destructive" className="ml-auto">
            failed
          </Badge>
        ) : retirable ? (
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto h-7"
            disabled={retire.isPending}
            onClick={handleRetire}
          >
            Retire
          </Button>
        ) : null}
      </div>
      {block.status === "failed" ? (
        <p className="text-destructive text-sm">{block.error}</p>
      ) : (
        <TutorialBlockView renderer={block.renderer} payload={block.payload} />
      )}
    </article>
  );
}
