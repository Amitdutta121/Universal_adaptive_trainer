import { redirect } from "next/navigation";
import { coursePath } from "@/lib/course";

export default async function FeedbackPage(props: PageProps<"/courses/[courseId]/feedback">) {
  const { courseId } = await props.params;
  redirect(coursePath(courseId, "/review"));
}
