import Link from "next/link";

import {Button} from "./ui/button";
import {ActionDialog} from "./ui/dialog";
import {Badge, Field} from "./ui/primitives";
import {activeJobFilterLabels, jobsHref, type JobFilters as Filters} from "@/lib/query";

function FilterOptions({name, legend, selected, options}: {
  name: string; legend: string; selected: string; options: [string, string][];
}) {
  return <fieldset className="jl-filter-options"><legend>{legend}</legend><div className="jl-choice-group">
    {options.map(([value, label]) => <label key={value}><input type="radio" name={name} value={value} defaultChecked={value === selected} /><span>{label}</span></label>)}
  </div></fieldset>;
}

export function JobFilters({filters}: {filters: Filters}) {
  const labels = activeJobFilterLabels(filters);
  const clearHref = jobsHref({...filters, q: "", city: "", minSalaryK: "", remoteStatus: "", source: "", sort: "latest"}, 0);
  const hasConditions = labels.length > 0 || filters.sort !== "latest";
  return <div className="jl-job-filter">
    <div className="jl-job-filter-row">
      <form className="jl-job-search" action="/jobs" key={jobsHref(filters)}>
        <Field id="job-search" label="搜岗位、公司或技能"><input id="job-search" name="q" defaultValue={filters.q} placeholder="例如：Agent 工程师" type="search" /></Field>
        <Field id="job-city" label="城市"><input id="job-city" name="city" defaultValue={filters.city} placeholder="不限城市" type="search" /></Field>
        <input type="hidden" name="limit" value={filters.limit} />
        <input type="hidden" name="minSalaryK" value={filters.minSalaryK} />
        <input type="hidden" name="remoteStatus" value={filters.remoteStatus} />
        <input type="hidden" name="source" value={filters.source} />
        <input type="hidden" name="sort" value={filters.sort} />
        <Button type="submit" variant="secondary">搜索</Button>
      </form>
      <ActionDialog key={`advanced-${jobsHref(filters)}`} trigger={<Button variant="secondary">更多筛选</Button>}
        title="更多筛选" guardDraft description="按薪资、工作方式和来源缩小范围；应用后回到第一页。"
        action={<Button type="submit" form="advanced-job-filters">应用筛选</Button>}>
        <form className="jl-filter-form" action="/jobs" id="advanced-job-filters">
          <input type="hidden" name="q" value={filters.q} /><input type="hidden" name="city" value={filters.city} />
          <Field id="minSalaryK" label="最低月薪（千元）">
            <input id="minSalaryK" name="minSalaryK" type="number" min="0" step="any" defaultValue={filters.minSalaryK} />
          </Field>
          <FilterOptions name="remoteStatus" legend="远程状态" selected={filters.remoteStatus}
            options={[["", "不限"], ["confirmed", "支持远程"], ["rejected", "不支持远程"], ["unknown", "未说明"]]} />
          <Field id="source" label="岗位来源"><input id="source" name="source" defaultValue={filters.source} /></Field>
          <FilterOptions name="sort" legend="排序" selected={filters.sort}
            options={[["latest", "最近采集"], ["salaryDesc", "薪资从高到低"], ["salaryAsc", "薪资从低到高"]]} />
          <input type="hidden" name="limit" value={filters.limit} />
        </form>
      </ActionDialog>
    </div>
    {hasConditions && <div className="jl-inline jl-active-filters">
      <ul className="jl-filter-tags" aria-label="当前筛选和排序">
        {labels.map(label => <li key={label}><Badge tone="info">{label}</Badge></li>)}
        {filters.sort !== "latest" && <li><Badge>{filters.sort === "salaryDesc" ? "薪资从高到低" : "薪资从低到高"}</Badge></li>}
      </ul>
      <Link className="jl-text-link" href={clearHref}>清空筛选</Link>
    </div>}
  </div>;
}
