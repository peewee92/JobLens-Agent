const VERSION = '1.4.8';
const MAX_SELECTED_CITIES = 20;
const DEFAULT_KEYWORDS = [
  'AI 应用开发工程师',
  'AI 应用开发',
  'AI Agent 工程师',
  '智能体开发工程师',
  '大模型应用开发工程师',
  'LLM 应用开发',
  'AI 产品工程师',
  'AI Product Engineer',
  'FDE',
  '前线部署工程师',
  'AI 前线部署工程师',
  'AI 交付工程师',
  'AI 实施工程师',
  'AI 解决方案工程师',
  '大模型 解决方案工程师',
  'Agent 开发',
  '多智能体',
  'RAG 开发工程师',
  'AI 研发工程师'
];

const CITY_DATA = globalThis.BossCityData;
const el = id => document.getElementById(id);
const selectedCities = new Map();
let activeProvince = '湖北';
let recentCityCodes = [];
let lastJobLensImportId = null;

function renderJobLensImportLink(importId) {
  lastJobLensImportId = typeof importId === 'string' && importId ? importId : null;
  el('openJobLensImport').hidden = !lastJobLensImportId;
}

function canonicalCity(raw) {
  if (!raw) return null;
  const city = CITY_DATA.byCode[String(raw.code || '')] || CITY_DATA.byName[String(raw.name || '')];
  return city ? { name: city.name, code: city.code, province: city.province } : null;
}

function setSelectedCities(cities) {
  selectedCities.clear();
  for (const raw of cities || []) {
    const city = canonicalCity(raw);
    if (city && selectedCities.size < MAX_SELECTED_CITIES) selectedCities.set(city.code, city);
  }
  renderAllCityUi();
}

function toggleCity(cityRaw) {
  const city = canonicalCity(cityRaw);
  if (!city) return;
  if (selectedCities.has(city.code)) {
    selectedCities.delete(city.code);
  } else if (selectedCities.size >= MAX_SELECTED_CITIES) {
    el('status').textContent = `最多同时选择 ${MAX_SELECTED_CITIES} 个城市。`;
    return;
  } else {
    selectedCities.set(city.code, city);
  }
  renderAllCityUi();
}

function cityButton(city, extraClass = '') {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = `city-button ${extraClass}`.trim();
  button.textContent = city.name;
  button.title = `${city.province} · BOSS 城市编码 ${city.code}`;
  button.dataset.code = city.code;
  if (selectedCities.has(city.code)) button.classList.add('selected');
  button.addEventListener('click', () => toggleCity(city));
  return button;
}

function renderSelectedCities() {
  const container = el('selectedCities');
  container.textContent = '';
  if (!selectedCities.size) {
    const placeholder = document.createElement('span');
    placeholder.className = 'selected-placeholder';
    placeholder.textContent = '未选择城市；可仅运行“全国远程”。';
    container.appendChild(placeholder);
  } else {
    for (const city of selectedCities.values()) {
      const chip = document.createElement('span');
      chip.className = 'city-chip';
      const name = document.createElement('span');
      name.textContent = city.name;
      const province = document.createElement('small');
      province.textContent = city.province === city.name ? '' : city.province;
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'chip-remove';
      remove.textContent = '×';
      remove.title = `移除${city.name}`;
      remove.addEventListener('click', () => toggleCity(city));
      chip.append(name);
      if (province.textContent) chip.append(province);
      chip.append(remove);
      container.appendChild(chip);
    }
  }
  el('selectedCount').textContent = `已选 ${selectedCities.size}/${MAX_SELECTED_CITIES}`;
}

function renderHotCities() {
  const container = el('hotCities');
  container.textContent = '';
  for (const city of CITY_DATA.hotCities) container.appendChild(cityButton(city));
}

function renderRecentCities() {
  const recent = recentCityCodes
    .map(code => CITY_DATA.byCode[code])
    .filter(Boolean)
    .slice(0, 8);
  const section = el('recentSection');
  section.hidden = recent.length === 0;
  const container = el('recentCities');
  container.textContent = '';
  for (const city of recent) container.appendChild(cityButton(city));
}

function renderProvinceList() {
  const container = el('provinceList');
  container.textContent = '';
  for (const province of CITY_DATA.provinces) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'province-button';
    button.textContent = province.name;
    if (province.name === activeProvince) button.classList.add('active');
    button.addEventListener('click', () => {
      activeProvince = province.name;
      el('citySearch').value = '';
      renderProvinceList();
      renderCityList();
    });
    container.appendChild(button);
  }
}

function normalizedSearchText(value = '') {
  return String(value).trim().toLocaleLowerCase('zh-CN').replace(/[省市区县\s]/g, '');
}

