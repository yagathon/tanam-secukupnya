import type { NextConfig } from "next";

// Production: static export served by Firebase Hosting, which rewrites /api/** to Cloud Run
// (same origin, no CORS). Dev: proxy /api to the local FastAPI (`just api`).
const isProd = process.env.NODE_ENV === "production";

const nextConfig: NextConfig = isProd
  ? { output: "export" }
  : {
      async rewrites() {
        const api = process.env.API_URL ?? "http://localhost:8100";
        return [{ source: "/api/:path*", destination: `${api}/api/:path*` }];
      },
    };

export default nextConfig;
