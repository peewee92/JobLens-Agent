(() => {
  'use strict';

  const VERSION = '1.3.1';
  const PUA_ZERO = 0xE031;
  const PUA_NINE = 0xE03A;

  const clean = value => String(value ?? '').replace(/\s+/g, ' ').trim();



  function limitText(value, maxLength = 50000) {
    const text = clean(value);
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

  function decodeBossText(value, customMap = {}) {
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
      text: clean(output),
      decodedCount,
      hadPua: /[\uE000-\uF8FF]/.test(text),
      unknownPua: [...unknownPua]
    };
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

  const REMOTE_STRONG = /(全远程|纯远程|完全远程|100%\s*远程|fully\s*remote|remote\s*only)/i;
  const REMOTE_POSITIVE = /(可远程|支持远程|接受远程|远程(?:办公|工作|协作|岗位)?|居家办公|在家办公|可居家|不限地点|工作地点不限|全国可办公|全国办公|异地办公|线上办公|remote|work\s*from\s*home|\bwfh\b)/i;
  const REMOTE_NEGATIVE = /(不支持|不接受|不可|不能|拒绝|非)\s*(?:全)?远程|必须.{0,5}(到岗|坐班|驻场)|需.{0,5}(到岗|坐班|驻场)|仅限.{0,8}(本地|到岗|坐班)/i;

  function detectRemote(input = {}) {
    const fields = typeof input === 'string'
      ? { text: input }
      : {
          title: input.title,
          area: input.area,
          tags: input.tags,
          rawText: input.rawText,
          detailText: input.detailText,
          description: input.description
        };
    const sources = [];
    let fullText = '';
    for (const [key, value] of Object.entries(fields)) {
      const decoded = normalizeText(value || '');
      if (!decoded) continue;
      fullText += ` ${decoded}`;
      if (REMOTE_STRONG.test(decoded) || REMOTE_POSITIVE.test(decoded)) sources.push(key);
    }
    fullText = clean(fullText);

    const area = normalizeText(fields.area || '');
    const areaExact = /^(全国|不限地点|工作地点不限|线上|远程)(?:[·\-\s].*)?$/i.test(area);
    const strong = REMOTE_STRONG.test(fullText) || areaExact;
    const positive = REMOTE_POSITIVE.test(fullText) || areaExact;
    const negative = REMOTE_NEGATIVE.test(fullText);

    if (strong) {
      return { matched: true, status: 'confirmed', confidence: 'high', negative, evidence: sources };
    }
    if (negative) {
      return { matched: false, status: 'rejected', confidence: 'high', negative: true, evidence: sources };
    }
    if (positive) {
      return { matched: true, status: 'confirmed', confidence: 'medium', negative: false, evidence: sources };
    }
    return { matched: false, status: 'unknown', confidence: 'low', negative: false, evidence: [] };
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

  function scoreRelevance(job = {}) {
    const title = normalizeText(job.title || '');
    const full = normalizeText([title, job.tags, job.rawText, job.description].filter(Boolean).join(' '));
    let score = 0;
    const reasons = [];

    if (/(ai|人工智能|大模型|\bllm\b|\bagent\b|智能体|\brag\b|\bfde\b)/i.test(title)) {
      score += 35;
      reasons.push('标题含 AI/大模型/Agent 等核心词');
    } else if (/(ai|人工智能|大模型|\bllm\b|\bagent\b|智能体|\brag\b|\bfde\b)/i.test(full)) {
      score += 15;
      reasons.push('卡片或详情含 AI 核心词');
    }

    const categories = classifyCategory(job);
    if (!categories.includes('其他 AI 相关')) {
      score += Math.min(30, categories.length * 15);
      reasons.push(`命中分类：${categories.join('、')}`);
    }

    if (/(开发|研发|工程师|架构|解决方案|交付|实施|产品工程)/.test(title)) {
      score += 20;
      reasons.push('岗位形态符合工程/交付方向');
    }

    if (/(销售|商务|运营|客服|数据标注|审核|行政|招聘|猎头)/.test(title)) {
      score -= 60;
      reasons.push('标题偏非研发岗位');
    }
    if (/(助理|实习|兼职)/.test(title)) {
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
    limitText,
    normalizeStringList,
    normalizeNumberList,
    mergeSearchMetadata,
    normalizeDigitMap,
    decodeBossText,
    normalizeText,
    findSalaryInText,
    parseSalary,
    extractPuaSalaryToken,
    inferDigitMap,
    detectRemote,
    classifyCategory,
    extractSkills,
    scoreRelevance,
    employmentFlags
  };
})();
