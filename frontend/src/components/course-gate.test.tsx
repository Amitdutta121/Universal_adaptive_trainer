import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import { CourseGate } from "./course-gate";

let pathname = "/courses/7/books";
let courseState: Record<string, unknown> = {};

vi.mock("next/navigation", () => ({ usePathname: () => pathname }));
vi.mock("@/lib/api/queries", () => ({ useCourse: () => courseState }));

beforeEach(() => {
  pathname = "/courses/7/books";
  courseState = { isSuccess: false, isError: false, error: null };
});

describe("CourseGate", () => {
  it("renders the screen once the course loads", () => {
    courseState = { isSuccess: true, isError: false, data: { id: 7, name: "Intro" } };
    render(<CourseGate>course screen</CourseGate>);
    expect(screen.getByText("course screen")).toBeInTheDocument();
  });

  it("renders nothing while the course is loading", () => {
    const { container } = render(<CourseGate>course screen</CourseGate>);
    expect(container).toBeEmptyDOMElement();
  });

  it("replaces the screen with a not-found card when the course is not the professor's", () => {
    courseState = {
      isSuccess: false,
      isError: true,
      error: new ApiError(404, "not_found", "Course 7 does not exist."),
    };
    render(<CourseGate>course screen</CourseGate>);

    expect(screen.queryByText("course screen")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Course not found" })).toBeInTheDocument();
    expect(screen.getByText(/None of your courses has id 7/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to your courses" })).toHaveAttribute(
      "href",
      "/courses",
    );
  });

  it("shows any other failure as the API's own error", () => {
    courseState = {
      isSuccess: false,
      isError: true,
      error: new ApiError(500, "internal_error", "Database unreachable."),
    };
    render(<CourseGate>course screen</CourseGate>);
    expect(screen.getByText("Database unreachable.")).toBeInTheDocument();
  });

  it("does not gate a page outside a course", () => {
    pathname = "/courses";
    render(<CourseGate>course list</CourseGate>);
    expect(screen.getByText("course list")).toBeInTheDocument();
  });
});
