"use client";

/**
 * The curriculum library. The table of saved taxonomies is the page; everything that changes a
 * taxonomy happens in one big modal opened from it.
 *
 * Choosing a row (or its Preview button) opens a copy of that taxonomy in the builder modal, and
 * saving from there creates a new version: the one that was opened is never changed (ADR-021/046).
 * "New taxonomy" opens the same modal blank. Importing a finished document is a smaller modal
 * opened from the header.
 *
 * Opening a row never asks anything and never touches work left unsaved elsewhere: each taxonomy
 * has its own slot in browser storage, and what is kept there is offered back on the page.
 *
 * Server state — the list, the approved version, every mutation — belongs to TanStack Query in
 * `lib/api/queries.ts`. What this component owns is what the browser owns: the search box, the
 * status filter, whether the builder is open and whether it holds changes that closing would throw
 * away, and which row a dialog is open for.
 *
 * The filter lives in the URL so a filtered view can be reloaded or shared. It earns its place
 * more here than on the books page: every upload supersedes the one before it, so superseded rows
 * accumulate while exactly one is ever approved, and "show me the live one" is the common question.
 */

import { useQueryClient } from "@tanstack/react-query";
import { History, Plus, Upload } from "lucide-react";
import { parseAsString, parseAsStringLiteral, useQueryState } from "nuqs";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { EmptyState, QueryError, TableSkeleton } from "@/components/query-state";
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  curriculumVersionQuery,
  useActivateCurriculumVersion,
  useApprovedCurriculum,
  useCurriculumVersions,
} from "@/lib/api/queries";
import type { CurriculumVersionSummary } from "@/lib/api/types";
import { formatTimestamp, pluralise } from "@/lib/display";
import { SECTIONS_BY_KEY } from "@/lib/navigation";
import {
  type BuilderSource,
  TaxonomyBuilder,
  type TaxonomyBuilderHandle,
} from "./builder/taxonomy-builder";
import { draftFromVersion, emptyDraft } from "./builder/taxonomy-draft";
import { clearDraft, loadDrafts, type SavedDraft } from "./builder/taxonomy-draft-storage";
import { ApprovedVersionCard } from "./components/approved-version-card";
import { CurriculumVersionsTable } from "./components/curriculum-versions-table";
import { TaxonomyImportDialog } from "./components/taxonomy-import-dialog";
import { VersionDeleteDialog } from "./components/version-delete-dialog";
import { VersionEditDialog } from "./components/version-edit-dialog";
import { generatedByLabel, versionStanding } from "./curriculum-display";

/**
 * The filter is over *standing*, not over the raw status column.
 *
 * Every upload is written `approved` and nothing ever supersedes it, so filtering
 * on the status would put every row in one bucket and answer the wrong question.
 * What a professor wants is "which one is live" versus "which are history".
 */
const STANDING_FILTERS = ["all", "live", "replaced", "proposed", "under_review"] as const;

const STANDING_FILTER_LABEL: Record<(typeof STANDING_FILTERS)[number], string> = {
  all: "All versions",
  live: "Active",
  replaced: "Replaced",
  proposed: "Proposed",
  under_review: "Under review",
};

function matches(version: CurriculumVersionSummary, search: string): boolean {
  const needle = search.trim().toLowerCase();
  if (!needle) return true;
  return [version.label, generatedByLabel(version)].some((value) =>
    value.toLowerCase().includes(needle),
  );
}

/** What is being opened in the builder: a saved taxonomy, or (`null`) a blank one. */
type OpenTarget = CurriculumVersionSummary | null;

