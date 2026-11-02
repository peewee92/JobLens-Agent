"""Small, reviewable vocabulary. Retrieval is not a capability assessment."""
RETRIEVAL_VERSION = "evidence-retrieval-v2"
MAX_CANDIDATES = 3

TECHNOLOGIES = (
    ("TypeScript",), ("JavaScript",), ("Java",), ("React", "React.js"),
    ("Electron",), ("Python",), ("FastAPI",), ("Docker",), ("Tauri",),
    ("Vue", "Vue.js"), ("Node.js", "NodeJS"), ("Agent", "智能体"),
    ("Tool Calling", "Function Calling", "工具调用"),
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
