(() => {
  const DEFAULT_ENDPOINT = 'http://127.0.0.1:8000/api/v1/job-imports';
  const DEFAULT_WEB_ORIGIN = 'http://127.0.0.1:3000';
  const QUICK_TARGETS = Object.freeze({
    local: Object.freeze({
      endpoint: 'http://127.0.0.1:8102/api/v1/job-imports',
      webOrigin: 'http://127.0.0.1:3102'
    }),
    development: Object.freeze({ endpoint: DEFAULT_ENDPOINT, webOrigin: DEFAULT_WEB_ORIGIN })
  });

  function parseReport(lastRun) {
    if (lastRun?.report && typeof lastRun.report === 'object' && !Array.isArray(lastRun.report)) {
      return lastRun.report;
    }
    if (typeof lastRun?.json === 'string' && lastRun.json.trim()) {
      const parsed = JSON.parse(lastRun.json);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed;
    }
    throw new Error('还没有可同步的完整报告。');
  }

  async function syncReport(report, { fetchImpl = fetch, endpoint = DEFAULT_ENDPOINT, localOnly = false } = {}) {
    const response = await fetchImpl(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(report),
      ...(localOnly ? { redirect: 'error', credentials: 'omit', signal: AbortSignal.timeout(8000) } : {})
    });

    let body = null;
    try {
      body = await response.json();
    } catch {
      // Preserve the HTTP status below when the backend does not return JSON.
    }

    if (!response.ok) {
      const detail = body?.detail?.message || body?.message || body?.error?.message;
      throw new Error(detail || `JobLens 同步失败（HTTP ${response.status}）。`);
    }
    return body;
  }

  function buildImportDetailUrl(importId, { webOrigin = DEFAULT_WEB_ORIGIN } = {}) {
    if (typeof importId !== 'string' || !/^imp_[A-Za-z0-9_-]+$/.test(importId)) {
      throw new Error('JobLens 没有返回可打开的导入批次。');
    }
    return `${webOrigin.replace(/\/$/, '')}/imports/${encodeURIComponent(importId)}`;
  }

  function formatSyncResult(result) {
    const created = Number(result?.created || 0);
    const updated = Number(result?.updated || 0);
    const skipped = Number(result?.skipped || 0);
    const errors = Array.isArray(result?.errors) ? result.errors.length : 0;
    const parts = [`新增 ${created}`, `更新 ${updated}`, `跳过 ${skipped}`];
    if (errors) parts.push(`失败 ${errors}`);
    return `已同步到 JobLens：${parts.join('，')}。`;
  }

  function quickTarget(key) {
    if (key !== 'local' && key !== 'development') throw new Error('请选择本机同步目标。');
    return QUICK_TARGETS[key];
  }

  function quickImportUrl(importId, target) {
    return buildImportDetailUrl(importId, quickTarget(target));
  }

  async function syncQuickReport(report, target, fetchImpl = fetch) {
    const result = await syncReport(report, { fetchImpl, endpoint: quickTarget(target).endpoint, localOnly: true });
    quickImportUrl(result?.importId, target);
    const counts = [result.created, result.updated, result.skipped];
    if (result.received !== 1 || !Array.isArray(result.errors) || result.errors.length
        || !counts.every(n => Number.isInteger(n) && n >= 0) || counts.reduce((a, b) => a + b, 0) !== 1) {
      throw new Error('本机没有确认这条岗位已导入，请先检查导入记录，再手动重试或下载 JSON。');
    }
    return result;
  }

  globalThis.JobLensSync = {
    DEFAULT_ENDPOINT,
    DEFAULT_WEB_ORIGIN,
    parseReport,
    syncReport,
    buildImportDetailUrl,
    formatSyncResult,
    quickImportUrl,
    syncQuickReport
  };
})();
