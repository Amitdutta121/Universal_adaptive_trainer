import { beforeEach, describe, expect, it } from "vitest";
import {
  clearLearnerIdentity,
  loadLearnerIdentity,
  rememberedLearnerEmail,
  rememberedLearnerName,
  saveLearnerIdentity,
} from "./learner-identity";

const IDENTITY = {
  studentId: 7,
  resumeToken: "tok_abc123",
  displayName: "Ada",
  email: "ada@example.edu",
};

describe("learner identity storage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("round-trips a saved identity", () => {
    saveLearnerIdentity(IDENTITY);
    expect(loadLearnerIdentity()).toEqual(IDENTITY);
  });

  it("returns null when nothing is stored", () => {
    expect(loadLearnerIdentity()).toBeNull();
  });

  it("rejects a stored blob that is missing the token", () => {
    window.localStorage.setItem(
      "adaptive-trainer:learner-identity",
      JSON.stringify({ studentId: 7, displayName: "Ada" }),
    );
    expect(loadLearnerIdentity()).toBeNull();
  });

  it("rejects a stored blob that is missing the email", () => {
    window.localStorage.setItem(
      "adaptive-trainer:learner-identity",
      JSON.stringify({ studentId: 7, resumeToken: "tok_abc123", displayName: "Ada" }),
    );
    expect(loadLearnerIdentity()).toBeNull();
  });

  it("survives unparseable storage", () => {
    window.localStorage.setItem("adaptive-trainer:learner-identity", "{not json");
    expect(loadLearnerIdentity()).toBeNull();
  });

  it("clears both the identity and the legacy name key", () => {
    saveLearnerIdentity(IDENTITY);
    clearLearnerIdentity();
    expect(loadLearnerIdentity()).toBeNull();
    expect(rememberedLearnerName()).toBe("");
  });

  it("prefills the name from a legacy-only browser", () => {
    window.localStorage.setItem("adaptive-trainer:learner-name", "Grace");
    expect(loadLearnerIdentity()).toBeNull();
    expect(rememberedLearnerName()).toBe("Grace");
  });

  it("prefers the identity name over the legacy key", () => {
    window.localStorage.setItem("adaptive-trainer:learner-name", "Grace");
    saveLearnerIdentity(IDENTITY);
    expect(rememberedLearnerName()).toBe("Ada");
  });

  it("remembers the email only from a full identity", () => {
    expect(rememberedLearnerEmail()).toBe("");
    saveLearnerIdentity(IDENTITY);
    expect(rememberedLearnerEmail()).toBe("ada@example.edu");
  });
});