function searchCities(query) {
  const normalized = normalizedSearchText(query);
  if (!normalized) return null;
  return CITY_DATA.cities.filter(city => {
    const haystacks = [city.name, city.province, ...(city.aliases || [])].map(normalizedSearchText);
    return haystacks.some(value => value.includes(normalized));
  });
}

function renderCityList() {
  const query = el('citySearch').value;
  const matches = searchCities(query);
  const province = CITY_DATA.provinces.find(item => item.name === activeProvince) || CITY_DATA.provinces[0];
  const cities = matches || province.cities;
  el('activeProvinceName').textContent = matches ? `搜索“${query.trim()}”` : province.name;
  el('cityResultCount').textContent = `${cities.length} 个城市`;
  el('provinceList').style.display = matches ? 'none' : '';
  el('cityList').parentElement.parentElement.style.gridTemplateColumns = matches ? '1fr' : '';

  const container = el('cityList');
  container.textContent = '';
  if (!cities.length) {
    const empty = document.createElement('div');
    empty.className = 'empty-result';
    empty.textContent = '没有找到匹配城市';
    container.appendChild(empty);
    return;
  }
  for (const city of cities) container.appendChild(cityButton(city));
}

function updateTaskEstimate() {
  const keywordCount = el('keywords').value.split('\n').map(value => value.trim()).filter(Boolean).length;
  const scopeCount = selectedCities.size + (el('remote').checked ? 1 : 0);
  const pages = Math.max(1, Number(el('pagesPerQuery').value || 1));
  const taskCount = keywordCount * scopeCount;
  const maxPages = taskCount * pages;
  const estimate = el('taskEstimate');
  estimate.textContent = `预计：${keywordCount} 个搜索词 × ${scopeCount} 个范围 = ${taskCount} 组搜索，最多 ${maxPages} 页。`;
  estimate.classList.toggle('warning', maxPages > 200);
  updateSearchGuidance();
}

function updateSearchGuidance() {
  const cityNames = [...selectedCities.values()].map(city => city.name);
  const remoteEnabled = el('remote').checked;
  const coverage = [];
  if (cityNames.length) coverage.push(`${cityNames.join('、')}的线下/本地岗位`);
  if (remoteEnabled) coverage.push('全国明确支持远程的岗位');
  const coverageSuffix = remoteEnabled
    ? '不会包含未选择城市的线下岗位；“全国远程”不等于“全国所有岗位”。'
    : '不会包含未选择城市的岗位。';
  el('coverageSummary').textContent = `${coverage.length ? `本次会搜索：${coverage.join(' + ')}。` : '当前没有可执行的搜索范围。'}${coverageSuffix}`;

  const hints = [];
  const pages = Math.max(1, Number(el('pagesPerQuery').value || 1));
  const salary = Math.max(1, Number(el('minSalaryK').value || 1));
  const relevance = Math.max(0, Number(el('minRelevanceScore').value || 0));
  const detailLimit = Math.max(0, Number(el('detailLimit').value || 0));

  if (cityNames.length === 0 && remoteEnabled) {
    hints.push('没有选择线下城市，现在只会留下全国远程岗位。');
  } else if (cityNames.length === 1) {
    hints.push(`线下岗位目前只搜 ${cityNames[0]}；如果也接受其他城市，需要手动添加城市。`);
  }
  if (pages <= 1) {
    hints.push('每个关键词只搜 1 页，覆盖会明显偏少；一般建议 2–3 页。');
  }
  if (el('salaryMode').value === 'minGte') {
    hints.push(`当前按最低薪资严格过滤（门槛 ${salary}K）；例如门槛 13K 时，12–20K 也会被排除。`);
  }
  if (relevance >= 40) {
    hints.push(`搜索词匹配门槛 ${relevance} 分比较严格，可能漏掉标题写法不同但实际相关的岗位。`);
  } else if (relevance > 20) {
    hints.push(`搜索词匹配门槛 ${relevance} 分高于推荐值 20，结果会更少。`);
  }
  if (remoteEnabled && el('remotePolicy').value === 'cardOnly') {
    hints.push('全国远程目前只看列表卡片；详情里才写“可远程”的岗位可能被漏掉。');
  }
  if (remoteEnabled && el('remotePolicy').value === 'cardOrDetail' && el('detailMode').value === 'off') {
    hints.push('你关闭了详情补采，卡片没写清远程的岗位无法继续确认。');
  } else if (remoteEnabled && el('remotePolicy').value === 'cardOrDetail' && detailLimit < 20) {
    hints.push(`详情页上限只有 ${detailLimit}，较低时可能有远程候选来不及确认。`);
  }
  if (el('smartStop').value === 'true' && pages > 1) {
    hints.push('开启了“没有新岗位就提前停止”，遇到重复页时可能不会扫满你设置的页数。');
  }
  const exclusions = [
    el('excludePartTime').checked ? '兼职/日结' : '',
    el('excludeIntern').checked ? '实习' : '',
    el('excludeAssistant').checked ? '助理' : ''
  ].filter(Boolean);
  if (exclusions.length) hints.push(`已主动排除：${exclusions.join('、')}。`);
  if (!hints.length) hints.push('当前配置偏平衡；如果结果仍少，主要取决于 BOSS 的真实岗位供给和关键词本身。');

  const list = el('scarcityHints');
  list.textContent = '';
  for (const hint of hints) {
    const item = document.createElement('li');
    item.textContent = hint;
    list.appendChild(item);
  }
}

