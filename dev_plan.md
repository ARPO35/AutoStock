# A 股 LLM 模拟交易系统开发计划

## 0. 项目定位

本项目是一个 **A 股模拟盘实验系统**，核心目标不是构建传统量化交易平台，而是研究：

> LLM 在拥有行情、公告、搜索、账户、下单等工具后，能否像一个主观交易员一样持续观察市场、形成判断、执行模拟交易，并通过长期记录分析其“直接炒股”的可行性。

系统不接实盘，不做真实资金交易。所有资金、订单、持仓、成交均为模拟数据，币种统一使用人民币。

---

## 1. 设计意图

### 1.1 核心意图

系统应尽量保留 LLM 的主观能动性。

传统量化系统通常强调固定策略、强风控、规则化信号。本项目不同，核心实验对象是 LLM 本身，因此：

- 不强行限制 LLM 的投资判断。
- 不将 LLM 固定为“策略生成器”。
- 不要求 LLM 只执行预设量化因子。
- 允许 LLM 主动搜索、分析、复盘、买入、卖出、等待。
- 所有能力都通过 tool call 暴露给 LLM。
- 所有 LLM 行为都必须记录，便于事后分析。

### 1.2 WebChat 式交互意图

与 LLM 的实际交互应类似普通 AI 网站的 WebChat。

也就是说，系统的核心对象不是“后台任务”，而是 **Chat Session**：

```text
LLM Account
└─ Chat Session
   ├─ 完整对话记录
   ├─ thinking / reasoning 记录
   ├─ tool call 记录
   ├─ tool result 记录
   ├─ 当前绑定 skill
   ├─ 当前绑定模拟账户
   ├─ 当前绑定触发器
   └─ 交易、复盘、成本、行情快照记录
```

定时任务也不应是独立黑盒任务，而应表现为：

```text
定时触发器
→ 向指定 Chat Session 注入一条事件消息
→ 继续这条会话
→ LLM 在该会话中调用工具
→ 工具结果和最终回复显示在 WebChat 里
```

---

## 2. 总体要求

| 类别 | 要求 |
|---|---|
| 市场 | 主要针对 A 股 |
| 资金 | 人民币模拟资金 |
| 交易 | 模拟盘，不接实盘 |
| 数据源 | 免费数据源，优先只用一个 |
| 主数据源 | AKShare |
| 搜索 | 内置 Tavily 搜索和网页抽取 |
| LLM Provider | 默认支持 OpenAI-Compatible 和 DeepSeek |
| 模型选择 | 统一使用完整模型列表，Provider 由模型隐式绑定 |
| DeepSeek | 默认支持 DeepSeek V4 API |
| Tool Call | 所有功能通过 tool call 实现 |
| Skill | 支持加载、上传、编辑、启用、禁用 |
| WebUI | 四入口统一工作台（交易 / 查看 / 修改 / 管理） |
| 部署 | 只能一个 Docker 容器 |
| 存储 | 本地持久化保存配置、行情、订单、日志、会话 |
| 事件循环 | 可人工触发，也可配置带 prompt 的定时触发 |
| 数据缓存 | 支持手动拉取指定时间段数据并永久保存 |
| 数据合并 | 实时数据和历史缓存数据自动合并 |
| 复盘 | 保存完整 LLM 决策过程，支持后续分析 |

---

## 3. 技术依据

OpenAI 官方将 function calling / tool calling 定义为模型通过 JSON Schema 调用应用侧函数、访问外部系统和数据的机制，适合本项目中“LLM 通过工具访问行情、搜索、账户和下单能力”的设计。

DeepSeek 官方说明 DeepSeek V4 API 可保持 base_url，只需更新模型名为 `deepseek-v4-pro` 或 `deepseek-v4-flash`，并支持 OpenAI ChatCompletions API；DeepSeek V4 同时支持 Thinking / Non-Thinking 双模式和 1M 上下文。DeepSeek 官方也提供 tool calls 文档，并说明 strict mode 可让模型按函数 JSON Schema 输出工具调用，但该模式属于 beta，且对 schema 有额外限制。

AKShare 官方股票数据文档覆盖 A 股实时行情、历史行情、公告等接口，其中 `stock_zh_a_spot_em` 面向东方财富沪深京 A 股实时行情，`stock_zh_a_hist` 等接口用于历史行情。

Tavily 官方 Python SDK 支持 `search` 和 `extract`，可分别用于实时网页搜索和网页内容抽取。

APScheduler 支持 cron、interval、date 等触发方式；CronTrigger 的行为类似 UNIX cron，IntervalTrigger 用于周期性运行任务，适合实现开盘前、盘中、尾盘和收盘复盘触发器。

FastAPI 是基于 Python 类型标注的 Web 框架，官方也支持 WebSocket，可用于实现 WebChat 实时消息流、tool call 过程展示和前端状态推送。

参考来源：

- OpenAI Function Calling / Tool Calling: <https://developers.openai.com/api/docs/guides/function-calling>
- DeepSeek V4 API News: <https://api-docs.deepseek.com/news/news260424>
- DeepSeek Tool Calls: <https://api-docs.deepseek.com/guides/tool_calls>
- AKShare 股票数据: <https://akshare.akfamily.xyz/data/stock/stock.html>
- Tavily Python SDK: <https://docs.tavily.com/sdk/python/reference>
- APScheduler CronTrigger: <https://apscheduler.readthedocs.io/en/stable/modules/triggers/cron.html>
- FastAPI: <https://fastapi.tiangolo.com/>

---

## 4. 总体架构

```text
Single Docker Container
├─ FastAPI Backend
├─ WebUI Static Frontend
├─ WebChat Session Runtime
├─ LLM Provider Layer
│  ├─ OpenAI-Compatible Provider        ← 已实现
│  └─ DeepSeek Provider                 ← 已实现
├─ Provider Config (llm_providers 表)   ← 已实现
├─ Tool Call Runtime                    ← 已实现 (4 tools)
├─ Skill Manager                        ← 未实现
├─ Session-bound Trigger Scheduler      ← 未实现
├─ AKShare Market Provider              ← 已实现
├─ Market Cache / Data Warehouse        ← 已实现 (DuckDB)
├─ Tavily Search Provider               ← 已实现
├─ A股 Simulator                        ← 未实现
├─ SQLite
│  ├─ 配置 (llm_providers, llm_accounts)
│  ├─ 会话 (chat_sessions)
│  ├─ 消息 (chat_messages)
│  ├─ 运行记录 (chat_runs)
│  ├─ 工具调用 (chat_tool_calls)
│  └─ 工具结果 (chat_tool_results)
└─ DuckDB
   ├─ 历史行情 (market_bars)
   ├─ 实时行情快照 (market_quotes)
   ├─ 缓存状态 (market_cache_status)
   └─ 数据冲突 (data_conflicts)
```

设计原则：

