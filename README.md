# 智约校园 (Smart Campus Booking)

本项目是一个面向港科广校园场景的高并发综合预约 Web 平台。支持会议室、体育场地、活动票务等多类资源的预订与管理。系统采用**纯异步 Python (FastAPI + Celery) + Jinja2/ES6 原生前端**的全栈架构，基于“时间片 (Time-Slot Sharding)”设计，完美解决高并发抢订与复杂规则校验问题。

---

## 1. 项目目录结构 (物理隔离与解耦重构版)

本项目遵循“基于特性 (Feature-Driven)”的领域驱动解耦设计，严格剥离底层基建与上层多态业务模块，确保多人协作零冲突。各目录与核心文件的详细功能与联动关系如下：

```text
├── main.py                  # 【主入口】功能：初始化 FastAPI 应用实例。联动：挂载 routers/ws.py、各 modules/ 路由；调用 core/redis_db.py 管理生命周期；装载静态与模板资源。
├── requirements.txt         # 【依赖管理】功能：记录全局 Python 依赖包清单。
├── Dockerfile               # 【部署容器】多阶段构建，优化镜像体积与安全。
├── docker-compose.yml       # 【服务编排】一键拉起 Postgres、Redis、Web 及 Celery Worker。
├── core/                    # 【核心基建与公共服务层】功能：全局单例服务，独立于任何单一业务模块。
│   ├── redis_db.py          #   - 功能：Redis 异步连接池与操作服务。联动：被 main.py、routers/ws.py、modules/event/router.py 调用或订阅。
│   ├── security.py          #   - 功能：HttpOnly 会话令牌签发与当前登录用户解析，避免前端伪造 user_id。
│   ├── database.py          #   - 功能：PostgreSQL 异步引擎设置及初始化保障。
│   ├── models.py            #   - 功能：底层数据库模型实体（包括时间缓冲区间、排斥约束等特性化建表配置）。
│   └── judge.py             #   - 功能：资格判定引擎，接管核心的前置校验逻辑。
├── modules/                 # 【自治业务微服务层】功能：按特性划分的物理隔离微服务（避免代码合流与网关冲突）。
│   ├── event/               #   - 【活动秒杀】功能：高并发活动抢票的独立闭环。
│   │   ├── router.py        #     - 功能：秒杀鉴权与极速 Redis 预扣网关。绝对禁止直接查写 DB。
│   │   ├── schemas.py       #     - 功能：事件模块私有 Pydantic 模型。仅供同级 router.py 单向校验。
│   │   └── tasks.py         #     - 功能：Celery Worker 消费者，抗峰并执行落库与回滚。成功或失败均通过 Redis PubSub 通知 routers/ws.py。
│   ├── space/               #   - 【空间调度】功能：处理学术空间、离散体育设施等非并发预约。
│   │   ├── router.py        #     - 功能：空间分配与时间缓冲期排他校验路由。底层调用 rules_fsm 进行复杂规则结算。
│   │   └── schemas.py       #     - 功能：空间模块私有 Pydantic 校验模型。
│   └── rules_fsm/           #   - 【抽象规则底层引擎】功能：统一的复杂业务过滤与流转决策中心。
│       ├── fsm/order_fsm.py #     - 功能：流转订单状态（待确认/已取消等），防幽灵支付。
│       └── rule_engine/base.py#   - 功能：预约规则判断的责任链拦截器。验证用户配额与门槛。
├── routers/                 # 【全局非业务路由层】存放通信、状态等底座级外网敞口。
│   ├── auth.py              #   - 功能：登录校验与发给前端的自动身份信息整合，密码哈希存储等控制。
│   └── ws.py                #   - 功能：全站长连接广播下发节点。实时推送确权结果至前端 static/js/core/ws.js。
├── schemas/                 # 【全局共有规范层】存放各线高度重叠时的基础泛型封装。
├── static/                  # 【前端静态资源层】按域隔离的原生 ES6 与样式。
│   ├── css/style.css        #   - 功能：全局的基础 UI 级统一样式定义。
│   └── js/
│       └── core/            #   - 【前端基建】
│           └── ws.js        #     - 功能：单页面全局 WS 长连接守护进程。
├── templates/               # 【服务端渲染模板层】基于 Jinja2 构建的动态视图。
│   ├── index.html           #   - 功能：平台的首屏单页面 Web 骨架。
│   └── login.html           #   - 功能：用户登录/默认自动注册页面。
├── tests/                   # 【测试资源库】功能：涵盖核心机制和模块的完备单元测试。
│   ├── test_fsm.py          #   - 功能：校验 FSM 状态机跳转及安全卡口。
│   └── test_rules.py        #   - 功能：验证高复杂度配置及排他等组合规则链处理。
└── .github/workflows/       # 【CI 流水线】自动化验收，包含了构建镜像与代码风格校验（ruff）和单元测试运行。
```

