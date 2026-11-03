import "server-only";
import {cache} from "react";
import {backendResponse} from "@/lib/backend";
import {publicDemoEnabled} from "@/lib/public-demo";
export const publicSession = cache(async function publicSession(): Promise<{mode: "sample" | "byok"; synthetic: boolean} | null> {
  if (!publicDemoEnabled()) return null;
  try {
    const r = await backendResponse("/api/v1/demo/session");
    return r.ok ? await r.json() : null;
  } catch {return null;}
});
