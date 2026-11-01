/**
 * The CopilotKit runtime for the agent panel (Phase 8, Task 35).
 *
 * The chat panel talks to this route; each run is forwarded to the backend's AG-UI endpoint
 * (`POST /api/agent`, Pydantic AI), which owns the agent, its tools and its approvals. The
 * runtime only relays: the agent is built per request, carrying just the professor's session
 * cookie and the course header, so the backend checks the login and the course as on every
 * other call. Outside `/api` on purpose: `/api/*` is rewritten to FastAPI (`next.config.ts`).
 *
 * New dependency: `@copilotkit/runtime` (MIT) -- the open-source way to serve CopilotKit's chat
 * protocol; letting the browser hold the agent itself is a licensed CopilotKit feature.
 */

import { HttpAgent } from "@ag-ui/client";
import { CopilotRuntime, createCopilotRuntimeHandler } from "@copilotkit/runtime/v2";
import { COURSE_HEADER } from "@/lib/api/client";

// CopilotKit's runtime reports usage to its vendor unless told not to.
process.env.COPILOTKIT_TELEMETRY_DISABLED ??= "true";

const API_ORIGIN = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

const runtime = new CopilotRuntime({
  agents: ({ request }) => {
    const headers: Record<string, string> = {};
    const cookie = request.headers.get("cookie");
    const course = request.headers.get(COURSE_HEADER);
    if (cookie) headers.cookie = cookie;
    if (course) headers[COURSE_HEADER] = course;
    return { default: new HttpAgent({ url: `${API_ORIGIN}/api/agent`, headers }) };
  },
  // Only what the factory above sets reaches the backend.
  forwardHeaders: { allow: [] },
});

const handler = createCopilotRuntimeHandler({ runtime, basePath: "/copilotkit" });

export const GET = handler;
export const POST = handler;
