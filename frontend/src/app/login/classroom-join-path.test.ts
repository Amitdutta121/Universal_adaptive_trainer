import { describe, expect, it } from "vitest";
import { classroomJoinPath } from "./login-screen";

describe("classroomJoinPath", () => {
  it("takes a bare classroom number as a set id", () => {
    expect(classroomJoinPath(" 12 ")).toBe("/students/join?set=12");
  });

  it("takes a full or relative join link", () => {
    expect(classroomJoinPath("https://trainer.example.edu/students/join?set=7")).toBe(
      "/students/join?set=7",
    );
    expect(classroomJoinPath("/students/join?taxonomy=3")).toBe("/students/join?taxonomy=3");
  });

  it("rejects anything that is not a classroom", () => {
    expect(classroomJoinPath("PY-4821")).toBeNull();
    expect(classroomJoinPath("https://example.com/?set=abc")).toBeNull();
  });
});
