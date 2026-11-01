"use client";

/**
 * The taxonomy's tutorial recipes as a filterable table, approved or stopped by recipe
 * (Phase 6, Task 24).
 *
 * Each row is a recipe: its format, the guidance levels it is written at, its decision for the
 * whole taxonomy and how students did after its blocks. "View sample" opens a few of its blocks
 * under the row, as students see them, each retirable on its own. Search and the Status /
 * Source / Format filters work on the loaded list, in the same filter bar as Students.
 *
 * With live tutorials off, students only see approved recipes' blocks, frozen with a question
 * set, and the missing blocks are priced (`dry_run` of `POST /api/tutorial-pregeneration`) and
 * generated as one job above the table. With live tutorials on (`live` in the response) a
 * library recipe's blocks are shown once they pass their checks and a missing one is written
 * when a student needs it, so approving a library recipe only marks it as looked at; a recipe
 * made for the course (id `exp.`) is used only once approved. Nothing is priced or generated
 * then: the bank fills as students go.
 */

import { Search } from "lucide-react";
import { Fragment, useState } from "react";
import { toast } from "sonner";
import { RecipeEditorDialog } from "@/app/experimental_tutorial/recipe-builder";
import { EmptyState, QueryError, TableSkeleton } from "@/components/query-state";
import { ActiveFilterChip, FilterLabel, FilterSelect } from "@/components/table-filters";
import { TutorialBlockView } from "@/components/tutorial/renderer-registry";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useDecideTutorialRecipe,
  useExperimentalRecipes,
  usePregenerateTutorials,
  useRetireTutorialBlock,
  useTutorialRecipes,
  useTutorialSample,
} from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/types";
import { useCourseId } from "@/lib/use-course";

type Plan = Schemas["TutorialPregenerationPlan"];
type RecipeStats = Schemas["TutorialRecipeStatsOut"];
type OwnRecipe = Schemas["ExperimentalRecipeOut"];
type Renderer = Schemas["TutorialRenderer"];

/** What a student sees, in a professor's words. */
const FORMAT_LABELS: Record<Renderer, string> = {
  markdown: "Text",
  mermaid: "Diagram",
  chartjs: "Chart",
  html: "Interactive",
  video_clip: "Video clip",
};

type Status = "in_use" | "awaiting" | "stopped";
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
function OutcomeCell({ stats }: { stats?: RecipeStats }) {
  if (!stats || stats.outcomes === 0) {
    return <span className="text-muted-foreground">No answers yet</span>;
  }
  return (
    <span>
      <span className="font-mono tabular-nums">{percent(stats.next_correct_rate ?? 0)}</span>
      <span className="text-muted-foreground"> of {stats.outcomes}</span>
      {stats.weight === 0 ? (
        <span className="block text-destructive text-xs">No longer shown to students</span>
      ) : null}
    </span>
  );
}

