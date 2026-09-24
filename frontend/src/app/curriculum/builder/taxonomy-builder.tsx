"use client";

/**
 * Build a taxonomy by hand: an outline of topics and subtopics on the left, the
 * selected topic's fields and subtopic table on the right. It fills the big modal the
 * curriculum page opens from its table (a title bar with the name, the two panes, a
 * bar of actions), so it sizes itself to the height it is given and scrolls inside.
 *
 * Saving serialises the draft to the taxonomy document and sends it through the
 * existing `POST /curriculum/versions` (`useImportTaxonomy`). This screen holds no
 * validation rules of its own beyond "finished": the backend owns what a valid
 * taxonomy is, duplicate names included, and its refusal is shown as it words it.
 * The document is a new version, never an edit of an existing one (ADR-021/046). A
 * saved taxonomy can be opened here as a copy (`source`); saving still creates a new
 * version and leaves the one it was opened from untouched.
 * Input limits are read from the served field reference, not typed here.
 *
 * The draft is kept in this browser while it has unsaved changes, so a reload or a
 * refused save loses nothing. A copy that has not been changed is not kept: there is
 * nothing in it that the saved version does not already hold.
 *
 * Removal never asks "are you sure". It happens at once and can be undone three
 * ways — the toast (for `UNDO_TOAST_MS`, held while hovered), the header Undo, and
 * Ctrl+Z — because a confirm on every ✕ teaches people to click through it.
 */

import {
  ArrowDown,
  ArrowUp,
  ChevronDown,
  ChevronRight,
  History,
  Plus,
  Search,
  Trash2,
  TriangleAlert,
  Undo2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { CopyButton } from "@/components/copy-button";
import { QueryError } from "@/components/query-state";
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  useApprovedCurriculum,
  useImportTaxonomy,
  useTaxonomyDocumentGuide,
} from "@/lib/api/queries";
import type { CurriculumVersionDetail } from "@/lib/api/types";
import { formatTimestamp, pluralise } from "@/lib/display";
import { fileFromPastedJson } from "@/lib/json-document";
import { cn } from "@/lib/utils";
import { TaxonomyRefusalAlert } from "../components/taxonomy-refusal-alert";
import { MANUAL_TAXONOMY_FILENAME } from "../taxonomy-document";
import type { NamedDocument } from "../taxonomy-refusal";
import {
  countMatches,
  countSubtopics,
  type Draft,
  type DraftProblem,
  describeRemoval,
  draftSignature,
  emptyDraft,
  filterTree,
  findProblem,
  isDraftEmpty,
  limitsFromGuide,
  matchedByDescriptionOnly,
  moveSubtopic,
  moveTopic,
  newId,
  type Removal,
  removeSubtopic,
  removeTopic,
  restoreRemoval,
  type Selection,
  toTaxonomyDocument,
} from "./taxonomy-draft";
import { clearDraft, type DraftOrigin, loadDraft, saveDraft } from "./taxonomy-draft-storage";

/** How long the removal toast stays up. It holds while hovered, and the header Undo outlasts it. */
const UNDO_TOAST_MS = 10_000;
/** How many removals the header Undo and Ctrl+Z can walk back through. */
const UNDO_DEPTH = 20;

interface Doc {
  draft: Draft;
  undo: Removal[];
}

/** Ask the effect below to move keyboard focus once the next render has put the target on screen. */
type FocusRequest = { serial: number; target: "tree" | { inputId: string } } | null;

function Highlight({ text, query, fallback }: { text: string; query: string; fallback: string }) {
  if (!text) return <span className="text-muted-foreground italic">{fallback}</span>;
  const needle = query.trim();
  const at = needle ? text.toLowerCase().indexOf(needle.toLowerCase()) : -1;
  if (at < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, at)}
      <mark className="rounded-sm bg-(--warn-wash) px-0.5 text-inherit">
        {text.slice(at, at + needle.length)}
      </mark>
      {text.slice(at + needle.length)}
    </>
  );
}

/** `max` is absent until the guide has loaded, when only the running length is shown. */
function CharCount({ value, max }: { value: string; max: number | undefined }) {
  return (
    <span className="font-mono text-muted-foreground text-xs tabular-nums">
      {max === undefined ? value.length : `${value.length}/${max}`}
    </span>
  );
}

const ROW =
  "scroll-mb-24 group/row flex w-full cursor-pointer items-center gap-1 rounded-lg border border-transparent px-1.5 py-1 text-left text-sm outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 aria-selected:border-primary/30 aria-selected:bg-accent aria-selected:text-accent-foreground";

/** The ✕ takes its space at all times so names never jump; it shows on hover, keyboard focus, and touch. */
const REMOVE =
  "size-5 shrink-0 text-muted-foreground opacity-0 hover:bg-destructive/10 hover:text-destructive group-hover/row:opacity-100 group-focus-within/row:opacity-100 focus-visible:opacity-100 [@media(hover:none)]:opacity-100";

