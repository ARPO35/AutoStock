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
| DeepSeek | 默认支持 DeepSeek V4 API |
| Tool Call | 所有功能通过 tool call 实现 |
| Skill | 支持加载、上传、编辑、启用、禁用 |
| WebUI | 单一统一管理页面 |
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
│  ├─ OpenAI-Compatible Provider
│  └─ DeepSeek Provider
├─ Provider Capability Registry
├─ Tool Call Runtime
├─ Skill Manager
├─ Session-bound Trigger Scheduler
├─ AKShare Market Provider
├─ Market Cache / Data Warehouse
├─ Tavily Search Provider
├─ A股 Simulator
├─ SQLite
│  ├─ 配置
│  ├─ 会话
│  ├─ 消息
│  ├─ 触发器
│  ├─ 订单
│  ├─ 成交
│  └─ 决策日志
└─ DuckDB
   ├─ 历史行情
   ├─ 实时行情缓存
   ├─ 回放数据
   └─ 分析结果
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
│  │  ├─ core/
│  │  ├─ providers/
│  │  ├─ tools/
│  │  ├─ simulator/
│  │  ├─ scheduler/
│  │  ├─ skills/
│  │  └─ storage/
│  └─ pyproject.toml
├─ frontend_dist/
├─ user_skills/
├─ data/
│  ├─ app.db
│  ├─ market.duckdb
│  ├─ logs/
│  └─ exports/
└─ config/
   └─ default.yaml
```

### 5.2 启动方式

容器内只启动一个主服务：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

不拆 Postgres、Redis、worker、AKTools 等额外容器。后台调度、行情拉取、LLM 运行、WebChat 推送都在同一 FastAPI 进程内完成。

---

## 6. WebUI 页面设计

### 6.1 Dashboard

用途：总览系统运行状态。

内容：

- 当前交易日。
- 当前市场状态。
- 活跃 Chat Session。
- 活跃 LLM Account。
- 今日模拟收益。
- 最近订单。
- 最近 tool call。
- 最近 LLM 决策。
- 数据源状态。
- Tavily 状态。
- 调度器状态。

### 6.2 API 配置

用途：配置外部 API。

内容：

- AKShare 配置。
- Tavily API Key。
- Tavily search depth 默认值。
- Tavily max results 默认值。
- 行情缓存策略。
- 接口失败重试次数。
- 接口超时时间。
- 是否允许缺失数据时自动补拉。

### 6.3 LLM Provider 配置

用途：配置模型来源。

默认支持：

```text
openai_compatible
deepseek
```

OpenAI-Compatible 配置项：

```text
name
base_url
api_key
model
temperature
max_tokens
timeout
supports_tools
supports_parallel_tool_calls
supports_strict_schema
```

DeepSeek 配置项：

```text
api_key
base_url = https://api.deepseek.com
model = deepseek-v4-pro / deepseek-v4-flash
thinking_mode = thinking / non_thinking
strict_tool_schema = true / false
temperature
max_tokens
timeout
```

### 6.4 Prompt 配置

用途：编辑不同层级的 prompt。

Prompt 分层：

```text
全局系统提示词
+ Provider 适配提示词
+ Skill 提示词
+ Session 提示词
+ Trigger 事件提示词
+ 用户手动消息
```

页面功能：

- 编辑全局 system prompt。
- 编辑交易员人格 prompt。
- 编辑复盘 prompt。
- 编辑异常处理 prompt。
- 查看 prompt 版本历史。
- 回滚 prompt 版本。
- 查看某次运行实际拼接后的完整 prompt。

### 6.5 Tool 配置

用途：管理 LLM 可调用工具。

工具分组：

```text
market.*
portfolio.*
order.*
simulator.*
tavily.*
journal.*
report.*
data.*
```

功能：

- 启用 / 禁用工具。
- 查看 tool schema。
- 测试工具调用。
- 设置工具超时。
- 设置工具是否允许被定时触发调用。
- 设置工具是否写入审计日志。
- 设置 skill 级工具白名单。

### 6.6 Skill 管理

用途：上传、编辑、启用、禁用 skill。

功能：

- 上传 skill zip。
- 在线编辑 `skill.yaml`。
- 在线编辑 `system.md`。
- 在线编辑 tool 白名单。
- 启用 / 禁用 skill。
- 热重载 skill。
- 查看 skill 版本。
- 回滚 skill。
- 绑定 skill 到 Chat Session。
- 绑定 skill 到 LLM Account。

### 6.7 LLM 账户管理

用途：管理虚拟交易账户和模型配置。

一个 LLM Account 包含：

```text
账户名称
Provider
模型
API Key 引用
初始资金
当前现金
持仓
绑定股票池
默认 skill
默认 trigger 模板
成本统计
```

### 6.8 WebChat Session

用途：核心交互界面。

每个 Session 显示：

- 用户消息。
- 定时事件消息。
- LLM 回复。
- thinking / reasoning 记录。
- tool call。
- tool result。
- 下单结果。
- 持仓变化。
- 行情快照。
- 成本记录。
- 复盘总结。

### 6.9 事件触发器

用途：为某个 Chat Session 配置自动消息。

触发器类型：

| 类型 | 用途 |
|---|---|
| manual | 手动点击运行一次 |
| cron | 开盘前、尾盘、收盘等固定时间 |
| interval | 盘中每 5 / 15 / 30 分钟 |
| once | 指定时间单次实验 |
| market_event | 后续计划：行情异动触发 |

触发器绑定对象：

```text
trigger -> chat_session_id
```

不是直接绑定后台账户任务。

### 6.10 数据仓库

用途：手动拉取、保存、合并行情数据。

功能：

- 输入股票代码。
- 选择时间段。
- 选择周期：日线、分钟线等。
- 选择复权方式。
- 手动拉取。
- 永久保存。
- 查看缓存覆盖范围。
- 查看缺失数据。
- 查看数据冲突。
- 手动重新拉取。
- 导出 CSV / Parquet。

### 6.11 模拟盘

用途：查看模拟交易状态。

内容：

- 现金。
- 可用资金。
- 持仓。
- 冻结资金。
- 当前市值。
- 总资产。
- 订单。
- 成交。
- 收益曲线。
- 换手率。
- 最大回撤。
- 持仓成本。
- 每笔交易来源 Session。

### 6.12 决策日志

用途：审计和研究 LLM 炒股可行性。

记录：

- Session ID。
- Trigger ID。
- Provider。
- Model。
- Prompt 版本。
- Skill 版本。
- 输入消息。
- thinking / reasoning。
- tool call。
- tool result。
- 最终回复。
- 订单。
- 成交。
- 行情快照。
- token 消耗。
- 耗时。
- 费用估算。

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
- llm_account_id
- skill_id
- simulator_account_id
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
- created_at
```

