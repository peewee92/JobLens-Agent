import {NextResponse} from "next/server";

import {BackendApiError, backendResponse} from "@/lib/backend";

export const dynamic = "force-dynamic";

function error(status: number, code: string, message: string) {
  return NextResponse.json({error: {code, message}}, {status});
}

export async function POST(request: Request): Promise<Response> {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return error(422, "request_validation_error", "Request body must be valid JSON.");
  }

  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    return error(
      422,
      "request_validation_error",
      "Collector report root must be a JSON object.",
    );
  }

  try {
    const response = await backendResponse("/api/v1/job-imports", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    return new Response(await response.text(), {
      status: response.status,
      headers: {"Content-Type": "application/json"},
    });
  } catch (caught) {
    if (caught instanceof BackendApiError) {
      return error(caught.status, caught.code, caught.message);
    }
    return error(500, "internal_server_error", "Unexpected Web proxy error.");
  }
}