function renderAllCityUi() {
  renderSelectedCities();
  renderHotCities();
  renderRecentCities();
  renderProvinceList();
  renderCityList();
  updateTaskEstimate();
}

async function downloadData(filename, mime, text) {
  const blob = new Blob([text], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  try {
    await chrome.downloads.download({ url, filename, saveAs: true });
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 30_000);
  }
}

function migratedCities(config) {
  if (Array.isArray(config?.selectedCities)) {
    return config.selectedCities.map(canonicalCity).filter(Boolean);
  }
  if (config?.scopes?.wuhan === false) return [];
  return [CITY_DATA.defaultCity];
}

async function loadState() {
  const { lastConfig, lastRun, recentCityCodes: storedRecent, lastJobLensImportId: storedImportId } = await chrome.storage.local.get([
    'lastConfig', 'lastRun', 'recentCityCodes', 'lastJobLensImportId'
  ]);
  const config = lastConfig || {};
  recentCityCodes = Array.isArray(storedRecent) ? storedRecent.filter(code => CITY_DATA.byCode[code]) : [];
  el('keywords').value = (config.keywords || DEFAULT_KEYWORDS).join('\n');
  setSelectedCities(migratedCities(config));
  el('remote').checked = config.scopes?.remote ?? true;
  el('minSalaryK').value = config.minSalaryK ?? 14;
  el('salaryMode').value = config.salaryMode || 'minGte';
  el('pagesPerQuery').value = config.pagesPerQuery ?? 2;
  el('remotePolicy').value = config.remotePolicy || 'cardOrDetail';
  el('detailMode').value = config.version === VERSION ? (config.detailMode || 'matched') : 'matched';
  el('detailLimit').value = config.detailLimit ?? 40;
  el('minRelevanceScore').value = config.minRelevanceScore ?? 20;
  el('smartStop').value = String(config.smartStop ?? true);
  el('excludePartTime').checked = config.excludePartTime ?? true;
  el('excludeIntern').checked = config.excludeIntern ?? false;
  el('excludeAssistant').checked = config.excludeAssistant ?? false;
  activeProvince = [...selectedCities.values()][0]?.province || '湖北';
  renderAllCityUi();
  renderJobLensImportLink(storedImportId);

  if (lastRun?.jobs) {
    const counts = lastRun.diagnostics?.counts;
    el('status').textContent = counts
      ? `上次：原始 ${counts.rawCards}，薪资解析 ${counts.salaryParsed}，字体解码 ${counts.salaryDecodedFromPua}，最终 ${counts.finalAfterCrossScopeDedupe}。`
      : `上次完成：${lastRun.jobs.length} 条。`;
  }
}

el('openCityPicker').addEventListener('click', () => {
  el('cityPicker').hidden = false;
  el('citySearch').focus();
});
el('closeCityPicker').addEventListener('click', () => { el('cityPicker').hidden = true; });
el('confirmCities').addEventListener('click', () => { el('cityPicker').hidden = true; });
el('resetCities').addEventListener('click', () => {
  activeProvince = '湖北';
  el('citySearch').value = '';
  setSelectedCities([CITY_DATA.defaultCity]);
});
el('citySearch').addEventListener('input', renderCityList);
el('clearCitySearch').addEventListener('click', () => {
  el('citySearch').value = '';
  renderCityList();
  el('citySearch').focus();
});
el('keywords').addEventListener('input', updateTaskEstimate);
el('pagesPerQuery').addEventListener('input', updateTaskEstimate);
el('remote').addEventListener('change', updateTaskEstimate);
for (const id of [
  'minSalaryK', 'salaryMode', 'minRelevanceScore', 'remotePolicy', 'detailMode',
  'detailLimit', 'smartStop', 'excludePartTime', 'excludeIntern', 'excludeAssistant'
]) {
  el(id).addEventListener(['minSalaryK', 'minRelevanceScore', 'detailLimit'].includes(id) ? 'input' : 'change', updateSearchGuidance);
}

