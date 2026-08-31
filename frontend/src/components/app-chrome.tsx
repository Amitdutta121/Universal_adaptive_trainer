"use client";

import { Sparkles } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AppSidebar } from "@/components/app-sidebar";
import { AuthGate } from "@/components/auth-gate";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";

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
            {children}
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
          <Link href="/" className="student-shell__console-link">
            Instructor Studio
          </Link>
        </header>
        <div className="student-shell__content">{children}</div>
      </div>
    </main>
  );
}

export function AppChrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isStudentRoute = pathname.startsWith("/students/join");
  // The login page renders full-page (see login-screen.tsx) and must never sit
  // behind AuthGate itself, or a logged-out visitor could never reach it.
  const isLoginRoute = pathname === "/login";
  // A multi-column workspace, not a document — capping it to reading width
  // wastes a wide monitor instead of giving the PDF pane the room it needs.
  const isWideRoute = pathname.startsWith("/questions/generate/single");
  // Standalone design prototypes under /experiments bring their own full-page
  // shell and never call the API, so they skip both the console chrome and the
  // auth gate — the same treatment the login route gets.
  const isExperimentRoute = pathname.startsWith("/experiments");

  if (isLoginRoute || isExperimentRoute) return <>{children}</>;
  return isStudentRoute ? (
    <StudentChrome>{children}</StudentChrome>
  ) : (
    <ProfessorChrome isWideRoute={isWideRoute}>{children}</ProfessorChrome>
  );
}
