"use client";

/**
 * Experimental recipe builder: write tutorial recipes with AI, keep them per course, try them.
 *
 * A check on whether recipes can be made from the UI at all. Describe a recipe and the model
 * drafts its YAML (`POST /api/experimental/recipes/draft`); describe a change and it revises the
 * YAML in the editor. The YAML stays editable by hand. Save validates it with the library's
 * recipe schema. A valid draft is shown as a readable summary (the YAML is one click away) with
 * two example blocks written for real subtopics by the library's generator, shown with the
 * student renderers and never saved. Every model call says inline where it is generating, and
 * nothing blocks the rest of the page. A saved recipe joins the course's tutorial recipes and
 * reaches students once approved there (`recipe-approval.tsx`).
 *
 * The course's Tutorials page opens the editor in a modal (`RecipeEditorDialog`). This route
 * lives outside `/courses/{id}`, so it picks the course itself.
 */

import {
  ChevronDown,
  ChevronRight,
  FlaskConical,
  Loader2,
  Plus,
  Sparkles,
  Trash2,
  XCircle,
} from "lucide-react";
import { useEffect, useId, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { QueryError, TableSkeleton } from "@/components/query-state";
import { TutorialBlockView } from "@/components/tutorial/renderer-registry";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { readApiError } from "@/lib/api/client";
import {
  useCourses,
  useDeleteExperimentalRecipe,
  useDraftExperimentalRecipe,
  useExperimentalCurriculum,
  useExperimentalExample,
  useExperimentalRecipes,
  useModelSettings,
  useSaveExperimentalRecipe,
  useTryExperimentalRecipe,
} from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/types";

type Recipe = Schemas["ExperimentalRecipeOut"];
type Level = Schemas["GuidanceLevel"];

const LEVELS: Level[] = ["worked", "faded", "cue"];

/** Starting points for a new recipe, one per renderer, so the box is never a blank page. */
const RECIPE_EXAMPLES = [
  {
    label: "Everyday analogy",
    text: "Explain the idea with one everyday analogy in two or three sentences, then one sentence on where the analogy breaks down.",
  },
  {
    label: "Common mistake",
    text: "Show the most common mistake students make with this idea as a short wrong example, then the corrected version, and one sentence on why the mistake happens.",
  },
  {
    label: "Step-by-step flowchart",
    text: "Draw the steps of this idea as a small flowchart of 4 to 7 boxes, with a one-sentence caption saying what to notice.",
  },
  {
    label: "Compare in a chart",
    text: "When the idea involves quantities or comparisons, show them as a simple bar chart with a caption explaining what the bars show.",
  },
  {
    label: "Step through code",
    text: "Write a short Python program (under 10 lines) that uses this idea, and let the student step through it line by line with a note on the important lines.",
  },
  {
    label: "Predict, then reveal",
    text: "An interactive card: show a short code snippet, ask the student to guess the result, and reveal the answer with a one-line explanation when they click a button.",
  },
  {
    label: "Quick reminder",
    text: "A one-line reminder of the key rule for students who almost have it, with no worked example.",
  },
];

/** Things to ask when a recipe is already in the editor. */
const CHANGE_EXAMPLES = [
  { label: "Shorter", text: "Make the blocks shorter: at most 60 words." },
  {
    label: "Add a cue level",
    text: "Add the cue guidance level: one short reminder, no worked example.",
  },
  { label: "Simpler words", text: "Use simpler words, as for a first-week beginner." },
  {
    label: "Add a code example",
    text: "Add a tiny Python example of at most 4 lines in a code block.",
  },
  {
    label: "End with a question",
    text: "End every block with one short question the student can answer in their head.",
  },
];

function ErrorAlert({ error }: { error: unknown }) {
  const parsed = readApiError(error);
  if (!parsed) return null;
  return (
    <Alert variant="destructive">
      <XCircle />
      <AlertTitle>{parsed.message}</AlertTitle>
      {parsed.detail ? (
        <AlertDescription className="whitespace-pre-wrap">{parsed.detail}</AlertDescription>
      ) : null}
    </Alert>
  );
}

function RecipeList({
  recipes,
  selected,
  onSelect,
  onNew,
}: {
  recipes: Recipe[];
  selected: number | null;
  onSelect: (recipe: Recipe) => void;
  onNew: () => void;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle className="text-base">Recipes</CardTitle>
        <Button size="sm" variant="outline" onClick={onNew}>
          <Plus />
          New
        </Button>
      </CardHeader>
      <CardContent className="space-y-1">
        {recipes.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            None yet. Describe one on the right and draft it with AI.
          </p>
        ) : (
          recipes.map((recipe) => (
            <button
              key={recipe.id}
              type="button"
              aria-current={recipe.id === selected}
              onClick={() => onSelect(recipe)}
              className="w-full rounded-md px-2 py-1.5 text-left hover:bg-muted aria-[current=true]:bg-muted"
            >
              <span className="block truncate font-medium text-sm">{recipe.name}</span>
              <span className="flex items-center gap-1.5 text-muted-foreground text-xs">
                <span className="truncate font-mono">{recipe.recipe_id}</span>
                <Badge variant="outline">{recipe.renderer}</Badge>
              </span>
            </button>
          ))
        )}
      </CardContent>
    </Card>
  );
}

