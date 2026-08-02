import type { ImportOutcome, RemoteStatus } from "@/lib/contracts";

export function formatSalary(
  salaryMinK: number | null,
  salaryMaxK: number | null,
): string {
  if (salaryMinK !== null && salaryMaxK !== null) {
    return `${salaryMinK}–${salaryMaxK}K`;
  }
  if (salaryMinK !== null) {
    return `≥ ${salaryMinK}K`;
  }
  if (salaryMaxK !== null) {
    return `≤ ${salaryMaxK}K`;
  }
  return "薪资未公开";
}

export function formatRemoteStatus(status: RemoteStatus): string {
  return {
    confirmed: "明确支持远程",
    rejected: "明确不支持远程",
    unknown: "远程信息不足",
  }[status];
}

export function formatImportOutcome(outcome: ImportOutcome): string {
  return {
    created: "新建",
    updated: "更新",
    skipped: "跳过",
    error: "错误",
  }[outcome];
}

export function formatDateTime(value: string | null): string {
  if (!value) return "时间未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Shanghai",
  }).format(date);
}
