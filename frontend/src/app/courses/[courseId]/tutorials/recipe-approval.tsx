"use client";

/**
 * The taxonomy's tutorial recipes as a filterable grid of styles, approved or stopped by recipe
 * (Phase 6, Task 24).
 *
 * Each recipe (a tutorial "style" to the professor) is a card: its format, the guidance levels
 * it is written at, its status and how students did after its blocks, with a switch that turns
 * it on or off for the whole taxonomy (approve / stop). Clicking a card opens it in
 * `StyleDialog` (`style-dialog.tsx`): its details and examples, the same switch, and
 * "Show tutorials", the gallery of every block written with it. Search and the Status /
 * Source / Format filters work on the loaded list, in the same filter bar as Students.
 *
 * With live tutorials off, students only see approved recipes' blocks, frozen with a question
 * set, and the missing blocks are priced (`dry_run` of `POST /api/tutorial-pregeneration`) and
 * generated as one job above the grid. With live tutorials on (`live` in the response) a
 * library recipe's blocks are shown once they pass their checks and a missing one is written
 * when a student needs it, so approving a library recipe only marks it as looked at; a recipe
 * made for the course (id `exp.`) is used only once approved. Nothing is priced or generated
 * then: the bank fills as students go.
 */

import { Search } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { RecipeEditorDialog } from "@/app/experimental_tutorial/recipe-builder";
import { EmptyState, QueryError, TableSkeleton } from "@/components/query-state";
import { ActiveFilterChip, FilterLabel, FilterSelect } from "@/components/table-filters";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  useDecideTutorialRecipe,
  useExperimentalRecipes,
  usePregenerateTutorials,
  useTutorialRecipes,
} from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/types";
import { useCourseId } from "@/lib/use-course";
import { FORMAT_LABELS, LEVEL_LABELS } from "@/lib/tutorial-labels";
import { StyleDialog, type StyleStatus, statusVariant } from "./style-dialog";

type Plan = Schemas["TutorialPregenerationPlan"];
type RecipeStats = Schemas["TutorialRecipeStatsOut"];
type OwnRecipe = Schemas["ExperimentalRecipeOut"];
type Renderer = Schemas["TutorialRenderer"];

type Status = StyleStatus;
type StatusFilter = Status | "all";
type SourceFilter = "all" | "library" | "course";
type FormatFilter = Renderer | "all";

const SOURCE_OPTIONS: { value: SourceFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "library", label: "Built in" },
  { value: "course", label: "Made for this course" },
];

/** Made in the recipe builder for this course (`app/tutorials/experimental.py` ids). */
function isCourseRecipe(recipeId: string) {
  return recipeId.startsWith("exp.");
}

/**
 * Whether students get the recipe. Live, a library recipe is in use until stopped, while a
 * course's own waits for approval; not live, every recipe waits for approval.
 */
function statusOf(decision: boolean | undefined, own: boolean, live: boolean): Status {
  if (decision === false) return "stopped";
  if (decision === true) return "in_use";
  return live && !own ? "in_use" : "awaiting";
}

function statusOptions(live: boolean): { value: StatusFilter; label: string }[] {
  return [
    { value: "all", label: "All" },
    { value: "in_use", label: "In use" },
    { value: "awaiting", label: "Awaiting approval" },
    { value: "stopped", label: live ? "Stopped" : "Rejected" },
  ];
}

function percent(rate: number) {
  return `${Math.round(rate * 100)}%`;
}