1. 单容器部署。
2. 单 WebUI 管理。
3. 单股票数据源：AKShare。
4. 数据本地持久化。
5. LLM 交互以 Chat Session 为中心。
6. 定时任务本质是向 Session 注入事件消息。
7. 所有能力通过 tool call 暴露。
8. skill 可 WebUI 上传、编辑、热加载。
9. 真实市场规则要模拟，但不做投资风控。
10. 所有决策、工具调用、行情快照、成本和结果都可追溯。

---

## 5. 单容器部署设计

### 5.1 容器内目录结构

```text
/app
├─ backend/
│  ├─ app/
│  │  ├─ main.py
│  │  ├─ api/
│  │  │  ├─ sessions.py
│  │  │  ├─ providers.py
│  │  │  ├─ tools.py
│  │  │  ├─ market.py
│  │  │  ├─ data.py
│  │  │  ├─ ws.py
│  │  │  └─ dependencies.py
│  │  ├─ core/
│  │  │  ├─ config.py
│  │  │  └─ websocket_manager.py
│  │  ├─ llm/
│  │  │  ├─ base.py
│  │  │  ├─ openai_compatible.py
│  │  │  ├─ deepseek.py
│  │  │  └─ registry.py
│  │  ├─ tools/
│  │  │  ├─ registry.py
│  │  │  ├─ executor.py
│  │  │  └─ market_tools.py
│  │  ├─ market/
│  │  │  ├─ akshare_provider.py
│  │  │  └─ normalizer.py
│  │  ├─ sessions/
│  │  │  └─ runtime.py
│  │  └─ storage/
│  │     ├─ sqlite.py
│  │     └─ duckdb.py
│  ├─ pyproject.toml
│  └─ tests/
├─ frontend_dist/
├─ data/
│  ├─ app.db
│  └─ market.duckdb
└─ config/
   └─ default.yaml
```

说明：
- `app/llm/` 对应原计划中的 `app/providers/`（已更名为 llm）
- `app/simulator/` 已实现
- `user_skills/` 目录未创建，Skill 系统未实现
- `data/logs/`、`data/exports/` 目录未创建
- `config/default.yaml` 存在但代码未通过 YAML 加载配置，配置通过环境变量 + 数据类管理

### 5.2 启动方式

容器内只启动一个主服务：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

不拆 Postgres、Redis、worker、AKTools 等额外容器。后台调度、行情拉取、LLM 运行、WebChat 推送都在同一 FastAPI 进程内完成。

---

## 6. WebUI 页面设计（与 frontend.md 对齐）

本节与 `frontend.md` 保持一致；如后续有冲突，以 `frontend.md` 为准。

### 6.1 顶部一级导航

顶部一级导航固定为四个入口：

```text
交易（LLM） | 查看 | 修改 | 管理
```

推荐一级路由：

```text
/trade
/view
/edit
/manage
```

复杂功能不放在顶部，而是在各一级页面内通过二级导航组织。

### 6.2 全局布局原则

```text
交易页：WebChat 式 LLM 交互主入口。
查看页：全局观察、跨账号对比、行情浏览、时间线控制。
修改页：人工修改账户与绑定关系，必须审计。
管理页：模型、API、Skill、Tool、触发器、数据和系统配置。
```

通用约束：

- 顶部导航保持简洁。
- Tool Result 必须优先人类可读展示，不可仅回显 JSON。
- 同一账户允许多 Session 并行，但交易归属必须可追溯到 Session / 模型 / run。

### 6.3 交易页（/trade）三栏布局

交易页采用三栏结构：

```text
左侧：账户文件夹与 Session 列表
中间：LLM 线性流程（消息、推理、工具、结果、下单、回复）
右侧：账户观察（资产、持仓、交易、指标）
```

宽度规则：

- 左侧栏默认 `260px ~ 320px`，支持折叠。
- 中间区最小宽度 `520px`。
- 右侧栏最小宽度 `420px`，支持拖拽调整，宽度建议持久化到 `localStorage`。

### 6.4 交易页左侧：账户与 Session

结构关系：

```text
Account = 资金和持仓归属
Session = 一条独立 LLM 运行线程
Model = Session 级配置（不强制与账户一一绑定）
```

同一账户下可并行多个 Session；左侧需展示账户概览和 Session 状态（idle/running/queued/error/has trigger）。

### 6.5 交易页中间：LLM 线性流程

线性流程包含：

```text
用户消息
定时事件消息
可见推理
tool call
tool result
下单结果
最终回复
错误
```

展示边界：

```text
不展示完整 CoT；
仅展示 Provider 可见推理内容或推理摘要；
若 Provider 不返回可见推理，则明确显示“无可见推理”。
```

### 6.6 Tool Result 渲染规则

必须按工具类型结构化渲染：

- `tavily.search`：标题、域名、摘要、发布时间（若有）、原始链接。
- `market.quote`：价格、涨跌幅、成交量、时间。
- `market.history`：K 线/历史图表 + 时间范围 + 数据条数。
- `order.*` / `simulator.*`：下单结果、成交结果、账户变动摘要。
- `portfolio.*`：现金、持仓市值、总资产、当日收益等。

`tool call` 默认折叠，详情按需展开；长 JSON 默认懒加载。

### 6.7 交易页右侧：账户观察栏

右侧固定展示当前账户观察信息：

- 当前账户基本信息。
- 资产变化折线图（当前右侧栏使用 SVG 折线，显示最高值 / 中位值 / 最低值三档纵向标尺）。
- 数字指标面板（现金、总资产、浮盈亏、仓位等）。
- 持仓列表。
- 交易记录折叠栏（当前右侧栏显示 `买入/卖出 股票名（六位代码）`，价格为 `¥x.xx/股` 口径）。

该区域需随 WebSocket 事件实时刷新。

### 6.8 交易页底部输入区

输入区包含多种运行动作：

```text
发送
作为事件运行
只写入
停止
```

可提供常用快捷事件模板（开盘前观察、盘中检查、尾盘决策、收盘复盘）。

### 6.9 查看页（/view）

查看页用于全局观察与分析，建议子路由：

```text
/view/overview
/view/account-detail
/view/trades
/view/assets
/view/stock
/view/logs
/view/timeline
```

支持全局总览、账号详情、交易历史、资产曲线、股票信息、决策日志和时间线控制。

### 6.10 修改页（/edit）

修改页用于人工修正账户状态和绑定关系，建议子路由：

```text
/edit/accounts
/edit/balance
/edit/positions
/edit/orders
/edit/session-binding
```

所有人工修改必须记录审计字段（修改人、时间、修改前后、原因、影响账号/Session），并在资产曲线中可标记人工干预点。

### 6.11 管理页（/manage）

管理页承载系统配置能力，采用分组管理：

```text
模型与 API：OpenAI-Compatible / DeepSeek / Tavily / AKShare
Agent 能力：Skills / Tools / Prompts
自动化：触发器
数据：缓存、冲突、批量拉取、导出清理
系统：日志、备份、全局设置
```

管理页中的数据管理偏系统级；单只股票的临时查看与拉取保存放在 `/view/stock`。

---

## 7. Chat Session 模型

### 7.1 核心概念

系统核心对象是 Chat Session。

