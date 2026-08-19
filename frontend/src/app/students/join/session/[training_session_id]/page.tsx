import { StudentSessionScreen } from "./student-session-screen";

export default async function StudentSessionPage({
  params,
}: PageProps<"/students/join/session/[training_session_id]">) {
  const resolved = await params;
  return <StudentSessionScreen trainingSessionId={Number(resolved.training_session_id)} />;
}
