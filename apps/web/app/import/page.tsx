import {ImportForm} from "@/components/import-form";
import {ImportGuide} from "@/components/import-guide";
import {ManualImportChoices} from "@/components/manual-import-choices";

import {PageHeading} from "@/components/ui/patterns";

export const dynamic = "force-dynamic";

export default function ImportPage() {
  return (
    <div className="jl-section-stack jl-import-page">
      <PageHeading kicker="第 2 步 · 添加岗位" title="添加你正在考虑的岗位"
        description="粘贴招聘描述就能开始。岗位保存后，先核对要求，再比较它和你的经历是否匹配。" />
      <ManualImportChoices />
      <details className="detail-card">
        <summary>从浏览器插件或岗位文件导入</summary>
        <ImportForm />
        <ImportGuide />
      </details>
      <p className="jl-description jl-import-footnote">这里只添加岗位，不会自动帮你投递。</p>
    </div>
  );
}