```text
Chat Session = 一条完整的 LLM 交易实验线程
```

一个 Session 可以：

- 手动聊天。
- 接收定时事件消息。
- 调用工具。
- 下模拟单。
- 写复盘。
- 生成报告。
- 持续保留上下文。

### 7.2 Session 数据结构

```sql
chat_sessions
- id
- name
- skill_id           ← 已预留，未使用
- simulator_account_id  ← 关联模拟账户（已实现）
- provider_id        ← 实际列（绑定 Provider）
- model              ← 实际列（Session 级模型）
- status
- created_at
- updated_at
- archived_at
```

```sql
chat_messages
- id
- session_id
- role
- content
- message_type
- trigger_id
- parent_message_id
- reasoning_content  ← 实际列（DeepSeek thinking 内容）
- created_at
```

```sql
chat_runs             ← 实际表，原计划未单独列出
- id
- session_id
- provider_id
- model
- status
- event_message_id
- started_at
- finished_at
- final_message_id
- error
```

```sql
chat_tool_calls
- id
- run_id              ← 实际列（关联 run）
- session_id
- message_id
- provider_call_id
- tool_name
- arguments_json
- status
- started_at
- finished_at
- error
```

```sql
chat_tool_results
- id
- run_id              ← 实际列（关联 run）
- session_id
- tool_call_id
- result_json
- created_at
```

### 7.3 定时任务与 Session 的关系

定时任务不直接运行一个后台交易账户，而是向 Session 注入消息：

```text
trigger fires
→ create event message in chat_messages
→ start LLM run for that Session
→ LLM uses tools
→ all records append to same Session
```

---

## 8. LLM 事件循环

### 8.1 实际工作流（当前实现）

```text
用户发送消息 → DB 创建消息
→ POST /api/sessions/{id}/run
→ SessionRunManager.run_once()
→ _load_context()：从 DB 加载历史消息
→ _tool_definitions()：从 ToolRegistry 获取工具定义
→ _run_loop(account, messages, tools):
    → provider.chat_stream() 流式调用 LLM
    → WS 推送 assistant_token（逐 token）
    → WS 推送 assistant_reasoning（DeepSeek thinking）
    → 累积完整回复
    → 解析 tool calls
    → 若无 tool calls：创建 assistant 消息 → 发送 assistant_message + run_finished
    → 若有 tool calls：
        → 遍历每个 tool call：
            → WS 推送 tool_call_started
            → ToolExecutor.execute()
            → DB 存入 tool_call + tool_result
            → WS 推送 tool_call_finished
            → 将 tool result 追加到 messages 上下文
        → 继续下一轮 LLM 调用，直到模型自然产出最终回复、用户取消或发生错误
```

### 8.2 WebSocket 事件类型（实际）

| 事件 | 方向 | 说明 |
|---|---|---|
| `run_started` | S→C | run 启动 |
| `assistant_token` | S→C | LLM 逐 token 流式输出 |
| `assistant_reasoning` | S→C | DeepSeek thinking 内容 |
| `tool_call_started` | S→C | 工具调用开始 |
| `tool_call_finished` | S→C | 工具执行完成（ok/error） |
| `assistant_message` | S→C | 最终助理消息已创建 |
| `run_finished` | S→C | run 结束 |
| `error` | S→C | 异常；携带 `error` 字段，前端写入 `runError` |

### 8.3 并发规则 ← 未实现

当前无并发控制机制。同一 Session 串行执行，不同 Session 可并行。后续计划：

| 场景 | 规则 |
|---|---|
| 同一 Session 已有 active run，又来了触发器 | 可配置：排队 / 跳过 / 合并 |
| 不同 Session 同时运行 | 允许 |
| 不同 LLM Account 同时运行 | 允许 |
| 同一虚拟账户被多个 Session 同时操作 | 默认禁止，除非开启共享账户实验 |
| 用户手动消息与定时触发冲突 | 优先用户手动消息，定时事件排队 |

---

## 9. 定时触发器设计 ← 未实现

### 9.1 触发器结构

```json
{
  "id": "open_market_check",
  "enabled": true,
  "session_id": "session_deepseek_v4_001",
  "trigger_type": "cron",
  "cron": "25 9 * * 1-5",
  "timezone": "Asia/Shanghai",
  "event_name": "开盘前观察",
  "event_prompt": "现在是A股开盘前，请检查持仓、公告、隔夜消息和市场情绪，决定今日模拟交易计划。",
  "max_runtime_seconds": 180,
  "conflict_policy": "queue"
}
```

### 9.2 内置触发器模板

| 名称 | 时间 | 用途 |
|---|---:|---|
| 开盘前观察 | 09:20 / 09:25 | 搜索隔夜消息、公告、持仓影响 |
| 开盘后决策 | 09:35 | 结合开盘走势决定是否交易 |
| 盘中轮询 | 每 5 / 15 / 30 分钟 | 检查持仓、异动、新闻 |
| 午盘复盘 | 11:35 | 总结上午表现 |
| 尾盘决策 | 14:45 / 14:55 | 判断是否调仓 |
| 收盘复盘 | 15:10 | 生成当日复盘和明日计划 |

### 9.3 交易日历计划项

第一阶段可以先按工作日运行，后续必须加入交易日历：

```text
计划项：
- 识别 A 股节假日
- 识别休市日
- 识别非交易时段
- 识别临时休市
- 触发器运行前检查交易日历
```

---

## 10. LLM Provider 设计

### 10.1 Provider 类型

默认支持：

```text
openai_compatible
deepseek
```

### 10.2 OpenAI-Compatible Provider

用于接入：

- OpenAI。
- 第三方 OpenAI-compatible 网关。
- 本地模型网关。
- 反代 API。
- 聚合 API。

配置：

```yaml
provider_type: openai_compatible
name: custom_gateway
base_url: https://example.com/v1
api_key: sk-xxx
model: some-model
capabilities:
  supports_tools: true
  supports_parallel_tool_calls: false
  supports_strict_schema: false
  supports_streaming_tool_calls: false
  supports_thinking_mode: false
```

### 10.3 DeepSeek Provider ← 已实现

DeepSeek 虽然兼容 OpenAI API，但仍单独做 Provider（继承 OpenAICompatibleProvider）。

实际实现要点：

- `deepseek.py` 继承 `openai_compatible.py` 的 `OpenAICompatibleProvider`
- `_build_chat_request()` 覆写：移除 `temperature`（thinking 模式不支持），添加 `reasoning_effort: "high"` 和 `extra_body: {"thinking": {"type": "enabled"}}`
- `chat_stream()` 继承基类实现
- `_message_to_payload()` 覆写：将 `reasoning_content` 编入消息 payload，否则后续轮次不传思考内容会导致 400
- 发送请求前流程：
  ```text
  Provider Config (strict_tool_schema, thinking_mode)
  → ToolRegistry 构建 JSON Schema
  → _build_chat_request() 注入 reasoning_effort/thinking
  → openai SDK streaming API
  → 回读 reasoning_content + content
  → 保存到 chat_messages.reasoning_content
  ```

