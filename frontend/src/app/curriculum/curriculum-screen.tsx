"use client";

/**
 * The curriculum library: upload a taxonomy, and manage what is already uploaded.
 *
 * Server state — the list, the approved version, the guide, every mutation —
 * belongs to TanStack Query in `lib/api/queries.ts`. What this component owns is
 * what the browser owns: the search box, the status filter, and which row a
 * dialog is open for.
 *
 * The filter lives in the URL so a filtered view can be reloaded or shared. It
 * earns its place more here than on the books page: every upload supersedes the
 * one before it, so superseded rows accumulate while exactly one is ever
 * approved, and "show me the live one" is the common question.
 */

import { parseAsString, parseAsStringLiteral, useQueryState } from "nuqs";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { EmptyState, QueryError, TableSkeleton } from "@/components/query-state";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useActivateCurriculumVersion,
  useApprovedCurriculum,
  useCurriculumVersions,
  useTaxonomyDocumentGuide,
} from "@/lib/api/queries";
import type { CurriculumVersionSummary } from "@/lib/api/types";
import { pluralise } from "@/lib/display";
import { SECTIONS_BY_KEY } from "@/lib/navigation";
import { ApprovedVersionCard } from "./components/approved-version-card";
import { CurriculumVersionsTable } from "./components/curriculum-versions-table";
import { TaxonomyGuideCard } from "./components/taxonomy-guide-card";
import { TaxonomyUploadCard } from "./components/taxonomy-upload-card";
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
  live: "In use",
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

  const [editing, setEditing] = useState<CurriculumVersionSummary | null>(null);
  const [deleting, setDeleting] = useState<CurriculumVersionSummary | null>(null);

  const activateVersion = useActivateCurriculumVersion();
  const versions = useCurriculumVersions();
  const approved = useApprovedCurriculum();
  const guide = useTaxonomyDocumentGuide();

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

  return (
    <>
      <PageHeader title={section.label} summary={section.summary} />

      <TaxonomyUploadCard guide={guide.data} />

      <TaxonomyGuideCard guide={guide.data} isPending={guide.isPending} error={guide.error} />

      <ApprovedVersionCard
        approved={approved.data}
        isPending={approved.isPending}
        error={approved.error}
      />

      <Card>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value || null)}
              placeholder="Search label or source"
              className="max-w-xs"
              aria-label="Search curriculum versions"
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
          </div>

          {versions.isPending ? <TableSkeleton /> : null}
          {versions.isError ? <QueryError error={versions.error} /> : null}

          {versions.isSuccess && visible.length === 0 ? (
            total === 0 ? (
              <EmptyState
                title="No taxonomy has been uploaded yet"
                hint="Copy the prompt above, have an assistant turn your syllabus into a taxonomy document, then upload it."
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
              onActivate={handleActivate}
              onEdit={setEditing}
              onDelete={setDeleting}
            />
          ) : null}
        </CardContent>
      </Card>

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
