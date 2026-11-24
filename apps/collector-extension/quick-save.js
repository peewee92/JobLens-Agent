(() => {
  const { VERSION, currentBossJobUrl } = BossJobFilterLib;
  const el = id => document.getElementById(id);
  const status = message => { el('quickStatus').textContent = message; };
  const messages = {
    blocked: 'BOSS 要求登录或完成安全验证。请在网页中手动处理，然后重新采集。',
    unsupported: '请在 BOSS 桌面版（www.zhipin.com）手动打开独立职位详情页。移动版、搜索列表和右侧预览暂不支持快存。',
    changed: '当前岗位已切换。请重新采集并核对正文。',
    conflict: '发现多个主详情或岗位标识不一致，未采集。请重新打开独立职位详情。',
    unready: '暂时无法读取主详情。请等网页加载完成；若仍无法读取，请刷新后再试或手动粘贴。'
  };
  let draft = null;
  let receipt = null;
  let busy = true;

  const eligible = job => Boolean(job?.requirementReviewEligible === true
    && job.descriptionQuality === 'full_jd' && job.description
    && currentBossJobUrl(job.url) === job.url);

  function asReport({ job, generatedAt }) {
    return { version: VERSION, generatedAt, config: {}, statistics: {}, jobs: [job], candidates: [] };
  }

  function render() {
    const job = draft?.job;
    const canSync = eligible(job);
    el('quickCapture').disabled = busy;
    el('quickPreview').hidden = !job;
    el('quickJobTitle').textContent = job?.title || '';
    el('quickJobMeta').textContent = job ? [job.company, job.area || '地点未核实', job.salary || '薪资未核实'].join(' · ') : '';
    el('quickDescription').value = job?.description || '';
    const reasons = job?.requirementReviewIneligibilityReasons || [];
    el('quickQuality').textContent = !job ? '' : canSync ? '正文通过质量检查，请核对后确认同步。'
      : reasons.includes('visible_description_folded') ? '页面正文仍折叠。请手动展开后重新采集。'
      : reasons.includes('description_capture_limit') ? '正文超出采集上限。请在 JobLens 手动粘贴完整正文。'
      : !job.description ? '未读取到主详情正文。请等待页面加载、重新采集或手动粘贴。'
      : reasons.includes('page_noise_detected') ? '正文混有其他页面内容，不能快存。请手动粘贴岗位正文。'
      : '未确认完整正文，不能快存。请查看详情或手动粘贴。';
    el('quickActions').hidden = !canSync;
    el('quickSync').disabled = busy || !canSync;
    el('quickTarget').disabled = busy;
    el('quickDownload').hidden = !canSync;
    el('quickDownload').disabled = busy;
    el('quickOpenImport').hidden = !receipt;
    el('quickOpenImport').disabled = busy;
  }

  async function activeTab() {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    return tab;
  }

  async function readCurrent(tab, expectedUrl) {
    // Read only the main frame, then ensure the popup still refers to it.
    if (tab.pendingUrl) return { status: 'changed' };
    try {
      const result = await chrome.tabs.sendMessage(tab.id, { type: 'CAPTURE_CURRENT_JOB', expectedUrl }, { frameId: 0 });
      const current = await activeTab();
      if (current?.id !== tab.id || current.pendingUrl || currentBossJobUrl(current.url) !== expectedUrl) {
        return { status: 'changed' };
      }
      return result;
    } catch {
      return { status: expectedUrl ? 'unready' : 'unsupported' };
    }
  }

  async function action(callback) {
    if (busy) return;
    busy = true;
    render();
    try {
      await callback();
    } catch (error) {
      status(error?.message || '当前操作没有完成，请手动重试。');
    } finally {
      busy = false;
      render();
    }
  }

  el('quickCapture').addEventListener('click', () => action(async () => {
    draft = null;
    await chrome.storage.local.remove('quickSaveDraft');
    render();
    const tab = await activeTab();
    const expectedUrl = currentBossJobUrl(tab?.url);
    const isBoss = typeof tab?.url === 'string' && tab.url.startsWith('https://www.zhipin.com/');
    if (!isBoss || !Number.isInteger(tab.id)) return status(messages.unsupported);
    const result = await readCurrent(tab, expectedUrl);
    if (result?.status !== 'preview' || !expectedUrl || result.job?.url !== expectedUrl) {
      return status(messages[result?.status] || messages.unready);
    }
    draft = { tabId: tab.id, generatedAt: new Date().toISOString(), job: result.job };
    if (eligible(draft.job)) await chrome.storage.local.set({ quickSaveDraft: draft });
    status('仅生成了本机预览，尚未同步。');
  }));

  el('quickSync').addEventListener('click', () => action(async () => {
    if (!eligible(draft?.job)) return;
    const target = el('quickTarget').value;
    const tab = await activeTab();
    const expectedUrl = draft.job.url;
    if (tab?.id !== draft.tabId || currentBossJobUrl(tab.url) !== expectedUrl) return status(messages.changed);
    const result = await readCurrent(tab, expectedUrl);
    if (result?.status !== 'preview') return status(messages[result?.status] || messages.unready);
    if (JSON.stringify(result.job) !== JSON.stringify(draft.job)) {
      return status('页面内容已变化。请重新采集并核对后再同步。');
    }
    status('正在同步这条岗位到所选本机环境…');
    try {
      const saved = await JobLensSync.syncQuickReport(asReport(draft), target);
      receipt = { importId: saved.importId, target };
      await chrome.storage.local.set({ quickSaveReceipt: receipt }).catch(() => {});
      status(JobLensSync.formatSyncResult(saved));
    } catch {
      status('同步未确认。请检查所选本机服务和导入记录；草稿已保留，也可以下载 JSON 手工导入。');
    }
  }));

  el('quickDownload').addEventListener('click', () => action(async () => {
    if (!eligible(draft?.job)) return;
    const stamp = draft.generatedAt.replace(/[:.]/g, '-');
    await downloadData(`boss-job-filter-quick-v${VERSION}-${stamp}.json`, 'application/json',
      JSON.stringify(asReport(draft), null, 2));
  }));

  el('quickOpenImport').addEventListener('click', () => action(async () => {
    if (!receipt) return;
    await chrome.tabs.create({ url: JobLensSync.quickImportUrl(receipt.importId, receipt.target), active: true });
  }));

  async function initialize() {
    try {
      const { quickSaveDraft, quickSaveReceipt } = await chrome.storage.local.get(['quickSaveDraft', 'quickSaveReceipt']);
      if (eligible(quickSaveDraft?.job) && Number.isInteger(quickSaveDraft.tabId)
          && Number.isFinite(Date.parse(quickSaveDraft.generatedAt))) {
        draft = quickSaveDraft;
        status('已恢复上次草稿。同步前会重新核对当前页面。');
      }
      if (quickSaveReceipt) {
        JobLensSync.quickImportUrl(quickSaveReceipt.importId, quickSaveReceipt.target);
        receipt = quickSaveReceipt;
      }
    } catch {
      status('未能恢复上次快存记录；可重新采集。');
    } finally {
      busy = false;
      render();
    }
  }

  initialize();
})();
