import {backendResponse} from "@/lib/backend";
export async function POST(request: Request, {params}: {params: Promise<{id: string}>}) {
  const {id} = await params;
  const body = await request.text();
  return backendResponse(`/api/v1/jobs/${encodeURIComponent(id)}/requirement-calls`, {
    method: "POST", headers: {"Content-Type": "application/json"}, body,
  });
}
