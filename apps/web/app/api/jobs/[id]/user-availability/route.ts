import {backendProxyResponse} from "@/lib/backend";

export async function PUT(request: Request, {params}: {params: Promise<{id: string}>}) {
  const {id} = await params;
  return backendProxyResponse(`/api/v1/jobs/${encodeURIComponent(id)}/user-availability`, {
    method: "PUT", headers: {"Content-Type": "application/json"}, body: await request.text(),
  });
}
