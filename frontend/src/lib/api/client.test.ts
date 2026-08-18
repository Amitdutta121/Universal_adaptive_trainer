/**
 * The client's contract with `app/errors.py`.
 *
 * The backend answers a failure with `{"error": {code, message, detail?}}` and only
 * does so when the request asked for JSON. Both of those are easy to break silently,
 * so they are pinned here.
 */

import { describe, expect, it, vi } from "vitest";
import { ApiError, createApiClient, unwrap } from "./client";

function result<T>(body: T, status = 200) {
  const response = new Response(null, { status });
  return Promise.resolve(
    status < 400 ? { data: body, response } : { error: body as unknown, response },
  );
}

describe("unwrap", () => {
  it("returns the payload on success", async () => {
    await expect(unwrap(result({ status: "ok" }))).resolves.toEqual({ status: "ok" });
  });

  it("raises the backend's own error code, message and detail", async () => {
    const failure = unwrap(
      result(
        { error: { code: "invalid_taxonomy_document", message: "Rejected.", detail: "topics[0]" } },
        422,
      ),
    );

    await expect(failure).rejects.toBeInstanceOf(ApiError);
    await expect(failure).rejects.toMatchObject({
      status: 422,
      code: "invalid_taxonomy_document",
      message: "Rejected.",
      detail: "topics[0]",
    });
  });

  it("marks a 502 as an upstream failure, so it may be retried", async () => {
    expect.assertions(2);
    try {
      await unwrap(
        result({ error: { code: "llm_request_error", message: "Provider unreachable." } }, 502),
      );
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).isUpstream).toBe(true);
    }
  });

  it("still produces an ApiError when the body is not the expected envelope", async () => {
    await expect(unwrap(result("<html>gateway</html>", 500))).rejects.toMatchObject({
      status: 500,
      code: "unknown_error",
    });
  });
});

describe("request headers", () => {
  it("asks for JSON, or the backend renders an HTML error page instead", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await createApiClient("http://backend.test").GET("/api/health");

    const request = fetchSpy.mock.calls[0]?.[0] as Request;
    expect(request.headers.get("Accept")).toBe("application/json");
    fetchSpy.mockRestore();
  });
});