```sql
chat_tool_calls
- id
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

### 8.1 工作流

```text
事件触发
→ 写入 Chat Session 消息
→ 构建上下文
→ 加载 Provider
→ 加载 Skill
→ 加载可用 Tools
→ 调用 LLM
→ 解析 tool calls
→ 执行工具
→ 写入 tool results
→ 再次调用 LLM
→ 直到没有 tool call 或达到限制
→ 保存最终回复
→ 更新模拟账户
→ 写入成本和日志
```

### 8.2 伪代码

```python
async def run_session_once(session_id: str, event_message_id: str):
    session = db.get_session(session_id)
    account = db.get_llm_account(session.llm_account_id)
    skill = skill_manager.load(session.skill_id)
    provider = provider_registry.get(account.provider_type)

    messages = context_builder.build(
        session_id=session_id,
        global_prompt=db.get_global_prompt(),
        skill_prompt=skill.prompt,
        event_message_id=event_message_id,
        recent_messages_limit=session.context_limit,
    )

    tools = tool_registry.resolve(skill.allowed_tools)
    tools = provider.adapter.adapt_tools(tools)

    run = db.create_run(session_id=session_id)

    for i in range(session.max_tool_rounds):
        response = await provider.chat(
            account=account,
            messages=messages,
            tools=tools,
        )

        db.save_llm_response(run.id, response)

        if not response.tool_calls:
            db.finish_run(run.id, final_message=response.content)
            return response

        for call in response.tool_calls:
            normalized_call = provider.adapter.normalize_tool_call(call)
            result = await tool_executor.execute(
                session_id=session_id,
                tool_call=normalized_call,
            )

            db.save_tool_call(run.id, normalized_call)
            db.save_tool_result(run.id, normalized_call.id, result)

            messages.append({
                "role": "tool",
                "tool_call_id": normalized_call.id,
                "content": result.to_json()
            })

    db.finish_run(run.id, status="max_tool_rounds_reached")
