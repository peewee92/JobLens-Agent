(() => {
  'use strict';

  const {
    currentBossJobUrl,
    clean,
    cleanMultiline,
    decodeBossText,
    decodeBossMultilineText,
    extractJobDescriptionSegment,
    assessDescriptionQuality,
    findSalaryInText,
    parseSalary,
    inferDigitMap,
    detectRemote,
    parseRecruiterActivity,
    extractSkills
  } = globalThis.BossJobFilterLib;

  const TEXT_ATTRS = [
    'aria-label',
    'title',
    'data-salary',
    'data-job-salary',
    'data-pay',
    'data-wage',
    'data-label',
    'data-text'
  ];

  function getElementText(element, digitMap = {}) {
    if (!element) return '';
    const values = [];
    const seen = new Set();
    const push = raw => {
      const value = decodeBossText(raw || '', digitMap).text;
      if (!value || seen.has(value)) return;
      seen.add(value);
      values.push(value);
    };
    push(element.innerText || element.textContent);
    for (const attr of TEXT_ATTRS) push(element.getAttribute?.(attr));
    return clean(values.join(' '));
  }

  function getElementMultilineText(element, digitMap = {}) {
    if (!element) return '';
    const raw = element.innerText || element.textContent || '';
    return decodeBossMultilineText(raw, digitMap).text;
  }

  function pickText(root, selectors, digitMap = {}) {
    for (const selector of selectors) {
      const element = root.querySelector(selector);
      const text = getElementText(element, digitMap);
      if (text) return text;
    }
    return '';
  }

  function collectText(root, selectors, digitMap = {}) {
    const values = [];
    for (const selector of selectors) {
      for (const element of root.querySelectorAll(selector)) {
        const text = getElementText(element, digitMap);
        if (text && !values.includes(text)) values.push(text);
      }
    }
    return values.join(' / ');
  }

  function collectAttributeCandidates(root, digitMap = {}) {
    const values = [];
    const elements = [root, ...root.querySelectorAll('*')].slice(0, 350);
    for (const element of elements) {
      for (const attr of element.getAttributeNames?.() || []) {
        if (!/(salary|pay|wage|money|price|label|title|text|aria)/i.test(attr)) continue;
        const raw = element.getAttribute(attr);
        const decoded = decodeBossText(raw || '', digitMap).text;
        if (decoded && !values.includes(decoded)) values.push(decoded);
      }
    }
    return values;
  }

  function findSalaryWithSource({ title, rawText, card, digitMap }) {
    const sources = [];
    const push = (source, value) => {
      const salary = findSalaryInText(value, digitMap);
      if (salary && !sources.some(item => item.salary === salary)) sources.push({ source, salary });
    };

    push('title', title);

    const selectors = [
      '.job-salary',
      '.salary',
      '[class*="job-salary"]',
      '[class~="salary"]',
      '[class$="salary"]',
      '[class*="salary"]',
      '[class*="pay"]',
      '[class*="wage"]'
    ];
    for (const selector of selectors) {
      for (const element of card.querySelectorAll(selector)) {
        push(`selector:${selector}`, getElementText(element, digitMap));
      }
    }

    for (const candidate of collectAttributeCandidates(card, digitMap)) push('attribute', candidate);
    push('cardTextDecoded', rawText);

    return {
      salary: sources[0]?.salary || '',
      salarySource: sources[0]?.source || 'none',
      salaryCandidates: sources.slice(0, 8)
    };
  }

  function escapeRegExp(value = '') {
    return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function findAreaInText(text = '', digitMap = {}, meta = {}) {
    const normalized = decodeBossText(text, digitMap).text;
    const cityName = clean(meta.cityName || (meta.scopeType === 'city' ? meta.scope : ''));
    const patterns = [];
    if (cityName) {
      patterns.push(new RegExp(`(${escapeRegExp(cityName)}(?:市)?(?:[·\\-\\s][\u4e00-\u9fa5]{1,16}){0,3})`));
    }
    patterns.push(
      /([\u4e00-\u9fa5]{2,10}(?:市)?[·][\u4e00-\u9fa5]{1,16}(?:[·][\u4e00-\u9fa5]{1,16}){0,2})/,
      /(全国|不限地点|远程办公|居家办公|全远程)/
    );
    for (const pattern of patterns) {
      const match = normalized.match(pattern);
      if (match) return clean(match[0]);
    }
    return '';
  }

  function learnPageDigitMap(cards, initialMap = {}) {
    let map = { ...(initialMap || {}) };
    for (const card of cards) {
      const rawText = clean(card.innerText || card.textContent);
      const title = clean(card.querySelector('.job-name, .job-title, [class*="job-name"], [class*="job-title"]')?.textContent);
      map = inferDigitMap(title, rawText, map);
    }
    return map;
  }

  const RECOMMENDATIONS = '.recommend-job, .job-recommend, .similar-job, aside';
  const VERIFICATION_TEXT = /安全验证|请完成验证|滑动验证|访问过于频繁|异常访问|系统检测到异常/;
  const visible = node => node.getClientRects().length > 0
    && !node.closest('[hidden], [aria-hidden="true"]')
    && getComputedStyle(node).visibility === 'visible';
  const allVisible = (root, selector) => [...root.querySelectorAll(selector)].filter(visible);
  const visibleText = node => clean(node?.innerText || '');

  function hasBlockingOverlay() {
    return VERIFICATION_TEXT.test(document.title) || /登录后查看职位/.test(document.title)
      || /^\/web\/user(?:\/(?:login|register))?\/?$|^\/(?:wapi\/)?(?:security|captcha)(?:\/|$)/i.test(location.pathname)
      || allVisible(document, '.geetest_panel, .captcha-container, .security-check, #captcha, .login-dialog, .login-modal, .job-login-mask').length > 0
      || allVisible(document, '[role="dialog"], .boss-popup__title').some(node =>
        VERIFICATION_TEXT.test(visibleText(node)) || /请登录|登录后/.test(visibleText(node)));
  }

  async function autoScroll() {
    const maxSteps = 8;
    let previousHeight = 0;
    for (let i = 1; i <= maxSteps; i += 1) {
      const height = document.body.scrollHeight;
      window.scrollTo(0, Math.floor(height * i / maxSteps));
      await new Promise(resolve => setTimeout(resolve, 380));
      if (height === previousHeight && i >= 5) break;
      previousHeight = height;
    }
    window.scrollTo(0, 0);
    await new Promise(resolve => setTimeout(resolve, 700));
  }

  // 页脚/导航里存在 href="/job_detail/" 的空锚点，它的最近祖先是整块站点导航，
  // 会被当成一条岗位抓进来（实测导出了 title=职位搜索 的假卡片）。
  const JOB_DETAIL_HREF = /\/job_detail\/[A-Za-z0-9~_-]{6,}\.html/;

  function isJobDetailHref(href = '') {
    return JOB_DETAIL_HREF.test(String(href ?? '').split('?')[0]);
  }

  function getCardForAnchor(anchor) {
    return anchor.closest(
      '.job-card-wrapper, .job-card-box, li, article, [class*="job-card"]'
    ) || anchor.parentElement;
  }

  function extractList(meta = {}, initialDigitMap = {}) {
    const pageFailure = (pageState, issue = '') => ({ jobs: [], pageState, issue, blocked: pageState === 'blocked' });
    if (hasBlockingOverlay()) return pageFailure('blocked');
    const params = new URL(location.href).searchParams;
    if (location.origin !== 'https://www.zhipin.com' || location.pathname !== '/web/geek/jobs'
      || params.get('query') !== meta.searchQuery || params.get('city') !== String(meta.cityCode)
      || Number(params.get('page') || 1) !== meta.page) return pageFailure('unready', 'search_context_mismatch');

    const lists = allVisible(document, '.job-list-box').filter(node => !node.closest(RECOMMENDATIONS));
    if (document.readyState === 'loading' || lists.length !== 1) return pageFailure('unready', 'main_list_unavailable');
    const list = lists[0];
    // Observe standard semantics when supplied. Do not infer the active page
    // from the URL or guess site-specific controls.
    const activePages = allVisible(list.closest('main') || list.parentElement || list, 'nav [aria-current="page"]').filter(node => !node.closest(RECOMMENDATIONS));
    const activePage = activePages.length === 1 ? activePages[0] : null;
    const label = visibleText(activePage);
    const observedPage = /^\d{1,3}$/.test(label) && Number(label) > 0 ? Number(label) : null;
    const next = observedPage !== null ? activePage.closest('nav')?.querySelector('[rel~="next"]') : null;
    const lastPage = Boolean(next && visible(next)
      && (next.disabled === true || next.getAttribute('aria-disabled') === 'true'));

    const selectors = {
      title: ['.job-name', '.job-title', '[class*="job-name"]', '[class*="job-title"]'],
      area: [
        '.job-area',
        '.job-location',
        '.company-location',
        '[class*="job-area"]',
        '[class*="job-location"]',
        '[class*="company-location"]'
      ],
      company: ['.company-name', '[class*="company-name"]', '.boss-name', '[class*="company"] a'],
      tags: [
        '.tag-list span',
        '.job-info span',
        '[class*="tag-list"] span',
        '[class*="job-info"] span',
        '[class*="tag"]'
      ]
    };

    const anchors = allVisible(list, 'a[href*="/job_detail/"]').filter(anchor =>
      !anchor.closest(RECOMMENDATIONS) && currentBossJobUrl(anchor.href));
    const cardFor = new Map(anchors.map(anchor => [anchor, getCardForAnchor(anchor)]).filter(([, card]) =>
      card && card !== list && list.contains(card)));
    const cards = [...new Set(cardFor.values())];
    const digitMap = learnPageDigitMap(cards, initialDigitMap);
    const seen = new Set();
    const jobs = [];
    let puaCards = 0;
    let decodedCharacters = 0;

    for (const anchor of anchors) {
      const url = currentBossJobUrl(anchor.href);
      if (seen.has(url)) continue;
      const card = cardFor.get(anchor);
      if (!card) continue;

      const originalRawText = clean(card.innerText || card.textContent);
      const decoded = decodeBossText(originalRawText, digitMap);
      const rawText = decoded.text;
      if (!rawText) continue;
      if (decoded.hadPua) puaCards += 1;
      decodedCharacters += decoded.decodedCount;

      let title = pickText(card, selectors.title, digitMap) || getElementText(anchor, digitMap);
      let area = pickText(card, selectors.area, digitMap);
      const company = pickText(card, selectors.company, digitMap);
      const tags = collectText(card, selectors.tags, digitMap);
      const salaryResult = findSalaryWithSource({ title, rawText, card, digitMap });

      if (!area || area.length > 100) area = findAreaInText(rawText, digitMap, meta);
      if (!title || title.length > 140) {
        const chunks = rawText.split(/\s{2,}|\n/).map(clean).filter(Boolean);
        title = chunks.find(chunk => (
          chunk.length <= 90
          && !findSalaryInText(chunk, digitMap)
          && !/(经验|学历|公司|招聘者|远程)/.test(chunk)
          && !(meta.cityName && chunk.includes(meta.cityName))
        )) || title;
      }
      if (!title) continue;

      const experience = (rawText.match(/(经验不限|在校\/应届|应届生|1年以内|1-3年|3-5年|5-10年|10年以上)/) || [])[1] || '';
      const education = (rawText.match(/(学历不限|初中及以下|中专\/中技|高中|大专|本科|硕士|博士)/) || [])[1] || '';
      const remote = detectRemote({ title, area, tags, rawText });
      const recruiterActive = parseRecruiterActivity(rawText).label;

      seen.add(url);
      jobs.push({
        ...meta,
        title,
        salary: salaryResult.salary,
        salarySource: salaryResult.salarySource,
        salaryCandidates: salaryResult.salaryCandidates,
        area,
        company,
        experience,
        education,
        tags,
        remoteMatched: remote.matched,
        remoteStatus: remote.status,
        remoteConfidence: remote.confidence,
        remoteEvidence: remote.evidence,
        recruiterActive,
        url,
        rawText,
        originalRawText,
        puaDecodedCount: decoded.decodedCount,
        collectedAt: new Date().toISOString()
      });
    }

    const pageDecoded = decodeBossText(visibleText(list), digitMap);
    const explicitEmpty = anchors.length === 0
      && /^(?:暂无(?:相关)?(?:职位|岗位)|未找到(?:相关)?(?:职位|岗位)|没有找到(?:相关)?(?:职位|岗位))[。！!]?$/.test(pageDecoded.text);
    const blocked = anchors.length === 0 && VERIFICATION_TEXT.test(pageDecoded.text);
    return {
      jobs: blocked ? [] : jobs,
      digitMap,
      blocked,
      pageState: blocked ? 'blocked' : jobs.length ? 'read' : explicitEmpty ? 'no_results' : 'unready',
      issue: !jobs.length && !explicitEmpty && !blocked ? 'no_readable_cards' : '',
      observedPage,
      lastPage,
      salarySamples: jobs.map(job => `${job.salary || '空'} [${job.salarySource}]`).slice(0, 8),
      extraction: {
        anchors: anchors.length,
        uniqueCards: cards.length,
        puaCards,
        decodedCharacters,
        unknownPua: pageDecoded.unknownPua
      }
    };
  }

  const DESCRIPTION_SELECTOR_RULES = [
    { selector: '.job-detail-section .job-sec-text', trust: 'trusted' },
    { selector: '.job-sec-text', trust: 'trusted' },
    { selector: '[class*="job-sec-text"]', trust: 'trusted' },
    { selector: '[class*="job-description"]', trust: 'trusted' },
    { selector: '[class*="detail-content"]', trust: 'trusted' },
    { selector: '.job-detail-section', trust: 'broad' },
    { selector: '.job-detail', trust: 'broad' },
    { selector: '[class*="job-detail"]', trust: 'broad' }
  ];

  function chooseDescriptionCandidate(digitMap = {}, bodyText = '') {
    const candidates = [];
    for (const rule of DESCRIPTION_SELECTOR_RULES) {
      for (const element of document.querySelectorAll(rule.selector)) {
        const rawText = getElementMultilineText(element, digitMap);
        if (!rawText) continue;
        const segment = extractJobDescriptionSegment(rawText);
        if (!segment.text) continue;
        const source = `selector:${rule.selector}`;
        const quality = assessDescriptionQuality({
          description: segment.text,
          descriptionSource: source,
          descriptionSelectorTrust: rule.trust,
          descriptionSanitized: segment.sanitized,
          detailAttempted: true,
          detailSucceeded: true
        });
        const score = (quality.requirementReviewEligible ? 1_000_000 : 0)
          + (rule.trust === 'trusted' ? 100_000 : 0)
          - quality.descriptionNoiseCount * 50_000
          + Math.min(quality.descriptionLength, 30_000);
        candidates.push({
          description: segment.text,
          descriptionSource: source,
          descriptionSelectorTrust: rule.trust,
          descriptionSanitized: segment.sanitized,
          descriptionStartMarker: segment.startMarker,
          descriptionStopMarker: segment.stopMarker,
          score
        });
      }
    }

    if (candidates.length) {
      return candidates.sort((left, right) => right.score - left.score)[0];
    }

    const fallback = extractJobDescriptionSegment(bodyText.slice(0, 30000));
    return {
      description: fallback.text,
      descriptionSource: 'body_fallback',
      descriptionSelectorTrust: 'fallback',
      descriptionSanitized: fallback.sanitized,
      descriptionStartMarker: fallback.startMarker,
      descriptionStopMarker: fallback.stopMarker,
      score: 0
    };
  }

  function extractDetail(meta = {}, digitMap = {}) {
    if (hasBlockingOverlay()) return { blocked: true };
    if (!meta.url || currentBossJobUrl(location.href) !== meta.url || document.readyState === 'loading') {
      return { error: '岗位详情尚未就绪或地址已变化' };
    }
    const bodyOriginal = cleanMultiline(document.body?.innerText || document.body?.textContent || '');
    const bodyDecoded = decodeBossMultilineText(bodyOriginal, digitMap);
    const bodyText = bodyDecoded.text;
    if (VERIFICATION_TEXT.test(bodyText) && !document.querySelector('.job-detail-section, .job-sec-text')) {
      return { blocked: true };
    }
    const selectedDescription = chooseDescriptionCandidate(digitMap, bodyText);
    const description = selectedDescription.description;

    const salary = findSalaryInText(bodyText, digitMap);
    // Remote status must come from bounded job evidence. The full page body also
    // contains recommended jobs and operational phrases such as remote monitoring.
    const remote = detectRemote({ description });
    const publishedAt = (bodyText.match(/(?:发布于|更新于|最近更新)\s*([^\s]{2,20})/) || [])[1] || '';
    const recruiterActive = parseRecruiterActivity(bodyText).label;
    const skills = extractSkills({ description, detailText: bodyText });

    return {
      ...meta,
      salary,
      description: description.slice(0, 30000),
      descriptionSource: selectedDescription.descriptionSource,
      descriptionSelectorTrust: selectedDescription.descriptionSelectorTrust,
      descriptionSanitized: selectedDescription.descriptionSanitized,
      descriptionStartMarker: selectedDescription.descriptionStartMarker,
      descriptionStopMarker: selectedDescription.descriptionStopMarker,
      detailText: bodyText.slice(0, 50000),
      remoteMatched: remote.matched,
      remoteStatus: remote.status,
      remoteConfidence: remote.confidence,
      remoteEvidence: remote.evidence,
      publishedAt,
      recruiterActive,
      skills,
      puaDecodedCount: bodyDecoded.decodedCount,
      blocked: false,
      title: document.title,
      collectedAt: new Date().toISOString()
    };
  }

  // Quick save is intentionally separate from bulk scraping: it never scans
  // the whole body, scrolls, or joins a search card to a different document.
  function captureCurrentJob(expectedUrl) {
    const all = allVisible;
    const pageUrl = currentBossJobUrl(location.href);
    if (hasBlockingOverlay()) return { status: 'blocked' };
    if (!expectedUrl) return { status: 'unsupported' };
    if (pageUrl !== expectedUrl) return { status: 'changed' };
    if (document.readyState === 'loading') return { status: 'unready' };

    const recommended = '.recommend-job, .job-recommend, .job-card-wrapper, .job-card-box, .similar-job, aside';
    const banners = all(document, '.job-banner').filter(node => !node.closest(recommended));
    const descriptions = all(document, '.job-detail-section .job-sec-text, .job-detail .job-sec-text')
      .filter(node => !node.closest(recommended));
    if (banners.length > 1 || descriptions.length > 1) return { status: 'conflict' };
    if (!banners.length) return { status: 'unready' };
    const banner = banners[0];
    const identities = [
      ...document.querySelectorAll('link[rel="canonical"]'),
      ...all(banner, 'a[href*="/job_detail/"]')
    ];
    if (identities.some(node => currentBossJobUrl(node.href) !== pageUrl)) return { status: 'conflict' };
    const titles = all(banner, 'h1');
    const companies = [...new Set(all(document, [
      '.sider-company .company-info a[href*="/gongsi/"]',
      '.sider-company .company-info .company-name',
      '.job-banner .company-name',
      '.job-detail .company-info a[href*="/gongsi/"]'
    ].join(', ')).filter(node => !node.closest('.recommend-job, .job-recommend, .job-card-wrapper, .job-card-box, .similar-job'))
      .map(visibleText).filter(Boolean))];
    if (titles.length > 1 || companies.length > 1) return { status: 'conflict' };
    const title = visibleText(titles[0]);
    const company = companies[0] || '';
    if (!title || !company || title.normalize('NFKC').length > 255 || company.normalize('NFKC').length > 255) {
      return { status: 'unready' };
    }

    const node = descriptions[0];
    if (node && all(node, recommended).length) return { status: 'conflict' };
    const section = node?.closest('.job-detail-section') || node;
    const layout = node ? getComputedStyle(node) : null;
    const raw = decodeBossMultilineText(node?.innerText || '').text;
    const folded = Boolean(node && (
      node.closest('.job-sec-text.is-collapsed, .job-sec-text.collapsed')
      || (node.scrollHeight > node.clientHeight && (Number(layout.webkitLineClamp) > 0 || /^(?:hidden|clip)$/.test(layout.overflowY)))
      || all(section, 'a, button, [role="button"], .show-more, .expand-btn, .text-more').some(control =>
        /^(?:展开(?:全文|全部|更多|职位描述)?|查看(?:完整|全部|更多)(?:职位|岗位)?描述|查看全文|显示更多)[\s›»>]*$/.test(visibleText(control)))
    ));
    const segment = extractJobDescriptionSegment(
      raw.replace(/\n\s*(?:展开全文|查看全文|显示更多|收起)\s*$/u, '')
    );
    const cropped = segment.text.length > 30_000;
    const description = segment.text.slice(0, 30_000);
    const provenance = {
      descriptionSource: node ? 'selector:.job-sec-text' : '',
      descriptionSelectorTrust: node ? 'trusted' : '',
      descriptionSanitized: segment.sanitized,
      descriptionStartMarker: segment.startMarker,
      descriptionStopMarker: segment.stopMarker,
      detailAttempted: true,
      detailSucceeded: Boolean(node && raw)
    };
    const quality = assessDescriptionQuality({ description, ...provenance });
    if (folded || cropped) {
      quality.descriptionQuality = description ? 'partial_jd' : 'unavailable';
      quality.requirementReviewEligible = false;
      quality.requirementReviewIneligibilityReasons = [
        folded ? 'visible_description_folded' : 'description_capture_limit', 'missing_full_jd'
      ];
    }
    const areaText = visibleText(all(banner, '.job-info .text-city, .job-info .job-area, .job-info .job-location')[0]);
    const area = areaText && areaText.normalize('NFKC').length <= 255 ? areaText : null;
    const salaryText = visibleText(all(banner, '.name .salary, .job-salary, .salary')[0]);
    const salary = salaryText.length <= 80 && decodeBossText(salaryText).unknownPua.length === 0
      ? findSalaryInText(salaryText) : '';
    const numbers = parseSalary(salary);
    const invalidSalary = [numbers.minK, numbers.maxK].some(value => value !== null && !Number.isFinite(value))
      || (numbers.minK !== null && numbers.maxK !== null && numbers.maxK < numbers.minK);
    const remote = detectRemote({ title, area, description });
    if (currentBossJobUrl(location.href) !== pageUrl) return { status: 'changed' };
    return { status: 'preview', job: {
      url: pageUrl, title, company, area, salary: invalidSalary ? '' : salary,
      salaryMinK: invalidSalary ? null : numbers.minK, salaryMaxK: invalidSalary ? null : numbers.maxK,
      description, ...provenance, ...quality,
      remoteStatus: remote.status, remoteConfidence: remote.confidence,
      skills: extractSkills({ description })
    } };
  }

  globalThis.BossAiContentInternals = {
    findAreaInText,
    escapeRegExp,
    getElementText,
    isJobDetailHref,
    chooseDescriptionCandidate,
    captureCurrentJob,
    extractDetail,
    extractList
  };
  if (globalThis.__BOSS_JOB_FILTER_TEST__) return;

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type === 'PING') {
      sendResponse({ ok: true, version: globalThis.BossJobFilterLib.VERSION });
      return;
    }

    if (message?.type === 'CAPTURE_CURRENT_JOB') {
      try {
        sendResponse(captureCurrentJob(message.expectedUrl));
      } catch {
        sendResponse({ status: 'unready' });
      }
      return;
    }

    if (message?.type === 'SCRAPE_PAGE') {
      (async () => {
        if (!hasBlockingOverlay()) await autoScroll();
        sendResponse(extractList(message.meta || {}, message.digitMap || {}));
      })().catch(error => sendResponse({
        jobs: [],
        blocked: false,
        salarySamples: [],
        error: String(error),
        stack: error?.stack || ''
      }));
      return true;
    }

    if (message?.type === 'SCRAPE_DETAIL') {
      (async () => {
        await new Promise(resolve => setTimeout(resolve, 900));
        sendResponse(extractDetail(message.meta || {}, message.digitMap || {}));
      })().catch(error => sendResponse({
        blocked: false,
        error: String(error),
        stack: error?.stack || ''
      }));
      return true;
    }
  });
})();
