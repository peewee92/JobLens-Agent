export type ReadinessCode = "ready" | "database_unavailable" | "migration_required"
  | "schema_incomplete" | "migration_metadata_unavailable";
type CheckStatus = "passed" | "failed" | "unknown";

export type SystemReadiness = {
  ready: boolean;
  code: ReadinessCode;
  checks: {database: CheckStatus; migrations: CheckStatus; tables: CheckStatus};
  currentRevisions: string[];
  requiredRevisions: string[];
  missingTables: string[];
};

export function readinessMessage(code: ReadinessCode): string {
  switch (code) {
    case "ready": return "运行环境已就绪。";
    case "database_unavailable": return "暂时无法连接求职数据库。请检查数据库是否存在、连接配置和访问权限。";
    case "migration_required": return "数据库版本与当前程序不一致。请先备份数据库，在副本上验证迁移后再升级；本页面不会自动修改数据。";
    case "schema_incomplete": return "数据库版本已登记，但所需数据表不完整。请先检查备份与迁移记录，不要直接重建或清空数据库。";
    case "migration_metadata_unavailable": return "程序缺少可用的迁移文件。请检查后端安装是否完整。";
  }
}

export function isSystemReadiness(value: unknown): value is SystemReadiness {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<SystemReadiness>;
  const codes = ["ready", "database_unavailable", "migration_required", "schema_incomplete", "migration_metadata_unavailable"];
  const checks = item.checks;
  const keys = ["ready", "code", "checks", "currentRevisions", "requiredRevisions", "missingTables"];
  const strings = (list: unknown): list is string[] => Array.isArray(list) && list.every((v) => typeof v === "string");
  const validCheck = (check: unknown) => ["passed", "failed", "unknown"].includes(String(check));
  return Object.keys(item).length === keys.length && Object.keys(item).every((key) => keys.includes(key))
    && typeof item.ready === "boolean" && codes.includes(item.code ?? "")
    && !!checks && validCheck(checks.database) && validCheck(checks.migrations) && validCheck(checks.tables)
    && Object.keys(checks).length === 3
    && strings(item.currentRevisions) && strings(item.requiredRevisions) && strings(item.missingTables)
    && (item.ready
      ? item.code === "ready" && Object.values(checks).every((v) => v === "passed") && item.missingTables.length === 0
        && item.currentRevisions.length > 0
        && JSON.stringify([...item.currentRevisions].sort()) === JSON.stringify([...item.requiredRevisions].sort())
      : item.code !== "ready");
}
