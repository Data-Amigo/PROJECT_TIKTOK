import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a self-contained server (.next/standalone) so the Docker image is
  // small and doesn't need the full node_modules at runtime. Required by the
  // Railway Dockerfile deploy (see frontend/Dockerfile, docs/DEPLOY.md).
  output: "standalone",
};

export default nextConfig;