function errorText(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

/** How students did on their next answer after this recipe's blocks. */
function Outcome({ stats }: { stats?: RecipeStats }) {
  if (!stats || stats.outcomes === 0) return <span>No answers yet</span>;
  return (
    <span>
      <span className="font-mono text-foreground tabular-nums">
        {percent(stats.next_correct_rate ?? 0)}
      </span>{" "}
      next answer right, of {stats.outcomes}
      {stats.weight === 0 ? <span className="text-destructive"> · no longer shown</span> : null}
    </span>
  );
}

export function RecipeApproval({
  versionId,
  subtopicNames,
}: {
  versionId: number;
  /** Subtopic id to name, for the gallery's labels and filter. */
  subtopicNames: Map<number, string>;
}) {
  const courseId = useCourseId();
  const recipes = useTutorialRecipes(versionId);
  // The saved rows of the course's own recipes, to open one in the editor.
  const ownRows = useExperimentalRecipes(courseId);
  const pregenerate = usePregenerateTutorials();
  const decide = useDecideTutorialRecipe();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [editing, setEditing] = useState<OwnRecipe | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all");
  const [formatFilter, setFormatFilter] = useState<FormatFilter>("all");

  if (recipes.isPending) return <TableSkeleton rows={4} />;
  if (recipes.isError) return <QueryError error={recipes.error} />;

  async function price() {
    try {
      const result = await pregenerate.mutateAsync({
        curriculum_version_id: versionId,
        dry_run: true,
      });
      setPlan(result as Plan);
    } catch (error) {
      toast.error("Could not price the blocks", { description: errorText(error, "") });
    }
  }

  async function start() {
    try {
      await pregenerate.mutateAsync({ curriculum_version_id: versionId, dry_run: false });
      setPlan(null);
      toast.success("Generating tutorial blocks", { description: "Follow it in Jobs." });
    } catch (error) {
      toast.error("Could not start", { description: errorText(error, "") });
    }
  }

  async function setDecision(recipeId: string, approved: boolean) {
    try {
      const result = await decide.mutateAsync({
        recipeId,
        curriculum_version_id: versionId,
        approved,
      });
      const count = result.blocks_changed;
      toast.success(approved ? "Style turned on" : "Style turned off", {
        description:
          count === 0
            ? undefined
            : `${count} tutorial${count === 1 ? "" : "s"} ${approved ? "shown to students" : "hidden from students"}.`,
      });
    } catch (error) {
      toast.error("Could not save the decision", { description: errorText(error, "") });
    }
  }

  const decisions = recipes.data.decisions ?? {};
  const live = recipes.data.live ?? false;
  const needsVideo = new Set(recipes.data.needs_video ?? []);
  // The badge: a clip style without a course video is not reaching students whatever its switch.
  const badgeOf = (recipeId: string, status: Status) =>
    needsVideo.has(recipeId)
      ? { label: "Needs a video", variant: "outline" as const }
      : { label: STATUS_LABELS[status], variant: statusVariant(status) };
  const STATUS_LABELS = Object.fromEntries(
    statusOptions(live).map((option) => [option.value, option.label]),
  ) as Record<StatusFilter, string>;

  const rows = recipes.data.recipes.map((recipe) => {
    const own = isCourseRecipe(recipe.id);
    const decision = decisions[recipe.id];
    return {
      recipe,
      own,
      decision,
      status: statusOf(decision, own, live),
      ownRow: own ? ownRows.data?.find((row) => row.recipe_id === recipe.id) : undefined,
    };
  });
  const opened = rows.find((row) => row.recipe.id === openId);
  const formats = [...new Set(rows.map((row) => row.recipe.renderer))];
  const formatOptions: { value: FormatFilter; label: string }[] = [
    { value: "all", label: "All" },
    ...formats.map((format) => ({ value: format, label: FORMAT_LABELS[format] })),
  ];

  const term = search.trim().toLowerCase();
  const shown = rows.filter(
    ({ recipe, own, status }) =>
      (term === "" ||
        recipe.name.toLowerCase().includes(term) ||
        recipe.summary.toLowerCase().includes(term)) &&
      (statusFilter === "all" || status === statusFilter) &&
      (sourceFilter === "all" || (sourceFilter === "course") === own) &&
      (formatFilter === "all" || recipe.renderer === formatFilter),
  );

  const activeFilters = [
    term ? { label: "search", value: search.trim(), onClear: () => setSearch("") } : null,
    statusFilter !== "all"
      ? {
          label: "status",
          value: STATUS_LABELS[statusFilter],
          onClear: () => setStatusFilter("all"),
        }
      : null,
    sourceFilter !== "all"
      ? {
          label: "source",
          value: SOURCE_OPTIONS.find((option) => option.value === sourceFilter)?.label ?? "",
          onClear: () => setSourceFilter("all"),
        }
      : null,
    formatFilter !== "all"
      ? {
          label: "format",
          value: FORMAT_LABELS[formatFilter],
          onClear: () => setFormatFilter("all"),
        }
      : null,
  ].filter((value): value is NonNullable<typeof value> => value !== null);
  const isFiltered = activeFilters.length > 0;

  function clearFilters() {
    setSearch("");
    setStatusFilter("all");
    setSourceFilter("all");
    setFormatFilter("all");
  }

  return (
    <section className="space-y-4">
      {live ? null : (
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="outline" onClick={price} disabled={pregenerate.isPending}>
            Price missing blocks
          </Button>
          {plan ? (
            plan.blocks_to_create === 0 ? (
              <span className="text-muted-foreground text-sm">
                Every block is made ({plan.already_made} in the bank).
              </span>
            ) : (
              <>
                <span className="text-sm">
                  {plan.blocks_to_create} blocks · {plan.generation_calls} model calls (up to{" "}
                  {plan.generation_calls * plan.max_attempts_per_block} with repairs) ·{" "}
                  {plan.already_made} already made
                </span>
                <Button onClick={start} disabled={pregenerate.isPending}>
                  Generate {plan.blocks_to_create} blocks
                </Button>
              </>
            )
          ) : null}
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-border bg-card">
        <div className="space-y-3 border-border border-b p-4">
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search styles..."
              aria-label="Search styles"
              maxLength={200}
              className="h-9 pl-9"
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <FilterSelect
              label="Status"
              value={statusFilter}
              allValue="all"
              options={statusOptions(live)}
              onChange={setStatusFilter}
            />
            <FilterSelect
              label="Source"
              value={sourceFilter}
              allValue="all"
              options={SOURCE_OPTIONS}
              onChange={setSourceFilter}
            />
            <FilterSelect
              label="Format"
              value={formatFilter}
              allValue="all"
              options={formatOptions}
              onChange={setFormatFilter}
            />
            <Button variant="ghost" size="sm" disabled={!isFiltered} onClick={clearFilters}>
              Clear
            </Button>
          </div>
        </div>

        {isFiltered ? (
          <div className="flex flex-wrap items-center gap-2 border-border border-b bg-muted/30 px-4 py-2.5">
            <FilterLabel>Active view</FilterLabel>
            {activeFilters.map((filter) => (
              <ActiveFilterChip
                key={filter.label}
                label={filter.label}
                value={filter.value}
                onClear={filter.onClear}
              />
            ))}
          </div>
        ) : null}

        {shown.length === 0 ? (
          <div className="p-5">
            <EmptyState
              title={isFiltered ? "No styles match this filter" : "No styles yet"}
            />
          </div>
        ) : (
          <ul className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-3">
            {shown.map(({ recipe, own, status }) => (
              <li
                key={recipe.id}
                className="relative flex h-full flex-col gap-2 rounded-lg border border-border bg-background p-4 transition-colors focus-within:ring-2 focus-within:ring-ring hover:border-foreground/25 hover:bg-accent/40"
              >
                <span className="flex items-start gap-2">
                  {/* The name's button covers the card, so a click anywhere opens the style;
                      the switch sits above it and only turns the style on or off. */}
                  <button
                    type="button"
                    onClick={() => setOpenId(recipe.id)}
                    className="min-w-0 flex-1 text-left font-medium text-sm outline-none after:absolute after:inset-0 after:rounded-lg"
                  >
                    {recipe.name}
                  </button>
                  <Badge variant={badgeOf(recipe.id, status).variant} className="shrink-0">
                    {badgeOf(recipe.id, status).label}
                  </Badge>
                  <Switch
                    className="relative z-10"
                    checked={status === "in_use"}
                    disabled={decide.isPending}
                    onCheckedChange={(on) => setDecision(recipe.id, on)}
                    aria-label={`${status === "in_use" ? "Turn off" : "Turn on"} ${recipe.name}`}
                    title={status === "in_use" ? "On: students get it" : "Off: students don't"}
                  />
                </span>
                <span className="line-clamp-3 text-muted-foreground text-sm">{recipe.summary}</span>
                <span className="mt-auto flex flex-wrap items-center gap-x-2 gap-y-1 pt-1 text-muted-foreground text-xs">
                  <span className="font-medium text-foreground">
                    {FORMAT_LABELS[recipe.renderer]}
                  </span>
                  <span aria-hidden>·</span>
                  <span>{recipe.guidance_levels.map((level) => LEVEL_LABELS[level]).join(", ")}</span>
                  {own ? (
                    <>
                      <span aria-hidden>·</span>
                      <span>made for this course</span>
                    </>
                  ) : null}
                </span>
                <span className="text-muted-foreground text-xs">
                  <Outcome stats={recipes.data.stats?.[recipe.id]} />
                </span>
              </li>
            ))}
          </ul>
        )}

        <div className="border-border/70 border-t bg-muted/18 px-5 py-3 text-muted-foreground text-sm">
          <span className="font-semibold text-foreground">{shown.length}</span>
          {isFiltered ? ` of ${rows.length}` : ""} style{rows.length === 1 ? "" : "s"}
        </div>
      </div>

      {opened ? (
        <StyleDialog
          versionId={versionId}
          recipe={opened.recipe}
          own={opened.own}
          live={live}
          status={opened.status}
          badge={badgeOf(opened.recipe.id, opened.status)}
          stats={recipes.data.stats?.[opened.recipe.id]}
          subtopicNames={subtopicNames}
          deciding={decide.isPending}
          onDecide={(approved) => setDecision(opened.recipe.id, approved)}
          onEdit={
            opened.ownRow
              ? () => {
                  setEditing(opened.ownRow ?? null);
                  setOpenId(null);
                }
              : null
          }
          onClose={() => setOpenId(null)}
        />
      ) : null}

      {editing ? (
        <RecipeEditorDialog courseId={courseId} recipe={editing} onClose={() => setEditing(null)} />
      ) : null}
    </section>
  );
}