## 2. 核心组件功能说明

1. **FastAPI 网关 (API Gateway / main.py & routers)**
   - **功能**：处理前端发来的 HTTP 请求，完成基础路由、鉴权并挂载应用框架。
   - **高并发策略**：不直接在路由中查写数据库。它负责阻挡所有不符合规范的请求，调用轻量操作，以保证主请求能以极高的吞吐量返回。
2. **预生产时间片与秒杀判定 (Redis + Lua)**
   - **功能**：解决库存争抢（超卖）的核心。采用时段碎片化概念，也就是对具体每一个时间片发放唯一库存（如 `Slot_羽毛球1号_1800` 存为1）。
   - **高并发策略**：当数百人争抢同一目标资源时，通过 Lua 脚本在 Redis 内存中原子执行“读库存+减库存”，让无效请求提早出局。
3. **异步消费调度 (Celery Worker MQ)**
   - **功能**：承接经 Redis 放行的、“大概率成功”的高意向请求，将其解耦送入缓冲队列。
   - **高并发策略**：实现巨大的流量削峰。让后端的数据库以自己最稳健的速率吃下数据写入，而不必承担瞬时迸发的 TCP 并发连接峰值。
4. **强一致性数据库底座 (PostgreSQL)**
   - **功能**：最真实的业务仓储底座。
   - **高并发策略**：活动订单已补齐独立的 `event_orders` 持久化表，Worker 会在 Redis 预扣后完成订单状态落库，并通过版本号 CAS 与唯一约束做“物理兜底”。
5. **前端协作层 (Jinja2 + Native ES6)**
   - **功能**：负责页面元素的展示呈现与动作下发，拒绝如 Next.js 类臃肿SPA的目录侵入。
   - **协作策略**：UI 层在发单后立即拿到“预约正在确认”的状态切面。通过独立的 `ws.js` 与服务端长连接通信来接受确权后的结果推送。HTTP 接口则依赖 HttpOnly 会话 Cookie 识别当前用户，不再仅信任前端提交的 `user_id`。

## 3. 分层协作流程：一条抢票请求的生命周期

以某学生在 UI 点击**“预约 周五 18:00 羽毛球场”**为例：

1. **前端触发 (Static JS)**
   用户点击界面（`modules/event/static/js/booking.js` 拦截动作），封装用户 ID 与他要抢占的目标 `Slot_ID` 值，通过 Ajax (Fetch) 抛向后端秒杀接口 `/api/v1/events/seckill`。
   
2. **网关拦截与风控校验 (FastAPI + core/judge.py)**
   接收到数据。控制器先向 `core/judge.py` 对比学生的风控信誉档案与活动窗口、取消惩罚等前置条件。
   若是不满足（如上周爽约未扣完分），路由火速在最不耗资源的地方中断并踢回 `HTTP 403/400 警告`。

3. **Redis 毫秒级争抢决断 (Redis/Lua)**
   风控通过后，FastAPI 调用 `core/redis_db.py` 向内部 Redis 下发一段 Lua 指令。
   Redis 检查对应该场地对应时间片的 `Slot_ID` 坑位是否空闲。
   - **未能扣中**：立马返回失败，前端展示已被他人横刀夺爱。
   - **成功预扣**：给前端发送 `200 正在出单...`，以安慰剂方式响应用户请求。