/** What to put in the builder: a blank draft, or a copy of a saved taxonomy. A new object loads again. */
export interface BuilderSource {
  origin: DraftOrigin | null;
  draft: Draft;
}

export function TaxonomyBuilder({
  source = null,
  onDirtyChange,
  onSaved,
}: {
  source?: BuilderSource | null;
  /** Whether the draft differs from what was loaded, so the page can warn before replacing it. */
  onDirtyChange?: (dirty: boolean) => void;
  /** Called with the version that was just created. */
  onSaved?: (detail: CurriculumVersionDetail) => void;
}) {
  const [doc, setDoc] = useState<Doc>(() => ({ draft: emptyDraft(), undo: [] }));
  const { draft } = doc;

  const [selection, setSelection] = useState<Selection>({ topicId: "", subtopicId: null });
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const [query, setQuery] = useState("");
  const [focusRequest, setFocusRequest] = useState<FocusRequest>(null);

  const treeRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const undoRef = useRef<Removal[]>([]);
  undoRef.current = doc.undo;
  /** removal id → the toast that offers to undo it, so undoing elsewhere can dismiss it. */
  const toastFor = useRef(new Map<string, string | number>());
  const focusSerial = useRef(0);

  const guide = useTaxonomyDocumentGuide();
  const approved = useApprovedCurriculum();
  const importTaxonomy = useImportTaxonomy();
  const limits = useMemo(() => limitsFromGuide(guide.data?.fields), [guide.data]);

  const [restored, setRestored] = useState<{ savedAt: string } | null>(null);
  const [problem, setProblem] = useState<DraftProblem | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  /** What was last sent, so a refusal can name the topic it is about even if the draft has changed since. */
  const [sentDocument, setSentDocument] = useState<NamedDocument | null>(null);
  /** False until the stored draft has been looked at, so the autosave below cannot overwrite it with an empty one. */
  const hydrated = useRef(false);
  /** The saved taxonomy this draft is a copy of, if any. */
  const [origin, setOrigin] = useState<DraftOrigin | null>(null);
  /** What the draft looked like when it was loaded; anything else is an unsaved change. */
  const [baseline, setBaseline] = useState(() => draftSignature(emptyDraft()));
  const dirty = useMemo(() => draftSignature(draft) !== baseline, [draft, baseline]);
  const onDirtyChangeRef = useRef(onDirtyChange);
  onDirtyChangeRef.current = onDirtyChange;

  const searching = query.trim() !== "";
  const tree = useMemo(() => filterTree(draft.topics, query), [draft.topics, query]);
  const matchCount = countMatches(draft.topics, query);

  // The topic on the right is always one that exists: a removal or a search never leaves it dangling.
  const activeTopic = draft.topics.find((topic) => topic.id === selection.topicId);

  // Restored after mount, not in the initial state: storage exists only in the browser, and
  // reading it during render would make the server and the client disagree about the page.
  useEffect(() => {
    const stored = loadDraft();
    if (stored && !isDraftEmpty(stored.draft)) {
      setDoc({ draft: stored.draft, undo: [] });
      setSelection({ topicId: stored.draft.topics[0]?.id ?? "", subtopicId: null });
      setRestored({ savedAt: stored.savedAt });
      setOrigin(stored.origin);
    }
    hydrated.current = true;
  }, []);

  useEffect(() => {
    if (!hydrated.current) return;
    const timer = setTimeout(() => {
      if (!dirty || isDraftEmpty(draft)) clearDraft();
      else saveDraft(draft, origin);
    }, 400);
    return () => clearTimeout(timer);
  }, [draft, dirty, origin]);

  useEffect(() => {
    onDirtyChangeRef.current?.(dirty);
  }, [dirty]);

  // Load what the page asks for: a blank draft, or a copy of a saved taxonomy. Everything that
  // belonged to the previous draft (selection, search, messages, undo history) goes with it.
  // biome-ignore lint/correctness/useExhaustiveDependencies: `importTaxonomy` changes every render; only a new source should reload.
  useEffect(() => {
    if (!source) return;
    setDoc({ draft: source.draft, undo: [] });
    setBaseline(draftSignature(source.draft));
    setOrigin(source.origin);
    setSelection({ topicId: source.draft.topics[0]?.id ?? "", subtopicId: null });
    setCollapsed(new Set());
    setQuery("");
    setProblem(null);
    setRestored(null);
    setSentDocument(null);
    importTaxonomy.reset();
    clearDraft();
  }, [source]);

  const requestFocus = useCallback((target: NonNullable<FocusRequest>["target"]) => {
    focusSerial.current += 1;
    setFocusRequest({ serial: focusSerial.current, target });
  }, []);

  useEffect(() => {
    if (!focusRequest) return;
    if (focusRequest.target === "tree") {
      treeRef.current?.querySelector<HTMLElement>('[aria-selected="true"]')?.focus();
    } else {
      document.getElementById(focusRequest.target.inputId)?.focus();
    }
  }, [focusRequest]);

  const select = useCallback(
    (next: Selection, focus: "tree" | "field") => {
      setSelection(next);
      if (focus === "tree") requestFocus("tree");
      else if (next.subtopicId) requestFocus({ inputId: `subtopic-name-${next.subtopicId}` });
      else requestFocus({ inputId: `topic-name-${next.topicId}` });
    },
    [requestFocus],
  );

  // ---- edits ----------------------------------------------------------------

  const update = (change: (draft: Draft) => Draft) => {
    setProblem(null);
    setDoc((current) => ({ ...current, draft: change(current.draft) }));
  };

  const renameTopic = (topicId: string, patch: { name?: string; description?: string }) =>
    update((d) => ({
      ...d,
      topics: d.topics.map((topic) => (topic.id === topicId ? { ...topic, ...patch } : topic)),
    }));

  const patchSubtopic = (
    topicId: string,
    subtopicId: string,
    patch: { name?: string; description?: string },
  ) =>
    update((d) => ({
      ...d,
      topics: d.topics.map((topic) =>
        topic.id === topicId
          ? {
              ...topic,
              subtopics: topic.subtopics.map((s) => (s.id === subtopicId ? { ...s, ...patch } : s)),
            }
          : topic,
      ),
    }));

  const addTopic = () => {
    const id = newId("topic");
    setQuery("");
    update((d) => ({
      ...d,
      topics: [...d.topics, { id, name: "", description: "", subtopics: [] }],
    }));
    select({ topicId: id, subtopicId: null }, "field");
  };

  const addSubtopic = (topicId: string) => {
    const id = newId("sub");
    setQuery("");
    update((d) => ({
      ...d,
      topics: d.topics.map((topic) =>
        topic.id === topicId
          ? { ...topic, subtopics: [...topic.subtopics, { id, name: "", description: "" }] }
          : topic,
      ),
    }));
    setCollapsed((current) => {
      const next = new Set(current);
      next.delete(topicId);
      return next;
    });
    select({ topicId, subtopicId: id }, "field");
  };

  const dismissToast = (removalId: string) => {
    const toastId = toastFor.current.get(removalId);
    if (toastId !== undefined) toast.dismiss(toastId);
    toastFor.current.delete(removalId);
  };

  /** Undo one specific removal. A no-op if it was already undone (its toast may still be on screen). */
  const undoRemoval = (removal: Removal) => {
    if (!undoRef.current.some((entry) => entry.id === removal.id)) return;
    dismissToast(removal.id);
    setDoc((current) => ({
      draft: restoreRemoval(current.draft, removal),
      undo: current.undo.filter((entry) => entry.id !== removal.id),
    }));
    if (removal.kind === "topic") {
      select({ topicId: removal.topic.id, subtopicId: null }, "tree");
    } else {
      setCollapsed((current) => {
        const next = new Set(current);
        next.delete(removal.topicId);
        return next;
      });
      select({ topicId: removal.topicId, subtopicId: removal.subtopic.id }, "tree");
    }
  };

  const undoLast = () => {
    const last = undoRef.current.at(-1);
    if (last) undoRemoval(last);
  };

  const remove = (topicId: string, subtopicId: string | null) => {
    const result = subtopicId
      ? removeSubtopic(draft, topicId, subtopicId)
      : removeTopic(draft, topicId);

    setDoc({ draft: result.draft, undo: [...doc.undo, result.removal].slice(-UNDO_DEPTH) });

    // Land on a neighbour that still exists.
    if (subtopicId) {
      const siblings = draft.topics.find((topic) => topic.id === topicId)?.subtopics ?? [];
      const at = siblings.findIndex((s) => s.id === subtopicId);
      const next = siblings[at + 1] ?? siblings[at - 1];
      select({ topicId, subtopicId: next?.id ?? null }, "tree");
    } else {
      const at = draft.topics.findIndex((topic) => topic.id === topicId);
      const next = draft.topics[at + 1] ?? draft.topics[at - 1];
      if (next) select({ topicId: next.id, subtopicId: null }, "tree");
    }

    const toastId = toast(describeRemoval(result.removal), {
      duration: UNDO_TOAST_MS,
      action: { label: "Undo", onClick: () => undoRemoval(result.removal) },
    });
    toastFor.current.set(result.removal.id, toastId);
  };

  // Ctrl/Cmd+Z and "/" — but never while typing, where Ctrl+Z belongs to the field.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea")) return;
      if ((event.ctrlKey || event.metaKey) && !event.shiftKey && event.key.toLowerCase() === "z") {
        event.preventDefault();
        undoLast();
      } else if (event.key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey) {
        event.preventDefault();
        searchRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

  // ---- save --------------------------------------------------------------------

  const taxonomyDocument = guide.data ? toTaxonomyDocument(draft, guide.data.schema_version) : null;

  const discardDraft = () => {
    setDoc({ draft: emptyDraft(), undo: [] });
    setBaseline(draftSignature(emptyDraft()));
    setSelection({ topicId: "", subtopicId: null });
    clearDraft();
    setRestored(null);
    setProblem(null);
    setOrigin(null);
  };

  const requestSave = () => {
    importTaxonomy.reset();
    const found = findProblem(draft);
    setProblem(found);
    if (found) {
      setQuery("");
      if (found.at === "label") {
        document.getElementById("version-label")?.focus();
      } else {
        const { topicId } = found.at;
        setCollapsed((current) => {
          const next = new Set(current);
          next.delete(topicId);
          return next;
        });
        select(found.at, "field");
      }
      return;
    }
    // A valid save becomes the live taxonomy at once (ADR-021), so say so first when there is one to replace.
    if (approved.data) setConfirmOpen(true);
    else void save();
  };

  const save = async () => {
    if (!taxonomyDocument) return;
    setSentDocument(taxonomyDocument);
    try {
      const detail = await importTaxonomy.mutateAsync({
        file: fileFromPastedJson(JSON.stringify(taxonomyDocument), MANUAL_TAXONOMY_FILENAME),
      });
      // Only now is the draft dropped: a refused save leaves it exactly as typed.
      clearDraft();
      toast.success(`Saved “${detail.version.label}”`, {
        description:
          `${pluralise(detail.topic_count, "topic")} and ` +
          `${pluralise(detail.subtopic_count, "subtopic")}. ` +
          "It is now the active taxonomy.",
      });
      setConfirmOpen(false);
      onSaved?.(detail);
    } catch {
      // Rendered from `importTaxonomy.error` with the backend's own wording; the draft is untouched.
      setConfirmOpen(false);
    }
  };

  // ---- outline keyboard navigation -------------------------------------------

  const visibleRows = useMemo<Selection[]>(
    () =>
      tree.flatMap(({ topic, subtopics }) => [
        { topicId: topic.id, subtopicId: null },
        ...(searching || !collapsed.has(topic.id)
          ? subtopics.map((s) => ({ topicId: topic.id, subtopicId: s.id }))
          : []),
      ]),
    [tree, collapsed, searching],
  );

  const onTreeKeyDown = (event: React.KeyboardEvent) => {
    const at = visibleRows.findIndex(
      (row) => row.topicId === selection.topicId && row.subtopicId === selection.subtopicId,
    );
    const go = (row: Selection | undefined) => {
      if (!row) return;
      event.preventDefault();
      select(row, "tree");
    };

    switch (event.key) {
      case "ArrowDown":
        return go(visibleRows[at + 1]);
      case "ArrowUp":
        return go(visibleRows[at - 1]);
      case "Home":
        return go(visibleRows[0]);
      case "End":
        return go(visibleRows.at(-1));
      case "ArrowLeft": {
        event.preventDefault();
        if (selection.subtopicId) return select({ ...selection, subtopicId: null }, "tree");
        if (!searching) setCollapsed((current) => new Set(current).add(selection.topicId));
        return;
      }
      case "ArrowRight": {
        if (selection.subtopicId) return;
        if (collapsed.has(selection.topicId) && !searching) {
          event.preventDefault();
          setCollapsed((current) => {
            const next = new Set(current);
            next.delete(selection.topicId);
            return next;
          });
          return;
        }
        // Expanded: step into the first subtopic, if the next row belongs to this topic.
        const next = visibleRows[at + 1];
        return go(next?.topicId === selection.topicId ? next : undefined);
      }
      case "Enter":
        if (selection.subtopicId) {
          event.preventDefault();
          requestFocus({ inputId: `subtopic-name-${selection.subtopicId}` });
        }
        return;
      case "Delete":
      case "Backspace":
        event.preventDefault();
        return remove(selection.topicId, selection.subtopicId);
    }
  };

  const topicIndex = draft.topics.findIndex((topic) => topic.id === selection.topicId);
  const lastRemoval = doc.undo.at(-1);

  return (
    <div className="@container flex h-full min-h-0 min-w-0 flex-col">
      <div className="border-b py-4 pr-14 pl-6">
        <p className="text-muted-foreground text-xs">
          {origin ? (
            <>
              Editing a copy of{" "}
              <span className="font-medium text-foreground">“{origin.label}”</span>. Saving creates
              a new version and leaves it unchanged.
            </>
          ) : (
            "New taxonomy"
          )}
        </p>
        <div className="mt-1 flex items-center gap-3">
          <Label htmlFor="version-label" className="sr-only">
            Taxonomy name
          </Label>
          <Input
            id="version-label"
            value={draft.label}
            maxLength={limits.label}
            placeholder="Taxonomy name, e.g. Introductory Python, Fall 2026"
            className="h-auto max-w-xl border-transparent bg-transparent px-1.5 py-0.5 font-heading font-semibold text-xl shadow-none hover:border-input focus-visible:bg-background md:text-xl"
            onChange={(event) => update((d) => ({ ...d, label: event.target.value }))}
          />
          <CharCount value={draft.label} max={limits.label} />
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-3 px-6 py-4">
        {restored ? (
          <Alert>
            <History />
            <AlertTitle>Unsaved draft restored</AlertTitle>
            <AlertDescription>
              This is the taxonomy you were building in this browser, last edited{" "}
              {formatTimestamp(restored.savedAt)}.
            </AlertDescription>
            <AlertAction className="flex gap-1">
              <Button variant="outline" size="xs" onClick={discardDraft}>
                Discard draft
              </Button>
              <Button variant="ghost" size="xs" onClick={() => setRestored(null)}>
                Keep editing
              </Button>
            </AlertAction>
          </Alert>
        ) : null}
        {problem ? (
          <Alert variant="destructive">
            <TriangleAlert />
            <AlertTitle>Not ready to save</AlertTitle>
            <AlertDescription>{problem.message}</AlertDescription>
          </Alert>
        ) : null}
        {importTaxonomy.error ? (
          <TaxonomyRefusalAlert
            error={importTaxonomy.error}
            doc={sentDocument}
            heading="This taxonomy was not saved. Please fix the following:"
          />
        ) : null}
        {guide.error ? <QueryError error={guide.error} /> : null}

        <div className="grid min-h-0 flex-1 @2xl:grid-cols-[minmax(17rem,22rem)_minmax(0,1fr)] @2xl:grid-rows-1 gap-4">
          {/* ---- outline ---- */}
          <Card className="min-h-0">
            <CardHeader>
              <CardTitle>Outline</CardTitle>
              <CardAction className="flex items-center gap-1">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={!lastRemoval}
                        onClick={undoLast}
                      >
                        <Undo2 />
                        Undo
                        {doc.undo.length > 0 ? (
                          <Badge variant="secondary" className="h-4 px-1.5 font-mono">
                            {doc.undo.length}
                          </Badge>
                        ) : null}
                      </Button>
                    </span>
                  </TooltipTrigger>
                  <TooltipContent>
                    {lastRemoval
                      ? `Put back: ${describeRemoval(lastRemoval).replace("Removed ", "")} (Ctrl+Z)`
                      : "Nothing to undo yet"}
                  </TooltipContent>
                </Tooltip>
                <Button variant="outline" size="sm" onClick={addTopic}>
                  <Plus />
                  Add topic
                </Button>
              </CardAction>
            </CardHeader>

            <CardContent className="flex min-h-0 flex-1 flex-col gap-2">
              <div className="relative">
                <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  ref={searchRef}
                  type="search"
                  value={query}
                  placeholder="Search topics and subtopics"
                  aria-label="Search the outline"
                  className="pr-8 pl-8 [&::-webkit-search-cancel-button]:hidden"
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Escape") setQuery("");
                    if ((event.key === "ArrowDown" || event.key === "Enter") && visibleRows[0]) {
                      event.preventDefault();
                      select(visibleRows[0], "tree");
                    }
                  }}
                />
                {query ? (
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    className="absolute top-1/2 right-1.5 -translate-y-1/2"
                    aria-label="Clear search"
                    title="Clear search"
                    onClick={() => {
                      setQuery("");
                      searchRef.current?.focus();
                    }}
                  >
                    <X />
                  </Button>
                ) : null}
              </div>
              <p className="min-h-4 text-muted-foreground text-xs" aria-live="polite">
                {searching
                  ? `${pluralise(matchCount, "match", "matches")} in ${pluralise(tree.length, "topic")}`
                  : "Search names and descriptions. Press / to focus."}
              </p>

              <div
                ref={treeRef}
                role="tree"
                aria-label="Taxonomy outline"
                tabIndex={-1}
                onKeyDown={onTreeKeyDown}
                className="-mx-1 @2xl:max-h-none max-h-[24rem] min-h-0 flex-1 overflow-y-auto px-1"
              >
                {tree.length === 0 ? (
                  <p className="py-6 text-center text-muted-foreground text-sm">
                    {searching
                      ? `Nothing matches “${query.trim()}”.`
                      : "No topics yet. Use “Add topic” to start."}
                  </p>
                ) : (
                  <ul className="space-y-0.5">
                    {tree.map(({ topic, subtopics }) => {
                      const open = searching || !collapsed.has(topic.id);
                      const topicSelected =
                        selection.topicId === topic.id && selection.subtopicId === null;
                      return (
                        <li key={topic.id} role="none">
                          {/* biome-ignore lint/a11y/useKeyWithClickEvents: the tree container handles the keys for every row (roving tabindex), so a per-row handler would fire twice. */}
                          <div
                            role="treeitem"
                            aria-level={1}
                            aria-expanded={open}
                            aria-selected={topicSelected}
                            tabIndex={topicSelected ? 0 : -1}
                            className={ROW}
                            onClick={() => select({ topicId: topic.id, subtopicId: null }, "tree")}
                          >
                            <button
                              type="button"
                              tabIndex={-1}
                              aria-label={open ? `Collapse ${topic.name}` : `Expand ${topic.name}`}
                              title={open ? `Collapse ${topic.name}` : `Expand ${topic.name}`}
                              className={cn(
                                "grid size-5 shrink-0 place-items-center rounded text-muted-foreground hover:bg-muted-foreground/15",
                                (topic.subtopics.length === 0 || searching) && "invisible",
                              )}
                              onClick={(event) => {
                                event.stopPropagation();
                                setCollapsed((current) => {
                                  const next = new Set(current);
                                  if (next.has(topic.id)) next.delete(topic.id);
                                  else next.add(topic.id);
                                  return next;
                                });
                              }}
                            >
                              {open ? (
                                <ChevronDown className="size-3.5" />
                              ) : (
                                <ChevronRight className="size-3.5" />
                              )}
                            </button>
                            <span className="min-w-0 flex-1 truncate font-medium">
                              <Highlight
                                text={topic.name}
                                query={query}
                                fallback="Untitled topic"
                              />
                            </span>
                            {matchedByDescriptionOnly(topic, query) ? (
                              <Badge variant="outline" className="h-4 px-1.5 font-mono">
                                desc
                              </Badge>
                            ) : null}
                            {topic.subtopics.length === 0 ? (
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <span
                                    className="size-2 shrink-0 rounded-full bg-(--warn-solid)"
                                    role="img"
                                    aria-label="Needs at least one subtopic"
                                  />
                                </TooltipTrigger>
                                <TooltipContent>
                                  A topic needs at least one subtopic.
                                </TooltipContent>
                              </Tooltip>
                            ) : null}
                            <Badge variant="secondary" className="h-4 px-1.5 font-mono">
                              {topic.subtopics.length}
                            </Badge>
                            <Button
                              variant="ghost"
                              size="icon-xs"
                              tabIndex={-1}
                              className={REMOVE}
                              aria-label={`Remove topic ${topic.name || "Untitled topic"}`}
                              title={`Remove topic ${topic.name || "Untitled topic"}`}
                              onClick={(event) => {
                                event.stopPropagation();
                                remove(topic.id, null);
                              }}
                            >
                              <X />
                            </Button>
                          </div>

                          {open ? (
                            <ul className="mt-0.5 ml-[1.35rem] space-y-0.5 border-l pl-1.5">
                              {subtopics.map((subtopic) => {
                                const subSelected =
                                  selection.topicId === topic.id &&
                                  selection.subtopicId === subtopic.id;
                                return (
                                  <li key={subtopic.id} role="none">
                                    {/* biome-ignore lint/a11y/useKeyWithClickEvents: keys are handled by the tree container, as for the topic row. */}
                                    <div
                                      role="treeitem"
                                      aria-level={2}
                                      aria-selected={subSelected}
                                      tabIndex={subSelected ? 0 : -1}
                                      className={ROW}
                                      onClick={() =>
                                        select(
                                          { topicId: topic.id, subtopicId: subtopic.id },
                                          "field",
                                        )
                                      }
                                    >
                                      <span className="mx-1.5 size-1.5 shrink-0 rounded-full bg-border group-aria-selected/row:bg-primary" />
                                      <span className="min-w-0 flex-1 truncate">
                                        <Highlight
                                          text={subtopic.name}
                                          query={query}
                                          fallback="Untitled subtopic"
                                        />
                                      </span>
                                      {matchedByDescriptionOnly(subtopic, query) ? (
                                        <Badge variant="outline" className="h-4 px-1.5 font-mono">
                                          desc
                                        </Badge>
                                      ) : null}
                                      <Button
                                        variant="ghost"
                                        size="icon-xs"
                                        tabIndex={-1}
                                        className={REMOVE}
                                        aria-label={`Remove subtopic ${subtopic.name || "Untitled subtopic"}`}
                                        title={`Remove subtopic ${subtopic.name || "Untitled subtopic"}`}
                                        onClick={(event) => {
                                          event.stopPropagation();
                                          remove(topic.id, subtopic.id);
                                        }}
                                      >
                                        <X />
                                      </Button>
                                    </div>
                                  </li>
                                );
                              })}
                              {searching ? null : (
                                <li role="none">
                                  <Button
                                    variant="ghost"
                                    size="xs"
                                    className="text-muted-foreground"
                                    onClick={() => addSubtopic(topic.id)}
                                  >
                                    <Plus />
                                    Add subtopic
                                  </Button>
                                </li>
                              )}
                            </ul>
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>

              <div className="flex gap-1 border-t pt-2">
                <Button variant="ghost" size="xs" onClick={() => setCollapsed(new Set())}>
                  Expand all
                </Button>
                <Button
                  variant="ghost"
                  size="xs"
                  onClick={() => {
                    setCollapsed(new Set(draft.topics.map((topic) => topic.id)));
                    setSelection((current) => ({ ...current, subtopicId: null }));
                  }}
                >
                  Collapse all
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* ---- detail ---- */}
          {activeTopic ? (
            <Card className="min-h-0">
              <CardHeader>
                <CardTitle>
                  Topic {topicIndex + 1} of {draft.topics.length}
                </CardTitle>
                <CardAction className="flex items-center gap-0.5">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Move topic up"
                    title="Move topic up"
                    disabled={topicIndex === 0}
                    onClick={() => update((d) => moveTopic(d, activeTopic.id, -1))}
                  >
                    <ArrowUp />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Move topic down"
                    title="Move topic down"
                    disabled={topicIndex === draft.topics.length - 1}
                    onClick={() => update((d) => moveTopic(d, activeTopic.id, 1))}
                  >
                    <ArrowDown />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="hover:text-destructive"
                    aria-label="Remove topic"
                    title="Remove topic"
                    onClick={() => remove(activeTopic.id, null)}
                  >
                    <Trash2 />
                  </Button>
                </CardAction>
              </CardHeader>

              <CardContent className="min-h-0 flex-1 space-y-5 overflow-y-auto">
                <nav className="flex flex-wrap items-center gap-1.5 text-muted-foreground text-xs">
                  <span>{draft.label || "Untitled"}</span>
                  <ChevronRight className="size-3" />
                  <span className={cn(!selection.subtopicId && "font-medium text-foreground")}>
                    {activeTopic.name || "Untitled topic"}
                  </span>
                  {selection.subtopicId ? (
                    <>
                      <ChevronRight className="size-3" />
                      <span className="font-medium text-foreground">
                        {activeTopic.subtopics.find((s) => s.id === selection.subtopicId)?.name ||
                          "Untitled subtopic"}
                      </span>
                    </>
                  ) : null}
                </nav>

                <div className="space-y-1.5">
                  <div className="flex items-baseline justify-between">
                    <Label htmlFor={`topic-name-${activeTopic.id}`}>Topic name</Label>
                    <CharCount value={activeTopic.name} max={limits.topicName} />
                  </div>
                  <Input
                    id={`topic-name-${activeTopic.id}`}
                    className="scroll-mb-24"
                    value={activeTopic.name}
                    maxLength={limits.topicName}
                    placeholder="e.g. Loops"
                    onChange={(event) => renameTopic(activeTopic.id, { name: event.target.value })}
                  />
                </div>

                <div className="space-y-1.5">
                  <div className="flex items-baseline justify-between">
                    <Label htmlFor={`topic-description-${activeTopic.id}`}>
                      Description{" "}
                      <span className="font-normal text-muted-foreground">(optional)</span>
                    </Label>
                    <CharCount value={activeTopic.description} max={limits.topicDescription} />
                  </div>
                  <Textarea
                    id={`topic-description-${activeTopic.id}`}
                    className="scroll-mb-24"
                    rows={2}
                    value={activeTopic.description}
                    maxLength={limits.topicDescription}
                    onChange={(event) =>
                      renameTopic(activeTopic.id, { description: event.target.value })
                    }
                  />
                </div>

                <div className="space-y-2">
                  <div className="flex items-baseline justify-between">
                    <Label>Subtopics in this topic</Label>
                    <span className="font-mono text-muted-foreground text-xs">
                      {activeTopic.subtopics.length}
                    </span>
                  </div>

                  <div className="overflow-hidden rounded-lg border">
                    {activeTopic.subtopics.length === 0 ? (
                      <p className="p-4 text-center text-muted-foreground text-sm">
                        This topic has no subtopics yet. A topic needs at least one.
                      </p>
                    ) : (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="w-[38%]">Name</TableHead>
                            <TableHead>Description</TableHead>
                            <TableHead className="w-24" />
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {activeTopic.subtopics.map((subtopic, index) => (
                            <TableRow
                              key={subtopic.id}
                              data-state={
                                selection.subtopicId === subtopic.id ? "selected" : undefined
                              }
                            >
                              <TableCell className="align-top">
                                <Input
                                  id={`subtopic-name-${subtopic.id}`}
                                  className="scroll-mb-24"
                                  aria-label={`Subtopic ${index + 1} name`}
                                  value={subtopic.name}
                                  maxLength={limits.subtopicName}
                                  placeholder="Subtopic name"
                                  onFocus={() =>
                                    setSelection({
                                      topicId: activeTopic.id,
                                      subtopicId: subtopic.id,
                                    })
                                  }
                                  onChange={(event) =>
                                    patchSubtopic(activeTopic.id, subtopic.id, {
                                      name: event.target.value,
                                    })
                                  }
                                />
                              </TableCell>
                              <TableCell className="align-top">
                                <Input
                                  aria-label={`Subtopic ${index + 1} description`}
                                  className="scroll-mb-24"
                                  value={subtopic.description}
                                  maxLength={limits.subtopicDescription}
                                  placeholder="Optional"
                                  onFocus={() =>
                                    setSelection({
                                      topicId: activeTopic.id,
                                      subtopicId: subtopic.id,
                                    })
                                  }
                                  onChange={(event) =>
                                    patchSubtopic(activeTopic.id, subtopic.id, {
                                      description: event.target.value,
                                    })
                                  }
                                />
                              </TableCell>
                              <TableCell className="text-right align-top">
                                <Button
                                  variant="ghost"
                                  size="icon-sm"
                                  aria-label={`Move subtopic ${index + 1} up`}
                                  title={`Move subtopic ${index + 1} up`}
                                  disabled={index === 0}
                                  onClick={() =>
                                    update((d) => moveSubtopic(d, activeTopic.id, subtopic.id, -1))
                                  }
                                >
                                  <ArrowUp />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="icon-sm"
                                  aria-label={`Move subtopic ${index + 1} down`}
                                  title={`Move subtopic ${index + 1} down`}
                                  disabled={index === activeTopic.subtopics.length - 1}
                                  onClick={() =>
                                    update((d) => moveSubtopic(d, activeTopic.id, subtopic.id, 1))
                                  }
                                >
                                  <ArrowDown />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="icon-sm"
                                  className="hover:text-destructive"
                                  aria-label={`Remove subtopic ${index + 1}`}
                                  title={`Remove subtopic ${index + 1}`}
                                  onClick={() => remove(activeTopic.id, subtopic.id)}
                                >
                                  <X />
                                </Button>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    )}
                  </div>

                  <Button variant="ghost" size="sm" onClick={() => addSubtopic(activeTopic.id)}>
                    <Plus />
                    Add subtopic
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="space-y-3 py-10 text-center text-muted-foreground text-sm">
                {draft.topics.length === 0 ? (
                  <>
                    <p>This taxonomy is empty. Add a topic to begin.</p>
                    <Button variant="outline" size="sm" onClick={addTopic}>
                      <Plus />
                      Add topic
                    </Button>
                  </>
                ) : (
                  <p>No topic selected. Pick one from the outline.</p>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      {/* Actions on the left, so the removal toast (bottom right) never covers Save. */}
      <div className="flex flex-wrap items-center gap-2 border-t bg-muted/30 px-6 py-3">
        <Button onClick={requestSave} disabled={!taxonomyDocument || importTaxonomy.isPending}>
          {importTaxonomy.isPending ? "Saving…" : origin ? "Save as new version" : "Save taxonomy"}
        </Button>
        <Button variant="ghost" disabled={!taxonomyDocument} onClick={() => setPreviewOpen(true)}>
          Preview document
        </Button>
        <p className="ml-2 text-muted-foreground text-sm">
          <span className="font-medium text-foreground">
            {pluralise(draft.topics.length, "topic")}
          </span>
          {" · "}
          <span className="font-medium text-foreground">
            {pluralise(countSubtopics(draft), "subtopic")}
          </span>
          {dirty ? " · unsaved changes are kept in this browser" : ""}
        </p>
      </div>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Make this the active taxonomy?</DialogTitle>
            <DialogDescription>
              Saving creates a new version and makes it the active taxonomy, the one that question
              generation and coverage use.
            </DialogDescription>
          </DialogHeader>
          {approved.data ? (
            <div className="space-y-2 text-sm">
              <p>
                <span className="font-medium">{approved.data.version.label}</span> (
                {pluralise(approved.data.topic_count, "topic")},{" "}
                {pluralise(approved.data.subtopic_count, "subtopic")}) is active now and will be
                replaced.
              </p>
              <p className="text-muted-foreground">
                Its questions and your students' progress stay with it. You can make it active again
                later from the versions list.
              </p>
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => void save()} disabled={importTaxonomy.isPending}>
              {importTaxonomy.isPending ? "Saving…" : "Save and make active"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Taxonomy document (JSON)</DialogTitle>
            <DialogDescription>
              This is exactly what will be saved. It is checked again when you save.
            </DialogDescription>
          </DialogHeader>
          <pre className="max-h-[24rem] overflow-auto rounded-lg border bg-muted/40 p-3 font-mono text-xs">
            {JSON.stringify(taxonomyDocument, null, 2)}
          </pre>
          <DialogFooter>
            <CopyButton text={JSON.stringify(taxonomyDocument, null, 2)} label="Copy JSON" />
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
