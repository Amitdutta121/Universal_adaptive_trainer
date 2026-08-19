/**
 * One subtopic's route shell.
 *
 * `params` is async in Next 16; the id is resolved here and the screen below is a
 * client component because this page renames the subtopic it is showing.
 */

import { notFound } from "next/navigation";
import { SubtopicDetailScreen } from "./subtopic-detail-screen";

export default async function CurriculumSubtopicPage(
  props: PageProps<"/curriculum/subtopics/[subtopic_id]">,
) {
  const { subtopic_id } = await props.params;
  const id = Number(subtopic_id);
  if (!Number.isInteger(id)) notFound();
  return <SubtopicDetailScreen subtopicId={id} />;
}