配置：

```yaml
provider_type: deepseek
base_url: https://api.deepseek.com
api_key: sk-xxx
model: deepseek-v4-pro
thinking_mode: thinking
strict_tool_schema: true
max_tokens: 8192
```

### 10.4 模型能力差异

“模型能力差异”不是指模型智力差异，而是指不同 Provider 对 API 协议和 tool call 的支持程度不同。

| 能力 | 可能差异 |
|---|---|
| tools 参数 | 有的支持，有的不支持 |
| parallel tool calls | 有的可一次返回多个工具调用，有的只能一个 |
| strict schema | 有的严格遵守 JSON Schema，有的不支持 |
| tool_choice | 有的支持强制工具，有的不完整 |
| streaming tool call | 流式 tool call delta 格式可能不同 |
| thinking 内容 | DeepSeek 等模型可能有 thinking / non-thinking |
| usage 字段 | token 统计格式不同 |
| 错误格式 | 限流、余额不足、schema 错误返回结构不同 |
| JSON Schema 子集 | 嵌套 object、enum、array、additionalProperties 支持不一致 |

因此需要 Capability Registry。

### 10.5 Capability Registry

```yaml
providers:
  deepseek:
    supports_tools: true
    supports_strict_tools: true
    supports_parallel_tool_calls: true
    supports_thinking_mode: true
    supports_streaming_tool_calls: check
    schema_mode: deepseek_strict_subset

  openai_compatible:
    supports_tools: configurable
    supports_strict_tools: configurable
    supports_parallel_tool_calls: configurable
    supports_thinking_mode: false
    schema_mode: generic
```

发送请求前流程：

```text
Internal Tool Schema
→ Provider Capability Check
→ Schema Downgrade / Strict Mode Adapter
→ Send to LLM
→ Normalize Response
→ Save to Chat Session
```

---

## 11. Skill 系统设计 ← 未实现

### 11.1 Skill 目标

Skill 用于改变 LLM 行为方式，而不是直接执行任意代码。

第一阶段建议只支持：

```text
prompt
tool whitelist
默认参数
运行约束
说明文档
```

不建议一开始允许 skill 上传任意 Python 代码，否则会引入容器内代码执行风险。

### 11.2 Skill 目录结构

```text
user_skills/
  short_term_trader/
    skill.yaml
    system.md
    tools.json
    memory.md
    README.md
```

### 11.3 skill.yaml

```yaml
name: short_term_trader
description: A股短线主观交易模拟 skill
version: 1.0.0
enabled: true

prompt: system.md

tools:
  - market.stock_list
  - market.quote
  - market.history
  - market.minute
  - market.announcement
  - portfolio.get_state
  - order.buy
  - order.sell
  - tavily.search
  - tavily.extract
  - journal.write

defaults:
  max_runtime_seconds: 180
```

### 11.4 WebUI 功能

- 上传 zip。
- 校验 skill 结构。
- 在线编辑 prompt。
- 在线编辑 tool 白名单。
- 启用 / 禁用。
- 绑定到 Session。
- 绑定到 LLM Account。
- 查看版本。
- 回滚版本。

---

## 12. Tool Call 设计

### 12.1 已实现的工具

当前核心工具（`app/tools/registry.py`）：

| 工具名 | 显示名 | 说明 |
|---|---|---|
| `system_echo` | system.echo | Echo 测试工具 |
| `market_quote` | market.quote | 查询 A 股实时行情（通过 AKShare） |
| `market_history` | market.history | 查询历史 K 线（优先本地缓存，支持自动补拉） |
| `data_fetch_history` | data.fetch_history | 手动拉取并缓存历史行情到 DuckDB |
| `portfolio_get_state` | portfolio.get_state | 查询模拟账户资产概览（与账户面板同估值口径） |
| `portfolio_get_positions` | portfolio.get_positions | 查询持仓（含 `quantity`/`available_quantity`） |
| `portfolio_get_orders` | portfolio.get_orders | 查询订单列表（支持状态过滤） |
| `order_buy` | order.buy | 模拟买入（默认绑定当前会话账户） |
| `order_sell` | order.sell | 模拟卖出（默认绑定当前会话账户） |
| `order_cancel` | order.cancel | 撤销 `pending` 订单 |

### 12.2 计划中的工具分组 ← 未实现

```text
market.*          ← 部分实现 (market_quote, market_history)
data.*            ← 部分实现 (data_fetch_history)
portfolio.*       ← 已实现 (portfolio_get_state, portfolio_get_positions, portfolio_get_orders)
order.*           ← 已实现 (order_buy, order_sell, order_cancel)
simulator.*       ← 未实现
tavily.*          ← 已实现
journal.*         ← 未实现
report.*          ← 未实现
```

### 12.3 计划中的工具清单

以下均为计划设计，尚未实现：

<details>
<summary>未来工具详情（点击展开）</summary>

**Market Tools (待实现: stock_list, index_quote)**

```text
market.stock_list
market.minute
market.announcement
market.index_quote
```

**Data Tools (待实现: cache_status, find_missing, resolve_conflict)**

```text
data.cache_status
data.find_missing
data.resolve_conflict
```

**Portfolio Tools**

```text
portfolio.get_state
portfolio.get_positions
portfolio.get_orders
portfolio.get_trades
portfolio.get_performance
```

**Order Tools**

```text
order.buy
order.sell
order.cancel
```

**Simulator Tools**

```text
simulator.next_tick
simulator.run_until
simulator.reset
simulator.set_mode
```

**Tavily Tools**

```text
tavily.search
tavily.extract
```

**Journal Tools**

```text
journal.write
journal.query_recent
```

**Report Tools**

```text
report.generate_daily
report.generate_session
report.generate_comparison
```

</details>

---

## 13. 市场数据设计

### 13.1 数据源选择

只使用 AKShare 作为免费主数据源。

原因：

- 覆盖 A 股实时行情。
- 覆盖历史行情。
- 覆盖公告。
- Python 内直接调用。
- 不需要额外容器。
- 适合模拟盘和研究实验。

注意：

AKShare 不是交易级行情源，不应假设稳定性等同券商或交易所直连。因此必须建设本地 Market Cache。

### 13.2 数据仓库设计

WebUI 需要支持手动拉取某个指定时间段的数据，并永久保存。

流程：

```text
用户选择 symbol / interval / date range / adjust
→ 调用 AKShare
→ 标准化字段
→ 写入 DuckDB
→ 与已有数据自动合并
→ 生成缓存覆盖范围
```

### 13.3 标准行情表

```sql
market_bars
- symbol
- name
- interval
- datetime
- open
- high
- low
- close
- volume
- amount
- adjust
- source
- fetch_time
- raw_hash
```

唯一键：

```text
symbol + interval + datetime + adjust
```

### 13.4 实时数据合并

```text
实时 quote / minute
→ 标准化
→ upsert 到 market_bars
→ 若唯一键已存在且值一致，跳过
→ 若唯一键已存在但值不一致，写入 data_conflicts
```

### 13.5 数据冲突表

