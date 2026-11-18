import Link from "next/link";

import {Button} from "./ui/button";
import {ActionDialog} from "./ui/dialog";
import {Badge, Field} from "./ui/primitives";
import {activeJobFilterLabels, jobsHref, type JobFilters as Filters} from "@/lib/query";

export function JobFilters({filters}: {filters: Filters}) {
  const labels = activeJobFilterLabels(filters);
  const clearHref = jobsHref({...filters, q: "", city: "", minSalaryK: "", remoteStatus: "", source: ""}, 0);
  return <div className="jl-job-filter">
    <div className="jl-inline">
      <ActionDialog
        key={jobsHref(filters)}
        trigger={<Button variant="secondary">{labels.length ? `筛选岗位（${labels.length}）` : "筛选岗位"}</Button>}
        title="筛选岗位"
        description="选择你关心的条件。返回岗位列表时，这些条件仍可恢复。"
      >
        <form className="jl-filter-form" action="/jobs" method="get">
          <Field id="q" label="关键词"><input id="q" name="q" defaultValue={filters.q} placeholder="岗位名、公司名或技能" /></Field>
          <Field id="city" label="城市"><input id="city" name="city" defaultValue={filters.city} placeholder="例如：武汉" /></Field>
          <Field id="minSalaryK" label="最低月薪（千元）">
            <input id="minSalaryK" name="minSalaryK" type="number" min="0" step="any" defaultValue={filters.minSalaryK} />
          </Field>
          <Field id="remoteStatus" label="远程状态">
            <select id="remoteStatus" name="remoteStatus" defaultValue={filters.remoteStatus}>
              <option value="">全部</option>
              <option value="confirmed">支持远程</option>
              <option value="rejected">不支持远程</option>
              <option value="unknown">未说明是否远程</option>
            </select>
          </Field>
          <Field id="source" label="岗位来源"><input id="source" name="source" defaultValue={filters.source} /></Field>
          <Field id="sort" label="排序">
            <select id="sort" name="sort" defaultValue={filters.sort}>
              <option value="latest">最近采集</option>
              <option value="salaryDesc">薪资从高到低</option>
              <option value="salaryAsc">薪资从低到高</option>
            </select>
          </Field>
          <input type="hidden" name="limit" value={filters.limit} />
          <div className="jl-inline jl-filter-actions">
            <Button type="submit">应用筛选</Button>
            {labels.length > 0 && <Link className="jl-text-link" href={clearHref}>清空筛选条件</Link>}
          </div>
        </form>
      </ActionDialog>
      {labels.length > 0 && <Link className="jl-text-link" href={clearHref}>清空全部筛选</Link>}
    </div>
    {(labels.length > 0 || filters.sort !== "latest") && <ul className="jl-filter-tags" aria-label="当前筛选和排序">
      {labels.map(label => <li key={label}><Badge tone="info">{label}</Badge></li>)}
      {filters.sort !== "latest" && <li><Badge>{filters.sort === "salaryDesc" ? "薪资从高到低" : "薪资从低到高"}</Badge></li>}
    </ul>}
  </div>;
}
