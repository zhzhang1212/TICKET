import sys
with open('README.md', 'r', encoding='utf-8') as f:
    text = f.read()
start_marker = "技术实现"
start_idx = text.find(start_marker)
if start_idx == -1:
    print("Not found")
    sys.exit(1)
before = text[:start_idx + len(start_marker)]

new_tech = """

针对“智约校园”这种高并发、强规则约束的业务逻辑，结合项目的工程规范要求，我们采用**统一纯异步 Python (FastAPI + Worker) 以及 Jinja2 原生前端**的全栈分层漏斗架构。

这个架构的核心思想是：**依赖预生成时间片避免复杂计算**，逐层拦截无效请求，最核心的冲突校验在最快的地方做，最终的持久化异步完成。摒弃跨语言调用的复杂运维负担，统一技术栈，在保证高并发性能的同时实现快速开发迭代。

---

## 1. 总体架构与技术栈映射

系统被拆分为四个核心层级，坚决避免过度设计：

| 架构分层 | 技术组件 | 解决的核心问题 |
|---|---|---|
| **前端展示与组件层** | Jinja2 + ES6 + WebSocket | **防过度设计：** 严禁引入 Next.js 等重型框架。通过 `static/js` (core/features/shared) 规范分块实现页面逻辑与 DOM 更新；WebSocket保证状态强闭环。 |
| **高性能接入层** | Nginx + FastAPI (Python) | **流量闸门：** 阻挡瞬时刷票。JWT权限鉴权，拉取 `core/scoring.py` 策略进行规则预审。 |
| **预扣与队列层** | Redis + Lua + Celery/RabbitMQ | **超卖与排队缓冲：** 通过 Redis 预扣时间片库存(Time-Slot)，将高耗时 DB 操作投递入后台队列，完成实时解耦和削峰。 |
| **持久化强一致层** | PostgreSQL (联合唯一约束) | **撞车拦截底座：** 完全依靠时间片 Unique 约束物理防重，拒绝任何由于并发导致的空间或时段分配重叠。 |

## 2. 核心黑科技：预生成时间片 (Time-Slot Sharding)

为了兼顾极致性能与强一致性，我们**彻底抛弃了直接计算时间区间重叠 (如利用 PostgreSQL `tsrange` 或是 `&&` 交集操作符)** 的传统做法。

* **资源发布时碎片化：** 在数据库初始化或资源发布时，就将可用时间预先硬切分为最小单位的实体（例如每 30 分钟一个全局唯一的 Slot_ID）。
* **Redis 极速抢占：** 抢订场地实际上变成了用户抢夺对应的 Slot_ID（把复杂的时间轴重叠计算，降维成对独立 Key 的争夺）。如果某用户选择了 14:00-15:00，实际是同时抢夺并独占 Slot_A (14:00-14:30) 和 Slot_B (14:30-15:00)。通过 Lua 脚本原子判断。
* **PostgreSQL 终极简化的防御：** Worker 子模块只执行最简单的一条 `INSERT INTO bookings (user_id, slot_id)` 即可。凭借数据库的 `Unique(resource_id, slot_id)` 联合唯一索引来做最终防重兜底，不仅瞬间且无开销地拦截冲突，写入效率更是提高了一个量级！

## 3. 协作流程：一个请求的一生

当学生在前端点击“立即预约 羽毛球场 18:00-19:00”标签时，内部流转如下：

1. **第一阶段：流量拦截与预处理 (耗时极速)**
   * **请求到达:** FastAPI 接收。
   * **鉴权风控:** 调用 `core/scoring.py` 检测学生本周是否越权或违约记过。
   * **缓存预扣:** Redis 运行 EVAL 检查该 18:00 和 18:30 这两个对应 Slot 是否可被预扣。若能，减数量并上锁。立即给用户返回“**抢订中，请稍等...**”状态。

2. **第二阶段：MQ 排队与后台落库 (解耦机制)**
   * **推入队列:** 将 `{"task": "confirm_booking", "user": "User_123", "slots": ["Slot_X", "Slot_Y"]}` 推入 Celery 任务队列。
   * **Worker 落地:** Python Async Worker 异步拉取任务，向 DB 做 `Insert`。如果 DB 因为主键/联合索引约束而报错抛出冲突，系统立即将消息打回，命令 Redis 释放库存 (`INCR`)。

3. **第三阶段：基于 WS 的实时闭环**
   * **事件广播:** Worker 写入确权成功后，调用通过 Redis Pub/Sub 给正在坚听的 WebSocket 推送一条成功信息。
   * **页面渲染:** JS 回调刷新页面 DOM，展示最终生成的“预约凭证（二维码）”。

## 4. 针对校园场景的“优雅”机制

* **信誉与风控自动化 (Scoring Core)：**
针对点击抢订、已占场但迟迟不签到/不付款的破坏性行为，系统依靠 Redis 的 `EXPIRE` 倒计时功能建立软锁（如锁定 15 分钟）。一旦 TTL 失效，触发延时 Callback 或队列，不仅将 PostgreSQL 的坑位腾出，还联动 `core/scoring.py` 自动削减违约用户的**校园信用分**。

## 5. 后端依赖环境一览

```bash
# 核心 Web 与异步服务
pip install fastapi uvicorn             # 纯异步 Web 框架
pip install aioredis                    # 异步 Redis 胶水层
pip install sqlalchemy[asyncio]         # 异步 ORM 层
pip install asyncpg                     # PostgreSQL 高速异步驱动
pip install pydantic-settings           # 配置与环境变量统管

# 异步后台任务调度系
pip install celery                      # 工业级后台 Worker 调度引擎
pip install redis                       # 用作跨模块全局的消息服务 Broker
```
"""

with open('README.md', 'w', encoding='utf-8') as f:
    f.write(before + new_tech)