```sql
data_conflicts
- id
- symbol
- interval
- datetime
- existing_value_json
- new_value_json
- source
- fetch_time
- status
```

默认不静默覆盖旧数据。

### 13.6 缓存优先策略

```text
查询历史数据：
1. 先查 DuckDB 本地缓存
2. 如果缺失且允许自动补拉，则调用 AKShare
3. 拉取后写入 DuckDB
4. 返回合并后的完整数据
```

### 13.7 计划项

```text
计划项：
- 数据完整性检查
- 数据缺口扫描
- 每日收盘后自动归档
- 数据冲突处理页面
- 历史行情快照锁定
- Replay Dataset 版本化
```

---

## 14. A 股模拟器设计 ← 已实现

### 14.1 模拟器目标

模拟器不是投资风控系统，而是市场环境。

它不应限制 LLM 的主观判断，但必须保证交易符合 A 股基本规则，否则实验结果无意义。

### 14.2 需要模拟的规则

```text
人民币计价
A 股交易时间
T+1
买入 100 股整数倍
卖出可按持仓数量
涨跌停
停牌
手续费
印花税
分红送转
前复权 / 后复权 / 不复权
```

### 14.3 订单模型

```sql
orders
- id
- session_id
- simulator_account_id
- symbol
- side
- order_type
- price
- quantity
- status
- reason_message_id
- created_at
- updated_at
```

### 14.4 成交模型

```sql
trades
- id
- order_id
- session_id
- symbol
- side
- price
- quantity
- fee
- tax
- traded_at
```

### 14.5 持仓模型

```sql
positions
- simulator_account_id
- symbol
- quantity
- available_quantity
- avg_cost
- market_value
- unrealized_pnl
- updated_at
```

### 14.6 账户模型

```sql
simulator_accounts
- id
- name
- initial_cash
- cash
- frozen_cash
- total_asset
- commission_rate    ← 佣金比率，可每账号独立配置
- min_commission      ← 最低佣金，可每账号独立配置
- created_at
```

---

## 15. 历史回放一致性 ← 未实现

这是计划项，但应在架构上提前预留。

目标：

```text
实时盘和历史回放共用同一套：
- Event
- Tool
- Market Provider Interface
- Simulator
- Portfolio
- Order Matching
- Journal
```

不能出现：

```text
实时模拟一套逻辑
历史回测另一套逻辑
```

否则 LLM 在 replay 中学到的行为和实时模拟环境不一致。

### 15.1 统一接口

```python
class MarketProvider:
    async def quote(symbol: str): ...
    async def history(symbol: str, start: str, end: str, interval: str): ...
    async def minute(symbol: str, start: str, end: str): ...
    async def announcement(symbol: str, start: str, end: str): ...
```

实时模式：

```text
MarketProvider -> AKShare + latest cache
```

回放模式：

```text
MarketProvider -> DuckDB snapshot by replay clock
```

### 15.2 Replay Clock

```text
replay_clock.current_time
```

所有 market tool 在 replay 模式下只能返回 `current_time` 之前的数据，不能泄露未来数据。

---

## 16. Tavily 搜索设计 ← 已实现

### 16.1 用途

Tavily 用于补充 AKShare 不覆盖或不充分覆盖的信息。

主要场景：

- 公司新闻。
- 行业消息。
- 政策事件。
- 宏观事件。
- 突发消息。
- 公告解读。
- 舆情搜索。

### 16.2 Tool Schema

```json
{
  "name": "tavily.search",
  "description": "搜索实时网页信息，用于股票新闻、政策、行业事件分析",
  "parameters": {
    "type": "object",
    "properties": {
      "query": { "type": "string" },
      "search_depth": {
        "type": "string",
        "enum": ["basic", "advanced"]
      },
      "max_results": { "type": "integer" }
    },
    "required": ["query"],
    "additionalProperties": false
  }
}
```

```json
{
  "name": "tavily.extract",
  "description": "抽取指定网页正文内容",
  "parameters": {
    "type": "object",
    "properties": {
      "urls": {
        "type": "array",
        "items": { "type": "string" }
      }
    },
    "required": ["urls"],
    "additionalProperties": false
  }
}
```

---

## 17. 成本记录 ← 未实现

### 17.1 目标

记录每次 LLM 调用成本，便于分析不同模型的交易性价比。

### 17.2 记录字段

```sql
llm_usage_records
- id
- session_id
- run_id
- provider
- model
- prompt_tokens
- completion_tokens
- total_tokens
- thinking_tokens
- input_cost
- output_cost
- estimated_total_cost
- latency_ms
- created_at
```

### 17.3 报表

WebUI 应展示：

- 每日 token 消耗。
- 每个 Session 成本。
- 每个模型成本。
- 每次交易平均成本。
- 每 1 元收益对应 API 成本。
- tool call 次数与成本关系。

---

## 18. 决策日志与实验分析 ← 未实现

### 18.1 必须保存的内容

每次 LLM Run 必须保存：

```text
触发来源
触发 prompt
完整上下文摘要
Provider
Model
Skill 版本
Prompt 版本
tool schema 版本
LLM thinking / reasoning
tool call 参数
tool result
最终自然语言回复
订单
成交
行情快照
成本
耗时
```

### 18.2 分析指标

```text
收益率
超额收益
最大回撤
胜率
盈亏比
换手率
平均持仓时间
交易频率
tool call 次数
搜索次数
搜索依赖程度
公告依赖程度
单次决策成本
每笔交易成本
不同模型对比
不同 skill 对比
不同 prompt 对比
```

---

## 19. 多模型实验设计 ← 未实现

### 19.1 目标

验证不同 LLM 的模拟炒股能力差异。

### 19.2 实验方式

```text
同一股票池
同一初始资金
同一时间触发器
同一行情快照
不同模型 / prompt / skill
```

示例：

```text
账户1：DeepSeek V4 Pro
账户2：DeepSeek V4 Flash
账户3：OpenAI-Compatible 模型 A
账户4：OpenAI-Compatible 模型 B
```

### 19.3 对比报告

```text
收益
回撤
交易频率
持仓风格
搜索频率
工具使用风格
复盘质量
成本
稳定性
幻觉率
违反交易规则次数
```

---

## 20. 安全与边界

### 20.1 不做投资风控

本项目明确不限制 LLM 的投资判断。  
例如不强制限制：

- 最大仓位。
- 止损线。
- 单票比例。
- 最大回撤。
- 行业集中度。

### 20.2 仍需技术约束

但必须保留技术和市场规则约束：

```text
不能买入不存在的股票
不能卖出超过持仓
不能在停牌时成交
不能违反 T+1
不能用未来数据
不能跳过交易时间规则
不能重复执行同一个 tool call
不能让 skill 执行任意系统命令
```

### 20.3 Skill 安全

第一阶段不允许 skill 上传任意 Python 代码。

只允许：

```text
prompt
tool whitelist
配置
文档
```

后续如果要支持代码型 skill，应增加：

```text
沙箱
权限声明
文件访问限制
网络访问限制
超时限制
审计日志
```

