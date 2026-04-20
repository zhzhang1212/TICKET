0. 回复原则：
    - 使用中文回答
    - 禁止私自进行git操作
    - 严禁使用py脚本进行代码修改，只准使用ide工具
1. 核心工程准则 (Engineering Principles)
模块化与 SRP：保持代码模块化，每个文件/类/函数必须职责单一。禁止在单个文件中集成过多无关功能。
物理隔离解耦优先：实现代码在目录层的完全物理隔离，防范多人协作冲突。所有的并行业务被彻底迁移出根目录扁平的 routers/ 和 schemas/，封装在 `modules/` 下独立的领域微服务单元中。跨模块通信严禁直接 import 路由控制器。
设计模式：遵循 FastAPI 最佳实践。逻辑写在 core/ 或 modules/*/ 底层，模块 router.py 仅负责网关分发。
文档同步：始终维护 readme.md（项目结构与依赖关系）。如果代码改动导致项目结构变化，必须同步更新该文档。
脚本清理：如果生成并执行了任何一次性修改脚本，执行完成后必须立即删除该脚本。
2. 严格开发限制 (Strict Constraints)
细分 Agent 职责（前后端隔离范围）：开发 space、event 时必须遵循其专属 Agent（@SpaceDev, @EventDev）的修改边界和执行规范，对于平级的并行业务千万不要越权修改或引用。除了只属于该模块自己的 `router.py`, `schemas.py`、专属 `templates/` 及专属 `static/` 之外，绝不能去修改根目录的全局核心文件。特殊的是：底层风控引擎 `modules/rules_fsm/` 是属于 AB 的共建依赖域，AB Agent 均可通过新增独立策略文件或扩展责任链节点的方式对其内容进行协同修造，而不再将其视为一个独立的代理。
变量名保护：严禁修改我既有的任何变量名，完全按照我的命名思路和既有风格进行扩展。
功能克制：完全按照我的要求实现功能，不要多做任何无关的东西。 * 建议隔离：如有更好的方案或重构建议，请在代码块之外的独立段落提出，不要直接修改到生成的代码中。
语言偏好：除代码本身外，所有解释、注释和文档更新请使用中文。
3. 技术栈特定规范 (Tech Stack Standards)
高并发拦截：如秒杀场景严禁直接穿透写DB，所有后端 I/O 并发操作必须交由 Redis 削峰，并推送到 Celery (Worker)。
数据校验：所有的 Request Body 必须使用本模块内 `schemas.py` 下对应的 Pydantic 模型，路由必须声明 response_model 拒绝全站复用的粗放模型。
前端集成：
所有业务模块均有独立的 `templates/`（HTML骨架）与 `static/` 目录存放特定的专属业务与前端样式。全局只留有 `/templates/index.html` 以及 `static/js/core/` 处理大路由分发、原生 Fetch 封装与全局 ws 长连接管理。开发任何具体模块时必须在它们各自的专属模块目录的 `templates/` 与 `static/` 内修改，而不是去根目录修改。
风控逻辑：涉及权限、信誉分的底座操作必须下沉经过 core/scoring.py 和 modules/rules_fsm/ 防御链。
4. 文件功能字典引用 (File Dictionary)
在生成代码前，请务必参考以下结构与代理职责分配，确保代码放置在正确的模块微服务层级和对应的前端资源目录下：
main.py: 主入口，只负责初始化 FastAPI、生命周期启停、挂载 components 与 `modules/` 各模块及其页面资源和路由组。
modules/space/: 由 @SpaceDev 负责。含有 `router.py`，`schemas.py`，以及独立专属的前端目录 `templates/`（HTML视图）和 `static/`（含JS业务逻辑）。负责离散或连续学术空间的预订校验，并包含隐形5分钟缓冲机制计算。修改空间相关的页面或脚本只能在此模块下进行。
modules/event/: 由 @EventDev 负责。含有 `router.py`，`schemas.py`，消费队列 `tasks.py`，以及专属秒杀体验页面所在的独立 `templates/` 与 `static/`。专属高并发秒杀排队与后端落库、DB冲突兜底。活动页面的改动只能在此目录内部进行。
modules/rules_fsm/: 底层跨模块共建层。抽象的动态规则防重与防漏洞安全层（责任链+流转引擎），作为被 space 或 event 调用的底层逻辑。由开发各自具体业务的 @SpaceDev 或 @EventDev 在这里补充对应领域所需的新型策略节点与流转控制模块，无专职代理。不含有业务层面供用户直接调用的 Web 路由！但它拥有独立的 `templates/` 与 `static/` 用于承载底层观测、防范规则等管理员/后台大盘页面。
routers/: 现在仅用作全局底座开放信道，例如全局 WebSocket 广播网关（`ws.py`）。
core/: 关键机制（scoring.py风控）、全局单例服务（redis_db.py及Lua脚本源）与 AI 算法模块（ai_moderation.py）。