export function CurriculumScreen() {
  const [standing, setStanding] = useQueryState(
    "standing",
    parseAsStringLiteral(STANDING_FILTERS).withDefault("all"),
  );
  const [search, setSearch] = useQueryState("q", parseAsString.withDefault(""));
  const [importOpen, setImportOpen] = useState(false);

  // The builder modal. `editor` is what it was opened with (`null` = closed); a `source` of `null`
  // inside it means "pick up the unsaved draft kept in this browser".
  const client = useQueryClient();
  const [editor, setEditor] = useState<{ source: BuilderSource | null } | null>(null);
  const [dirty, setDirty] = useState(false);
  const [openingId, setOpeningId] = useState<number | null>(null);
  const [discarding, setDiscarding] = useState(false);
  /** The unsaved taxonomies kept in this browser, each in its own slot. */
  const [drafts, setDrafts] = useState<SavedDraft[]>([]);
  const builder = useRef<TaxonomyBuilderHandle>(null);
  const opened = useRef(0);

  const [editing, setEditing] = useState<CurriculumVersionSummary | null>(null);
  const [deleting, setDeleting] = useState<CurriculumVersionSummary | null>(null);

  const activateVersion = useActivateCurriculumVersion();
  const versions = useCurriculumVersions();
  const approved = useApprovedCurriculum();

  const approvedVersionId = versions.data?.approved_version_id;

  // Browser-only, so read after mount rather than during render.
  useEffect(() => {
    setDrafts(loadDrafts());
  }, []);

  const visible = useMemo(() => {
    const all = versions.data?.versions ?? [];
    return all.filter(
      (version) =>
        (standing === "all" || versionStanding(version, approvedVersionId) === standing) &&
        matches(version, search),
    );
  }, [versions.data, approvedVersionId, standing, search]);

  const section = SECTIONS_BY_KEY.curriculum;
  const total = versions.data?.total ?? 0;

  async function handleActivate(version: CurriculumVersionSummary) {
    try {
      const activated = await activateVersion.mutateAsync(version.id);
      toast.success(`Active taxonomy is now "${activated.version.label}"`);
    } catch {
      // Rendered through the affected queries on refetch or by later retry.
    }
  }

  /** Open the builder on a copy of `target`, or on a blank taxonomy. */
  async function open(target: OpenTarget) {
    if (target === null) {
      opened.current += 1;
      setEditor({ source: { origin: null, draft: emptyDraft() } });
      return;
    }
    const attempt = ++opened.current;
    setOpeningId(target.id);
    try {
      // Always read it fresh: the list may be older than the taxonomy's last rename. No retries:
      // this answers a click, so a failure should be said now, and clicking again is the retry.
      const detail = await client.fetchQuery({
        ...curriculumVersionQuery(target.id),
        staleTime: 0,
        retry: false,
      });
      if (attempt !== opened.current) return; // a later click superseded this one
      setEditor({
        source: {
          origin: { id: target.id, label: detail.version.label },
          draft: draftFromVersion(detail.version.label, detail.topics),
        },
      });
    } catch {
      toast.error(`Could not open “${target.label}”`, {
        description: "The taxonomy could not be loaded. Try again.",
      });
    } finally {
      if (attempt === opened.current) setOpeningId(null);
    }
  }

  function closeEditor() {
    opened.current += 1;
    setEditor(null);
    setDirty(false);
    setDiscarding(false);
    setDrafts(loadDrafts());
  }

  /** Closing with unsaved changes asks; the changes are dropped only if the professor says so. */
  function requestClose() {
    if (dirty) setDiscarding(true);
    else closeEditor();
  }

  return (
    <>
      <PageHeader
        title={section.label}
        summary={section.summary}
        actions={
          <Button variant="outline" onClick={() => setImportOpen(true)}>
            <Upload />
            Import
          </Button>
        }
      />

      <ApprovedVersionCard
        approved={approved.data}
        isPending={approved.isPending}
        error={approved.error}
      />

      {editor
        ? null
        : drafts.map((draft) => (
            <Alert key={draft.key}>
              <History />
              <AlertTitle>Unsaved taxonomy: “{draft.draft.label || "Untitled"}”</AlertTitle>
              <AlertDescription>
                {draft.origin
                  ? `Changes to “${draft.origin.label}” you were making`
                  : "A taxonomy you were building"}
                , last edited {formatTimestamp(draft.savedAt)}.
              </AlertDescription>
              <AlertAction className="flex gap-1">
                <Button
                  size="xs"
                  onClick={() =>
                    setEditor({
                      source: {
                        origin: draft.origin,
                        draft: draft.draft,
                        restoredAt: draft.savedAt,
                      },
                    })
                  }
                >
                  Continue editing
                </Button>
                <Button
                  variant="outline"
                  size="xs"
                  onClick={() => {
                    clearDraft(draft.origin);
                    setDrafts(loadDrafts());
                  }}
                >
                  Discard
                </Button>
              </AlertAction>
            </Alert>
          ))}

      <Card>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value || null)}
              placeholder="Search by name"
              className="max-w-xs"
              aria-label="Search taxonomies by name"
            />
            <Select
              value={standing}
              onValueChange={(value) =>
                setStanding(value === "all" ? null : (value as (typeof STANDING_FILTERS)[number]))
              }
            >
              <SelectTrigger className="w-44" aria-label="Filter by standing">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {STANDING_FILTERS.map((value) => (
                  <SelectItem key={value} value={value}>
                    {STANDING_FILTER_LABEL[value]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="ml-auto text-muted-foreground text-sm">
              {visible.length === total
                ? pluralise(total, "version")
                : `${visible.length} of ${pluralise(total, "version")}`}
            </p>
            <Button onClick={() => void open(null)}>
              <Plus />
              New taxonomy
            </Button>
          </div>

          {versions.isPending ? <TableSkeleton /> : null}
          {versions.isError ? <QueryError error={versions.error} /> : null}

          {versions.isSuccess && visible.length === 0 ? (
            total === 0 ? (
              <EmptyState
                title="No taxonomy has been saved yet"
                hint="Use New taxonomy to build one, or Import if you already have a taxonomy document."
              />
            ) : (
              <EmptyState
                title="No version matches this filter"
                hint="Clear the search or choose a different standing."
              />
            )
          ) : null}

          {visible.length > 0 ? (
            <CurriculumVersionsTable
              versions={visible}
              approvedVersionId={approvedVersionId}
              activatingVersionId={activateVersion.isPending ? activateVersion.variables : null}
              openingId={openingId}
              onOpen={open}
              onActivate={handleActivate}
              onEdit={setEditing}
              onDelete={setDeleting}
            />
          ) : null}
        </CardContent>
      </Card>

      <TaxonomyImportDialog open={importOpen} onOpenChange={setImportOpen} />

      {/* The builder: a big modal, almost the whole screen. */}
      <Dialog open={editor !== null} onOpenChange={(open) => !open && requestClose()}>
        <DialogContent
          className="flex h-[92vh] w-[96vw] max-w-none flex-col gap-0 overflow-hidden p-0 sm:max-w-[min(96vw,1600px)]"
          // Toasts sit outside the modal; pressing Undo on one must not read as "click away".
          onPointerDownOutside={(event) => {
            if ((event.target as HTMLElement | null)?.closest("[data-sonner-toast]")) {
              event.preventDefault();
            }
          }}
          // Escape in the outline's search box clears the search; it must not also close the builder.
          onEscapeKeyDown={(event) => {
            if ((event.target as HTMLElement | null)?.closest("input[type=search]")) {
              event.preventDefault();
            }
          }}
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            document.getElementById("version-label")?.focus();
          }}
        >
          <DialogHeader className="sr-only">
            <DialogTitle>Taxonomy builder</DialogTitle>
            <DialogDescription>
              Build a topic and subtopic taxonomy, or edit a copy of a saved one.
            </DialogDescription>
          </DialogHeader>
          <TaxonomyBuilder
            ref={builder}
            source={editor?.source ?? null}
            onDirtyChange={setDirty}
            onSaved={closeEditor}
          />
        </DialogContent>
      </Dialog>

      <Dialog open={discarding} onOpenChange={setDiscarding}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Discard your changes?</DialogTitle>
            <DialogDescription>
              This taxonomy has changes that are not saved. Closing throws them away.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDiscarding(false)}>
              Keep editing
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                builder.current?.discardStored();
                closeEditor();
              }}
            >
              Discard changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Keyed so the form remounts with the values of whichever row was chosen. */}
      <VersionEditDialog
        key={`edit-${editing?.id ?? "none"}`}
        version={editing}
        open={editing !== null}
        onOpenChange={(open) => !open && setEditing(null)}
      />
      <VersionDeleteDialog
        key={`delete-${deleting?.id ?? "none"}`}
        version={deleting}
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
      />
    </>
  );
}
