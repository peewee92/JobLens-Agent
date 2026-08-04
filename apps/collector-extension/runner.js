(() => {
  'use strict';

  const {
    VERSION,
    clean,
    limitText,
    limitMultilineText,
    normalizeStringList,
    mergeSearchMetadata,
    parseSalary,
    detectRemote,
    assessDescriptionQuality,
    classifyCategory,
    extractSkills,
    scoreRelevance,
    employmentFlags,
    normalizeDigitMap
  } = globalThis.BossJobFilterLib;

  const state = {
    aborted: false,
    jobs: [],
    jobTabId: null,
    config: null,
    lastRun: null,
    pageStats: [],
    digitMap: normalizeDigitMap({}),
    detailStats: { attempted: 0, succeeded: 0, failed: 0, blocked: 0 }
  };

  const el = id => document.getElementById(id);

  function log(message) {
    const timestamp = new Date().toLocaleTimeString();
    const logElement = el('log');
    const next = `${logElement.textContent}[${timestamp}] ${limitText(message, 4000)}\n`;
    logElement.textContent = next.length > 200000 ? next.slice(-150000) : next;
    logElement.scrollTop = logElement.scrollHeight;
  }

  function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  function randomDelay(config, multiplier = 1) {
    const min = Number(config.delayMinMs || 3500) * multiplier;
    const max = Math.max(min, Number(config.delayMaxMs || 6500) * multiplier);
    return Math.floor(min + Math.random() * (max - min + 1));
  }

  function selectedCitiesFromConfig(config = {}) {
    if (Array.isArray(config.selectedCities)) {
      return config.selectedCities
        .map((city, index) => ({
          name: limitText(city?.name, 80),
          code: limitText(city?.code, 20),
          province: limitText(city?.province, 80),
          order: index
        }))
        .filter(city => city.name && /^\d{9}$/.test(city.code))
        .slice(0, 20);
    }
    if (config.scopes?.wuhan) {
      return [{ name: '武汉', code: config.cityCodes?.wuhan || '101200100', province: '湖北', order: 0 }];
    }
    return [];
  }

  function normalizeRuntimeConfig(config = {}) {
    const selectedCities = selectedCitiesFromConfig(config);
    return {
      ...config,
      selectedCities,
      scopes: {
        ...config.scopes,
        cities: selectedCities.length > 0,
        remote: Boolean(config.scopes?.remote)
      },
      cityCodes: {
        ...config.cityCodes,
        nationwide: config.cityCodes?.nationwide || '100010000'
      }
    };
  }

  function isRemoteJob(job = {}) {
    return job.scopeType === 'remote'
      || (Array.isArray(job.scopeTypes) && job.scopeTypes.includes('remote'))
      || job.scope === '全国远程';
  }

  function isCityJob(job = {}) {
    return job.scopeType === 'city'
      || (Array.isArray(job.scopeTypes) && job.scopeTypes.includes('city'))
      || (!isRemoteJob(job) && Boolean(job.cityName || job.scope));
  }

  function buildTasks(configRaw) {
    const config = normalizeRuntimeConfig(configRaw);
    const tasks = [];
    for (const keyword of config.keywords) {
      for (const city of config.selectedCities) {
        tasks.push({
          scope: city.name,
          scopeType: 'city',
          cityName: city.name,
          provinceName: city.province,
          cityOrder: city.order,
          keyword,
          query: keyword,
          city: city.code
        });
      }
      if (config.scopes.remote) {
        tasks.push({
          scope: '全国远程',
          scopeType: 'remote',
          cityName: '',
          provinceName: '',
          cityOrder: 9999,
          keyword,
          query: keyword,
          city: config.cityCodes.nationwide
        });
      }
    }
    return tasks;
  }

  function makeUrl(task, pageNo) {
    const params = new URLSearchParams({
      query: task.query,
      city: task.city,
      page: String(pageNo)
    });
    return `https://www.zhipin.com/web/geek/job?${params.toString()}`;
  }

  function mergeDigitMap(next = {}) {
    state.digitMap = { ...state.digitMap, ...(next || {}) };
  }

  function salaryPasses(salary, config) {
    const threshold = Number(config.minSalaryK || 14);
    if (!['monthlyK', 'annualWan'].includes(salary.type) || salary.minK == null) return false;
    if (config.salaryMode === 'maxGte') return (salary.maxK ?? salary.minK) >= threshold;
    if (config.salaryMode === 'midGte') {
      const midpoint = salary.maxK == null ? salary.minK : (salary.minK + salary.maxK) / 2;
      return midpoint >= threshold;
    }
    return salary.minK >= threshold;
  }

  function normalizeJob(raw = {}) {
    const salaryText = raw.salary || raw.detailSalary || raw.rawText || raw.detailText || '';
    const salary = parseSalary(salaryText, state.digitMap);
    const remote = detectRemote(raw);
    const relevance = scoreRelevance(raw);
    const flags = employmentFlags(raw);
    const skills = [...new Set([...(raw.skills || []), ...extractSkills(raw)])].slice(0, 128);
    const searchMeta = mergeSearchMetadata({}, raw);
    const scopes = normalizeStringList(raw.scope, {
      separator: /\s*\/\s*/,
      maxItems: 24,
      maxItemLength: 80
    });
    const inferredScopeType = raw.scopeType || (scopes.includes('全国远程') ? 'remote' : 'city');
    const scopeTypes = normalizeStringList([raw.scopeTypes, inferredScopeType], {
      separator: null,
      maxItems: 4,
      maxItemLength: 20
    });
    const searchCities = normalizeStringList([
      raw.searchCities,
      inferredScopeType === 'city' ? (raw.cityName || scopes.filter(scope => scope !== '全国远程')) : []
    ], { separator: null, maxItems: 20, maxItemLength: 80 });
    const searchCityCodes = normalizeStringList([
      raw.searchCityCodes,
      inferredScopeType === 'city' ? (raw.cityCode || '') : ''
    ], { separator: null, maxItems: 20, maxItemLength: 20 });
    const searchProvinces = normalizeStringList([
      raw.searchProvinces,
      inferredScopeType === 'city' ? (raw.provinceName || '') : ''
    ], { separator: null, maxItems: 20, maxItemLength: 80 });
    const detailAttempted = Boolean(raw.detailAttempted);
    const detailSucceeded = Boolean(raw.detailSucceeded);
    const description = limitMultilineText(raw.description, 30000);
    const descriptionSource = limitText(raw.descriptionSource, 300);
    const descriptionSelectorTrust = limitText(raw.descriptionSelectorTrust, 40);
    const descriptionSanitized = Boolean(raw.descriptionSanitized);
    const descriptionStartMarker = limitText(raw.descriptionStartMarker, 80);
    const descriptionStopMarker = limitText(raw.descriptionStopMarker, 80);
    const quality = assessDescriptionQuality({
      description,
      descriptionSource,
      descriptionSelectorTrust,
      descriptionSanitized,
      detailAttempted,
      detailSucceeded
    });
    const sourceUrl = limitText(String(raw.sourceUrl || raw.url || '').split('?')[0], 2000);

    return {
      ...raw,
      scope: scopes.join('/'),
      scopeType: inferredScopeType,
      scopeTypes,
      cityName: limitText(raw.cityName || searchCities[0], 80),
      provinceName: limitText(raw.provinceName || searchProvinces[0], 80),
      cityCode: limitText(raw.cityCode || searchCityCodes[0], 20),
      cityOrder: Number.isFinite(Number(raw.cityOrder)) ? Number(raw.cityOrder) : 9999,
      searchCities,
      searchCityCodes,
      searchProvinces,
      searchKeyword: searchMeta.searchKeyword,
      searchKeywords: searchMeta.searchKeywords,
      title: limitText(raw.title, 300),
      salary: limitText(raw.salary || raw.detailSalary || salary.decodedRaw, 120),
      salarySource: limitText(raw.salarySource || (salary.hadPua ? 'puaDecoded' : 'text'), 120),
      salaryMinK: salary.minK,
      salaryMaxK: salary.maxK,
      salaryType: salary.type,
      salarySourceUnit: salary.sourceUnit,
      salaryMonths: salary.months,
      annualMinWan: salary.annualMinWan,
      annualMaxWan: salary.annualMaxWan,
      salaryHadPua: salary.hadPua || Number(raw.puaDecodedCount || 0) > 0,
      salaryDecodedCount: salary.decodedCount,
      area: limitText(raw.area, 200),
      company: limitText(raw.company, 200),
      experience: limitText(raw.experience, 80),
      education: limitText(raw.education, 80),
      tags: limitText(raw.tags, 1500),
      remoteMatched: remote.matched,
      remoteStatus: remote.status,
      remoteConfidence: remote.confidence,
      remoteEvidence: normalizeStringList(remote.evidence, { separator: null, maxItems: 16, maxItemLength: 80 }),
      categories: relevance.categories,
      relevanceScore: relevance.score,
      relevanceReasons: relevance.reasons,
      skills,
      employmentFlags: flags,
      source: raw.source || 'boss_zhipin',
      sourceUrl,
      sourceVersion: raw.sourceVersion || VERSION,
      url: sourceUrl,
      page: searchMeta.page,
      pages: searchMeta.pages,
      collectedAt: raw.collectedAt || new Date().toISOString(),
      firstSeenAt: raw.firstSeenAt || raw.collectedAt || new Date().toISOString(),
      lastSeenAt: raw.lastSeenAt || raw.collectedAt || new Date().toISOString(),
      hitCount: Math.max(1, Number(raw.hitCount || 1)),
      detailAttempted,
      detailSucceeded,
      detailError: limitText(raw.detailError, 1000),
      description,
      descriptionSource,
      descriptionSelectorTrust,
      descriptionSanitized,
      descriptionStartMarker,
      descriptionStopMarker,
      descriptionQuality: quality.descriptionQuality,
      descriptionLength: quality.descriptionLength,
      descriptionHash: quality.descriptionHash,
      descriptionHasSectionSignal: quality.descriptionHasSectionSignal,
      descriptionHasContentSignal: quality.descriptionHasContentSignal,
      descriptionNoiseCount: quality.descriptionNoiseCount,
      requirementReviewEligible: quality.requirementReviewEligible,
      requirementReviewIneligibilityReasons: quality.requirementReviewIneligibilityReasons,
      detailText: limitMultilineText(raw.detailText, 50000),
      originalRawText: limitText(raw.originalRawText, 20000),
      rawText: limitText(raw.rawText, 20000)
    };
  }

  function chooseRicherText(previousValue, nextValue, maxLength) {
    const previous = limitText(previousValue, maxLength);
    const next = limitText(nextValue, maxLength);
    if (!previous) return next;
    if (!next) return previous;
    return next.length > previous.length ? next : previous;
  }

  function chooseRicherMultilineText(previousValue, nextValue, maxLength) {
    const previous = limitMultilineText(previousValue, maxLength);
    const next = limitMultilineText(nextValue, maxLength);
    if (!previous) return next;
    if (!next) return previous;
    return next.length > previous.length ? next : previous;
  }

  function mergeJobs(previousRaw, nextRaw) {
    const previous = normalizeJob(previousRaw);
    const next = normalizeJob(nextRaw);
    const searchMeta = mergeSearchMetadata(previous, next);
    const scopes = normalizeStringList([previous.scope, next.scope], {
      separator: /\s*\/\s*/,
      maxItems: 24,
      maxItemLength: 80
    });
    const scopeTypes = normalizeStringList([previous.scopeTypes, next.scopeTypes], {
      separator: null, maxItems: 4, maxItemLength: 20
    });
    const searchCities = normalizeStringList([previous.searchCities, next.searchCities], {
      separator: null, maxItems: 20, maxItemLength: 80
    });
    const searchCityCodes = normalizeStringList([previous.searchCityCodes, next.searchCityCodes], {
      separator: null, maxItems: 20, maxItemLength: 20
    });
    const searchProvinces = normalizeStringList([previous.searchProvinces, next.searchProvinces], {
      separator: null, maxItems: 20, maxItemLength: 80
    });

    const previousSalaryValid = Number.isFinite(previous.salaryMinK);
    const nextSalaryValid = Number.isFinite(next.salaryMinK);
    const preferredSalary = nextSalaryValid || !previousSalaryValid ? next : previous;
    const preferredDescription = next.description.length > previous.description.length ? next : previous;
    const merged = {
      ...previous,
      ...Object.fromEntries(Object.entries(next).filter(([, value]) => (
        value !== '' && value != null && !(Array.isArray(value) && value.length === 0)
      ))),
      ...searchMeta,
      scope: scopes.join('/'),
      scopeType: scopeTypes.length === 1 ? scopeTypes[0] : (next.scopeType || previous.scopeType),
      scopeTypes,
      searchCities,
      searchCityCodes,
      searchProvinces,
      cityName: searchCities[0] || next.cityName || previous.cityName || '',
      provinceName: searchProvinces[0] || next.provinceName || previous.provinceName || '',
      cityCode: searchCityCodes[0] || next.cityCode || previous.cityCode || '',
      cityOrder: Math.min(Number(previous.cityOrder ?? 9999), Number(next.cityOrder ?? 9999)),
      salary: preferredSalary.salary,
      salarySource: preferredSalary.salarySource,
      salaryMinK: preferredSalary.salaryMinK,
      salaryMaxK: preferredSalary.salaryMaxK,
      salaryType: preferredSalary.salaryType,
      salarySourceUnit: preferredSalary.salarySourceUnit,
      salaryMonths: preferredSalary.salaryMonths,
      annualMinWan: preferredSalary.annualMinWan,
      annualMaxWan: preferredSalary.annualMaxWan,
      remoteMatched: previous.remoteMatched || next.remoteMatched,
      detailAttempted: previous.detailAttempted || next.detailAttempted,
      detailSucceeded: previous.detailSucceeded || next.detailSucceeded,
      skills: normalizeStringList([previous.skills, next.skills], { separator: null, maxItems: 128, maxItemLength: 100 }),
      categories: normalizeStringList([previous.categories, next.categories], { separator: null, maxItems: 32, maxItemLength: 100 }),
      description: chooseRicherMultilineText(previous.description, next.description, 30000),
      descriptionSource: preferredDescription.descriptionSource,
      descriptionSelectorTrust: preferredDescription.descriptionSelectorTrust,
      descriptionSanitized: preferredDescription.descriptionSanitized,
      descriptionStartMarker: preferredDescription.descriptionStartMarker,
      descriptionStopMarker: preferredDescription.descriptionStopMarker,
      detailText: chooseRicherMultilineText(previous.detailText, next.detailText, 50000),
      rawText: chooseRicherText(previous.rawText, next.rawText, 20000),
      originalRawText: chooseRicherText(previous.originalRawText, next.originalRawText, 20000),
      firstSeenAt: previous.firstSeenAt || previous.collectedAt || next.firstSeenAt || next.collectedAt,
      lastSeenAt: next.lastSeenAt || next.collectedAt || previous.lastSeenAt || previous.collectedAt,
      hitCount: Math.min(1000000, Number(previous.hitCount || 1) + Number(next.hitCount || 1))
    };
    return normalizeJob(merged);
  }

  function dedupe(jobs, preserveScope = false) {
    const map = new Map();
    for (const raw of jobs) {
      const job = normalizeJob(raw);
      const baseKey = job.url || `${job.title}|${job.company}|${job.area}|${job.salary}`;
      const scopedIdentity = `${job.scopeType}|${job.cityCode || job.scope}`;
      const key = preserveScope ? `${baseKey}|${scopedIdentity}` : baseKey;
      map.set(key, map.has(key) ? mergeJobs(map.get(key), job) : job);
    }
    return [...map.values()];
  }

  function classify(jobRaw, config, phase = 'final') {
    const job = normalizeJob(jobRaw);
    const salary = parseSalary(job.salary || job.rawText || job.detailText, state.digitMap);
    const remote = detectRemote(job);
    const flags = job.employmentFlags || employmentFlags(job);

    if (!['monthlyK', 'annualWan'].includes(salary.type) || salary.minK == null) {
      return { keep: false, pendingDetail: false, reason: '薪资无法解析', job, salary, remote };
    }
    if (!salaryPasses(salary, config)) {
      return { keep: false, pendingDetail: false, reason: '薪资低于阈值', job, salary, remote };
    }
    if (Number(config.minRelevanceScore || 0) > job.relevanceScore) {
      return { keep: false, pendingDetail: false, reason: '岗位相关度低于阈值', job, salary, remote };
    }
    if (config.excludePartTime && flags.partTime) {
      return { keep: false, pendingDetail: false, reason: '排除兼职岗位', job, salary, remote };
    }
    if (config.excludeIntern && flags.internship) {
      return { keep: false, pendingDetail: false, reason: '排除实习岗位', job, salary, remote };
    }
    if (config.excludeAssistant && flags.assistant) {
      return { keep: false, pendingDetail: false, reason: '排除助理岗位', job, salary, remote };
    }

    if (isCityJob(job) && !isRemoteJob(job)) {
      return { keep: true, pendingDetail: false, reason: '通过', job, salary, remote };
    }

    if (isRemoteJob(job)) {
      if (config.remotePolicy === 'loose') {
        return { keep: true, pendingDetail: false, reason: remote.matched ? '通过' : '宽松保留待人工确认', job, salary, remote };
      }
      if (remote.matched) {
        return { keep: true, pendingDetail: false, reason: '通过', job, salary, remote };
      }
      if (remote.status === 'rejected') {
        return { keep: false, pendingDetail: false, reason: '明确不支持远程', job, salary, remote };
      }
      if (config.remotePolicy === 'cardOrDetail' && phase === 'initial' && config.detailMode !== 'off') {
        return { keep: false, pendingDetail: true, reason: '待详情页确认远程', job, salary, remote };
      }
      if (config.remotePolicy === 'cardOrDetail' && !job.detailAttempted) {
        return { keep: false, pendingDetail: false, reason: '未识别远程标记（详情未补采）', job, salary, remote };
      }
      return { keep: false, pendingDetail: false, reason: '未识别到远程标记', job, salary, remote };
    }

    return { keep: false, pendingDetail: false, reason: '未知搜索范围', job, salary, remote };
  }

  function countBy(items, getter) {
    const counts = {};
    for (const item of items) {
      const values = getter(item);
      for (const value of (Array.isArray(values) ? values : [values])) {
        const key = clean(value || '未知');
        counts[key] = (counts[key] || 0) + 1;
      }
    }
    return counts;
  }

  function salaryBand(job) {
    const value = Number(job.salaryMinK);
    if (!Number.isFinite(value)) return '无法解析';
    if (value < 14) return '<14K';
    if (value < 20) return '14–19K';
    if (value < 30) return '20–29K';
    if (value < 40) return '30–39K';
    return '40K+';
  }

  function buildStatistics(finalJobs, candidates) {
    const averageMinSalaryK = finalJobs.length
      ? Math.round(finalJobs.reduce((sum, job) => sum + Number(job.salaryMinK || 0), 0) / finalJobs.length * 100) / 100
      : null;
    return {
      totals: {
        finalJobs: finalJobs.length,
        cityJobs: finalJobs.filter(job => job.searchCities?.length || (isCityJob(job) && !isRemoteJob(job))).length,
        selectedCityCount: state.config?.selectedCities?.length || 0,
        wuhan: finalJobs.filter(job => job.searchCities?.includes('武汉') || job.scope.split('/').includes('武汉')).length,
        remoteConfirmed: finalJobs.filter(job => job.remoteMatched).length,
        puaSalaryDecoded: candidates.filter(job => job.salaryHadPua && job.salaryMinK != null).length,
        detailEnriched: finalJobs.filter(job => job.detailSucceeded).length,
        fullJd: finalJobs.filter(job => job.descriptionQuality === 'full_jd').length,
        requirementReviewEligible: finalJobs.filter(job => job.requirementReviewEligible).length,
        detailCohortEnriched: candidates.filter(job => job.detailSucceeded).length,
        detailCohortFullJd: candidates.filter(job => job.descriptionQuality === 'full_jd').length,
        detailCohortRequirementReviewEligible: candidates.filter(job => job.requirementReviewEligible).length,
        averageMinSalaryK,
        totalCandidateHits: candidates.reduce((sum, job) => sum + Number(job.hitCount || 1), 0),
        duplicateCandidateHits: candidates.reduce((sum, job) => sum + Math.max(0, Number(job.hitCount || 1) - 1), 0),
        maxHitCount: candidates.reduce((max, job) => Math.max(max, Number(job.hitCount || 1)), 0)
      },
      byScope: countBy(finalJobs, job => job.scope.split('/')),
      bySearchCity: countBy(finalJobs, job => job.searchCities?.length ? job.searchCities : (job.cityName ? [job.cityName] : [])),
      bySearchProvince: countBy(finalJobs, job => job.searchProvinces || []),
      byCategory: countBy(finalJobs, job => job.categories),
      bySalaryBand: countBy(finalJobs, salaryBand),
      byArea: countBy(finalJobs, job => job.area),
      byCompany: countBy(finalJobs, job => job.company),
      byExperience: countBy(finalJobs, job => job.experience),
      byEducation: countBy(finalJobs, job => job.education),
      bySkill: countBy(finalJobs, job => job.skills),
      bySearchKeyword: countBy(finalJobs, job => job.searchKeywords),
      byRemoteStatus: countBy(finalJobs, job => job.remoteStatus),
      pageYield: state.pageStats
    };
  }

  function diagnosticSample(item) {
    return {
      scope: item.job.scope,
      scopeType: item.job.scopeType,
      cityName: item.job.cityName,
      provinceName: item.job.provinceName,
      cityCode: item.job.cityCode,
      searchCities: item.job.searchCities,
      title: item.job.title,
      salary: item.job.salary,
      salarySource: item.job.salarySource,
      salaryHadPua: item.job.salaryHadPua,
      parsedSalaryMinK: item.salary.minK,
      parsedSalaryMaxK: item.salary.maxK,
      area: item.job.area,
      company: item.job.company,
      relevanceScore: item.job.relevanceScore,
      categories: item.job.categories,
      remoteStatus: item.remote.status,
      remoteMatched: item.remote.matched,
      detailAttempted: item.job.detailAttempted,
      detailSucceeded: item.job.detailSucceeded,
      descriptionSource: item.job.descriptionSource,
      descriptionSelectorTrust: item.job.descriptionSelectorTrust,
      descriptionSanitized: item.job.descriptionSanitized,
      descriptionStartMarker: item.job.descriptionStartMarker,
      descriptionStopMarker: item.job.descriptionStopMarker,
      descriptionQuality: item.job.descriptionQuality,
      descriptionLength: item.job.descriptionLength,
      descriptionHash: item.job.descriptionHash,
      descriptionNoiseCount: item.job.descriptionNoiseCount,
      requirementReviewEligible: item.job.requirementReviewEligible,
      requirementReviewIneligibilityReasons: item.job.requirementReviewIneligibilityReasons,
      url: item.job.url,
      hitCount: item.job.hitCount,
      searchKeywords: item.job.searchKeywords,
      pages: item.job.pages,
      rawText: item.job.rawText,
      originalRawText: item.job.originalRawText
    };
  }

  function serializeDigitMap(map) {
    return Object.fromEntries(Object.entries(map).map(([char, digit]) => [
      `U+${char.codePointAt(0).toString(16).toUpperCase().padStart(4, '0')}`,
      digit
    ]));
  }

  function buildDiagnostics(rawJobs, uniqueJobs, classified, finalJobs, config, statistics) {
    const rejectedReasons = {};
    const samplesByReason = {};
    for (const item of classified) {
      if (!item.keep) rejectedReasons[item.reason] = (rejectedReasons[item.reason] || 0) + 1;
      if (!samplesByReason[item.reason]) samplesByReason[item.reason] = [];
      if (samplesByReason[item.reason].length < 20) samplesByReason[item.reason].push(diagnosticSample(item));
    }

    const salarySources = countBy(uniqueJobs.filter(job => job.salaryMinK != null), job => job.salarySource || 'unknown');
    return {
      version: VERSION,
      generatedAt: new Date().toISOString(),
      config,
      learnedDigitMap: serializeDigitMap(state.digitMap),
      counts: {
        rawCards: rawJobs.length,
        uniqueCardsBeforeFilter: uniqueJobs.length,
        duplicateRawHits: Math.max(0, rawJobs.length - uniqueJobs.length),
        totalMergedHits: uniqueJobs.reduce((sum, job) => sum + Number(job.hitCount || 1), 0),
        maxHitCount: uniqueJobs.reduce((max, job) => Math.max(max, Number(job.hitCount || 1)), 0),
        repeatedJobs: uniqueJobs.filter(job => Number(job.hitCount || 1) > 1).length,
        cardsWithPua: uniqueJobs.filter(job => job.salaryHadPua || /[\uE000-\uF8FF]/.test(job.originalRawText || '')).length,
        salaryParsed: classified.filter(item => item.salary.minK != null).length,
        salaryDecodedFromPua: classified.filter(item => item.salary.minK != null && item.job.salaryHadPua).length,
        salaryPassed: classified.filter(item => item.salary.minK != null && salaryPasses(item.salary, config)).length,
        remoteConfirmed: classified.filter(item => item.remote.matched).length,
        detailAttempted: state.detailStats.attempted,
        detailSucceeded: state.detailStats.succeeded,
        detailFailed: state.detailStats.failed,
        finalDetailEnriched: finalJobs.filter(job => job.detailSucceeded).length,
        fullJd: finalJobs.filter(job => job.descriptionQuality === 'full_jd').length,
        partialJd: finalJobs.filter(job => job.descriptionQuality === 'partial_jd').length,
        cardOnly: finalJobs.filter(job => job.descriptionQuality === 'card_only').length,
        unavailableJd: finalJobs.filter(job => job.descriptionQuality === 'unavailable').length,
        requirementReviewEligible: finalJobs.filter(job => job.requirementReviewEligible).length,
        requirementReviewBlocked: finalJobs.filter(job => !job.requirementReviewEligible).length,
        detailCohortFullJd: uniqueJobs.filter(job => job.descriptionQuality === 'full_jd').length,
        detailCohortPartialJd: uniqueJobs.filter(job => job.descriptionQuality === 'partial_jd').length,
        detailCohortRequirementReviewEligible: uniqueJobs.filter(job => job.requirementReviewEligible).length,
        finalKeptBeforeCrossScopeDedupe: classified.filter(item => item.keep).length,
        finalAfterCrossScopeDedupe: finalJobs.length
      },
      salarySources,
      rejectedReasons,
      samplesByReason,
      pageStats: state.pageStats,
      statistics
    };
  }

  function csvCell(value) {
    const normalized = Array.isArray(value) ? value.join(' | ') : value;
    return `"${String(normalized ?? '').replaceAll('"', '""')}"`;
  }

  function toCsv(jobs) {
    const columns = [
      ['scope', '范围'],
      ['scopeTypes', '搜索类型'],
      ['searchCities', '搜索城市'],
      ['searchProvinces', '搜索省份'],
      ['searchCityCodes', '城市编码'],
      ['searchKeyword', '命中搜索词'],
      ['hitCount', '重复命中次数'],
      ['firstSeenAt', '首次命中时间'],
      ['lastSeenAt', '最后命中时间'],
      ['title', '岗位名称'],
      ['categories', '岗位分类'],
      ['relevanceScore', '相关度分数'],
      ['salary', '薪资原文/解码后'],
      ['salarySource', '薪资来源'],
      ['salaryHadPua', '薪资是否字体混淆'],
      ['salaryMinK', '月薪下限K'],
      ['salaryMaxK', '月薪上限K'],
      ['salaryMonths', '薪数'],
      ['annualMinWan', '估算年薪下限万'],
      ['annualMaxWan', '估算年薪上限万'],
      ['area', '地点'],
      ['remoteStatus', '远程状态'],
      ['remoteConfidence', '远程置信度'],
      ['remoteEvidence', '远程证据字段'],
      ['company', '公司'],
      ['experience', '经验'],
      ['education', '学历'],
      ['skills', '技能标签'],
      ['tags', '卡片标签'],
      ['publishedAt', '发布时间'],
      ['recruiterActive', '招聘者活跃'],
      ['detailSucceeded', '详情页读取成功'],
      ['descriptionSource', 'JD来源'],
      ['descriptionSelectorTrust', 'JD选择器可信级别'],
      ['descriptionSanitized', 'JD是否完成页面裁剪'],
      ['descriptionStartMarker', 'JD起始标记'],
      ['descriptionStopMarker', 'JD截止标记'],
      ['descriptionQuality', 'JD质量'],
      ['descriptionLength', 'JD长度'],
      ['descriptionHash', 'JD指纹'],
      ['descriptionNoiseCount', 'JD页面噪声计数'],
      ['requirementReviewEligible', '可用于Requirement验收'],
      ['requirementReviewIneligibilityReasons', 'Requirement验收阻断原因'],
      ['url', '职位链接'],
      ['pages', '搜索页码'],
      ['collectedAt', '采集时间'],
      ['rawText', '卡片原文'],
      ['description', '职位描述摘要']
    ];
    const lines = [columns.map(([, label]) => csvCell(label)).join(',')];
    for (const job of jobs) lines.push(columns.map(([key]) => csvCell(job[key])).join(','));
    return `\uFEFF${lines.join('\n')}`;
  }

  function buildRequirementReviewDataset(finalJobs, config, statistics) {
    const requiredSampleSize = 20;
    const eligibleJobs = finalJobs.filter(job => job.requirementReviewEligible);
    const selectedJobs = eligibleJobs.slice(0, requiredSampleSize);
    const ready = selectedJobs.length === requiredSampleSize;
    return {
      version: VERSION,
      generatedAt: new Date().toISOString(),
      purpose: 'requirement_manual_quality_review',
      qualityGate: {
        requiredSampleSize,
        eligibleCount: eligibleJobs.length,
        selectedCount: selectedJobs.length,
        status: ready ? 'ready' : 'blocked',
        blockers: ready ? [] : ['insufficient_full_jd_jobs']
      },
      config,
      statistics: {
        ...statistics,
        requirementReviewDataset: {
          requiredSampleSize,
          eligibleCount: eligibleJobs.length,
          selectedCount: selectedJobs.length
        }
      },
      jobs: selectedJobs,
      candidates: []
    };
  }

  async function dataDownload(filename, mime, content, saveAs = false) {
    const blob = new Blob([content], { type: `${mime};charset=utf-8` });
    const url = URL.createObjectURL(blob);
    try {
      return await chrome.downloads.download({ url, filename, saveAs });
    } finally {
      setTimeout(() => URL.revokeObjectURL(url), 30_000);
    }
  }

  function waitForTabComplete(tabId, url) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        chrome.tabs.onUpdated.removeListener(listener);
        reject(new Error('页面加载超时'));
      }, 70_000);
      const listener = (updatedId, changeInfo) => {
        if (updatedId === tabId && changeInfo.status === 'complete') {
          clearTimeout(timer);
          chrome.tabs.onUpdated.removeListener(listener);
          resolve();
        }
      };
      chrome.tabs.onUpdated.addListener(listener);
      chrome.tabs.update(tabId, { url, active: true }).catch(error => {
        clearTimeout(timer);
        chrome.tabs.onUpdated.removeListener(listener);
        reject(error);
      });
    });
  }

  async function sendToJobTab(message, retries = 8) {
    let lastError;
    for (let i = 0; i < retries; i += 1) {
      try {
        return await chrome.tabs.sendMessage(state.jobTabId, message);
      } catch (error) {
        lastError = error;
        await delay(750);
      }
    }
    throw lastError || new Error('无法连接到 BOSS 页面');
  }

  async function waitForVerification(meta, type = 'SCRAPE_PAGE') {
    log('检测到安全验证。请在 BOSS 标签页人工完成验证，插件不会尝试绕过。');
    await chrome.tabs.update(state.jobTabId, { active: true });
    for (let i = 0; i < 120 && !state.aborted; i += 1) {
      await delay(5_000);
      const result = await sendToJobTab({ type, meta, digitMap: state.digitMap }, 2).catch(() => null);
      if (result && !result.blocked) {
        log('验证已通过，继续运行。');
        return result;
      }
    }
    throw new Error('等待人工验证超时或任务已停止');
  }

  async function collectSearchPages(config) {
    const tasks = buildTasks(config);
    const pagesPerQuery = Number(config.pagesPerQuery || 1);
    const total = tasks.length * pagesPerQuery;
    el('progress').max = total;
    el('summary').textContent = `共 ${tasks.length} 组搜索，最多加载 ${total} 页。`;
    log(`v${VERSION}：启用稳定去重合并、BOSS 私有字体薪资解码、字段来源诊断和详情补采。`);

    const tab = await chrome.tabs.create({ url: 'https://www.zhipin.com/', active: true });
    state.jobTabId = tab.id;
    let completed = 0;

    for (const task of tasks) {
      const taskSeen = new Set();
      let consecutiveNoNew = 0;
      for (let pageNo = 1; pageNo <= pagesPerQuery; pageNo += 1) {
        if (state.aborted) throw new Error('用户已停止任务');
        const url = makeUrl(task, pageNo);
        const meta = {
          scope: task.scope,
          scopeType: task.scopeType,
          cityName: task.cityName,
          provinceName: task.provinceName,
          cityOrder: task.cityOrder,
          searchKeyword: task.keyword,
          searchQuery: task.query,
          searchUrl: url,
          cityCode: task.city,
          page: pageNo
        };

        log(`${task.scope} · ${task.keyword} · 第 ${pageNo} 页`);
        const startedAt = Date.now();
        await waitForTabComplete(state.jobTabId, url);
        await delay(1_300);
        let result = await sendToJobTab({ type: 'SCRAPE_PAGE', meta, digitMap: state.digitMap });
        if (result?.blocked) result = await waitForVerification(meta, 'SCRAPE_PAGE');
        if (result?.error) log(`页面解析提示：${result.error}`);
        mergeDigitMap(result?.digitMap);

        const jobs = result?.jobs || [];
        const newUrls = jobs.filter(job => job.url && !taskSeen.has(job.url));
        for (const job of jobs) taskSeen.add(job.url);
        state.jobs.push(...jobs);
        const extraction = result?.extraction || {};
        state.pageStats.push({
          scope: task.scope,
          scopeType: task.scopeType,
          cityName: task.cityName,
          provinceName: task.provinceName,
          cityCode: task.city,
          keyword: task.keyword,
          page: pageNo,
          cards: jobs.length,
          newWithinQuery: newUrls.length,
          puaCards: extraction.puaCards || 0,
          decodedCharacters: extraction.decodedCharacters || 0,
          durationMs: Date.now() - startedAt,
          salarySamples: result?.salarySamples || []
        });

        log(`抓到 ${jobs.length} 条，新岗位 ${newUrls.length}；字体混淆卡片 ${extraction.puaCards || 0}，已解码字符 ${extraction.decodedCharacters || 0}。`);
        log(`本页薪资样例：${(result?.salarySamples || []).join(' / ') || '无'}`);

        completed += 1;
        el('progress').value = completed;
        el('summary').textContent = `搜索进度 ${completed}/${total}，累计原始 ${state.jobs.length} 条。`;

        consecutiveNoNew = newUrls.length === 0 ? consecutiveNoNew + 1 : 0;
        if (config.smartStop && pageNo >= 2 && consecutiveNoNew >= 1) {
          log(`该关键词第 ${pageNo} 页没有新增岗位，智能停止后续页。`);
          break;
        }
        await delay(randomDelay(config));
      }
    }
  }

  function detailPriority(job, initialClass) {
    let score = Number(job.relevanceScore || 0);
    if (isRemoteJob(job) && initialClass.pendingDetail) score += 1000;
    if (job.remoteMatched) score += 100;
    score += Number(job.salaryMinK || 0);
    return score;
  }

  async function enrichDetails(uniqueJobs, config) {
    if (config.detailMode === 'off' || Number(config.detailLimit || 0) <= 0) return uniqueJobs;

    const initial = uniqueJobs.map(job => classify(job, config, 'initial'));
    let targets = initial
      .filter(item => item.pendingDetail)
      .map(item => ({ job: item.job, initialClass: item }));

    if (config.detailMode === 'matched') {
      const additional = initial
        .filter(item => !item.pendingDetail && (item.keep || item.reason === '通过'))
        .map(item => ({ job: item.job, initialClass: item }));
      targets.push(...additional);
    }

    const targetMap = new Map();
    for (const target of targets) {
      if (!target.job.url) continue;
      const previous = targetMap.get(target.job.url);
      if (!previous || detailPriority(target.job, target.initialClass) > detailPriority(previous.job, previous.initialClass)) {
        targetMap.set(target.job.url, target);
      }
    }
    const detailLimit = Number(config.detailLimit || 40);
    const uniqueTargets = [...targetMap.values()]
      .sort((a, b) => detailPriority(b.job, b.initialClass) - detailPriority(a.job, a.initialClass));
    if (config.detailMode === 'matched') {
      const acceptedTargets = uniqueTargets.filter(target => target.initialClass.keep);
      const pendingRemoteTargets = uniqueTargets.filter(target => target.initialClass.pendingDetail);
      const reviewQuota = Math.min(20, detailLimit, acceptedTargets.length);
      targets = [
        ...acceptedTargets.slice(0, reviewQuota),
        ...pendingRemoteTargets,
        ...acceptedTargets.slice(reviewQuota)
      ].slice(0, detailLimit);
    } else {
      targets = uniqueTargets.slice(0, detailLimit);
    }

    if (!targets.length) {
      log('没有需要补采详情的岗位。');
      return uniqueJobs;
    }

    log(`开始详情补采：${targets.length} 条。优先确认全国远程，其次补充技能与职位描述。`);
    const detailsByUrl = new Map();
    let index = 0;
    for (const { job } of targets) {
      if (state.aborted) throw new Error('用户已停止任务');
      index += 1;
      state.detailStats.attempted += 1;
      el('summary').textContent = `详情补采 ${index}/${targets.length}：${job.title}`;
      try {
        await waitForTabComplete(state.jobTabId, job.url);
        await delay(1_100);
        const meta = { url: job.url, title: job.title, scope: job.scope };
        let detail = await sendToJobTab({ type: 'SCRAPE_DETAIL', meta, digitMap: state.digitMap });
        if (detail?.blocked) {
          state.detailStats.blocked += 1;
          detail = await waitForVerification(meta, 'SCRAPE_DETAIL');
        }
        if (detail?.error) throw new Error(detail.error);
        detailsByUrl.set(job.url, {
          detailAttempted: true,
          detailSucceeded: true,
          detailSalary: detail.salary || '',
          description: detail.description || '',
          descriptionSource: detail.descriptionSource || '',
          descriptionSelectorTrust: detail.descriptionSelectorTrust || '',
          descriptionSanitized: Boolean(detail.descriptionSanitized),
          descriptionStartMarker: detail.descriptionStartMarker || '',
          descriptionStopMarker: detail.descriptionStopMarker || '',
          detailText: detail.detailText || '',
          detailCollectedAt: detail.collectedAt || new Date().toISOString(),
          publishedAt: detail.publishedAt || '',
          recruiterActive: detail.recruiterActive || '',
          skills: detail.skills || [],
          puaDecodedCount: Number(job.puaDecodedCount || 0) + Number(detail.puaDecodedCount || 0)
        });
        state.detailStats.succeeded += 1;
        const remote = detectRemote(detail);
        const quality = assessDescriptionQuality({
          description: detail.description,
          descriptionSource: detail.descriptionSource,
          descriptionSelectorTrust: detail.descriptionSelectorTrust,
          descriptionSanitized: detail.descriptionSanitized,
          detailAttempted: true,
          detailSucceeded: true
        });
        log(`详情 ${index}/${targets.length}：${job.title}；远程=${remote.status}；JD=${quality.descriptionQuality}(${quality.descriptionLength})；技能=${(detail.skills || []).join('/') || '未识别'}`);
      } catch (error) {
        state.detailStats.failed += 1;
        detailsByUrl.set(job.url, {
          detailAttempted: true,
          detailSucceeded: false,
          detailError: String(error?.message || error)
        });
        log(`详情补采失败：${job.title} · ${error?.message || error}`);
      }
      await delay(randomDelay(config, 0.65));
    }

    return uniqueJobs.map(job => {
      const detail = detailsByUrl.get(job.url);
      return detail ? normalizeJob({ ...job, ...detail }) : job;
    });
  }

  function sortFinalJobs(jobs, config = {}) {
    const orderByCode = new Map((config.selectedCities || []).map((city, index) => [String(city.code), index]));
    const cityRank = job => {
      const codes = job.searchCityCodes || (job.cityCode ? [job.cityCode] : []);
      const ranks = codes.map(code => orderByCode.get(String(code))).filter(Number.isFinite);
      return ranks.length ? Math.min(...ranks) : 9998;
    };
    return [...jobs].sort((a, b) => {
      const scopeA = a.searchCities?.length ? 0 : (isRemoteJob(a) ? 1 : 2);
      const scopeB = b.searchCities?.length ? 0 : (isRemoteJob(b) ? 1 : 2);
      return scopeA - scopeB
        || cityRank(a) - cityRank(b)
        || Number(b.relevanceScore || 0) - Number(a.relevanceScore || 0)
        || Number(b.salaryMinK || 0) - Number(a.salaryMinK || 0)
        || String(a.company).localeCompare(String(b.company), 'zh-CN');
    });
  }

  function renderDiagnostics(diagnostics) {
    const c = diagnostics.counts;
    log(`过滤诊断：原始 ${c.rawCards}，按范围去重 ${c.uniqueCardsBeforeFilter}，薪资可解析 ${c.salaryParsed}，其中字体解码 ${c.salaryDecodedFromPua}，最终 ${c.finalAfterCrossScopeDedupe}。`);
    log(`详情补采：尝试 ${c.detailAttempted}，页面读取成功 ${c.detailSucceeded}，失败 ${c.detailFailed}；完整 JD ${c.fullJd}，可用于 Requirement 验收 ${c.requirementReviewEligible}。`);
    const reasons = Object.entries(diagnostics.rejectedReasons).map(([reason, count]) => `${reason} ${count}`).join('；');
    if (reasons) log(`过滤原因：${reasons}`);
  }

  async function run() {
    const { pendingConfig } = await chrome.storage.local.get('pendingConfig');
    if (!pendingConfig) throw new Error('没有读取到配置，请从插件弹窗重新开始。');
    state.config = normalizeRuntimeConfig({ ...pendingConfig, version: VERSION });

    await collectSearchPages(state.config);
    const uniqueScopedBeforeDetail = dedupe(state.jobs, true);
    const uniqueScopedJobs = await enrichDetails(uniqueScopedBeforeDetail, state.config);
    const classified = uniqueScopedJobs.map(job => classify(job, state.config, 'final'));
    const keptBeforeDedupe = classified.filter(item => item.keep).map(item => normalizeJob({
      ...item.job,
      decision: item.reason,
      remoteMatched: item.remote.matched,
      remoteStatus: item.remote.status,
      remoteConfidence: item.remote.confidence,
      remoteEvidence: item.remote.evidence
    }));
    const finalJobs = sortFinalJobs(dedupe(keptBeforeDedupe, false), state.config);
    const statistics = buildStatistics(finalJobs, uniqueScopedJobs);
    const diagnostics = buildDiagnostics(state.jobs, uniqueScopedJobs, classified, finalJobs, state.config, statistics);
    renderDiagnostics(diagnostics);

    const candidateRecords = classified.map(item => ({
      ...item.job,
      keep: item.keep,
      decision: item.reason,
      pendingDetail: item.pendingDetail,
      parsedSalary: item.salary,
      remoteDecision: item.remote
    }));
    const report = {
      version: VERSION,
      generatedAt: new Date().toISOString(),
      config: state.config,
      statistics,
      jobs: finalJobs,
      candidates: candidateRecords
    };

    const requirementReviewDataset = buildRequirementReviewDataset(finalJobs, state.config, statistics);
    const csv = toCsv(finalJobs);
    const json = JSON.stringify(report, null, 2);
    const diagnosticJson = JSON.stringify(diagnostics, null, 2);
    const requirementReviewJson = JSON.stringify(requirementReviewDataset, null, 2);
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    const csvFilename = `boss-job-filter-v${VERSION}-${stamp}.csv`;
    const jsonFilename = `boss-job-filter-report-v${VERSION}-${stamp}.json`;
    const diagnosticFilename = `boss-job-filter-diagnostics-v${VERSION}-${stamp}.json`;
    const requirementReviewFilename = `boss-job-filter-requirement-review-v${VERSION}-${stamp}.json`;

    state.lastRun = {
      jobs: finalJobs,
      report,
      csv,
      json,
      diagnostics,
      diagnosticJson,
      requirementReviewDataset,
      requirementReviewJson,
      csvFilename,
      jsonFilename,
      diagnosticFilename,
      requirementReviewFilename,
      finishedAt: new Date().toLocaleString()
    };
    await chrome.storage.local.set({ lastRun: state.lastRun });
    await dataDownload(csvFilename, 'text/csv', csv, false);
    await dataDownload(jsonFilename, 'application/json', json, false);
    await dataDownload(diagnosticFilename, 'application/json', diagnosticJson, false);
    await dataDownload(requirementReviewFilename, 'application/json', requirementReviewJson, false);

    el('csv').disabled = false;
    el('json').disabled = false;
    el('diagnostics').disabled = false;
    el('requirementReview').disabled = false;
    const reviewGate = requirementReviewDataset.qualityGate;
    el('summary').textContent = `完成：最终 ${finalJobs.length} 条，完整 JD ${diagnostics.counts.fullJd} 条，Requirement 验收样本 ${reviewGate.selectedCount}/${reviewGate.requiredSampleSize}（${reviewGate.status}）。`;
    log(`Requirement 验收数据：${reviewGate.status}，可用 ${reviewGate.eligibleCount} 条，已选 ${reviewGate.selectedCount}/${reviewGate.requiredSampleSize}。`);
    log('运行完成，已下载 CSV、完整报告、诊断 JSON 和 Requirement 验收数据集。');
    document.title = `完成：筛选出 ${finalJobs.length} 条岗位`;
  }

  globalThis.BossAiRunnerInternals = {
    normalizeRuntimeConfig,
    buildTasks,
    normalizeJob,
    mergeJobs,
    dedupe,
    classify,
    sortFinalJobs,
    buildStatistics,
    buildRequirementReviewDataset
  };
  if (globalThis.__BOSS_JOB_FILTER_TEST__) return;

  el('stop').addEventListener('click', () => {
    state.aborted = true;
    el('stop').disabled = true;
    log('正在停止…');
  });

  el('csv').addEventListener('click', () => {
    if (state.lastRun) dataDownload(state.lastRun.csvFilename, 'text/csv', state.lastRun.csv, true);
  });
  el('json').addEventListener('click', () => {
    if (state.lastRun) dataDownload(state.lastRun.jsonFilename, 'application/json', state.lastRun.json, true);
  });
  el('diagnostics').addEventListener('click', () => {
    if (state.lastRun) dataDownload(state.lastRun.diagnosticFilename, 'application/json', state.lastRun.diagnosticJson, true);
  });
  el('requirementReview').addEventListener('click', () => {
    if (state.lastRun) dataDownload(
      state.lastRun.requirementReviewFilename,
      'application/json',
      state.lastRun.requirementReviewJson,
      true
    );
  });

  run().catch(async error => {
    el('summary').textContent = `任务结束：${error.message || error}`;
    log(`错误：${error.stack || error}`);
    document.title = '岗位筛选已停止';

    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    const emergency = {
      version: VERSION,
      generatedAt: new Date().toISOString(),
      error: {
        name: error?.name || 'Error',
        message: error?.message || String(error),
        stack: error?.stack || ''
      },
      config: state.config,
      counts: {
        rawCardsCollected: state.jobs.length,
        completedPages: state.pageStats.length
      },
      learnedDigitMap: serializeDigitMap(state.digitMap),
      pageStats: state.pageStats,
      rawJobs: state.jobs
    };
    try {
      await dataDownload(
        `boss-job-filter-error-v${VERSION}-${stamp}.json`,
        'application/json',
        JSON.stringify(emergency, null, 2),
        false
      );
      log('已自动导出错误现场 JSON，已采集数据不会完全丢失。');
    } catch (downloadError) {
      log(`错误现场导出失败：${downloadError?.message || downloadError}`);
    }
  });
})();
