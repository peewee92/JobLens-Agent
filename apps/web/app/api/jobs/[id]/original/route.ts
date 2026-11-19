import {BackendApiError, fetchJobDetail} from "@/lib/backend";

export const dynamic = "force-dynamic";

/** Read only the existing job fields needed for quick preview. */
export async function GET(_request: Request, {params}: {params: Promise<{id: string}>}) {
  const {id} = await params;
  try {
    const job = await fetchJobDetail(id);
    return Response.json({description: job.description}, {headers: {"Cache-Control": "no-store"}});
  } catch (error) {
    const status = error instanceof BackendApiError ? error.status : 503;
    const code = error instanceof BackendApiError ? error.code : "backend_unavailable";
    return Response.json({error: {code}}, {status, headers: {"Cache-Control": "no-store"}});
  }
}
