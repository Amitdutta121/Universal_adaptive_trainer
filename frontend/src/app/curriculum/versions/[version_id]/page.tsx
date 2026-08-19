/**
 * One curriculum version's route shell.
 *
 * `params` is async in Next 16; the id is resolved here and the screen below is a
 * client component because this page renames and deletes what it is showing.
 */

import { notFound } from "next/navigation";
import { VersionDetailScreen } from "./version-detail-screen";

export default async function CurriculumVersionPage(
  props: PageProps<"/curriculum/versions/[version_id]">,
) {
  const { version_id } = await props.params;
  const id = Number(version_id);
  if (!Number.isInteger(id)) notFound();
  return <VersionDetailScreen versionId={id} />;
}
