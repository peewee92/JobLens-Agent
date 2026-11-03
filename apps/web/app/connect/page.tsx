import {ModelConnection} from "@/components/model-connection";
import {publicDemoEnabled} from "@/lib/public-demo";
export const dynamic = "force-dynamic";
export default function ConnectPage() {
  return publicDemoEnabled() ? <ModelConnection/> : <section><h1>模型连接</h1><p>本地模式继续使用后端环境配置。此页面用于公开托管的临时会话。</p></section>;
}
