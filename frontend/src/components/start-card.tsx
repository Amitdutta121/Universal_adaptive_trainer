"use client";

/**
 * One way to start something, shown as a row of cards at the top of a page
 * (Curriculum: draft / import / build; Questions: single / bulk generate).
 * The action either runs `onClick` (opening a modal on the same page) or
 * follows `href`, which is relative to the open course.
 */

import { CourseLink } from "@/components/course-link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function StartCard({
  icon,
  title,
  description,
  action,
  ...target
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  action: string;
} & ({ onClick: () => void } | { href: string })) {
  return (
    <Card className="gap-4">
      <CardHeader className="gap-1.5">
        <CardTitle className="flex items-center gap-2 text-base">
          {icon}
          {title}
        </CardTitle>
        <CardDescription className="leading-6">{description}</CardDescription>
      </CardHeader>
      <CardContent className="mt-auto">
        {"href" in target ? (
          <Button asChild variant="outline" size="sm">
            <CourseLink href={target.href}>{action}</CourseLink>
          </Button>
        ) : (
          <Button variant="outline" size="sm" onClick={target.onClick}>
            {action}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
