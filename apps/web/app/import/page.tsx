import {ImportForm} from "@/components/import-form";
import {ImportGuide} from "@/components/import-guide";
import {ManualJobForm} from "@/components/manual-job-form";

export const dynamic = "force-dynamic";

export default function ImportPage() {
  return (
    <>
      <section className="hero">
        <p className="eyebrow">添加岗位</p>
        <h1>添加你正在考虑的岗位</h1>
        <p className="lede">
          先粘贴一个真实岗位，或添加浏览器插件导出的岗位文件。保存后继续核对要求，再根据你的真实经历分析。
        </p>
      </section>
      <ManualJobForm />
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
