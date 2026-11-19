import type { NextConfig } from "next";
import {hostingOrigin, isPrivateWorkspaceBuild, PRIVATE_WORKSPACE_PATH, privateWorkspaceRewrites} from "./lib/workspace-path";

const localPort = process.env.JOBLENS_LOCAL_WEB_PORT;
const privateBuild = isPrivateWorkspaceBuild();
const privateUpstream = privateBuild ? null : hostingOrigin(process.env.JOBLENS_PRIVATE_UPSTREAM_URL);
const cacheKey = localPort ? `local-${localPort}`
  : process.env.JOBLENS_DEMO === "1" ? `demo-${process.env.JOBLENS_DEMO_WEB_PORT ?? "3100"}` : null;

const nextConfig: NextConfig = {
  poweredByHeader: false,
  basePath: privateBuild ? PRIVATE_WORKSPACE_PATH : "",
  async rewrites() {
    return privateUpstream ? {beforeFiles: privateWorkspaceRewrites(privateUpstream)} : [];
  },
  distDir: cacheKey ? `.next-${cacheKey}` : ".next",
  typescript: {tsconfigPath: cacheKey ? `.tsconfig-${cacheKey}.json` : "tsconfig.json"},
  allowedDevOrigins: ["127.0.0.1", "localhost"],
};

export default nextConfig;