---

## 21. 数据库规划

### 21.1 SQLite

保存系统配置和高频写入之外的业务数据：

**已实现的表：**

```text
llm_providers        ← Provider 配置
chat_sessions        ← Session（含 simulator_account_id）
chat_messages        ← 消息（含 reasoning_content 列）
chat_runs            ← 每次 LLM 运行记录
chat_tool_calls      ← 工具调用记录
chat_tool_results    ← 工具调用结果
simulator_accounts   ← 模拟账户（含 commission_rate, min_commission）
positions            ← 持仓
orders               ← 订单
trades               ← 成交
```

**未实现的表：**

```text
skills               ← 未实现
skill_versions       ← 未实现
triggers             ← 未实现
journal_entries      ← 未实现
llm_usage_records    ← 未实现
```

### 21.2 DuckDB

保存行情和分析数据：

**已实现的表：**

```text
market_bars          ← K 线数据 (PK: symbol+interval+datetime+adjust)
market_quotes        ← 实时行情快照
market_cache_status  ← 缓存覆盖范围
data_conflicts       ← 数据冲突记录
```

**未实现的表：**

```text
replay_datasets       ← 未实现
performance_snapshots ← 未实现
analysis_reports      ← 未实现
```

---

## 22. 后端 API（实际实现）

### 22.1 健康检查

```text
GET    /api/health
```

### 22.2 Provider API ← 已实现

```text
GET    /api/providers
POST   /api/providers
GET    /api/providers/{provider_id}
PUT    /api/providers/{provider_id}
DELETE /api/providers/{provider_id}
POST   /api/providers/{provider_id}/models        ← 拉取远端模型列表
POST   /api/providers/{provider_id}/chat-test      ← 测试聊天
GET    /api/providers/{provider_id}/usage          ← 使用统计
```

### 22.3 Simulator Account API ← 已实现

```text
GET    /api/simulator/accounts
POST   /api/simulator/accounts
GET    /api/simulator/accounts/{id}
PUT    /api/simulator/accounts/{id}
DELETE /api/simulator/accounts/{id}
GET    /api/simulator/accounts/{id}/positions
GET    /api/simulator/accounts/{id}/orders
GET    /api/simulator/accounts/{id}/trades
POST   /api/simulator/accounts/{id}/reset
```

原 `llm_accounts` 表已合并到 `simulator_accounts`。

### 22.4 Session API ← 已实现

```text
GET    /api/sessions
POST   /api/sessions
GET    /api/sessions/{session_id}
PUT    /api/sessions/{session_id}
DELETE /api/sessions/{session_id}
GET    /api/sessions/{session_id}/messages
POST   /api/sessions/{session_id}/messages
GET    /api/sessions/{session_id}/timeline         ← 合并消息+工具调用+结果
GET    /api/sessions/{session_id}/runs
POST   /api/sessions/{session_id}/run              ← 触发 LLM 运行
```

`POST /api/sessions/{session_id}/run` 在 LLM Provider 网络连接失败时返回 `502 Bad Gateway`，同时将对应 `chat_runs.status` 置为 `error` 并通过 WebSocket `error` 事件推送可读错误。

### 22.5 Tools API ← 已实现

```text
GET    /api/tools
POST   /api/tools/{tool_name}/test
```

### 22.6 Market API ← 已实现

```text
GET    /api/market/history
GET    /api/market/quote
```

### 22.7 Data API ← 已实现

```text
POST   /api/data/fetch-history
GET    /api/data/cache-status
GET    /api/data/conflicts
POST   /api/data/conflicts/{conflict_id}/resolve
```

### 22.8 WebSocket ← 已实现

```text
WS     /ws/sessions/{session_id}
```

实际推送事件类型：

```text
run_started
assistant_token          ← 逐 token 流式输出
assistant_reasoning      ← DeepSeek thinking 内容
tool_call_started
tool_call_finished
assistant_message        ← 最终助手消息
run_finished
error
```

### 22.9 Skill API ← 未实现

```text
GET    /api/skills
POST   /api/skills/upload
GET    /api/skills/{id}
PUT    /api/skills/{id}
POST   /api/skills/{id}/enable
POST   /api/skills/{id}/disable
POST   /api/skills/{id}/reload
```

### 22.10 Trigger API ← 未实现

```text
GET    /api/triggers
POST   /api/triggers
PUT    /api/triggers/{id}
DELETE /api/triggers/{id}
POST   /api/triggers/{id}/run-now
```

### 22.11 Simulator API ← 已实现

```text
GET    /api/simulator/accounts
GET    /api/simulator/accounts/{id}
GET    /api/simulator/accounts/{id}/positions
GET    /api/simulator/accounts/{id}/orders
GET    /api/simulator/accounts/{id}/trades
POST   /api/simulator/accounts/{id}/reset
```

---

## 23. 前端规划

### 23.1 技术选择

建议：

```text
React + TypeScript + Vite
```

单容器部署时，前端 build 输出到：

```text
frontend_dist/
```

由 FastAPI 静态托管。

### 23.2 路由与页面结构

一级路由固定四入口：

```text
/trade
/view
/edit
/manage
```

`/view` 下建议包含：

```text
overview
account-detail
trades
assets
stock
logs
timeline
```

### 23.3 组件结构与展示约束

组件组织建议与 `frontend.md` 一致，核心包括：

```text
layouts/AppShell + TopNavigation
pages/TradePage + ViewPage + EditPage + ManagePage
features/trade/AccountSessionSidebar
features/trade/LLMLinearTimeline
features/trade/AccountInspectorPanel
features/trade/ChatInputBox
features/trade/tool-renderers/*
features/view/*
```

交易页展示规则：

```text
按时间线展示消息、可见推理、tool call、tool result、下单结果和最终回复；
不展示完整 CoT，只展示可见推理或摘要；
tool call 默认折叠，tool result 必须人类可读。
```

### 23.4 实时与性能要求

WebSocket 事件至少覆盖：

```text
llm.delta
reasoning.delta
tool.started
tool.finished
order.created
trade.created
portfolio.updated
run.finished
error
```

性能策略：

```text
Timeline 虚拟列表
按 run 分组折叠
默认加载最近 N 条
历史按需加载
图表懒渲染
长 JSON 懒加载
```

---

## 24. 开发阶段计划

## 阶段 1：MVP 骨架 ← 已完成

目标：跑通单容器 WebChat + LLM tool call。

任务：

- FastAPI 项目初始化。
- React WebUI 初始化。
- SQLite 初始化。
- Chat Session CRUD。
- WebSocket 消息推送。
- OpenAI-Compatible Provider。
- DeepSeek Provider。
- 基础 tool call runtime。
- 简单 echo tool 测试。
- 单容器 Dockerfile。

验收：

```text
可以在 WebUI 创建 Session
可以配置 LLM
可以发送消息
LLM 可以调用测试 tool
tool call 和 result 会显示在 Chat 中
```

---

## 阶段 2：AKShare 数据与 Market Cache ← 已完成

目标：接入免费 A 股数据源并本地保存。

