import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output keeps the Cloud Run image small (see Dockerfile).
  output: "standalone",
};

export default nextConfig;
