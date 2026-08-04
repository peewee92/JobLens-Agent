(() => {
  'use strict';

  const {
    clean,
    cleanMultiline,
    decodeBossText,
    decodeBossMultilineText,
    extractJobDescriptionSegment,
    assessDescriptionQuality,
    findSalaryInText,
    inferDigitMap,
    detectRemote,
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

  function getCardForAnchor(anchor) {
    return anchor.closest(
      '.job-card-wrapper, .job-card-box, .job-list-box, li, article, [class*="job-card"], [class*="job-list"]'
    ) || anchor.parentElement;
  }

  function extractList(meta = {}, initialDigitMap = {}) {
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

    const anchors = [...document.querySelectorAll('a[href*="/job_detail/"]')];
    const cards = [...new Set(anchors.map(getCardForAnchor).filter(Boolean))];
    const digitMap = learnPageDigitMap(cards, initialDigitMap);
    const seen = new Set();
    const jobs = [];
    let puaCards = 0;
    let decodedCharacters = 0;

    for (const anchor of anchors) {
      const url = String(anchor.href || anchor.getAttribute('href') || '').split('?')[0];
      if (!url || seen.has(url)) continue;
      const card = getCardForAnchor(anchor);
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
        url,
        rawText,
        originalRawText,
        puaDecodedCount: decoded.decodedCount,
        collectedAt: new Date().toISOString()
      });
    }

    const pageDecoded = decodeBossText(document.body?.innerText || document.body?.textContent || '', digitMap);
    const pageText = pageDecoded.text;
    return {
      jobs,
      digitMap,
      blocked: /(安全验证|请完成验证|滑动验证|访问过于频繁|异常访问|系统检测到异常)/.test(pageText),
      title: document.title,
      pageText: pageText.slice(0, 1000),
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
    const bodyOriginal = cleanMultiline(document.body?.innerText || document.body?.textContent || '');
    const bodyDecoded = decodeBossMultilineText(bodyOriginal, digitMap);
    const bodyText = bodyDecoded.text;
    const selectedDescription = chooseDescriptionCandidate(digitMap, bodyText);
    const description = selectedDescription.description;

    const salary = findSalaryInText(bodyText, digitMap);
    const remote = detectRemote({ detailText: bodyText, description });
    const publishedAt = (bodyText.match(/(?:发布于|更新于|最近更新)\s*([^\s]{2,20})/) || [])[1] || '';
    const recruiterActive = (bodyText.match(/(刚刚活跃|今日活跃|本周活跃|近两周活跃|本月活跃)/) || [])[1] || '';
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
      blocked: /(安全验证|请完成验证|滑动验证|访问过于频繁|异常访问|系统检测到异常)/.test(bodyText),
      title: document.title,
      collectedAt: new Date().toISOString()
    };
  }

  globalThis.BossAiContentInternals = {
    findAreaInText,
    escapeRegExp,
    getElementText,
    chooseDescriptionCandidate
  };
  if (globalThis.__BOSS_JOB_FILTER_TEST__) return;

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type === 'PING') {
      sendResponse({ ok: true, version: globalThis.BossJobFilterLib.VERSION });
      return;
    }

    if (message?.type === 'SCRAPE_PAGE') {
      (async () => {
        await autoScroll();
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
