"use client";

/**
 * How a version was produced.
 *
 * The one card that renders in both modes with entirely different bodies. For an
 * uploaded taxonomy it says so in a line, and then states what actually stands
 * behind the version: a validator, not a model. That sentence is the honest
 * replacement for the extraction-metadata table — an upload has no model
 * metadata, and rendering the table's headings with nothing under them would
 * imply it does (ADR-021).
 *
 * Client only for `formatTimestamp`, which must not run on the server.
 */

import type { CurriculumVersionDetail } from "@/lib/api/types";
import { formatTimestamp } from "@/lib/display";
import { isTaxonomyUpload } from "../../../curriculum-display";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap justify-between gap-2 border-b py-2 text-sm last:border-b-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}

export function VersionProvenance({ detail }: { detail: CurriculumVersionDetail }) {
  const { version, extraction_metadata } = detail;

  if (isTaxonomyUpload(version)) {
    return (
      <div className="space-y-2 text-sm">
        <p>Uploaded fixed taxonomy, {formatTimestamp(version.created_at)}.</p>
        <p className="text-muted-foreground">
          Validation is strict and total: unknown fields, duplicate names and empty topic or
          subtopic lists are refused before anything is stored. The uploaded file is not retained.
        </p>
      </div>
    );
  }

  if (!extraction_metadata) {
    return <p className="text-muted-foreground text-sm">This version records no metadata.</p>;
  }

  return (
    <dl>
      <Row label="Model">{extraction_metadata.generated_by}</Row>
      <Row label="Section analysis">{extraction_metadata.stage_a_version}</Row>
      <Row label="Cross-book normalization">{extraction_metadata.stage_b_version}</Row>
      <Row label="Books analysed">{extraction_metadata.books_analysed}</Row>
      <Row label="Sections analysed">{extraction_metadata.sections_analysed}</Row>
      {extraction_metadata.sections_skipped ? (
        <Row label="Sections not analysed">{extraction_metadata.sections_skipped}</Row>
      ) : null}
      <Row label="Candidate concepts found">{extraction_metadata.candidates_extracted}</Row>
      <Row label="Groups returned">{extraction_metadata.groups_returned}</Row>
    </dl>
  );
}
