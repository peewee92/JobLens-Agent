import {NextResponse} from "next/server";
import {fetchJobDetail} from "@/lib/backend";

/** Read-only display labels for a saved run; failures never alter its scope. */
export async function GET(request: Request) {
  const ids = new URL(request.url).searchParams.getAll("jobId");
  if (!ids.length || ids.length > 50 || new Set(ids).size !== ids.length || ids.some(id => !/^[A-Za-z0-9_-]{1,100}$/.test(id))) {
    return NextResponse.json({error: {code: "request_validation_error"}}, {status: 400});
  }
  const results = await Promise.allSettled(ids.map(id => fetchJobDetail(id)));
  return NextResponse.json({items: results.flatMap((result, index) =>
    result.status === "fulfilled" && result.value.id === ids[index]
      ? [{id: result.value.id, title: result.value.title}] : [])});
}
