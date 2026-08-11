import {NextResponse} from "next/server";

import {backendResponse} from "@/lib/backend";

export async function POST(
  request: Request,
  {params}: {params: Promise<{id: string}>},
) {
  const {id} = await params;
  const response = await backendResponse(
    `/api/v1/jobs/${encodeURIComponent(id)}/requirement-extractions`,
    {method: "POST"},
  );
  const body = await response.text();
  const returnTo = new URL(request.url).searchParams.get("returnTo");
  const safeReturnTo = `/jobs/${id}`;

  if (returnTo === safeReturnTo) {
    const target = new URL(safeReturnTo, request.url);
    if (!response.ok) {
      let errorCode = "requirement_extraction_failed";
      try {
        const parsed = JSON.parse(body) as {error?: {code?: string}};
        if (parsed.error?.code) errorCode = parsed.error.code;
      } catch {
        // Preserve the public fallback code when Backend did not return JSON.
      }
      target.searchParams.set("requirementExtractionError", errorCode);
    }
    return NextResponse.redirect(target, 303);
  }

  return new NextResponse(body, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("Content-Type") ?? "application/json",
    },
  });
}
