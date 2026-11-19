import {workspaceAuth, workspaceCodeAuth} from "@/lib/cloud-auth";
import {parseWorkspaceSignIn, workspaceCodeRecipients} from "@/lib/private-sign-in";
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
    const input = parseWorkspaceSignIn(await request.json().catch(() => null));
    if (!input) return reply(422, "请检查邮箱和登录信息。");
    const {mode, email} = input;
    const recipients = workspaceCodeRecipients(process.env.JOBLENS_CLOUD_CODE_EMAILS);
    if (mode === "send-code") {
      if (recipients.has(email)) {
        // The provider owns code delivery, expiry and throttling. Never automatically resend.
        await workspaceCodeAuth().emailOtp.sendVerificationOtp({email, type: "sign-in"}).catch(() => null);
      }
      // Do not reveal whether an address was invited or whether the provider accepted a send.
      return reply(202, "如果这个邮箱已受邀，请查收验证码。若没收到，请检查垃圾邮件，稍后再试或联系维护者。");
    }
    if (mode === "verify-code" && !recipients.has(email)) return reply(401, "验证码不正确或已过期，请核对邮件或重新获取。");
    const {error} = mode === "verify-code"
      ? await workspaceCodeAuth().signIn.emailOtp({email, otp: input.code})
      : await workspaceAuth().signIn.email({email, password: input.password, rememberMe: false});
    if (!error) return reply(204);
    if (error.status === 429) return reply(429, "尝试次数过多，请稍后再登录。");
    if ([400, 401, 403, 404, 422].includes(error.status ?? 0)) return reply(401, mode === "verify-code"
      ? "验证码不正确或已过期，请核对邮件或重新获取。"
      : "登录未成功。请核对受邀邮箱与密码，或联系维护者确认账号。");
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
