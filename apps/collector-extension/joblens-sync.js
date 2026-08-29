(() => {
  const DEFAULT_ENDPOINT = 'http://127.0.0.1:8000/api/v1/job-imports';
  const DEFAULT_WEB_ORIGIN = 'http://127.0.0.1:3000';

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

  async function syncReport(report, { fetchImpl = fetch, endpoint = DEFAULT_ENDPOINT } = {}) {
    const response = await fetchImpl(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(report)
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

  globalThis.JobLensSync = {
    DEFAULT_ENDPOINT,
    DEFAULT_WEB_ORIGIN,
    parseReport,
    syncReport,
    buildImportDetailUrl,
    formatSyncResult
  };
})();
