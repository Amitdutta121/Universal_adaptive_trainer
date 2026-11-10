"use client";

import { usePathname } from "next/navigation";
import { AgentProvider, AgentSidebar } from "@/components/agent/agent-panel";
import { AppSidebar } from "@/components/app-sidebar";
import { AuthGate } from "@/components/auth-gate";
import { CourseGate } from "@/components/course-gate";
import { StudentBrand } from "@/components/student-brand";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { VerifyEmailBanner } from "@/components/verify-email-banner";
import { courseIdFromPath } from "@/lib/course";
import { isStudentPath } from "@/lib/navigation";

function ProfessorChrome({
  children,
  isWideRoute,
}: {
  children: React.ReactNode;
  isWideRoute: boolean;
}) {
  // The agent works inside one course, so it exists only on course pages. Its side panel is
  // left out on the assistant page, which shows the same conversation full-page.
  const pathname = usePathname();
  const courseId = courseIdFromPath(pathname);
  const onAssistantPage = ASSISTANT_ROUTE.test(pathname);
  const chrome = (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="app-inset min-w-0">
        {/* `min-w-0`: without it this flex child refuses to shrink below the
              width of its widest content, and a long code listing would push
              the whole page into horizontal scroll instead of scrolling itself.
              `isWideRoute` drops the usual reading-width cap for screens built
              as a multi-column workspace rather than a document, so they use
              the full window on a wide monitor instead of leaving it blank. */}
        <div
          className={`app-shell mx-auto flex w-full min-w-0 flex-col gap-6 p-6 ${
            isWideRoute ? "h-[100dvh] overflow-hidden" : "max-w-7xl"
          }`}
        >
          <VerifyEmailBanner />
          <CourseGate>{children}</CourseGate>
        </div>
      </SidebarInset>
      {courseId !== null && !onAssistantPage ? <AgentSidebar /> : null}
    </SidebarProvider>
  );
  return (
    <AuthGate>
      {courseId !== null ? <AgentProvider courseId={courseId}>{chrome}</AgentProvider> : chrome}
    </AuthGate>
  );
}

/** The course assistant's own page: full height, with no side panel of its own. */
const ASSISTANT_ROUTE = /^\/courses\/\d+\/assistant(\/|$)/;

function StudentChrome({ children, wide }: { children: React.ReactNode; wide: boolean }) {
  return (
    <main className="student-shell min-h-screen">
      <div className="student-shell__backdrop" />
      <div
        className={
          wide ? "student-shell__frame student-shell__frame--wide" : "student-shell__frame"
        }
      >
        {/* The session screen puts the brand beside its progress card itself. */}
        {wide ? null : <StudentBrand />}
        <div className="student-shell__content">{children}</div>
      </div>
    </main>
  );
}

const SIGNED_OUT_ROUTES = new Set([
  "/login",
  "/register",
  "/verify",
  "/forgot-password",
  "/reset-password",
]);

export function AppChrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isStudentRoute = isStudentPath(pathname);
  // A running session puts the tutorial and the question side by side, which
  // needs more than the join form's width.
  const isStudentSession = pathname.startsWith("/students/join/session/");
  // The login page and the other signed-out account screens (sign up, verify email,
  // forgot/reset password) render full-page (`AuthCard`) and must never sit behind
  // AuthGate itself, or a logged-out visitor could never reach them.
  const isSignedOutRoute = SIGNED_OUT_ROUTES.has(pathname);
  // A multi-column workspace, not a document — capping it to reading width
  // wastes a wide monitor instead of giving the PDF pane the room it needs.
  const isWideRoute =
    /^\/courses\/\d+\/questions\/generate\/single/.test(pathname) || ASSISTANT_ROUTE.test(pathname);
  // The course list is where a professor lands after login, before any course is
  // open, so there is no course navigation to show yet: signed-in, no sidebar.
  const isCoursePicker = pathname === "/courses";
  // Standalone design prototypes under /experiments bring their own full-page
  // shell and never call the API, so they skip both the console chrome and the
  // auth gate — the same treatment the login route gets.
  const isExperimentRoute = pathname.startsWith("/experiments");
  // The landing page at the bare root is the first thing a new install shows,
  // before any account or backend exists, so it must be reachable logged out.
  const isLandingRoute = pathname === "/";

  if (isSignedOutRoute || isExperimentRoute || isLandingRoute) return <>{children}</>;
  if (isCoursePicker) return <AuthGate>{children}</AuthGate>;
  return isStudentRoute ? (
    <StudentChrome wide={isStudentSession}>{children}</StudentChrome>
  ) : (
    <ProfessorChrome isWideRoute={isWideRoute}>{children}</ProfessorChrome>
  );
}
