import {backendResponse} from "@/lib/backend";
export async function GET(_request: Request, {params}: {params: Promise<{id: string}>}) {
  const {id} = await params;
  return backendResponse(`/api/v1/jobs/${encodeURIComponent(id)}/semantic-call-plan`);
}
