import {backendProxyResponse} from '@/lib/backend';

export async function POST(request: Request) {
  return backendProxyResponse('/api/v1/career-agent/initial-scope-runs', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: await request.text(),
  });
}
