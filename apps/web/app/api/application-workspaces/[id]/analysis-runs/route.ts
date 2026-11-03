import {backendProxyResponse} from '@/lib/backend';
export async function POST(request: Request, {params}: {params: Promise<{id: string}>}) {
  const {id} = await params;
  return backendProxyResponse(`/api/v1/application-workspaces/${encodeURIComponent(id)}/analysis-runs`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: await request.text(),
  });
}
