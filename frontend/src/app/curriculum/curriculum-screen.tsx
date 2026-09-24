"use client";

/**
 * The curriculum library, as two panes. On the left, the saved taxonomies; on the right, the
 * builder. Choosing a saved taxonomy opens a copy of it in the builder, and saving from there
 * creates a new version — the one that was opened is never changed (ADR-021/046). "New" starts a
 * blank one, and importing a finished document is a modal opened from the header.
 *
 * Server state — the list, the approved version, every mutation —
 * belongs to TanStack Query in `lib/api/queries.ts`. What this component owns is
 * what the browser owns: the search box, the status filter, which row is open in the builder,
 * and which row a dialog is open for.
 *
 * The filter lives in the URL so a filtered view can be reloaded or shared. It
 * earns its place more here than on the books page: every upload supersedes the
 * one before it, so superseded rows accumulate while exactly one is ever
 * approved, and "show me the live one" is the common question.
 */

import { useQueryClient } from "@tanstack/react-query";
import { Plus, Upload } from "lucide-react";
import { parseAsString, parseAsStringLiteral, useQueryState } from "nuqs";
import { useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { EmptyState, QueryError, TableSkeleton } from "@/components/query-state";
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
import type { CurriculumVersionDetail, CurriculumVersionSummary } from "@/lib/api/types";
import { pluralise } from "@/lib/display";
import { SECTIONS_BY_KEY } from "@/lib/navigation";
import { type BuilderSource, TaxonomyBuilder } from "./builder/taxonomy-builder";
import { copyLabel, draftFromVersion, emptyDraft } from "./builder/taxonomy-draft";
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

export function CurriculumScreen() {
  const [standing, setStanding] = useQueryState(
    "standing",
    parseAsStringLiteral(STANDING_FILTERS).withDefault("all"),
  );
  const [search, setSearch] = useQueryState("q", parseAsString.withDefault(""));
  const [importOpen, setImportOpen] = useState(false);

  // Which saved taxonomy the builder holds a copy of, what to load into it next, and whether it has
  // changes that loading something else would throw away.
  const client = useQueryClient();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [openingId, setOpeningId] = useState<number | null>(null);
  const [source, setSource] = useState<BuilderSource | null>(null);
  const [dirty, setDirty] = useState(false);
  /** Set while the professor is being asked whether to discard unsaved changes. `undefined` = not asking. */
  const [replacing, setReplacing] = useState<CurriculumVersionSummary | null | undefined>(
    undefined,
  );
  const opened = useRef(0);

  const [editing, setEditing] = useState<CurriculumVersionSummary | null>(null);
  const [deleting, setDeleting] = useState<CurriculumVersionSummary | null>(null);

  const activateVersion = useActivateCurriculumVersion();
  const versions = useCurriculumVersions();
  const approved = useApprovedCurriculum();

  const approvedVersionId = versions.data?.approved_version_id;

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

  /** Put a copy of `version` (or a blank taxonomy) in the builder. */
  async function open(version: CurriculumVersionSummary | null) {
    if (version === null) {
      setSelectedId(null);
      setSource({ origin: null, draft: emptyDraft() });
      return;
    }
    const attempt = ++opened.current;
    setOpeningId(version.id);
    try {
      // Always read it fresh: the list may be older than the taxonomy's last rename. No retries: this
      // answers a click, so a failure should be said now, and clicking again is the retry.
      const detail = await client.fetchQuery({
        ...curriculumVersionQuery(version.id),
        staleTime: 0,
        retry: false,
      });
      if (attempt !== opened.current) return; // a later click superseded this one
      setSelectedId(version.id);
      setSource({
        origin: { id: version.id, label: detail.version.label },
        draft: draftFromVersion(copyLabel(detail.version.label), detail.topics),
      });
    } catch {
      toast.error(`Could not open “${version.label}”`, {
        description: "The taxonomy could not be loaded. Try again.",
      });
    } finally {
      if (attempt === opened.current) setOpeningId(null);
    }
  }

  /** Ask before replacing a draft that has unsaved changes; otherwise just open it. */
  function requestOpen(version: CurriculumVersionSummary | null) {
    if (version !== null && version.id === selectedId && !dirty) return;
    if (dirty) setReplacing(version);
    else void open(version);
  }

  /** A save creates a version; show it, as saved, in the builder. */
  function handleSaved(detail: CurriculumVersionDetail) {
    opened.current += 1;
    setSelectedId(detail.version.id);
    setSource({
      origin: { id: detail.version.id, label: detail.version.label },
      draft: draftFromVersion(detail.version.label, detail.topics),
    });
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

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(19rem,24rem)_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <CardTitle>Taxonomies</CardTitle>
            <CardAction>
              <Button variant="outline" size="sm" onClick={() => requestOpen(null)}>
                <Plus />
                New
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent className="space-y-3">
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value || null)}
              placeholder="Search by name"
              aria-label="Search taxonomies by name"
            />
            <div className="flex items-center gap-2">
              <Select
                value={standing}
                onValueChange={(value) =>
                  setStanding(value === "all" ? null : (value as (typeof STANDING_FILTERS)[number]))
                }
              >
                <SelectTrigger className="w-40" aria-label="Filter by standing">
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
            </div>

            {versions.isPending ? <TableSkeleton /> : null}
            {versions.isError ? <QueryError error={versions.error} /> : null}

            {versions.isSuccess && visible.length === 0 ? (
              total === 0 ? (
                <EmptyState
                  title="No taxonomy has been saved yet"
                  hint="Build one on the right, or use Import if you already have a taxonomy document."
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
                selectedId={selectedId}
                openingId={openingId}
                onSelect={requestOpen}
                onActivate={handleActivate}
                onEdit={setEditing}
                onDelete={setDeleting}
              />
            ) : null}
          </CardContent>
        </Card>

        <TaxonomyBuilder
          source={source}
          onDirtyChange={setDirty}
          onOriginChange={(origin) => setSelectedId(origin?.id ?? null)}
          onSaved={handleSaved}
        />
      </div>

      <TaxonomyImportDialog open={importOpen} onOpenChange={setImportOpen} />

      <Dialog
        open={replacing !== undefined}
        onOpenChange={(open) => !open && setReplacing(undefined)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Replace what you are working on?</DialogTitle>
            <DialogDescription>
              {replacing
                ? `Opening “${replacing.label}” replaces the taxonomy in the editor, and it has changes that are not saved.`
                : "Starting a new taxonomy replaces the one in the editor, and it has changes that are not saved."}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReplacing(undefined)}>
              Keep editing
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                const target = replacing ?? null;
                setReplacing(undefined);
                void open(target);
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
