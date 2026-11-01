"use client";

import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
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
} from "@/lib/api/queries";
import { CourseLink } from "@/components/course-link";

export function TaxonomySelector() {
  const versions = useCurriculumVersions();
  const approved = useApprovedCurriculum();
  const activateVersion = useActivateCurriculumVersion();

  const activeVersionId = approved.data?.version.id ?? versions.data?.approved_version_id ?? null;
  const approvedVersions =
    versions.data?.versions.filter((version) => version.status === "approved") ?? [];

  const disabled =
    versions.isPending ||
    approved.isPending ||
    activateVersion.isPending ||
    approvedVersions.length === 0;

  async function handleChange(value: string) {
    const versionId = Number(value);
    if (!Number.isFinite(versionId) || versionId === activeVersionId) return;
    try {
      const activated = await activateVersion.mutateAsync(versionId);
      toast.success(`Now working in "${activated.version.label}"`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not switch taxonomy.";
      toast.error("Could not switch taxonomy", { description: message });
    }
  }

  return (
    <div className="flex min-w-[18rem] items-center gap-3 rounded-2xl border border-border/70 bg-background/78 px-3 py-2 shadow-[0_10px_28px_-24px_rgba(19,26,28,0.55)] backdrop-blur">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[0.62rem] text-muted-foreground uppercase tracking-[0.16em]">
            Taxonomy
          </span>
          {activeVersionId ? (
            <Badge variant="outline" className="h-5 rounded-full px-2 font-mono text-[0.6rem]">
              v{activeVersionId}
            </Badge>
          ) : null}
        </div>
        {approvedVersions.length > 0 ? (
          <Select
            value={activeVersionId ? String(activeVersionId) : undefined}
            disabled={disabled}
            onValueChange={(value) => void handleChange(value)}
          >
            <SelectTrigger
              size="sm"
              className="mt-1 h-8 border-0 bg-transparent px-0 shadow-none hover:bg-transparent focus-visible:ring-0"
              aria-label="Taxonomy"
            >
              <SelectValue placeholder="Select taxonomy" />
            </SelectTrigger>
            <SelectContent>
              {approvedVersions.map((version) => (
                <SelectItem key={version.id} value={String(version.id)}>
                  {/* Two taxonomies may share a name; the version number tells them apart. */}
                  {version.label}{" "}
                  <span className="font-mono text-muted-foreground text-xs">v{version.id}</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <p className="mt-1 text-muted-foreground text-sm">
            No taxonomy yet.{" "}
            <CourseLink href="/curriculum" className="underline underline-offset-4">
              Create one
            </CourseLink>
            .
          </p>
        )}
      </div>
    </div>
  );
}
