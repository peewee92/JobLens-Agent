import {createHash} from "node:crypto";
import {backendProxyResponse, fetchJobDetail} from "@/lib/backend";
import {publicDemoEnabled} from "@/lib/public-demo";

export async function PUT(request: Request, {params}: {params: Promise<{id: string}>}) {
  if (publicDemoEnabled()) return Response.json({error: {code: "manual_description_source_read_only"}}, {status: 403});
  const {id} = await params;
  return backendProxyResponse(`/api/v1/jobs/${encodeURIComponent(id)}/manual-description`, {
    method: "PUT", headers: {"Content-Type": "application/json"}, body: await request.text(),
  });
}

// Read back the persisted version after a timeout; do not blindly replay a write.
export async function GET(_request: Request, {params}: {params: Promise<{id: string}>}) {
  if (publicDemoEnabled()) return new Response(null, {status: 403});
  const {id} = await params;
  try {
    const job = await fetchJobDetail(id);
    if (job.id !== id || job.source !== "manual") return new Response(null, {status: 409});
    return Response.json({revision: createHash("sha256").update(job.description ?? "").digest("hex")}, {
      headers: {"Cache-Control": "no-store"},
    });
  } catch {
    return new Response(null, {status: 503});
  }
}