type Curriculum = Schemas["CurriculumVersionDetail"];
type ParsedRecipe = Schemas["TutorialRecipe"];
type Subtopic = { id: number; label: string };

function subtopicsOf(curriculum: Curriculum | undefined): Subtopic[] {
  return (curriculum?.topics ?? []).flatMap((topic) =>
    topic.subtopics.map((subtopic) => ({
      id: subtopic.id,
      label: `${topic.name} · ${subtopic.name}`,
    })),
  );
}

/** Two subtopics to show examples on: from different topics when there are two. */
function exampleSubtopics(curriculum: Curriculum | undefined): Subtopic[] {
  const firstOfEach = (curriculum?.topics ?? [])
    .filter((topic) => topic.subtopics.length > 0)
    .map((topic) => ({
      id: topic.subtopics[0].id,
      label: `${topic.name} · ${topic.subtopics[0].name}`,
    }));
  return (firstOfEach.length >= 2 ? firstOfEach : subtopicsOf(curriculum)).slice(0, 2);
}

/** Where tutorial blocks and recipes are generated: the `tutorials` role's provider and model. */
function useGeneratingOn(): string {
  const settings = useModelSettings();
  const role = settings.data?.roles.find((item) => item.role === "tutorials");
  if (!role) return "the tutorials model";
  const where = role.base_url?.includes(".azure.com")
    ? "Azure"
    : role.provider === "openrouter"
      ? "OpenRouter"
      : role.provider;
  return `${where} · ${role.model}`;
}

function Generating({ what, on }: { what: string; on: string }) {
  return (
    <p role="status" className="flex items-center gap-2 text-muted-foreground text-sm">
      <Loader2 className="size-4 animate-spin" />
      Generating {what} on {on}…
    </p>
  );
}

function BlockResult({ block }: { block: Schemas["ExperimentalRecipeTryOut"] }) {
  if (block.error) {
    return (
      <Alert variant="destructive">
        <XCircle />
        <AlertTitle>This block failed its checks</AlertTitle>
        <AlertDescription className="whitespace-pre-wrap">{block.error}</AlertDescription>
      </Alert>
    );
  }
  return (
    <div className="space-y-2">
      <TutorialBlockView renderer={block.renderer} payload={block.payload} />
      <p className="text-muted-foreground text-xs">
        Written from {block.chunk_ids.length} book chunks by {block.model || "no model"} · not saved
      </p>
    </div>
  );
}

