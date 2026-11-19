import {workspaceAuth} from "@/lib/cloud-auth";
import {privateResponseHeaders} from "@/lib/private-routing";
import {hostingOrigin, isPrivateWorkspaceBuild} from "@/lib/workspace-path";

export const dynamic = "force-dynamic";

function reply(status: number, message?: string) {
  const headers = privateResponseHeaders();
  return status === 204 ? new Response(null, {status, headers}) : Response.json({message}, {status, headers});
}

function checkRequest(request: Request) {
  if (!isPrivateWorkspaceBuild()) return reply(404);
  const origin = hostingOrigin(process.env.JOBLENS_CLOUD_FRONTEND_ORIGIN);
  return !origin || origin !== request.headers.get("origin") ? reply(403, "请从个人工作台打开登录页面。") : null;
}

export async function POST(request: Request) {
  const rejected = checkRequest(request);
  if (rejected) return rejected;
  try {
    if (!request.headers.get("content-type")?.startsWith("application/json")) return reply(415, "请使用登录表单。");
    const payload = await request.json().catch(() => null);
    const {email, password} = payload ?? {};
    if (typeof email !== "string" || email.length > 254 || !email.includes("@") ||
        typeof password !== "string" || !password || password.length > 128) return reply(422, "请填写受邀邮箱与密码。");
    const {error} = await workspaceAuth().signIn.email({email: email.trim(), password, rememberMe: false});
    if (!error) return reply(204);
    if (error.status === 429) return reply(429, "尝试次数过多，请稍后再登录。");
    if ([400, 401, 403, 422].includes(error.status ?? 0)) return reply(401, "登录未成功。请核对受邀邮箱与密码，或联系维护者确认账号。");
    return reply(503, "暂时无法登录，请稍后再试。");
  } catch {
    return reply(503, "暂时无法登录，请稍后再试。");
  }
}

export async function DELETE(request: Request) {
  const rejected = checkRequest(request);
  if (rejected) return rejected;
  try {
    const {error} = await workspaceAuth().signOut();
    if (!error) return reply(204);
  } catch { /* Keep the current session visible if sign-out was not confirmed. */ }
  return reply(503, "没能确认退出，请稍后再试。");
}
