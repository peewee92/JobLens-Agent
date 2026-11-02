import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  distDir: process.env.JOBLENS_DEMO === "1" ? `.next-demo-${process.env.JOBLENS_DEMO_WEB_PORT ?? "3100"}` : ".next",
  typescript: {tsconfigPath: process.env.JOBLENS_DEMO === "1" ? `.tsconfig-demo-${process.env.JOBLENS_DEMO_WEB_PORT ?? "3100"}.json` : "tsconfig.json"},
  allowedDevOrigins: ["127.0.0.1", "localhost"],
};

export default nextConfig;
