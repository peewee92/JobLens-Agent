import {NextResponse} from "next/server";

import {backendResponse} from "@/lib/backend";

export async function POST(
  _request: Request,
  {params}: {params: Promise<{id: string}>},
) {
  const {id} = await params;
  const response = await backendResponse(
    `/api/v1/jobs/${encodeURIComponent(id)}/match-report`,
    {method: "POST"},
  );
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("Content-Type") ?? "application/json",
    },
  });
}
