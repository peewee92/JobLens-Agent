import {NextResponse} from "next/server";
import {backendResponse} from "@/lib/backend";

/** Bounded, read-only paging for the analysis job selector. */
export async function GET(request: Request) {
  const raw = new URL(request.url).searchParams.get("offset") ?? "0";
  if (!/^\d{1,7}$/.test(raw)) return NextResponse.json({error: {code: "request_validation_error"}}, {status: 400});
  const response = await backendResponse(`/api/v1/jobs?limit=20&offset=${Number(raw)}`);
  return new NextResponse(await response.text(), {status: response.status,
    headers: {"Content-Type": response.headers.get("Content-Type") ?? "application/json"}});
}