```

### 8.3 并发规则

这里的并发控制不是限制 LLM 交易自由，而是保证同一条会话不出现上下文交叉。

| 场景 | 规则 |
|---|---|
| 同一 Session 已有 active run，又来了触发器 | 可配置：排队 / 跳过 / 合并 |
| 不同 Session 同时运行 | 允许 |
| 不同 LLM Account 同时运行 | 允许 |
| 同一虚拟账户被多个 Session 同时操作 | 默认禁止，除非开启共享账户实验 |
| 用户手动消息与定时触发冲突 | 优先用户手动消息，定时事件排队 |

---

## 9. 定时触发器设计

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
  "max_tool_rounds": 20,
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

### 10.3 DeepSeek Provider

DeepSeek 虽然兼容 OpenAI API，但仍单独做 Provider。

原因：

- 默认 base_url 不同。
- DeepSeek V4 模型名可预设。
- Thinking / Non-Thinking 模式需要配置。
- strict tool schema 有 DeepSeek 自己的限制。
- thinking 内容解析需要特殊处理。
- 后续可以针对 DeepSeek V4 做 schema 降级和 prompt 适配。

配置：

```yaml
provider_type: deepseek
base_url: https://api.deepseek.com
api_key: sk-xxx
model: deepseek-v4-pro
thinking_mode: thinking
strict_tool_schema: true
temperature: 0.7
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

## 11. Skill 系统设计

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
  max_tool_rounds: 20
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

### 12.1 工具分组

```text
market.*
data.*
portfolio.*
order.*
simulator.*
tavily.*
journal.*
report.*
```

### 12.2 Market Tools

```text
market.stock_list
market.quote
market.history
market.minute
market.announcement
market.index_quote
```

用途：

- 查询股票列表。
- 查询实时行情。
- 查询历史 K 线。
- 查询分钟线。
- 查询公告。
- 查询指数行情。

### 12.3 Data Tools

```text
data.fetch_history
data.cache_status
data.find_missing
data.resolve_conflict
```

用途：

- 手动拉取指定时间段数据。
- 查看本地缓存。
- 查找缺失行情。
- 查看数据冲突。

### 12.4 Portfolio Tools

```text
portfolio.get_state
portfolio.get_positions
portfolio.get_orders
portfolio.get_trades
portfolio.get_performance
```

用途：

- 查询现金。
- 查询持仓。
- 查询订单。
- 查询成交。
- 查询收益。

### 12.5 Order Tools

```text
order.buy
order.sell
order.cancel
```

用途：

- 模拟买入。
- 模拟卖出。
- 撤销未成交订单。

### 12.6 Simulator Tools

```text
simulator.next_tick
simulator.run_until
simulator.reset
simulator.set_mode
```

用途：

- 历史回放推进。
- 实时模拟切换。
- 重置实验。
- 切换 replay / realtime。

### 12.7 Tavily Tools

```text
tavily.search
tavily.extract
```

用途：

- 搜索公司新闻。
- 搜索政策信息。
- 搜索行业变化。
- 抽取网页正文。
- 为 LLM 补充实时外部信息。

### 12.8 Journal Tools

```text
journal.write
journal.query_recent
```

用途：

- 让 LLM 写交易理由。
- 让 LLM 查询最近决策。
- 支持连续复盘。

### 12.9 Report Tools

```text
report.generate_daily
report.generate_session
report.generate_comparison
```

用途：

- 生成每日复盘。
- 生成单 Session 报告。
- 生成多模型对比报告。

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

