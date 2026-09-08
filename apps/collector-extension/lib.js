(() => {
  'use strict';

  const VERSION = '1.4.7';
  const PUA_ZERO = 0xE031;
  const PUA_NINE = 0xE03A;
  const CJK_RADICAL_FALLBACKS = Object.freeze({
    '⻓': '长'
  });

  const normalizeVisibleText = value => String(value ?? '')
    .replace(/[\u2E80-\u2FD5\uF900-\uFAFF]/g, character => (
      CJK_RADICAL_FALLBACKS[character] || character.normalize('NFKC')
    ))
    .replace(/[\u200B\u2060\uFEFF]/g, '');
  const clean = value => normalizeVisibleText(value).replace(/\s+/g, ' ').trim();

  function cleanMultiline(value) {
    return normalizeVisibleText(value)
      .replace(/\r\n?/g, '\n')
      .split('\n')
      .map(line => line.replace(/[\t\u00A0 ]+/g, ' ').trim())
      .join('\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }

  function limitText(value, maxLength = 50000) {
    const text = clean(value);
    const limit = Math.max(0, Number(maxLength) || 0);
    if (!limit || text.length <= limit) return text;
    return `${text.slice(0, Math.max(0, limit - 1))}…`;
  }

  function limitMultilineText(value, maxLength = 50000) {
    const text = cleanMultiline(value);
    const limit = Math.max(0, Number(maxLength) || 0);
    if (!limit || text.length <= limit) return text;
    return `${text.slice(0, Math.max(0, limit - 1))}…`;
  }

  function normalizeStringList(value, options = {}) {
    const {
      separator = /\s*\|\s*/,
      maxItems = 128,
      maxItemLength = 160
    } = options;
    const queue = Array.isArray(value) ? [...value] : [value];
    const result = [];
    const seen = new Set();

    while (queue.length && result.length < maxItems) {
      const item = queue.shift();
      if (item == null || item === '') continue;
      if (Array.isArray(item) || item instanceof Set) {
        queue.unshift(...item);
        continue;
      }

      const raw = String(item);
      const parts = separator ? raw.split(separator) : [raw];
      for (const part of parts) {
        const normalized = limitText(part, maxItemLength);
        if (!normalized || seen.has(normalized)) continue;
        seen.add(normalized);
        result.push(normalized);
        if (result.length >= maxItems) break;
      }
    }
    return result;
  }

  function normalizeNumberList(value, maxItems = 500) {
    const queue = Array.isArray(value) ? [...value] : [value];
    const numbers = [];
    const seen = new Set();
    while (queue.length && numbers.length < maxItems) {
      const item = queue.shift();
      if (Array.isArray(item) || item instanceof Set) {
        queue.unshift(...item);
        continue;
      }
      const number = Number(item);
      if (!Number.isFinite(number) || number <= 0 || seen.has(number)) continue;
      seen.add(number);
      numbers.push(number);
    }
    return numbers.sort((a, b) => a - b);
  }

  function mergeSearchMetadata(previous = {}, next = {}) {
    const previousSource = Array.isArray(previous.searchKeywords) && previous.searchKeywords.length
      ? previous.searchKeywords
      : previous.searchKeyword;
    const nextSource = Array.isArray(next.searchKeywords) && next.searchKeywords.length
      ? next.searchKeywords
      : next.searchKeyword;
    const searchKeywords = normalizeStringList([previousSource, nextSource]);
    const pages = normalizeNumberList([
      previous.pages,
      previous.page,
      next.pages,
      next.page
    ]);
    return {
      searchKeywords,
      searchKeyword: searchKeywords.join(' | '),
      pages,
      page: pages.length ? pages[0] : 1
    };
  }

  function normalizeDigitMap(input = {}) {
    const map = {};
    for (let digit = 0; digit <= 9; digit += 1) {
      map[String.fromCodePoint(PUA_ZERO + digit)] = String(digit);
    }
    for (const [key, value] of Object.entries(input || {})) {
      if (/^\d$/.test(String(value))) map[key] = String(value);
    }
    return map;
  }

  function decodeBossTextWithNormalizer(value, customMap = {}, normalizer = clean) {
    const text = String(value ?? '');
    const digitMap = normalizeDigitMap(customMap);
    let output = '';
    let decodedCount = 0;
    const unknownPua = new Set();

    for (const char of text) {
      if (Object.prototype.hasOwnProperty.call(digitMap, char)) {
        output += digitMap[char];
        decodedCount += 1;
        continue;
      }

      const codePoint = char.codePointAt(0);
      if (codePoint >= PUA_ZERO && codePoint <= PUA_NINE) {
        output += String(codePoint - PUA_ZERO);
        decodedCount += 1;
        continue;
      }

      if (codePoint >= 0xFF10 && codePoint <= 0xFF19) {
        output += String(codePoint - 0xFF10);
        decodedCount += 1;
        continue;
      }

      if (codePoint >= 0xE000 && codePoint <= 0xF8FF) unknownPua.add(char);
      output += char;
    }

    return {
      text: normalizer(output),
      decodedCount,
      hadPua: /[\uE000-\uF8FF]/.test(text),
      unknownPua: [...unknownPua]
    };
  }

  function decodeBossText(value, customMap = {}) {
    return decodeBossTextWithNormalizer(value, customMap, clean);
  }

  function decodeBossMultilineText(value, customMap = {}) {
    return decodeBossTextWithNormalizer(value, customMap, cleanMultiline);
  }

  function normalizeText(value, customMap = {}) {
    return decodeBossText(value, customMap).text
      .replace(/[Ｋｋ]/g, 'K')
      .replace(/[－—–~～至]/g, '-')
      .replace(/[，,]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  const SALARY_PATTERNS = [
    /\d+(?:\.\d+)?\s*K\s*-\s*\d+(?:\.\d+)?\s*K(?:\s*[·x×*]\s*\d{1,2}\s*薪)?/i,
    /\d+(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?\s*K(?:\s*[·x×*]\s*\d{1,2}\s*薪)?/i,
    /\d+(?:\.\d+)?\s*K(?:以上|起|\+)/i,
    /\d+(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?\s*万\s*\/\s*(?:月|个月|年|每年)/i,
    /年薪\s*\d+(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?\s*万/i,
    /\d+(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?\s*千\s*\/\s*(?:月|个月)/i,
    /\d{4,6}\s*-\s*\d{4,6}\s*元\s*\/\s*(?:月|个月)/i,
    /\d+(?:\.\d+)?\s*K(?:\s*[·x×*]\s*\d{1,2}\s*薪)?/i,
    /\d+\s*-\s*\d+\s*元\s*\/\s*(?:天|日|时|小时|次)/i,
    /面议|薪资面谈|薪资详谈/
  ];

  function findSalaryInText(value = '', customMap = {}) {
    const normalized = normalizeText(value, customMap);
    for (const pattern of SALARY_PATTERNS) {
      const match = normalized.match(pattern);
      if (match) return clean(match[0]);
    }
    return '';
  }

  function round2(value) {
    return Math.round(Number(value) * 100) / 100;
  }

  function parseSalary(value = '', customMap = {}) {
    const decoded = decodeBossText(value, customMap);
    const raw = clean(value);
    const normalized = normalizeText(decoded.text, customMap).replace(/\s+/g, '');
    const base = {
      raw,
      decodedRaw: decoded.text,
      normalized,
      decodedCount: decoded.decodedCount,
      hadPua: decoded.hadPua,
      unknownPua: decoded.unknownPua,
      type: 'unknown',
      minK: null,
      maxK: null,
      months: null,
      sourceUnit: '',
      annualMinWan: null,
      annualMaxWan: null
    };

    if (!normalized) return base;
    if (/面议|薪资面谈|薪资详谈/.test(normalized)) return { ...base, type: 'negotiable' };
    if (/元\/(天|日)|元每天|元\/次/.test(normalized)) return { ...base, type: 'daily' };
    if (/元\/(时|小时)/.test(normalized)) return { ...base, type: 'hourly' };

    const monthCount = Number((normalized.match(/[·x×*](\d{1,2})薪/i) || [])[1]) || null;
    let minK = null;
    let maxK = null;
    let type = 'unknown';
    let sourceUnit = '';

    let match = normalized.match(/(\d+(?:\.\d+)?)K-(\d+(?:\.\d+)?)K/i)
      || normalized.match(/(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)K/i);
    if (match) {
      minK = Number(match[1]);
      maxK = Number(match[2]);
      type = 'monthlyK';
      sourceUnit = 'K/月';
    }

    if (minK == null) {
      match = normalized.match(/(\d+(?:\.\d+)?)K(?:以上|起|\+)/i);
      if (match) {
        minK = Number(match[1]);
        maxK = null;
        type = 'monthlyK';
        sourceUnit = 'K/月';
      }
    }

    if (minK == null) {
      match = normalized.match(/(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)万\/(?:月|个月)/i);
      if (match) {
        minK = round2(Number(match[1]) * 10);
        maxK = round2(Number(match[2]) * 10);
        type = 'monthlyK';
        sourceUnit = '万/月';
      }
    }

    if (minK == null) {
      match = normalized.match(/(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)千\/(?:月|个月)/i);
      if (match) {
        minK = Number(match[1]);
        maxK = Number(match[2]);
        type = 'monthlyK';
        sourceUnit = '千/月';
      }
    }

    if (minK == null) {
      match = normalized.match(/(\d{4,6})-(\d{4,6})元\/(?:月|个月)/i);
      if (match) {
        minK = round2(Number(match[1]) / 1000);
        maxK = round2(Number(match[2]) / 1000);
        type = 'monthlyK';
        sourceUnit = '元/月';
      }
    }

    if (minK == null) {
      match = normalized.match(/(?:年薪)?(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)万\/(?:年|每年)|(?:年薪)(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)万/i);
      if (match) {
        const minWan = Number(match[1] ?? match[3]);
        const maxWan = Number(match[2] ?? match[4]);
        minK = round2(minWan * 10 / 12);
        maxK = round2(maxWan * 10 / 12);
        type = 'annualWan';
        sourceUnit = '万/年';
      }
    }

    if (minK == null) {
      match = normalized.match(/(\d+(?:\.\d+)?)K/i);
      if (match) {
        minK = Number(match[1]);
        maxK = minK;
        type = 'monthlyK';
        sourceUnit = 'K/月';
      }
    }

    if (minK == null) return base;

    const annualMonths = monthCount || 12;
    return {
      ...base,
      type,
      minK,
      maxK,
      months: monthCount,
      sourceUnit,
      annualMinWan: round2(minK * annualMonths / 10),
      annualMaxWan: maxK == null ? null : round2(maxK * annualMonths / 10)
    };
  }

  function extractPuaSalaryToken(value = '') {
    const text = String(value || '').replace(/[－—–~～至]/g, '-');
    const patterns = [
      /[\uE000-\uF8FF]+\s*-\s*[\uE000-\uF8FF]+\s*K(?:\s*[·x×*]\s*[\uE000-\uF8FF]+\s*薪)?/i,
      /[\uE000-\uF8FF]+\s*K/i,
      /[\uE000-\uF8FF]+\s*-\s*[\uE000-\uF8FF]+\s*元\s*\/\s*(?:天|日|月|时|小时)/i
    ];
    for (const pattern of patterns) {
      const match = text.match(pattern);
      if (match) return match[0];
    }
    return '';
  }

  function inferDigitMap(plainSalaryText = '', puaText = '', existingMap = {}) {
    const map = { ...(existingMap || {}) };
    const plain = findSalaryInText(plainSalaryText, existingMap);
    const puaToken = extractPuaSalaryToken(puaText);
    if (!plain || !puaToken) return map;

    const digits = plain.match(/\d/g) || [];
    const chars = [...puaToken].filter(char => /[\uE000-\uF8FF]/.test(char));
    if (digits.length !== chars.length) return map;

    const evidence = {};
    for (let index = 0; index < chars.length; index += 1) {
      const char = chars[index];
      const digit = digits[index];
      if (evidence[char] && evidence[char] !== digit) return { ...(existingMap || {}) };
      evidence[char] = digit;
    }

    // 标题中的明文薪资与同一卡片的私有区薪资是一组强证据。
    // 允许它覆盖内置的顺序映射，以应对 BOSS 将来轮换字体编码。
    return { ...map, ...evidence };
  }

  const REMOTE_NON_WORK_SUFFIX = '(?:监测|控制|运维|支持|服务|诊断|操作|设备|系统|医疗|教学|协助|访问|连接|调试|巡检|调用|桌面)';
  const REMOTE_STRONG = new RegExp(`(?:全国远程|全远程|纯远程|完全远程)(?!${REMOTE_NON_WORK_SUFFIX})|100%\\s*远程|fully\\s*remote|remote\\s*only`, 'i');
  const REMOTE_POSITIVE = /(可(?:全)?远程|支持(?:全)?远程|接受(?:全)?远程|远程(?:办公|工作|协作|岗位)|居家办公|在家办公|可居家|不限地点|工作地点不限|全国可办公|全国办公|异地办公|线上办公|work\s*from\s*home|\bwfh\b)/i;
  const REMOTE_TITLE_POSITIVE = new RegExp(`${REMOTE_POSITIVE.source}|远程(?!${REMOTE_NON_WORK_SUFFIX})|\\bremote\\b`, 'i');
  const REMOTE_NEGATIVE = /(?:不支持|不接受|不可|不能|拒绝|非)\s*(?:(?:全)?远程(?:办公|工作|协作|岗位)?|居家办公|在家办公|异地办公|线上办公|remote|work\s*from\s*home|\bwfh\b)|必须.{0,5}(?:到岗|坐班|驻场)|需.{0,5}(?:到岗|坐班|驻场)|仅限.{0,8}(?:本地|到岗|坐班)/i;

  function stripRemoteNegativePhrases(value = '') {
    return clean(String(value ?? '').replace(new RegExp(REMOTE_NEGATIVE.source, 'gi'), ' '));
  }

  function detectRemote(input = {}) {
    const fields = typeof input === 'string'
      ? { text: input }
      : {
          title: input.title,
          area: input.area,
          tags: input.tags,
          rawText: input.rawText,
          description: input.description
        };
    const sources = [];
    const negativeSources = [];
    let fullText = '';
    let positiveText = '';
    for (const [key, value] of Object.entries(fields)) {
      const decoded = normalizeText(value || '');
      if (!decoded) continue;
      fullText += ` ${decoded}`;
      if (REMOTE_NEGATIVE.test(decoded)) negativeSources.push(key);
      const positiveCandidate = stripRemoteNegativePhrases(decoded);
      positiveText += ` ${positiveCandidate}`;
      const positivePattern = key === 'title' || key === 'tags' || key === 'text'
        ? REMOTE_TITLE_POSITIVE
        : REMOTE_POSITIVE;
      if (REMOTE_STRONG.test(positiveCandidate) || positivePattern.test(positiveCandidate)) sources.push(key);
    }
    fullText = clean(fullText);
    positiveText = clean(positiveText);

    const area = normalizeText(fields.area || '');
    const areaExact = /^(全国|不限地点|工作地点不限|线上|远程)(?:[·\-\s].*)?$/i.test(area);
    const strong = REMOTE_STRONG.test(positiveText) || areaExact;
    const positive = sources.length > 0 || areaExact;
    const negative = REMOTE_NEGATIVE.test(fullText);

    if (strong) {
      return { matched: true, status: 'confirmed', confidence: 'high', negative, evidence: sources };
    }
    if (positive) {
      return { matched: true, status: 'confirmed', confidence: 'medium', negative, evidence: sources };
    }
    if (negative) {
      return { matched: false, status: 'rejected', confidence: 'high', negative: true, evidence: negativeSources };
    }
    return { matched: false, status: 'unknown', confidence: 'low', negative: false, evidence: [] };
  }

  const JD_SECTION_SIGNAL = /(岗位职责|职位职责|工作职责|任职要求|任职资格|职位要求|岗位要求|工作内容|职责描述|你将负责|我们希望|我们需要|能力要求|技术要求|硬性要求)/i;
  const JD_LIST_SIGNAL = /(?:^|[\s\n])(?:\d{1,2}[.、]|[一二三四五六七八九十]+[、.])\s*[^\s]/m;
  const JD_RESPONSIBILITY_SIGNAL = /(?:^|[。；;\n])[^。；;\n]{0,24}(负责|主导|参与|设计|构建|开发|建设|优化|维护|推进|跟踪|协同|制定|实现|搭建|输出|解决|保障|研究|探索|集成|调研|管理)/gim;
  const JD_REQUIREMENT_SIGNAL = /(本科|硕士|博士|学历|专业优先|年以上|年(?:相关)?工作经验|熟悉|精通|掌握|具备|优先考虑|有[^\n。；;]{0,20}经验|能力要求|任职|职位要求|岗位要求|硬性要求|加分项|技术栈)/gi;
  const JD_PAGE_NOISE = /(BOSS直聘|BOSS\s*安全提示|竞争力分析|查看完整个人竞争力|职位搜索|投资者关系|求职技巧|猜你喜欢|推荐职位|更多职位|精选职位|看过该职位的人还看了|城市招聘|热门职位|推荐公司|热门企业|页面更新时间|企业服务热线|隐私政策|防骗指南|电子营业执照|人力资源服务许可证)/gi;
  const JD_START_MARKER = /(?:职位描述|岗位描述)[ \t]*[:：]?/i;
  const JD_STOP_MARKERS = [
    '认证资质',
    '竞争力分析',
    'BOSS 安全提示',
    '更多职位',
    '看过该职位的人还看了',
    '精选职位',
    '城市招聘',
    '页面更新时间',
    '企业服务热线',
    '职位搜索 BOSS直聘APP'
  ];
  const JD_RECRUITER_TAIL = /(?:^|\n)[^\n]{1,40}(?:先生|女士)?[ \t]*\n(?:刚刚|今日|本周|近两周|本月|\d+\s*月内)活跃(?:\n[\s\S]{0,160})?$/i;

  function extractJobDescriptionSegment(value = '') {
    const original = cleanMultiline(value);
    let text = original;
    let startMarker = '';
    let stopMarker = '';

    const startMatch = JD_START_MARKER.exec(text);
    if (startMatch) {
      startMarker = startMatch[0];
      text = text.slice(startMatch.index + startMatch[0].length);
    }

    let stopIndex = -1;
    for (const marker of JD_STOP_MARKERS) {
      const index = text.indexOf(marker);
      if (index < 80 || (stopIndex >= 0 && index >= stopIndex)) continue;
      stopIndex = index;
      stopMarker = marker;
    }
    if (stopIndex >= 0) text = text.slice(0, stopIndex);

    const recruiterTailMatch = JD_RECRUITER_TAIL.exec(text);
    if (recruiterTailMatch && recruiterTailMatch.index >= 80) {
      text = text.slice(0, recruiterTailMatch.index);
      stopMarker = 'recruiter_profile';
    }

    text = cleanMultiline(text)
      .replace(/^[】\]）)]+\s*/, '')
      .replace(/^(?:(?:下载App[^\n]{0,80})?\s*)?(?:微信扫码分享\s*)?(?:举\s*报|举报)?\s*/i, '')
      .replace(/\s+[\u4e00-\u9fa5A-Za-z·（）()]{1,30}\s+(?:刚刚活跃|今日活跃|本周活跃|近两周活跃|本月活跃)(?:\s|$)[\s\S]*$/i, '')
      .trim();

    return {
      text,
      sanitized: Boolean(startMarker || stopMarker || text !== original),
      startMarker,
      stopMarker
    };
  }

  function stableTextHash(value = '') {
    const text = String(value ?? '');
    let hash = 0x811c9dc5;
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 0x01000193) >>> 0;
    }
    return `fnv1a32:${hash.toString(16).padStart(8, '0')}`;
  }

  function assessDescriptionQuality(input = {}) {
    const description = cleanMultiline(input.description || '');
    const descriptionSource = clean(input.descriptionSource || '');
    const descriptionSelectorTrust = clean(input.descriptionSelectorTrust || '');
    const descriptionSanitized = Boolean(input.descriptionSanitized);
    const detailAttempted = Boolean(input.detailAttempted);
    const detailSucceeded = Boolean(input.detailSucceeded);
    const descriptionLength = description.length;
    const hasSectionSignal = JD_SECTION_SIGNAL.test(description);
    const hasListSignal = JD_LIST_SIGNAL.test(description);
    const responsibilitySignalCount = (description.match(JD_RESPONSIBILITY_SIGNAL) || []).length;
    const requirementSignalCount = (description.match(JD_REQUIREMENT_SIGNAL) || []).length;
    const hasRoleEvidenceSignal = hasSectionSignal
      || (responsibilitySignalCount >= 2 && requirementSignalCount >= 2)
      || (hasListSignal && (responsibilitySignalCount >= 5 || requirementSignalCount >= 4));
    const hasContentSignal = hasRoleEvidenceSignal;
    const noiseMatches = description.match(JD_PAGE_NOISE) || [];
    if (JD_RECRUITER_TAIL.test(description)) noiseMatches.push('recruiter_profile');
    const isBodyFallback = descriptionSource === 'body_fallback';
    const isBroadSelector = descriptionSelectorTrust === 'broad'
      || descriptionSource === 'selector:.job-detail-section'
      || descriptionSource === 'selector:.job-detail'
      || descriptionSource === 'selector:[class*="job-detail"]';
    const trustedSource = descriptionSelectorTrust === 'trusted' || (!isBroadSelector && !isBodyFallback);
    const sourceEligible = trustedSource || (isBroadSelector && descriptionSanitized);
    const reasons = [];

    let descriptionQuality = 'unavailable';
    if (!detailAttempted) {
      descriptionQuality = 'card_only';
      reasons.push('detail_not_attempted', 'missing_full_jd');
    } else if (!detailSucceeded) {
      reasons.push('detail_fetch_failed', 'missing_full_jd');
    } else if (!description) {
      reasons.push('missing_description', 'missing_full_jd');
    } else if (isBodyFallback) {
      descriptionQuality = descriptionLength >= 120 ? 'partial_jd' : 'unavailable';
      reasons.push('body_fallback_not_trusted', 'missing_full_jd');
    } else if (
      descriptionLength >= 180
      && noiseMatches.length === 0
      && hasContentSignal
      && sourceEligible
    ) {
      descriptionQuality = 'full_jd';
    } else if (descriptionLength >= 80) {
      descriptionQuality = 'partial_jd';
      if (descriptionLength < 180) reasons.push('description_too_short');
      if (noiseMatches.length > 0) reasons.push('page_noise_detected');
      if (!hasContentSignal) reasons.push('missing_job_evidence');
      if (isBroadSelector && !descriptionSanitized) reasons.push('broad_selector_not_sanitized');
      if (!sourceEligible) reasons.push('description_source_not_trusted');
      reasons.push('missing_full_jd');
    } else {
      reasons.push('description_too_short', 'missing_full_jd');
    }

    const requirementReviewEligible = descriptionQuality === 'full_jd';
    return {
      descriptionQuality,
      descriptionLength,
      descriptionHash: description ? stableTextHash(description) : '',
      descriptionHasSectionSignal: hasSectionSignal,
      descriptionHasContentSignal: hasContentSignal,
      descriptionHasRoleEvidenceSignal: hasRoleEvidenceSignal,
      descriptionResponsibilitySignalCount: responsibilitySignalCount,
      descriptionRequirementSignalCount: requirementSignalCount,
      descriptionNoiseCount: noiseMatches.length,
      requirementReviewEligible,
      requirementReviewIneligibilityReasons: requirementReviewEligible ? [] : [...new Set(reasons)]
    };
  }

  const CATEGORY_RULES = [
    ['FDE / 前线部署', /\bfde\b|前线部署/i],
    ['AI Agent / 智能体', /\bagent\b|智能体|多智能体|mcp/i],
    ['RAG / 知识库', /\brag\b|检索增强|知识库|向量检索/i],
    ['大模型 / LLM 应用', /大模型|\bllm\b|生成式\s*ai|aigc/i],
    ['AI 交付 / 实施', /(?:ai|大模型).{0,8}(交付|实施)|(交付|实施).{0,8}(?:ai|大模型)/i],
    ['AI 解决方案', /(?:ai|大模型).{0,8}解决方案|解决方案.{0,8}(?:ai|大模型)/i],
    ['AI 产品工程', /ai\s*产品工程|ai\s*product\s*engineer/i],
    ['AI 全栈 / 前端', /(?:ai|大模型).{0,8}(全栈|前端)|(全栈|前端).{0,8}(?:ai|大模型)/i],
    ['AI 应用开发', /(?:ai|大模型|llm).{0,10}(应用|开发|研发|工程师)|(应用|开发|研发).{0,10}(?:ai|大模型|llm)/i]
  ];

  const SKILL_RULES = [
    ['JavaScript', /\bjavascript\b|\bjs\b/i],
    ['TypeScript', /\btypescript\b|\bts\b/i],
    ['React', /\breact(?:\.js)?\b/i],
    ['Vue', /\bvue(?:\.js)?\b/i],
    ['Node.js', /\bnode(?:\.js)?\b/i],
    ['Electron', /\belectron\b/i],
    ['Python', /\bpython\b/i],
    ['Java', /\bjava\b/i],
    ['Go', /\bgolang\b|\bgo语言\b/i],
    ['FastAPI', /\bfastapi\b/i],
    ['Django', /\bdjango\b/i],
    ['LangChain', /\blangchain\b/i],
    ['LangGraph', /\blanggraph\b/i],
    ['LlamaIndex', /\bllamaindex\b/i],
    ['RAG', /\brag\b|检索增强/i],
    ['Agent', /\bagent\b|智能体/i],
    ['MCP', /\bmcp\b|model context protocol/i],
    ['Prompt Engineering', /prompt\s*engineering|提示词工程/i],
    ['向量数据库', /向量数据库|vector\s*database|milvus|qdrant|weaviate|pinecone|faiss/i],
    ['Elasticsearch', /elasticsearch|\bes\b/i],
    ['PostgreSQL', /postgresql|postgres/i],
    ['MySQL', /mysql/i],
    ['Redis', /redis/i],
    ['Docker', /docker|容器化/i],
    ['Kubernetes', /kubernetes|\bk8s\b/i],
    ['AWS', /\baws\b|amazon web services/i],
    ['Azure', /\bazure\b/i],
    ['阿里云', /阿里云/i],
    ['腾讯云', /腾讯云/i]
  ];

  function classifyCategory(job = {}) {
    const text = normalizeText([job.title, job.tags, job.rawText, job.description].filter(Boolean).join(' '));
    const categories = CATEGORY_RULES.filter(([, pattern]) => pattern.test(text)).map(([name]) => name);
    return categories.length ? categories : ['其他 AI 相关'];
  }

  function extractSkills(job = {}) {
    const text = normalizeText([
      job.title,
      job.tags,
      job.rawText,
      job.description,
      job.detailText
    ].filter(Boolean).join(' '));
    return SKILL_RULES.filter(([, pattern]) => pattern.test(text)).map(([name]) => name);
  }

  const QUERY_ROLE_TERMS = [
    '设计', '开发', '工程师', '产品', '运营', '销售', '算法', '前端', '后端',
    '测试', '架构', '实施', '顾问', '经理', '总监', '研究', '教师', '老师'
  ];

  function compactRelevanceText(value) {
    return normalizeText(value || '')
      .toLocaleLowerCase()
      .replace(/[^\p{L}\p{N}\u3400-\u9FFF]+/gu, '');
  }

  function searchKeywordsForRelevance(job = {}) {
    return normalizeStringList([job.searchKeywords, job.searchKeyword], {
      separator: /\s*\|\s*/,
      maxItems: 128,
      maxItemLength: 200
    });
  }

  function searchIntentRelevance(job, title, full) {
    const compactTitle = compactRelevanceText(title);
    const compactFull = compactRelevanceText(full);
    let best = { score: 0, reason: '' };

    for (const keyword of searchKeywordsForRelevance(job)) {
      const normalizedKeyword = normalizeText(keyword).toLocaleLowerCase();
      const compactKeyword = compactRelevanceText(normalizedKeyword);
      if (!compactKeyword) continue;

      if (compactTitle.includes(compactKeyword)) {
        if (best.score < 70) best = { score: 70, reason: `标题直接命中搜索词：${keyword}` };
        continue;
      }

      let componentMatched = false;
      for (const roleTerm of QUERY_ROLE_TERMS) {
        const compactRole = compactRelevanceText(roleTerm);
        if (!compactKeyword.endsWith(compactRole)) continue;
        const prefix = compactKeyword.slice(0, -compactRole.length);
        if (prefix.length >= 2 && compactTitle.includes(prefix) && compactTitle.includes(compactRole)) {
          componentMatched = true;
          break;
        }
      }
      if (componentMatched && best.score < 55) {
        best = { score: 55, reason: `标题命中搜索意图核心词：${keyword}` };
        continue;
      }

      if (compactFull.includes(compactKeyword) && best.score < 30) {
        best = { score: 30, reason: `卡片或详情命中搜索词：${keyword}` };
      }
    }
    return best;
  }

  function scoreRelevance(job = {}) {
    const title = normalizeText(job.title || '');
    const full = normalizeText([title, job.tags, job.rawText, job.description].filter(Boolean).join(' '));
    const keywords = searchKeywordsForRelevance(job);
    const searchIntent = searchIntentRelevance(job, title, full);
    let score = searchIntent.score;
    const reasons = searchIntent.reason ? [searchIntent.reason] : [];

    const aiTitleMatched = /(ai|人工智能|大模型|\bllm\b|\bagent\b|智能体|\brag\b|\bfde\b)/i.test(title);
    const aiFullMatched = !aiTitleMatched && /(ai|人工智能|大模型|\bllm\b|\bagent\b|智能体|\brag\b|\bfde\b)/i.test(full);
    if (aiTitleMatched) {
      score += 35;
      reasons.push('标题含 AI/大模型/Agent 等核心词');
    } else if (aiFullMatched) {
      score += 15;
      reasons.push('卡片或详情含 AI 核心词');
    }

    const categories = classifyCategory(job);
    const hasAiCategory = !categories.includes('其他 AI 相关');
    if (hasAiCategory) {
      score += Math.min(30, categories.length * 15);
      reasons.push(`命中分类：${categories.join('、')}`);
    }

    const hasSearchOrAiSignal = searchIntent.score > 0 || aiTitleMatched || aiFullMatched || hasAiCategory;
    if (hasSearchOrAiSignal && /(开发|研发|工程师|架构|解决方案|交付|实施|产品工程)/.test(title)) {
      score += 20;
      reasons.push('岗位形态与已命中的搜索/技术方向一致');
    }

    const nonDevelopmentPattern = /(销售|商务|运营|客服|数据标注|审核|行政|招聘|猎头)/;
    const explicitlyTargetsNonDevelopment = keywords.some(keyword => nonDevelopmentPattern.test(normalizeText(keyword)));
    if (!explicitlyTargetsNonDevelopment && nonDevelopmentPattern.test(title)) {
      score -= 60;
      reasons.push('标题偏离当前搜索方向（销售/商务/运营等）');
    }

    const juniorPattern = /(助理|实习|兼职)/;
    const explicitlyTargetsJunior = keywords.some(keyword => juniorPattern.test(normalizeText(keyword)));
    if (!explicitlyTargetsJunior && juniorPattern.test(title)) {
      score -= 15;
      reasons.push('标题含助理/实习/兼职');
    }
    return { score: Math.max(0, Math.min(100, score)), reasons, categories };
  }

  function employmentFlags(job = {}) {
    const text = normalizeText([job.title, job.tags, job.rawText].filter(Boolean).join(' '));
    return {
      partTime: /(兼职|日结|小时工)/.test(text),
      internship: /(实习|实习生|在校)/.test(text),
      assistant: /(助理|初级助理)/.test(text)
    };
  }

  globalThis.BossJobFilterLib = {
    VERSION,
    clean,
    cleanMultiline,
    limitText,
    limitMultilineText,
    normalizeStringList,
    normalizeNumberList,
    mergeSearchMetadata,
    normalizeDigitMap,
    decodeBossText,
    decodeBossMultilineText,
    normalizeText,
    findSalaryInText,
    parseSalary,
    extractPuaSalaryToken,
    inferDigitMap,
    detectRemote,
    extractJobDescriptionSegment,
    stableTextHash,
    assessDescriptionQuality,
    classifyCategory,
    extractSkills,
    scoreRelevance,
    employmentFlags
  };
})();