export function RecipeApproval({ versionId }: { versionId: number }) {
  const courseId = useCourseId();
  const recipes = useTutorialRecipes(versionId);
  // The saved rows of the course's own recipes, to open one in the editor.
  const ownRows = useExperimentalRecipes(courseId);
  const pregenerate = usePregenerateTutorials();
  const decide = useDecideTutorialRecipe();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [sampled, setSampled] = useState<string | null>(null);
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
      toast.success(approved ? "Recipe approved" : "Recipe stopped", {
        description: `${count} block${count === 1 ? "" : "s"} ${approved ? "approved" : "hidden"}.`,
      });
    } catch (error) {
      toast.error("Could not save the decision", { description: errorText(error, "") });
    }
  }

  const decisions = recipes.data.decisions ?? {};
  const live = recipes.data.live ?? false;
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
      <div>
        <h2 className="font-semibold">
          {live ? "Recipes students get" : "Pre-generate and approve by recipe"}
        </h2>
        <p className="max-w-4xl text-muted-foreground text-sm">
          {live
            ? "Students see a recipe's blocks as soon as they pass their checks, and a block a student needs is written then (follow it in Jobs). A recipe made for this course waits for your approval first. Stop a recipe for the whole taxonomy, or retire a single block from its sample."
            : "Students only see blocks of approved recipes, frozen with the question set they train on. Look at a sample of each recipe's blocks, then approve or reject the recipe for the whole taxonomy."}
        </p>
      </div>

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
              placeholder="Search recipes..."
              aria-label="Search recipes"
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

        <div className="flex flex-wrap items-center gap-2 border-border border-b bg-muted/30 px-4 py-2.5">
          <FilterLabel>Active view</FilterLabel>
          {isFiltered ? (
            activeFilters.map((filter) => (
              <ActiveFilterChip
                key={filter.label}
                label={filter.label}
                value={filter.value}
                onClear={filter.onClear}
              />
            ))
          ) : (
            <span className="text-muted-foreground text-sm">No filters applied.</span>
          )}
        </div>

        {shown.length === 0 ? (
          <div className="p-5">
            <EmptyState
              title={isFiltered ? "No recipes match this filter" : "No recipes yet"}
              hint={isFiltered ? "Broaden the search or clear filters." : undefined}
            />
          </div>
        ) : (
          <Table className="table-auto">
            <TableHeader className="[&_tr]:border-b-0">
              <TableRow className="hover:bg-transparent">
                <TableHead>Recipe</TableHead>
                <TableHead>Format</TableHead>
                <TableHead>Levels</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Next answer right</TableHead>
                <TableHead className="text-right">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {shown.map(({ recipe, own, decision, status, ownRow }) => (
                <Fragment key={recipe.id}>
                  <TableRow className="hover:!bg-accent/28 border-border/60 border-b odd:bg-background even:bg-muted/18">
                    <TableCell className="max-w-md whitespace-normal py-3">
                      <span className="font-medium text-sm">{recipe.name}</span>
                      {own ? (
                        <Badge variant="outline" className="ml-2 align-middle">
                          made for this course
                        </Badge>
                      ) : null}
                      <span className="mt-0.5 block text-muted-foreground text-xs">
                        {recipe.summary}
                      </span>
                    </TableCell>
                    <TableCell className="py-3 text-sm">{FORMAT_LABELS[recipe.renderer]}</TableCell>
                    <TableCell className="py-3 text-muted-foreground text-sm">
                      {recipe.guidance_levels.join(", ")}
                    </TableCell>
                    <TableCell className="py-3">
                      <Badge
                        variant={
                          status === "stopped"
                            ? "destructive"
                            : status === "awaiting"
                              ? "outline"
                              : "secondary"
                        }
                      >
                        {STATUS_LABELS[status]}
                      </Badge>
                    </TableCell>
                    <TableCell className="py-3 text-sm">
                      <OutcomeCell stats={recipes.data.stats?.[recipe.id]} />
                    </TableCell>
                    <TableCell className="py-3">
                      <div className="flex justify-end gap-1.5">
                        {ownRow ? (
                          <Button size="sm" variant="ghost" onClick={() => setEditing(ownRow)}>
                            Edit
                          </Button>
                        ) : null}
                        <Button
                          size="sm"
                          variant="ghost"
                          aria-expanded={sampled === recipe.id}
                          onClick={() => setSampled(sampled === recipe.id ? null : recipe.id)}
                        >
                          {sampled === recipe.id ? "Hide sample" : "View sample"}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={decide.isPending || decision === false}
                          onClick={() => setDecision(recipe.id, false)}
                        >
                          {live ? "Stop using" : "Reject"}
                        </Button>
                        <Button
                          size="sm"
                          disabled={decide.isPending || decision === true}
                          onClick={() => setDecision(recipe.id, true)}
                        >
                          {live && !own ? "Mark reviewed" : "Approve"}
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                  {sampled === recipe.id ? (
                    <TableRow className="hover:bg-transparent">
                      <TableCell colSpan={6} className="whitespace-normal bg-muted/18 p-4">
                        <RecipeSample versionId={versionId} recipeId={recipe.id} live={live} />
                      </TableCell>
                    </TableRow>
                  ) : null}
                </Fragment>
              ))}
            </TableBody>
          </Table>
        )}

        <div className="border-border/70 border-t bg-muted/18 px-5 py-3 text-muted-foreground text-sm">
          <span className="font-semibold text-foreground">{shown.length}</span>
          {isFiltered ? ` of ${rows.length}` : ""} recipe{rows.length === 1 ? "" : "s"}
        </div>
      </div>

      {editing ? (
        <RecipeEditorDialog courseId={courseId} recipe={editing} onClose={() => setEditing(null)} />
      ) : null}
    </section>
  );
}

function RecipeSample({
  versionId,
  recipeId,
  live,
}: {
  versionId: number;
  recipeId: string;
  live: boolean;
}) {
  const sample = useTutorialSample(versionId, recipeId);
  const retire = useRetireTutorialBlock();

  // One bad block, without stopping the whole recipe; live, it is not written again there.
  async function handleRetire(blockId: number) {
    try {
      await retire.mutateAsync(blockId);
      toast.success("Block retired", { description: "Students no longer see it." });
    } catch (error) {
      toast.error("Could not retire the block", { description: errorText(error, "") });
    }
  }

  if (sample.isPending) return <TableSkeleton rows={1} />;
  if (sample.isError) return <QueryError error={sample.error} />;
  if (sample.data.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        {live
          ? "No blocks of this recipe yet. One is written the first time a student needs it."
          : "No blocks of this recipe yet. Price and generate the missing blocks above."}
      </p>
    );
  }
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {sample.data.map((block) => (
        <div key={block.id} className="min-w-0 space-y-2 rounded-md border bg-background p-3">
          <div className="flex items-center gap-2">
            <Badge variant="outline">{block.guidance_level}</Badge>
            {block.status === "failed" ? (
              <Badge variant="destructive">failed</Badge>
            ) : (
              <Button
                size="sm"
                variant="ghost"
                className="ml-auto h-7"
                disabled={retire.isPending}
                onClick={() => handleRetire(block.id)}
              >
                Retire
              </Button>
            )}
          </div>
          {block.status === "failed" ? (
            <p className="text-destructive text-sm">{block.error}</p>
          ) : (
            <TutorialBlockView renderer={block.renderer} payload={block.payload} />
          )}
        </div>
      ))}
    </div>
  );
}