## 14. A 股模拟器设计

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
- llm_account_id
- name
- initial_cash
- cash
- frozen_cash
- total_asset
- created_at
```

---

## 15. 历史回放一致性

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

## 16. Tavily 搜索设计

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

## 17. 成本记录

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

## 18. 决策日志与实验分析

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

## 19. 多模型实验设计

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

```text
settings
llm_providers
llm_accounts
skills
skill_versions
chat_sessions
chat_messages
chat_runs
chat_tool_calls
chat_tool_results
triggers
simulator_accounts
orders
trades
positions
journal_entries
llm_usage_records
```

### 21.2 DuckDB

保存行情和分析数据：

```text
market_bars
market_quotes
market_announcements
market_cache_status
data_conflicts
replay_datasets
performance_snapshots
analysis_reports
```

---

## 22. 后端 API 规划

### 22.1 Session API

```text
GET    /api/sessions
POST   /api/sessions
GET    /api/sessions/{id}
POST   /api/sessions/{id}/messages
POST   /api/sessions/{id}/run
GET    /api/sessions/{id}/messages
GET    /api/sessions/{id}/runs
```

### 22.2 WebSocket

```text
/ws/sessions/{id}
```

推送：

```text
new_message
llm_delta
thinking_delta
tool_call_started
tool_call_finished
order_created
trade_created
run_finished
error
```

### 22.3 Skill API

```text
GET    /api/skills
POST   /api/skills/upload
GET    /api/skills/{id}
PUT    /api/skills/{id}
POST   /api/skills/{id}/enable
POST   /api/skills/{id}/disable
POST   /api/skills/{id}/reload
```

### 22.4 Trigger API

```text
GET    /api/triggers
POST   /api/triggers
PUT    /api/triggers/{id}
DELETE /api/triggers/{id}
POST   /api/triggers/{id}/run-now
```

### 22.5 Data API

```text
POST   /api/data/fetch-history
GET    /api/data/cache-status
GET    /api/data/missing
GET    /api/data/conflicts
POST   /api/data/conflicts/{id}/resolve
```

### 22.6 Simulator API

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

单容器部署时，前端 build 后放入：

```text
frontend_dist/
```

由 FastAPI 静态托管。

### 23.2 关键组件

```text
ChatWindow
ToolCallTimeline
ThinkingBlock
PortfolioPanel
MarketPanel
TriggerEditor
SkillEditor
ProviderEditor
DataFetchPanel
OrderTable
TradeTable
CostPanel
```

### 23.3 WebChat 展示要求

每次 LLM Run 应按时间线展示：

```text
事件消息
→ LLM thinking
→ tool call
→ tool result
→ LLM 继续 thinking
→ 下单 tool call
→ 成交结果
→ 最终回复
```

---

## 24. 开发阶段计划

## 阶段 1：MVP 骨架

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

## 阶段 2：AKShare 数据与 Market Cache

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

## 阶段 3：模拟盘

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

---

## 阶段 4：Skill 管理

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

## 阶段 5：定时触发器

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

## 阶段 6：Tavily 搜索

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

## 阶段 7：成本记录与分析

目标：记录不同模型的运行成本。

任务：

- usage parser。
- 不同 Provider usage normalizer。
- llm_usage_records。
- 成本配置。
- 成本面板。
- Session 成本统计。
- 每笔交易成本统计。

验收：

```text
每次 LLM 调用都记录 token、耗时、模型、provider、估算成本
WebUI 可查看 Session 总成本和单次运行成本
```

---

## 阶段 8：历史回放一致性

目标：为历史 replay 做架构统一。

任务：

- Replay Clock。
- replay mode。
- market tools 按 replay time 返回数据。
- 禁止未来数据泄露。
- replay dataset。
- replay session。
- replay 报告。

验收：

```text
同一套 tool 在实时模式和 replay 模式都可用
replay 模式下 LLM 只能看到当前回放时间之前的数据
```

---

## 阶段 9：多模型实验

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

## 25. 推荐技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI |
| 前端 | React + TypeScript + Vite |
| LLM SDK | openai Python SDK + 自定义 Provider Adapter |
| DeepSeek | 独立 DeepSeek Provider |
| 调度 | APScheduler |
| 数据源 | AKShare |
| 搜索 | Tavily Python SDK |
| 配置库 | Pydantic Settings |
| 业务数据库 | SQLite |
| 行情数据库 | DuckDB |
| 数据处理 | pandas |
| 容器 | Docker |
| 实时推送 | WebSocket |
| 日志 | structlog / logging |
| 包管理 | uv |

---

## 26. 推荐项目结构

```text
backend/app/
├─ main.py
├─ api/
│  ├─ sessions.py
│  ├─ providers.py
│  ├─ skills.py
│  ├─ triggers.py
│  ├─ market.py
│  ├─ simulator.py
│  └─ data.py
├─ core/
│  ├─ config.py
│  ├─ database.py
│  ├─ event_bus.py
│  └─ websocket_manager.py
├─ llm/
│  ├─ base.py
│  ├─ openai_compatible.py
│  ├─ deepseek.py
│  ├─ capabilities.py
│  └─ adapters.py
├─ tools/
│  ├─ registry.py
│  ├─ executor.py
│  ├─ market_tools.py
│  ├─ order_tools.py
│  ├─ portfolio_tools.py
│  ├─ tavily_tools.py
│  ├─ data_tools.py
│  └─ journal_tools.py
├─ market/
│  ├─ akshare_provider.py
│  ├─ cache.py
│  ├─ normalizer.py
│  └─ replay_provider.py
├─ simulator/
│  ├─ account.py
│  ├─ order.py
│  ├─ matching.py
│  ├─ rules_a_stock.py
│  └─ portfolio.py
├─ sessions/
│  ├─ runtime.py
│  ├─ context_builder.py
│  └─ run_manager.py
├─ skills/
│  ├─ manager.py
│  ├─ validator.py
│  └─ loader.py
├─ scheduler/
│  ├─ manager.py
│  ├─ trigger_runner.py
│  └─ calendar.py
└─ storage/
   ├─ sqlite.py
   ├─ duckdb.py
   └─ migrations/
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
| Skill 上传风险 | 第一阶段不支持任意代码 |
| 成本不可控 | token / 费用记录 + 单次运行限制 |
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
实现 Skill WebUI 上传编辑和 Trigger 定时注入消息。

第五阶段：
接入 Tavily 搜索和 extract。

第六阶段：
补齐成本记录、交易日历、历史回放一致性。

第七阶段：
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
