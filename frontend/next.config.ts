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
  typedRoutes: true,
};

export default nextConfig;
