import {ImportForm} from "@/components/import-form";

export const dynamic = "force-dynamic";

export default function ImportPage() {
  return (
    <>
      <section className="hero">
        <p className="eyebrow">Import</p>
        <h1>把真实岗位数据导入 JobLens</h1>
        <p className="lede">
          选择浏览器插件导出的 Collector report。系统会保留来源证据、候选诊断和批次审计，同时避免重复创建同一个岗位。
        </p>
      </section>
      <ImportForm />
      <div className="notice">
        当前只接受 JSON report；不会上传简历，也不会自动投递岗位。
      </div>
    </>
  );
}