4. **后台落库排队与校验 (Celery Worker + DB)**
   步骤三虽然给用户返回了响应，但其实并没有写入硬盘。路由通过向 `modules/event/tasks.py` 派发一条插入事件来进行业务交接。
   Celery 消费者队列从容捞取订单，向 Postgres 提交 `INSERT`。
   若不幸被并发产生的极低概率幽灵资源碰出（导致主键重复），Worker 将异常吞下并调用 Redis 进行 `INCR +1` 将错误扣减坑位补偿复原。

5. **长连接信使与 UI 更新 (WebSocket)**
   当 Worker `INSERT` 落库大获全胜后，代表这笔预约尘埃落定。
   系统抛出广播信标。而前端的 `static/js/core/ws.js` 常驻后台恰好收听到此信标。将其交由 Booking 特征层，刷新界面渲染为“绿色-预定成功并显示二维码”。


## 4. 模块解耦与协作边界设计

为了支撑多人协作并杜绝代码冲突，项目在结构上实行了**基于特性（Feature-Driven）的严格物理目录隔离**。所有的并行业务被彻底迁移出扁平的 routers/schemas，而是封装成了独立的领域微服务单元 (`modules/`)。

### 模块 A：多态空间建模与预订系统 (`modules/space/`)
- **核心目标**：处理学术空间（5分钟缓冲挑战）和体育设施（离散复用冲突）。
- **文件边界**：
  - `modules/space/schemas.py`：完全独立的数据校验，拒绝与其他业务复用。
  - `modules/space/router.py`：仅暴露 `/api/v1/spaces` 路由组。绝对禁止跨模块 `import` 事件 (event) 的东西。
- **跨模块调用策略**：只能去调用全局挂载的基础接口或底层的 `modules/rules_fsm` 机制。

### 模块 B：校园热门活动聚合秒杀 (`modules/event/`)
- **核心目标**：利用 Redis + Celery 削峰，抗击并发流量洪峰。
- **文件边界**：
  - `modules/event/schemas.py`：秒杀入参校验模型。
   - `modules/event/router.py`：仅暴露 `/api/v1/events` 路由组。主流程通过 Redis 预扣与 FSM 流转执行并发控制，并调用同级 `tasks.py` 提供的 DB CAS 封装。
   - `modules/event/tasks.py`：除 Celery 消费外，包含事件订单表与 DB CAS 乐观锁封装，用于双层乐观锁一致性保障。
- **零耦合证明**：独立成包后，不需要也绝对无法和空间业务进行深层状态缠绕。资源争夺决断由底层的 `core.redis_db` 提供原生 Lua 脚本支持。

### 模块 C：复杂状态机与动态规则引擎 (`modules/rules_fsm/`)
- **核心目标**：提供可供复用的有限状态机流转控制与责任链规则拦截器。
- **文件边界**：
  - `modules/rules_fsm/rule_engine/base.py`：动态规则责任链底层抽象，处理权限/额度验证。
  - `modules/rules_fsm/fsm/order_fsm.py`：处理包含“待支付、已确认、已取消、已爽约”的流转及幽灵支付防范。
- **设计地位**：这是纯粹的“底层逻辑抽象层”，不依赖任何 A、B 模块的上游路由/接口格式包。只能由上层 modules 在需要时单向 `import` 进行计算调用。



## 5. 部署方式与运行说明

本项目原生支持 `docker-compose`，所有基础设施（PostgreSQL, Redis）和应用服务（Web, Worker）无需手动安装，全量容器化编排。

**环境依赖：**
- Docker（建议 20.10+ 版本）
- Docker Compose v2 插件

### 第一步：准备环境变量

```bash
cp .env.example .env
```

`.env.example` 已包含本地开发所需的全部默认值，直接复制即可，无需修改。

### 第二步：一键启动

```bash
docker compose up -d --build
```

此命令自动构建镜像并启动全部 4 个容器：

