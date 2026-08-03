import {NextResponse} from "next/server";

import {BackendApiError, backendResponse} from "@/lib/backend";

export const dynamic = "force-dynamic";
const MAX_FILE_BYTES = 5 * 1024 * 1024;

function error(status: number, code: string, message: string) {
  return NextResponse.json({error: {code, message}}, {status});
}

export async function POST(request: Request): Promise<Response> {
  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return error(422, "invalid_resume_document", "Request must contain a resume file.");
  }

  const file = form.get("file");
  if (!(file instanceof File) || file.size === 0) {
    return error(422, "invalid_resume_document", "Choose a non-empty PDF or DOCX resume.");
  }
  if (file.size > MAX_FILE_BYTES) {
    return error(413, "resume_document_too_large", "Resume file exceeds 5 MiB.");
  }

  const outbound = new FormData();
  outbound.set("file", file, file.name);
  try {
    const response = await backendResponse("/api/v1/profile-proposals/file", {
      method: "POST",
      body: outbound,
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
