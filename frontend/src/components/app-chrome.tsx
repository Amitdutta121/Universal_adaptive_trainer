"use client";

import { Sparkles } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AppSidebar } from "@/components/app-sidebar";
import { AuthGate } from "@/components/auth-gate";
import { CourseGate } from "@/components/course-gate";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { VerifyEmailBanner } from "@/components/verify-email-banner";

function ProfessorChrome({
  children,
  isWideRoute,
}: {
  children: React.ReactNode;
  isWideRoute: boolean;
}) {
  return (
    <AuthGate>
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
      </SidebarProvider>
    </AuthGate>
  );
}

function StudentChrome({ children }: { children: React.ReactNode }) {
  return (
    <main className="student-shell min-h-screen">
      <div className="student-shell__backdrop" />
      <div className="student-shell__frame">
        <header className="student-shell__header">
          <Link href={"/students/join" as Route} className="student-shell__brand">
            <span className="student-shell__brand-mark">
              <Sparkles className="size-4" />
            </span>
            <span>
              <span className="student-shell__eyebrow">Adaptive Trainer</span>
              <span className="student-shell__title">Student Classroom</span>
            </span>
          </Link>
        </header>
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
  const isStudentRoute = pathname.startsWith("/students/join");
  // The login page and the other signed-out account screens (sign up, verify email,
  // forgot/reset password) render full-page (`AuthCard`) and must never sit behind
  // AuthGate itself, or a logged-out visitor could never reach them.
  const isSignedOutRoute = SIGNED_OUT_ROUTES.has(pathname);
  // A multi-column workspace, not a document — capping it to reading width
  // wastes a wide monitor instead of giving the PDF pane the room it needs.
  const isWideRoute = /^\/courses\/\d+\/questions\/generate\/single/.test(pathname);
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
    <StudentChrome>{children}</StudentChrome>
  ) : (
    <ProfessorChrome isWideRoute={isWideRoute}>{children}</ProfessorChrome>
  );
}
