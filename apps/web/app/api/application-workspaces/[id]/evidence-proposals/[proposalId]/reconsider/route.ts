import {backendProxyResponse} from "@/lib/backend";
export async function POST(request: Request, {params}: {params: Promise<{id: string; proposalId: string}>}) {
  const {id, proposalId} = await params;
  return backendProxyResponse(`/api/v1/application-workspaces/${encodeURIComponent(id)}/evidence-proposals/${encodeURIComponent(proposalId)}/reconsider`, {
    method: "POST", headers: {"Content-Type": "application/json"}, body: await request.text(),
  });
}
