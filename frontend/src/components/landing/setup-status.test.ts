import { describe, expect, it } from "vitest";
import type { Health } from "@/lib/api/types";
import { describeHealth } from "./setup-status";

const healthy: Health = {
  status: "ok",
  version: "0.1.0",
  environment: "development",
  database_ok: true,
  llm_configured: true,
  llm_status: "configured",
};

const tones = (rows: ReturnType<typeof describeHealth>) => rows.map((row) => row.tone);

describe("describeHealth", () => {
  it("marks every row idle while the first request is in flight", () => {
    expect(tones(describeHealth(undefined, "pending"))).toEqual(["idle", "idle", "idle", "idle"]);
  });

  it("flags only the API as critical when the backend is unreachable", () => {
    expect(tones(describeHealth(undefined, "error"))).toEqual(["critical", "idle", "idle", "idle"]);
  });

  it("is all green for a healthy development backend", () => {
    expect(tones(describeHealth(healthy, "success"))).toEqual(["ok", "ok", "ok", "ok"]);
  });

  it("treats a missing LLM key as a warning, not a failure", () => {
    const rows = describeHealth({ ...healthy, llm_configured: false }, "success");
    expect(rows.find((row) => row.key === "llm")?.tone).toBe("warn");
  });

  it("reports an unreachable database as critical", () => {
    const rows = describeHealth({ ...healthy, database_ok: false }, "success");
    expect(rows.find((row) => row.key === "db")?.tone).toBe("critical");
  });

  it("warns that no dev account is seeded outside development", () => {
    const rows = describeHealth({ ...healthy, environment: "production" }, "success");
    const account = rows.find((row) => row.key === "account");
    expect(account?.tone).toBe("warn");
    expect(account?.detail).toContain("production");
  });
});
