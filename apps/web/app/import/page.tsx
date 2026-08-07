import {ImportForm} from "@/components/import-form";

export const dynamic = "force-dynamic";

export default function ImportPage() {
  return (
    <>
      <section className="hero">
        <p className="eyebrow">添加岗位</p>
        <h1>把浏览器里收集的岗位加到 JobLens</h1>
        <p className="lede">
          从 JobLens 浏览器插件导出岗位文件后，在这里一次性添加。系统会自动去重，并保留原始岗位链接，方便你之后核对。
        </p>
      </section>
      <ImportForm />
      <div className="notice">
        这里添加的是岗位数据，不是简历。JobLens 不会自动帮你投递岗位。
      </div>
    </>
  );
}
