"""Small, reviewable vocabulary. Retrieval is not a capability assessment."""
RETRIEVAL_VERSION = "evidence-retrieval-v5"
MAX_CANDIDATES = 3

TECHNOLOGIES = (
    ("TypeScript",), ("JavaScript",), ("Java",), ("React", "React.js"),
    ("Electron",), ("Python",), ("FastAPI",), ("Docker",), ("Tauri",),
    ("Vue", "Vue.js"), ("Node.js", "NodeJS"), ("Agent", "智能体"),
    ("Tool Calling", "Function Calling", "工具调用"),
    ("RAG", "检索增强生成"),
    ("streaming", "流式输出"), ("自动化测试", "automated testing"),
)

RESPONSIBILITIES = (
    ("客户端开发", "客户端重构", "客户端", "跨端开发", "多端开发", "桌面端开发", "桌面端", "Electron", "Tauri"),
    ("重构", "refactoring", "refactor"),
    ("组件库", "组件体系", "设计系统", "component library", "design system"),
    ("架构设计", "架构判断", "架构", "系统设计", "system architecture", "system design"),
    ("产品交付", "产品上线", "上线可用", "独立产品", "独立开发", "端到端交付"),
    ("质量保障", "质量基线", "质量治理", "自动化测试", "CI 门禁", "CI门禁", "前端监控", "quality assurance"),
    ("实时协作", "实时协同", "即时通讯", "实时通信", "real-time collaboration"),
    ("Agent 交互", "Agent交互", "智能体交互", "工具调用", "工具集成", "工具接入", "审批门", "用户确认流程", "Function Calling", "Tool Calling"),
)


# These are retrieval hints, not proof of production scope, tenure or ownership.
DELIVERED_SERVICE_TARGET = (
    r"(?:\b(?:API(?:s)?|back[- ]?end\s+(?:services?|APIs?))\b"
    r"|后端(?:服务|接口|API)|服务端(?:服务|接口|API))"
)
DELIVERY_REQUIREMENT = r"上线|部署|交付|\b(?:deploy(?:ed|ment|ing)?|shipp(?:ed|ing)|ship|production)\b"
DELIVERY_EVIDENCE = r"已上线|已部署|已交付|上线了|发布至生产|部署到生产|\b(?:deployed|shipped|launched|released to production)\b"
DELIVERY_COUNTEREXAMPLE = (
    r"未(?:曾|正式|实际)?(?:上线|部署|交付)|没有(?:上线|部署|交付)|仅(?:在|供)?(?:本地|演示|测试)|计划|教程|练习"
    r"|\b(?:no|not|never|learn(?:ed|ing)?|tutorials?|training|practice|mock(?:s|ed)?|prototype(?:s|d)?"
    r"|plan(?:ned|ning)?|sandbox|staging|demo|documentation|docs|locally|simulated)\b"
    r"|\b(?:local|test(?:ing)?|development|dev)[- ](?:server|environment|machine|cluster|instance)\b"
)

# Exact bilingual equivalence for an unqualified, explicitly alternative shipping
# requirement. Longer requirements (years, scale, technology, ownership) stay related.
PLAIN_DEPLOYED_SERVICE_REQUIREMENT = (
    r"做过已?上线的(?:全栈产品[、，]\s*)?"
    r"(?:API(?:\s*或\s*后端服务)?|后端接口|后端服务)[。.]?"
)
EXPLICIT_BUILT_AND_SHIPPED_SERVICE = (
    r"\b(?:built|developed|implemented)\s+and\s+(?:deployed|shipped|launched)"
    r"\s+(?:(?:an?|the)\s+)?(?:(?:backend\s+)?APIs?|backend\s+services?)\b"
)
