import {notFound} from "next/navigation";
import {PrivateSignInForm} from "@/components/private-session-controls";
import {PageHeading} from "@/components/ui/patterns";
import {workspaceCodeRecipients} from "@/lib/private-sign-in";
import {isPrivateWorkspaceBuild, publicDemoHref} from "@/lib/workspace-path";

export const dynamic = "force-dynamic";

export default function PrivateSignInPage() {
  if (!isPrivateWorkspaceBuild()) notFound();
  return <section className="jl-panel jl-private-sign-in">
    <PageHeading title="登录个人工作台" description="只有受邀账号可以登录。登录后只会看到自己的背景、岗位和准备记录。" />
    <PrivateSignInForm codeEnabled={workspaceCodeRecipients(process.env.JOBLENS_CLOUD_CODE_EMAILS).size > 0} />
    <p className="jl-private-sign-in-alternative">还没有受邀账号？可以直接<a href={publicDemoHref()} className="jl-text-link">体验公开样本</a>，无需登录。</p>
  </section>;
}