| 容器 | 作用 | 端口 |
|------|------|------|
| `postgres` | 主数据库，含健康检查与 btree_gist 扩展 | 5432 |
| `redis` | 缓存 + 消息队列 Broker | 6379 |
| `web` | FastAPI 主服务 + 静态资源托管 | **8000** |
| `worker` | Celery 异步任务消费进程 | — |

等待约 30–60 秒（PostgreSQL 完成初始化），再进行后续访问。

**跟踪启动日志：**
```bash
docker compose logs -f web worker
```

**验证全部服务健康：**
```bash
docker compose ps          # 所有服务均为 healthy / running
curl http://localhost:8000/ # 返回 HTML 即正常
```

---

### 用户操作流程

#### 1. 注册 / 登录
访问 `http://localhost:8000/login`，输入任意用户名与密码。

- 首次输入 → 系统自动注册并以 PBKDF2 哈希存储密码
- 再次输入相同用户名密码 → 正常登录

登录后跳转至首页 `http://localhost:8000/`，顶部显示当前用户名与信誉分。

#### 2. 模块 A：空间预订（`http://localhost:8000/space`）

**学术空间（会议室）：**
1. 点击任意学术空间卡片选中
2. 填写开始 / 结束时间，点击「查询可用性」
3. 若时段可用，点击「确认预约」
4. 系统自动在前后各锁定 5 分钟缓冲期，防止与其他预约冲突

**体育设施：**
1. 切换至「体育设施」Tab，选择日期
2. 勾选一个或多个「支持组合」的场地，点击绿色可用时段
3. 点击「确认预约」完成组合 / 单场地预约

**取消预约：**
在「我的预约」面板中点击对应记录的「取消」按钮。

#### 3. 模块 B：活动秒杀（`http://localhost:8000/event`）

*需先由管理员发布活动，见下方管理员流程。*

1. 进入活动大厅，点击任意活动卡片
2. 进入活动详情页，点击「点击报名 / 抢票」
3. 抢票成功后显示「待支付」订单，5 分钟内点击「立即模拟支付」
4. 支付后 Celery Worker 异步落库，WebSocket 实时推送「落库成功」通知

---

### 管理员操作流程

管理员所有接口均需携带请求头 `X-Admin-Key: dev-admin-key`（对应 `.env` 中的 `ADMIN_API_KEY`）。

#### 管理员 Web 界面（`http://localhost:8000/rules_fsm`）

提供图形化大盘，功能包括：
- **房间管理**：查看所有学术空间按日期/时段的预约矩阵
- **场地管理**：查看所有体育设施的占用状态热力图
- **票务管理**：查看活动抢票明细，并可在界面内发布/编辑活动（需填入管理员密钥）

#### 通过 API 发布活动

```bash
curl -X POST "http://localhost:8000/api/v1/events/" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: dev-admin-key" \
  -d '{
    "slot_id": "slot_001",
    "event_name": "十佳歌手决赛演示",
    "description": "模拟万级热门抢票体验",
    "capacity": 10
  }'
```

#### 查看全站预约记录

```bash
curl -H "X-Admin-Key: dev-admin-key" \
  http://localhost:8000/api/v1/spaces/admin/bookings
```

#### 标记用户爽约（扣除 10 分信誉分）

```bash
curl -X POST \
  -H "X-Admin-Key: dev-admin-key" \
  "http://localhost:8000/api/v1/spaces/admin/bookings/{booking_id}/no_show"
```

---

### CI/CD 验收

工程已集成标准的 `.github/workflows/ci.yml` 自动化验收管道，每次代码提交自动触发：

1. **Linting**（`ruff check .`）：代码风格检查
2. **单元测试**（`pytest`）：验证订单状态机（FSM）与规则引擎责任链
3. **冒烟测试**：基于多阶段构建拉起完整 compose 栈，`curl` 验证服务可达

### 停止与清理

```bash
docker compose down      # 停止容器，保留数据库卷
docker compose down -v   # 停止并删除所有数据（完全重置）
```
