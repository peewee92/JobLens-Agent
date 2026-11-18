import {ImportForm} from "@/components/import-form";
import {ImportGuide} from "@/components/import-guide";
import {ManualImportChoices} from "@/components/manual-import-choices";

export const dynamic = "force-dynamic";

export default function ImportPage() {
  return (
    <>
      <section className="hero">
        <p className="eyebrow">第 2 步 · 添加岗位</p>
        <h1>添加你正在考虑的岗位</h1>
        <p className="lede">
          可以逐条填写，也可以一次粘贴多条招聘文本。保存后先核对岗位要求，再用已确认的职业资料比较。
        </p>
      </section>
      <ManualImportChoices />
      <details className="detail-card">
        <summary>批量添加：浏览器插件与岗位文件</summary>
        <ImportForm />
        <ImportGuide />
      </details>
      <div className="notice">
        这里添加的是岗位数据，不是简历。JobLens 不会自动帮你投递岗位。
      </div>
    </>
  );
}