任务：

- AKShare Provider。
- `market.quote`。
- `market.history`。
- `market.minute`。
- `market.announcement`。
- DuckDB 初始化。
- market_bars 表。
- 手动拉取数据页面。
- 数据 upsert。
- 数据冲突表。
- 缓存覆盖范围展示。

验收：

```text
可以在 WebUI 手动拉取指定股票指定时间段数据
数据永久保存到 DuckDB
再次查询优先走本地缓存
实时数据和历史数据可自动合并
```

---

## 阶段 3：模拟盘 ← 已完成

目标：让 LLM 能真实操作模拟账户。

任务：

- simulator account。
- portfolio。
- order。
- trade。
- position。
- buy / sell / cancel tools。
- A 股基础规则。
- 订单和成交展示。
- 持仓面板。
- 资金曲线。

验收：

```text
LLM 可以通过 tool call 查询账户
LLM 可以通过 tool call 买入
LLM 可以通过 tool call 卖出
系统正确更新现金、持仓、订单、成交
```

阶段 3 收口补充（A 股规则严格版）：

- 工具执行层注入 `session_id` 与会话绑定的 `simulator_account_id`，LLM 下单默认归因到当前会话与账户。
- 印花税按卖出单边 `0.0005` 计算（2023-08-28 后减半口径）。
- T+1 通过 `available_quantity` 生效：当日买入不立即可卖，跨交易日自动解锁。
- 交易时段校验默认开启（可用 `AUTOSTOCK_SIMULATOR_ENFORCE_TRADING_HOURS` 配置关闭测试环境约束）。
- 成交后刷新持仓估值 `market_value/unrealized_pnl`，并据此更新 `total_asset`，与 `portfolio_get_state` 口径一致。
- timeline/messages API 回传 `reasoning_content`，支持完整复盘。

---

## 阶段 4：观察与分析页面（/trade 账户观察 + /view） ← 已完成

目标：实现账户实时观察与全局分析视图，形成“交易执行 + 全局复盘”闭环。

任务：

- 交易页右侧账户观察栏（当前账户基本信息、资产变化折线图、数字指标面板、持仓列表、交易记录折叠栏）。
- 账户观察栏随 WebSocket 事件实时刷新。
- 查看页子路由：`/view/overview`、`/view/account-detail`、`/view/trades`、`/view/assets`、`/view/stock`、`/view/logs`、`/view/timeline`。
- 支持账户/时间范围/股票维度筛选，并保持跨页面查询口径一致。
- 为查看页提供账户、交易、资产、日志、时间线的聚合查询接口。

已实现补充：

- 交易页右侧账户观察栏已展示账户指标、持仓、最近成交和资产变化 SVG 折线。
- 最近成交行显示股票名与六位代码，价格使用人民币每股单位。
- 资产变化折线保留轻量 SVG 实现，增加高 / 中 / 低三档纵向标尺和辅助网格线。
- `/api/view/*` 已统一账户、Session、模型、时间、股票和方向筛选，并回传 session / model / run / tool call 归因字段。
- 查看页 7 个入口均已可用：总览、账号详情、交易历史、资产曲线、股票信息、决策日志和时间线控制。
- 交易页右侧账户观察栏已通过 `order_created`、`trade_created`、`portfolio_updated` 等 WebSocket 事件触发防抖刷新。
- 最近成交可定位并高亮中间 timeline 中对应的 tool call。
- 股票信息页已支持报价、日线、分钟线、公告、缓存覆盖、拉取保存，以及新建股票分析 Session 的事件注入骨架。
- 时间线控制页当前为只读控制骨架；真实 Replay Clock、覆盖式重跑和触发器运行将在阶段 7 / 阶段 9 接入。

验收：

```text
交易页右侧观察栏可实时反映账户变化（下单、成交、估值更新）
查看页 7 个子路由均可访问并返回有效数据
同一账户在交易页与查看页的数据口径一致（现金、总资产、持仓市值、浮盈亏、交易记录）
```

---

## 阶段 5：Tavily 搜索 ← 已实现

目标：让 LLM 能搜索实时网页信息。

任务：

- Tavily 配置页。
- `tavily.search`。
- `tavily.extract`。
- 搜索结果缓存。
- 搜索结果写入日志。
- Tavily 成本 / 调用次数记录。

验收：

```text
LLM 可以调用 tavily.search
LLM 可以基于搜索结果继续调用 tavily.extract
搜索过程显示在 Chat 中
```

---

## 阶段 6：成本记录与分析 ← 未实现

目标：记录不同模型的运行成本。

任务：

- usage parser。
- 不同 Provider usage normalizer。
- llm_usage_records。
- 成本配置。
- 成本面板。
- Session 成本统计。
- 每次 run 的 token、耗时、provider、model 与估算成本记录。
- 每笔交易成本统计，优先通过 session / run / tool call 归因，避免仅按时间窗口粗算。
- 单次运行成本上限与后续自动化实验的成本基线。

验收：

```text
每次 LLM 调用都记录 token、耗时、模型、provider、估算成本
WebUI 可查看 Session 总成本和单次运行成本
交易记录可以追溯到触发它的 Session / run / tool call 成本上下文
```

---

## 阶段 7：历史回放一致性基础 ← 未实现

目标：先统一实时模式与 replay 模式的时间语义，避免后续实验出现未来数据泄露。

任务：

- Replay Clock。
- replay mode。
- market tools 按 replay time 返回数据。
- 禁止未来数据泄露。
- 交易日历与回放时间边界。
- 实时模式与 replay 模式共用同一套 tool 接口。
- 模拟盘时间来源可注入，避免订单、成交、T+1 与交易时段校验直接依赖真实当前时间。

暂不作为本阶段硬验收：

- replay dataset。
- replay session。
- replay 报告。

验收：

```text
同一套 tool 在实时模式和 replay 模式都可用
replay 模式下 LLM 只能看到当前回放时间之前的数据
实时模式仍按当前市场时间工作，不被 replay mode 污染
```

---

## 阶段 8：Skill 管理 ← 未实现

目标：让用户通过 WebUI 上传和编辑 skill。

任务：

- skill.yaml 解析。
- skill zip 上传。
- skill prompt 编辑。
- tool whitelist。
- skill 启用 / 禁用。
- skill 绑定 Session。
- skill 版本记录。
- 热重载。

验收：

```text
可以上传 skill
可以编辑 skill prompt
可以限制该 skill 可用工具
Session 可绑定不同 skill
LLM 运行时加载对应 skill
```

---

## 阶段 9：定时触发器 ← 未实现

目标：让 Session 支持带 prompt 的定时事件。

任务：

- APScheduler 集成。
- trigger 表。
- cron trigger。
- interval trigger。
- once trigger。
- trigger prompt。
- trigger 绑定 Session。
- 触发后自动写入 Chat message。
- active run 冲突策略。

验收：

```text
可以在 WebUI 给 Session 配置开盘前触发器
到时间后自动向 Session 注入事件消息
LLM 自动运行并调用工具
完整过程显示在 WebChat 中
```