el('start').addEventListener('click', async () => {
  const keywords = el('keywords').value.split('\n').map(value => value.trim()).filter(Boolean);
  if (!keywords.length) {
    el('status').textContent = '至少填写一个搜索词。';
    return;
  }
  if (!selectedCities.size && !el('remote').checked) {
    el('status').textContent = '至少选择一个工作城市，或开启“全国远程”。';
    return;
  }

  const cities = [...selectedCities.values()];
  const selectedCodes = cities.map(city => city.code);
  recentCityCodes = [...new Set([...selectedCodes, ...recentCityCodes])].slice(0, 12);
  const config = {
    version: VERSION,
    keywords,
    selectedCities: cities,
    scopes: { cities: cities.length > 0, remote: el('remote').checked },
    cityCodes: { nationwide: CITY_DATA.nationwide.code },
    cityDataVersion: CITY_DATA.version,
    minSalaryK: Number(el('minSalaryK').value || 14),
    salaryMode: el('salaryMode').value,
    pagesPerQuery: Number(el('pagesPerQuery').value || 2),
    remotePolicy: el('remotePolicy').value,
    detailMode: el('detailMode').value,
    detailLimit: Number(el('detailLimit').value || 0),
    minRelevanceScore: Number(el('minRelevanceScore').value || 0),
    smartStop: el('smartStop').value === 'true',
    excludePartTime: el('excludePartTime').checked,
    excludeIntern: el('excludeIntern').checked,
    excludeAssistant: el('excludeAssistant').checked,
    delayMinMs: 3500,
    delayMaxMs: 6500
  };

  await chrome.storage.local.set({ pendingConfig: config, lastConfig: config, recentCityCodes });
  await chrome.tabs.create({ url: chrome.runtime.getURL('runner.html'), active: true });
  window.close();
});

el('downloadCsv').addEventListener('click', async () => {
  const { lastRun } = await chrome.storage.local.get('lastRun');
  if (!lastRun?.csv) return void (el('status').textContent = '还没有可下载的结果。');
  await downloadData(lastRun.csvFilename || 'boss-job-filter.csv', 'text/csv', lastRun.csv);
});

el('downloadJson').addEventListener('click', async () => {
  const { lastRun } = await chrome.storage.local.get('lastRun');
  if (!lastRun?.json) return void (el('status').textContent = '还没有完整报告。');
  await downloadData(lastRun.jsonFilename || 'boss-job-filter-report.json', 'application/json', lastRun.json);
});

el('syncJobLens').addEventListener('click', async () => {
  const button = el('syncJobLens');
  const { lastRun } = await chrome.storage.local.get('lastRun');
  let report;
  try {
    report = JobLensSync.parseReport(lastRun);
  } catch (error) {
    el('status').textContent = error?.message || '还没有可同步的完整报告。';
    return;
  }

  button.disabled = true;
  el('status').textContent = '正在同步到本机 JobLens…';
  try {
    const result = await JobLensSync.syncReport(report);
    const importId = result?.importId;
    JobLensSync.buildImportDetailUrl(importId);
    await chrome.storage.local.set({ lastJobLensImportId: importId });
    renderJobLensImportLink(importId);
    el('status').textContent = `${JobLensSync.formatSyncResult(result)} 可直接查看这次导入。`;
  } catch (error) {
    el('status').textContent = `${error?.message || '同步失败。'} 可继续使用“完整报告”JSON 手工导入。`;
  } finally {
    button.disabled = false;
  }
});

el('openJobLensImport').addEventListener('click', async () => {
  if (!lastJobLensImportId) return;
  await chrome.tabs.create({ url: JobLensSync.buildImportDetailUrl(lastJobLensImportId), active: true });
});

el('downloadDiagnostics').addEventListener('click', async () => {
  const { lastRun } = await chrome.storage.local.get('lastRun');
  if (!lastRun?.diagnosticJson) return void (el('status').textContent = '还没有诊断文件。');
  await downloadData(lastRun.diagnosticFilename || 'boss-job-filter-diagnostics.json', 'application/json', lastRun.diagnosticJson);
});

el('downloadRequirementReview').addEventListener('click', async () => {
  const { lastRun } = await chrome.storage.local.get('lastRun');
  if (!lastRun?.requirementReviewJson) {
    return void (el('status').textContent = '还没有 Requirement 验收数据，请先用 v1.4.8 重新采集。');
  }
  await downloadData(
    lastRun.requirementReviewFilename || 'boss-job-filter-requirement-review.json',
    'application/json',
    lastRun.requirementReviewJson
  );
});

loadState();
