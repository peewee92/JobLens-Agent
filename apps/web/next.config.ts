import type { NextConfig } from "next";

const localPort = process.env.JOBLENS_LOCAL_WEB_PORT;
const cacheKey = localPort ? `local-${localPort}`
  : process.env.JOBLENS_DEMO === "1" ? `demo-${process.env.JOBLENS_DEMO_WEB_PORT ?? "3100"}` : null;

const nextConfig: NextConfig = {
  poweredByHeader: false,
  distDir: cacheKey ? `.next-${cacheKey}` : ".next",
  typescript: {tsconfigPath: cacheKey ? `.tsconfig-${cacheKey}.json` : "tsconfig.json"},
  allowedDevOrigins: ["127.0.0.1", "localhost"],
};

export default nextConfig;