/** One example block, generated once per examples run. */
function ExampleBlock({
  courseId,
  run,
  yaml,
  subtopic,
  level,
  on,
}: {
  courseId: number;
  run: number;
  yaml: string;
  subtopic: Subtopic;
  level: Level;
  on: string;
}) {
  const example = useExperimentalExample(courseId, run, {
    yaml,
    subtopic_id: subtopic.id,
    guidance_level: level,
  });

  return (
    <div className="min-w-0 space-y-2 rounded-md border p-4">
      <p className="font-medium text-sm">
        {subtopic.label} <span className="text-muted-foreground">· {level}</span>
      </p>
      {example.isPending ? <Generating what="an example" on={on} /> : null}
      <ErrorAlert error={example.error} />
      {example.data ? <BlockResult block={example.data} /> : null}
    </div>
  );
}

function RecipeSummary({ recipe, edited }: { recipe: ParsedRecipe; edited: boolean }) {
  return (
    <div className="space-y-2 rounded-md border bg-muted/30 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="font-medium">{recipe.name}</p>
        <span className="font-mono text-muted-foreground text-xs">{recipe.id}</span>
      </div>
      <p className="text-sm">{recipe.summary}</p>
      <dl className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
        <div className="flex gap-1">
          <dt className="text-muted-foreground">Draws as</dt>
          <dd>{recipe.renderer}</dd>
        </div>
        <div className="flex gap-1">
          <dt className="text-muted-foreground">Guidance</dt>
          <dd>{recipe.guidance_levels.join(", ")}</dd>
        </div>
        <div className="flex gap-1">
          <dt className="text-muted-foreground">Good for</dt>
          <dd>{recipe.fits.join(", ")}</dd>
        </div>
        {recipe.tool ? (
          <div className="flex gap-1">
            <dt className="text-muted-foreground">Tool</dt>
            <dd>{recipe.tool}</dd>
          </div>
        ) : null}
      </dl>
      {edited ? (
        <p className="text-muted-foreground text-xs">
          The YAML was edited by hand; this summary updates when you save.
        </p>
      ) : null}
    </div>
  );
}

