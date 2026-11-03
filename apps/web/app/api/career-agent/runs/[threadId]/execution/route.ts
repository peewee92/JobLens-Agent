import {backendProxyResponse} from "@/lib/backend";

export async function GET(_request: Request, {params}: {params: Promise<{threadId: string}>}) {
  const {threadId} = await params;
  return backendProxyResponse(`/api/v1/career-agent/runs/${encodeURIComponent(threadId)}/execution`);
}

export async function POST(request: Request, {params}: {params: Promise<{threadId: string}>}) {
  const {threadId} = await params;
  return backendProxyResponse(`/api/v1/career-agent/runs/${encodeURIComponent(threadId)}/execution`, {
    method: "POST", headers: {"Content-Type": "application/json"}, body: await request.text(),
  });
}
