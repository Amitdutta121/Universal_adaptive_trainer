"use client";

/**
 * One curriculum version: its hierarchy, where it came from, and what removing it
 * would cost.
 *
 * The gate that shapes this page is ADR-021. A taxonomy a professor uploaded
 * carries no textbook evidence, no grouping rationale and no model metadata, so
 * the sections that would show those are **not rendered** rather than rendered
 * empty — a heading naming a property, above a body denying it, still frames the
 * version as a thing that could have had one.
 */

import { ArrowLeft, Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { PageHeader } from "@/components/page-header";
import { QueryError, TableSkeleton } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useCurriculumVersion, useCurriculumVersions } from "@/lib/api/queries";
import { formatTimestamp, pluralise } from "@/lib/display";
import {
  ItemRenameDialog,
  type RenameTarget,
} from "../../components/item-rename-dialog";
import { VersionDeleteDialog } from "../../components/version-delete-dialog";
import { VersionEditDialog } from "../../components/version-edit-dialog";
import {
  isTaxonomyUpload,
  STANDING_LABEL,
  STANDING_MEANING,
  STANDING_VARIANT,
  versionStanding,
} from "../../curriculum-display";
import { CurriculumTree } from "./components/curriculum-tree";
import { ProposalWarningList } from "./components/proposal-warning-list";
import { VersionProvenance } from "./components/version-provenance";

export function VersionDetailScreen({ versionId }: { versionId: number }) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [renaming, setRenaming] = useState<RenameTarget | null>(null);
  const { data, isPending, isError, error } = useCurriculumVersion(versionId);
  // `usage.is_approved` already answers this, but the list is cached alongside
  // and keeps the wording identical to the table the professor arrived from.
  const versions = useCurriculumVersions();

  if (isPending) {
    return (
      <>
        <PageHeader title="Curriculum version" />
        <TableSkeleton />
      </>
    );
  }

  if (isError) {
    return (
      <>
        <PageHeader title="Curriculum version" />
        <QueryError error={error} />
        <Link href="/curriculum" className="text-muted-foreground text-sm hover:underline">
          ← All curriculum versions
        </Link>
      </>
    );
  }

  const { version, topics, topic_count, subtopic_count, books, warnings } = data;
  const fromUpload = isTaxonomyUpload(version);
  const standing = versionStanding(
    version,
    data.usage.is_approved ? version.id : versions.data?.approved_version_id,
  );

  return (
    <>
      <PageHeader
        title={version.label}
        summary={[
          pluralise(topic_count, "topic"),
          pluralise(subtopic_count, "subtopic"),
          `created ${formatTimestamp(version.created_at)}`,
        ].join(" · ")}
        actions={
          <>
            <Badge variant={STANDING_VARIANT[standing]}>{STANDING_LABEL[standing]}</Badge>
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
              <Pencil />
              Rename
            </Button>
            <Button variant="outline" size="sm" onClick={() => setDeleting(true)}>
              <Trash2 />
              Delete
            </Button>
          </>
        }
      />

      <Link
        href="/curriculum"
        className="flex w-fit items-center gap-1 text-muted-foreground text-sm hover:underline"
      >
        <ArrowLeft className="size-3" />
        All curriculum versions
      </Link>

      {/* Legacy proposals only: an upload records no caveats about itself. */}
      {!fromUpload && warnings.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Caveats about this proposal</CardTitle>
          </CardHeader>
          <CardContent>
            <ProposalWarningList warnings={warnings} />
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>{fromUpload ? "Approved hierarchy" : "Proposed hierarchy"}</CardTitle>
          <CardDescription>
            {fromUpload
              ? "The fixed taxonomy you supplied. Display names can be edited here; the structure comes from the document."
              : "Click a subtopic to see its definition, the sections that support it, and why the differing book wordings behind it were merged."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <CurriculumTree topics={topics} onRename={setRenaming} />
        </CardContent>
      </Card>

      {/* Legacy proposals only: an upload is not derived from books at all. */}
      {!fromUpload ? (
        <Card>
          <CardHeader>
            <CardTitle>Derived from</CardTitle>
          </CardHeader>
          <CardContent>
            {books.length > 0 ? (
              <ul className="space-y-1 text-sm">
                {books.map((book) => (
                  <li key={book.id}>
                    <Link href={`/books/${book.id}`} className="hover:underline">
                      {book.title}
                    </Link>
                    {book.author ? (
                      <span className="ml-2 text-muted-foreground text-xs">{book.author}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground text-sm">
                The books this proposal was derived from are no longer available.
              </p>
            )}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>How this was produced</CardTitle>
          <CardDescription>{STANDING_MEANING[standing]}</CardDescription>
        </CardHeader>
        <CardContent>
          <VersionProvenance detail={data} />
        </CardContent>
      </Card>

      <VersionEditDialog
        key={`edit-${version.id}`}
        version={version}
        open={editing}
        onOpenChange={setEditing}
      />
      <VersionDeleteDialog
        key={`delete-${version.id}`}
        version={version}
        open={deleting}
        onOpenChange={setDeleting}
        onDeleted={() => router.push("/curriculum")}
      />
      <ItemRenameDialog
        key={`rename-${renaming?.kind ?? "none"}-${renaming?.id ?? "none"}`}
        target={renaming}
        open={renaming !== null}
        onOpenChange={(open) => !open && setRenaming(null)}
      />
    </>
  );
}