function TryPanel({
  courseId,
  yaml,
  levels,
  on,
}: {
  courseId: number;
  yaml: string;
  levels: Level[];
  on: string;
}) {
  const id = useId();
  const curriculum = useExperimentalCurriculum(courseId);
  const tryRecipe = useTryExperimentalRecipe();
  const [subtopicId, setSubtopicId] = useState<string>("");
  const [picked, setLevel] = useState<Level | null>(null);
  // Only the levels the recipe is written at; any other is refused by the generator.
  const level = picked !== null && levels.includes(picked) ? picked : levels[0];
  const subtopics = subtopicsOf(curriculum.data);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Try on another subtopic</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {curriculum.isError ? (
          <p className="text-muted-foreground text-sm">
            This course has no approved curriculum, so there is no subtopic to try on.
          </p>
        ) : (
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-64 flex-1 space-y-1.5">
              <Label htmlFor={`${id}-subtopic`}>Subtopic</Label>
              <Select value={subtopicId} onValueChange={setSubtopicId}>
                <SelectTrigger id={`${id}-subtopic`} className="w-full">
                  <SelectValue placeholder="Pick a subtopic" />
                </SelectTrigger>
                <SelectContent>
                  {subtopics.map((subtopic) => (
                    <SelectItem key={subtopic.id} value={String(subtopic.id)}>
                      {subtopic.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={`${id}-level`}>Guidance</Label>
              <Select value={level} onValueChange={(value) => setLevel(value as Level)}>
                <SelectTrigger id={`${id}-level`} className="w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {levels.map((name) => (
                    <SelectItem key={name} value={name}>
                      {name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button
              variant="outline"
              disabled={!subtopicId || !yaml.trim() || tryRecipe.isPending}
              onClick={() =>
                tryRecipe.mutate({
                  courseId,
                  body: { yaml, subtopic_id: Number(subtopicId), guidance_level: level },
                })
              }
            >
              <FlaskConical />
              Try
            </Button>
          </div>
        )}
        {tryRecipe.isPending ? <Generating what="a block" on={on} /> : null}
        <ErrorAlert error={tryRecipe.error} />
        {tryRecipe.data ? (
          <div className="rounded-md border p-4">
            <BlockResult block={tryRecipe.data} />
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

interface Request {
  kind: "new" | "change";
  text: string;
}

function Editor({
  courseId,
  recipe,
  onSaved,
  onDeleted,
  showTitle = true,
}: {
  courseId: number;
  recipe: Recipe | null;
  onSaved: (recipe: Recipe) => void;
  onDeleted: () => void;
  /** Off inside a modal, whose own title names the recipe. */
  showTitle?: boolean;
}) {
  const id = useId();
  const on = useGeneratingOn();
  const curriculum = useExperimentalCurriculum(courseId);
  const [ask, setAsk] = useState("");
  const [requests, setRequests] = useState<Request[]>([]);
  const [yaml, setYaml] = useState(recipe?.yaml ?? "");
  const [parsed, setParsed] = useState<ParsedRecipe | null>(recipe?.recipe ?? null);
  const [edited, setEdited] = useState(false);
  const [showYaml, setShowYaml] = useState(false);
  // Each run of examples remounts its blocks; 0 means none asked for yet.
  const [examples, setExamples] = useState<{ run: number; yaml: string }>({ run: 0, yaml: "" });
  const draft = useDraftExperimentalRecipe();
  const save = useSaveExperimentalRecipe();
  const remove = useDeleteExperimentalRecipe();
  const problems = draft.data?.problems ?? [];
  const revising = yaml.trim().length > 0;
  const exampleOn = exampleSubtopics(curriculum.data);
  const level = parsed?.guidance_levels[0] ?? "worked";

  const showExamples = (text: string) =>
    setExamples((current) => ({ run: current.run + 1, yaml: text }));

  const runDraft = async () => {
    const request: Request = { kind: revising ? "change" : "new", text: ask.trim() };
    setRequests((list) => [...list, request]);
    setAsk("");
    const result = await draft.mutateAsync({
      courseId,
      body: { description: request.text, current_yaml: revising ? yaml : null },
    });
    setYaml(result.yaml);
    setParsed(result.recipe ?? null);
    setEdited(false);
    if (result.recipe) {
      if (exampleOn.length > 0) showExamples(result.yaml);
    } else {
      setShowYaml(true);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        {showTitle ? (
          <CardHeader>
            <CardTitle className="text-base">
              {recipe ? `Edit ${recipe.recipe_id}` : "New recipe"}
            </CardTitle>
          </CardHeader>
        ) : null}
        <CardContent className="space-y-4">
          {requests.length > 0 ? (
            <div className="space-y-1">
              <p className="text-muted-foreground text-xs">What you asked for</p>
              <ol className="space-y-1">
                {requests.map((request, index) => (
                  <li
                    // biome-ignore lint/suspicious/noArrayIndexKey: an append-only log
                    key={index}
                    className="rounded-md bg-muted/40 px-3 py-1.5 text-sm"
                  >
                    <span className="text-muted-foreground text-xs">
                      {request.kind === "new" ? "Recipe" : "Change"}:{" "}
                    </span>
                    {request.text}
                  </li>
                ))}
              </ol>
            </div>
          ) : null}

          <div className="space-y-1.5">
            <Label htmlFor={`${id}-ask`}>
              {revising ? "Describe a change" : "Describe the recipe"}
            </Label>
            <Textarea
              id={`${id}-ask`}
              value={ask}
              onChange={(event) => setAsk(event.target.value)}
              rows={3}
              placeholder={
                revising
                  ? "e.g. Make it shorter and add a cue level"
                  : "e.g. Explain the idea with one everyday analogy, then say where the analogy breaks"
              }
            />
            <div className="space-y-1">
              <p className="text-muted-foreground text-xs">
                {revising ? "Example changes (click to use):" : "Examples (click to use):"}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {(revising ? CHANGE_EXAMPLES : RECIPE_EXAMPLES).map((example) => (
                  <button
                    key={example.label}
                    type="button"
                    title={example.text}
                    onClick={() => setAsk(example.text)}
                    className="rounded-full border px-2.5 py-0.5 text-xs hover:bg-muted"
                  >
                    {example.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button
                variant="outline"
                size="sm"
                disabled={ask.trim().length < 3 || draft.isPending}
                onClick={() => void runDraft()}
              >
                <Sparkles />
                {revising ? "Revise with AI" : "Draft with AI"}
              </Button>
              {draft.isPending ? (
                <Generating what={revising ? "the revised recipe" : "the recipe"} on={on} />
              ) : null}
            </div>
          </div>
          <ErrorAlert error={draft.error} />
          {problems.length > 0 ? (
            <Alert variant="destructive">
              <XCircle />
              <AlertTitle>The draft is still not valid</AlertTitle>
              <AlertDescription>
                <ul className="list-disc pl-4">
                  {problems.map((problem) => (
                    <li key={problem}>{problem}</li>
                  ))}
                </ul>
                Fix it in the YAML, or describe the fix and revise again.
              </AlertDescription>
            </Alert>
          ) : null}

          {parsed ? <RecipeSummary recipe={parsed} edited={edited} /> : null}

          {revising ? (
            <div className="space-y-1.5">
              <Button variant="ghost" size="sm" onClick={() => setShowYaml((open) => !open)}>
                {showYaml ? <ChevronDown /> : <ChevronRight />}
                {showYaml ? "Hide YAML" : "Edit YAML"}
              </Button>
              {showYaml ? (
                <Textarea
                  aria-label="Recipe YAML"
                  value={yaml}
                  onChange={(event) => {
                    setYaml(event.target.value);
                    setEdited(true);
                  }}
                  rows={16}
                  spellCheck={false}
                  className="font-mono text-xs"
                />
              ) : null}
            </div>
          ) : null}

          <ErrorAlert error={save.error ?? remove.error} />
          <div className="flex flex-wrap gap-2">
            <Button
              disabled={!yaml.trim() || save.isPending}
              onClick={async () => {
                const saved = await save.mutateAsync({ courseId, id: recipe?.id ?? null, yaml });
                setParsed(saved.recipe);
                setEdited(false);
                onSaved(saved);
              }}
            >
              {save.isPending ? "Saving…" : recipe ? "Save changes" : "Save recipe"}
            </Button>
            {recipe ? (
              <Button
                variant="ghost"
                disabled={remove.isPending}
                onClick={async () => {
                  await remove.mutateAsync({ courseId, id: recipe.id });
                  onDeleted();
                }}
              >
                <Trash2 />
                Delete
              </Button>
            ) : null}
          </div>
        </CardContent>
      </Card>

      {revising ? (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardTitle className="text-base">Examples</CardTitle>
            {exampleOn.length > 0 ? (
              <Button variant="outline" size="sm" onClick={() => showExamples(yaml)}>
                <FlaskConical />
                {examples.run === 0 ? "Show 2 examples" : "Generate new examples"}
              </Button>
            ) : null}
          </CardHeader>
          <CardContent>
            {exampleOn.length === 0 ? (
              <p className="text-muted-foreground text-sm">
                Examples need a course with an approved curriculum and a book. Pick one above.
              </p>
            ) : examples.run === 0 ? (
              <p className="text-muted-foreground text-sm">
                See what students would get: two blocks written from this recipe for{" "}
                {exampleOn.map((subtopic) => subtopic.label).join(" and ")}.
              </p>
            ) : (
              <div className="grid gap-4 xl:grid-cols-2">
                {exampleOn.map((subtopic) => (
                  <ExampleBlock
                    key={`${examples.run}-${subtopic.id}`}
                    courseId={courseId}
                    run={examples.run}
                    yaml={examples.yaml}
                    subtopic={subtopic}
                    level={level}
                    on={on}
                  />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      ) : null}

      {revising ? (
        <TryPanel
          courseId={courseId}
          yaml={yaml}
          levels={parsed?.guidance_levels ?? LEVELS}
          on={on}
        />
      ) : null}
    </div>
  );
}

/**
 * The editor in a large modal, for a new recipe (`recipe` null) or a saved one. The course's
 * tutorials page opens it from "Create a recipe" and from a recipe's Edit. After the first save
 * it edits the saved recipe, as the list-and-editor below does.
 */
export function RecipeEditorDialog({
  courseId,
  recipe,
  onClose,
}: {
  courseId: number;
  recipe: Recipe | null;
  onClose: () => void;
}) {
  const [current, setCurrent] = useState<Recipe | null>(recipe);
  return (
    <Dialog open onOpenChange={(open) => (open ? null : onClose())}>
      <DialogContent className="flex max-h-[92vh] w-[96vw] max-w-none flex-col gap-0 overflow-hidden p-0 sm:max-w-[min(96vw,1100px)]">
        <DialogHeader className="border-b px-6 py-4">
          <DialogTitle>{current ? `Edit “${current.name}”` : "Create a recipe"}</DialogTitle>
          <DialogDescription>
            Describe a way of teaching and AI drafts the recipe. Try it on real subtopics, change
            it, and save it. A saved recipe reaches students once you approve it in the list.
          </DialogDescription>
        </DialogHeader>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
          <Editor
            courseId={courseId}
            recipe={current}
            onSaved={setCurrent}
            onDeleted={onClose}
            showTitle={false}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** The recipe list and editor for one course, on this route. */
export function RecipeWorkbench({ courseId }: { courseId: number }) {
  const [selected, setSelected] = useState<Recipe | null>(null);
  // Remounts the editor on a new selection, so its draft never leaks into another recipe.
  const [editorKey, setEditorKey] = useState(0);
  const recipes = useExperimentalRecipes(courseId);

  const open = (recipe: Recipe | null) => {
    setSelected(recipe);
    setEditorKey((key) => key + 1);
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[18rem_1fr]">
      <div>
        {recipes.isPending ? <TableSkeleton rows={4} /> : null}
        {recipes.isError ? <QueryError error={recipes.error} /> : null}
        {recipes.isSuccess ? (
          <RecipeList
            recipes={recipes.data}
            selected={selected?.id ?? null}
            onSelect={open}
            onNew={() => open(null)}
          />
        ) : null}
      </div>
      <Editor
        key={editorKey}
        courseId={courseId}
        recipe={selected}
        onSaved={(recipe) => setSelected(recipe)}
        onDeleted={() => open(null)}
      />
    </div>
  );
}

export function RecipeBuilder() {
  const courses = useCourses();
  const [courseId, setCourseId] = useState<number | null>(null);
  const list = courses.data?.courses ?? [];
  // Prefer a course with a curriculum: examples and Try need its subtopics.
  const firstCourse =
    (list.find((course) => course.curriculum_version_count > 0) ?? list[0])?.id ?? null;

  useEffect(() => {
    if (courseId === null && firstCourse !== null) setCourseId(firstCourse);
  }, [courseId, firstCourse]);

  return (
    <>
      <PageHeader
        title="Recipe builder (experimental)"
        summary="Draft tutorial recipes with AI, edit them, and try one on a real subtopic. A saved recipe reaches students once it is approved on the course's Tutorials page."
        showTaxonomySelector={false}
      />
      {courses.isPending ? <TableSkeleton rows={4} /> : null}
      {courses.isError ? <QueryError error={courses.error} /> : null}
      {courses.isSuccess && list.length === 0 ? (
        <Alert>
          <AlertTitle>No course yet</AlertTitle>
          <AlertDescription>Recipes belong to a course. Create one first.</AlertDescription>
        </Alert>
      ) : null}
      {courseId !== null ? (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Label htmlFor="experimental-course">Course</Label>
            <Select value={String(courseId)} onValueChange={(value) => setCourseId(Number(value))}>
              <SelectTrigger id="experimental-course" className="w-64">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {list.map((course) => (
                  <SelectItem key={course.id} value={String(course.id)}>
                    {course.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {/* Keyed by course, so switching courses starts with nothing selected. */}
          <RecipeWorkbench key={courseId} courseId={courseId} />
        </div>
      ) : null}
    </>
  );
}