---

## 阶段 10：多模型实验 ← 未实现

目标：支持比较不同 LLM 的炒股能力。

任务：

- 多 LLM Account。
- 多 Session 同步触发。
- 统一股票池。
- 统一初始资金。
- 对比报告。
- 模型表现排行榜。

验收：

```text
可以让 DeepSeek V4 Pro、DeepSeek V4 Flash、OpenAI-Compatible 模型同时运行同一实验
系统生成收益、回撤、成本、tool call 次数对比
```

---

## 25. 技术栈

| 层 | 技术 | 状态 |
|---|---|---|
| 后端 | FastAPI | 已实现 |
| 前端 | React + TypeScript + Vite | 已实现 |
| LLM SDK | openai Python SDK | 已实现 |
| DeepSeek | 独立 DeepSeek Provider (继承 OpenAI-Compatible) | 已实现 |
| A股模拟器 | app/simulator/ (engine + rules) | 已实现 |
| 数据源 | AKShare | 已实现 |
| 搜索 | Tavily Python SDK | 已实现 |
| 配置管理 | Python 数据类 + 环境变量 | 已实现 |
| 业务数据库 | SQLite | 已实现 |
| 行情数据库 | DuckDB | 已实现 |
| 数据处理 | pandas | 已实现 |
| 容器 | Docker (多阶段构建) | 已实现 |
| 实时推送 | WebSocket | 已实现 |
| 日志 | structlog / logging | 未实现 |
| 包管理 | uv | 已实现 |

---

## 26. 实际项目结构

```text
backend/app/
├─ main.py
├─ api/
│  ├─ __init__.py
│  ├─ sessions.py
│  ├─ providers.py
│  ├─ tools.py
│  ├─ market.py
│  ├─ data.py
│  ├─ ws.py
│  └─ dependencies.py
├─ core/
│  ├─ __init__.py
│  ├─ config.py
│  └─ websocket_manager.py
├─ llm/                       ← 原计划 app/providers/，已改名为 app/llm/
│  ├─ __init__.py
│  ├─ base.py
│  ├─ openai_compatible.py
│  ├─ deepseek.py
│  └─ registry.py
├─ tools/
│  ├─ __init__.py
│  ├─ registry.py
│  ├─ executor.py
│  ├─ market_tools.py
│  └─ tavily_tools.py
├─ market/
│  ├─ __init__.py
│  ├─ akshare_provider.py
│  └─ normalizer.py
├─ sessions/
│  ├─ __init__.py
│  └─ runtime.py
└─ storage/
   ├─ __init__.py
   ├─ sqlite.py
   └─ duckdb.py

backend/tests/
├─ test_mvp.py
└─ test_market.py
```

**未实现的目录：**

```text
app/simulator/                ← 已创建（A股模拟器）
app/scheduler/                ← 未创建（定时触发器）
app/skills/                   ← 未创建（Skill 系统）
app/tools/order_tools.py      ← 已创建
app/tools/portfolio_tools.py  ← 已创建
app/tools/tavily_tools.py     ← 已创建
app/tools/data_tools.py       ← 未创建
app/tools/journal_tools.py    ← 未创建
app/market/cache.py           ← 未创建（缓存逻辑在 storage/duckdb.py）
app/market/replay_provider.py ← 未创建
app/sessions/context_builder.py ← 未创建（上下文加载在 runtime.py 内联）
app/sessions/run_manager.py   ← 未创建
app/storage/migrations/       ← 未创建（表由 sqlite.py 自动创建）
```
```

---

## 27. 关键验收标准

### 27.1 功能验收

```text
单 Docker 容器可启动
WebUI 可访问
可配置 OpenAI-Compatible
可配置 DeepSeek
可创建 LLM Account
可创建 Chat Session
可上传 Skill
可配置 Trigger
可手动拉取行情
可永久保存行情
可合并实时与历史数据
LLM 可调用行情 tool
LLM 可调用 Tavily tool
LLM 可调用下单 tool
模拟盘可更新持仓和现金
所有 tool call 有记录
所有定时触发显示在 Chat 中
```

### 27.2 实验验收

```text
可以完整复现某次 LLM 决策
可以看到当时 prompt
可以看到当时行情快照
可以看到 LLM 调用了哪些工具
可以看到每个工具返回什么
可以看到最终为何下单
可以看到订单是否成交
可以看到该次调用成本
可以导出 Session 报告
```

---

## 28. 风险与应对

| 风险 | 应对 |
|---|---|
| AKShare 接口不稳定 | 本地缓存、失败重试、手动补拉、冲突审计 |
| Provider tool call 不兼容 | Capability Registry + Provider Adapter |
| DeepSeek strict schema 报错 | schema 降级、关闭 strict、简化工具参数 |
| 定时触发重叠 | Session active run 锁 + 队列策略 |
| LLM 误用工具 | 保留市场规则校验，不做投资风控 |
| 历史回放泄露未来数据 | Replay Clock 强制过滤 |
| Replay 污染实时路径 | live / replay 模式隔离，统一 Clock 注入，禁止在业务逻辑中直接读取真实当前时间 |
| Skill 上传风险 | 第一阶段不支持任意代码 |
| 成本不可控 | token / 费用记录 + 单次运行限制 |
| 交易成本归因不准确 | 按 session / run / tool call 建立成本归因，避免仅按时间窗口估算 |
| WebChat 上下文过长 | 历史摘要 + 最近消息窗口 + journal 查询工具 |

---

## 29. 最终推荐路线

```text
第一阶段：
先做单容器 WebChat + OpenAI-Compatible / DeepSeek + tool call runtime。

第二阶段：
接入 AKShare + DuckDB Market Cache，实现手动拉取、永久保存、自动合并。

第三阶段：
实现 A 股模拟盘，让 LLM 可以查询账户和下模拟单。

第四阶段：
实现交易页账户观察栏与查看页（/view）全量分析能力，打通实时观察与复盘查询。

第五阶段：
接入 Tavily 搜索和 extract。

第六阶段：
补齐成本记录与分析，建立 Session、run、tool call 和交易成本归因。

第七阶段：
补齐交易日历与历史回放一致性基础，先解决 Replay Clock、防未来数据泄露和 market tools 回放模式。

第八阶段：
实现 Skill WebUI 上传编辑。

第九阶段：
实现 Trigger 定时注入消息。

第十阶段：
做多模型实验和自动对比报告。
```

---

## 30. 一句话总结

本项目最终形态是：

```text
一个单容器部署的 A 股 LLM 模拟交易 WebChat 系统；
每个交易实验是一条 Chat Session；
OpenAI-Compatible 和 DeepSeek V4 都可作为模型来源；
AKShare 是唯一免费股票数据源；
Tavily 提供实时网页搜索；
Skill 可在 WebUI 上传和编辑；
定时任务本质是给 Session 自动发送带 prompt 的事件消息；
LLM 通过 tool call 自主查询、搜索、下单和复盘；
所有行情、对话、thinking、tool call、订单、成交、成本和结果都永久记录。
```
