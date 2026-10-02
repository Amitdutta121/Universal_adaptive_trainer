import type { NextConfig } from "next";

/**
 * The browser talks to `/api/*` on this origin and Next forwards it to FastAPI.
 *
 * This keeps every request same-origin, so CORS is never involved in development
 * and the backend URL is never baked into the client bundle. `CORS_ALLOW_ORIGINS`
 * on the backend is only needed if the two are ever deployed so that the browser
 * reaches FastAPI directly instead of through this rewrite.
 */
const API_ORIGIN = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
  // Professor screens moved under /courses/{id}; an old bookmark lands on the
  // course list rather than a 404.
  async redirects() {
    return ["books", "curriculum", "questions", "review", "coverage", "judges", "dashboard", "feedback"]
      .flatMap((section) => [`/${section}`, `/${section}/:path*`])
      .concat(["/students", "/students/roster"])
      .map((source) => ({ source, destination: "/courses", permanent: false }));
  },
  typedRoutes: true,
  experimental: {
    // Next's rewrite proxy kills the upstream connection after 30s by default
    // (dist/server/lib/router-utils/proxy-request.js). Coverage generation runs
    // one retrieval + LLM call per gap cell, sequentially -- a topic with a
    // dozen-plus gaps easily exceeds 30s even though the backend keeps working
    // and the request eventually succeeds server-side.
    proxyTimeout: 600_000,
  },
};

export default nextConfig;
