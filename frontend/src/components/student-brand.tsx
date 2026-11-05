import type { Route } from "next";
import Link from "next/link";
import { LogoGlyph } from "@/components/brand-logo";

export function StudentBrand({ className = "" }: { className?: string }) {
  return (
    <header className={`student-shell__header ${className}`}>
      <Link href={"/students/join" as Route} className="student-shell__brand">
        <span className="student-shell__brand-mark">
          <LogoGlyph className="size-5" />
        </span>
        <span>
          <span className="student-shell__eyebrow">Adaptive Trainer</span>
          <span className="student-shell__title">Student Classroom</span>
        </span>
      </Link>
    </header>
  );
}
