# Frontend Design：A 股 LLM 模拟交易系统 WebUI

## 1. 前端设计目标

本前端是 A 股 LLM 模拟交易系统的统一 WebUI，负责项目的全部使用、查看、修改和管理能力。

核心目标：

```text
用户可以像使用普通 LLM 网站一样与模型交互；
同时可以观察 LLM 的工具调用、可见推理、交易行为、账户变化、资产曲线和历史记录；
所有模拟交易、搜索、行情、订单、持仓、资产变化都应可追溯、可查看、可对比。
```

前端不是单纯后台管理页，而是一个 **WebChat 式 LLM 模拟交易工作台 + 全局模拟盘观察系统 + 配置管理系统**。

---

## 2. 顶部一级导航

顶部导航需要保持简洁，只包含四个一级入口：

```text
交易（LLM） | 查看 | 修改 | 管理
```

顶部示意：

```text
┌──────────────────────────────────────────────────────────────┐
│ A股LLM模拟盘        交易（LLM）    查看    修改    管理       │
└──────────────────────────────────────────────────────────────┘
```

四个一级入口的职责：

| 一级入口 | 定位 |
|---|---|
| 交易（LLM） | WebChat 式 LLM 交易工作台 |
| 查看 | 全局观察、对比分析、行情浏览、模拟时间线控制 |
| 修改 | 人工修改账户、余额、持仓、订单、Session 绑定 |
| 管理 | LLM、API、Skills、Tools、触发器、数据、系统配置 |

其他复杂功能不放在顶部，而是在各自一级页面内部通过二级导航或子页面组织。

推荐路由结构：

```text
/trade
/view
/edit
/manage
```

---

## 3. 全局布局原则

### 3.1 页面类型

整个系统页面分为四类：

```text
交易：实际与 LLM 交互。
查看：查看所有账号、Session、交易、资产曲线、行情和时间线。
修改：人工修改账户状态或 Session 绑定。
管理：配置模型、API、Skill、Tool、触发器、数据源和系统参数。
```

### 3.2 设计原则

```text
顶部导航必须简洁。
交易页必须以 WebChat 体验为核心。
查看页必须适合全局总览和跨账号对比。
修改页必须带审计意识。
管理页必须把配置分组清晰。
工具调用结果必须可读，而不是只展示 JSON。
```

---

## 4. 交易（LLM）页面

路由：

```text
/trade
```

交易页是核心使用页面，用于与 LLM 进行 WebChat 式交互，并实时观察 LLM 调用工具、查询行情、搜索网页、下模拟单、复盘的全过程。

### 4.1 三栏布局

交易页采用三栏布局：

```text
┌───────────────┬───────────────────────────────┬─────────────────────────────┐
│ 左侧账户栏     │ 中间 LLM 线性流程              │ 右侧账户观察栏               │
│ Account Tree  │ Chat / Tool / Reasoning        │ Portfolio Inspector          │
└───────────────┴───────────────────────────────┴─────────────────────────────┘
```

三栏职责：

| 区域 | 作用 |
|---|---|
| 左侧 | 账户文件夹与 Sessions 列表 |
| 中间 | LLM 线性对话、可见推理、tool call、tool result、最终回复 |
| 右侧 | 当前账户信息、持仓、交易记录、资产曲线、数字指标 |

### 4.2 宽度规则

```text
左侧栏：账户文件夹和 sessions，较窄。
中间区：LLM 交互主区域，需要保证可读性。
右侧栏：账户观察区，默认较宽，左边框可拖动调整宽度。
```

建议尺寸：

| 区域 | 建议 |
|---|---|
| 左侧栏默认宽度 | 260px ~ 320px |
| 左侧栏能力 | 可折叠 |
| 中间区最小宽度 | 520px |
| 右侧栏默认宽度 | 左栏外剩余宽度的一半 |
| 右侧栏最小宽度 | 420px |
| 右侧栏最大宽度 | 页面宽度的 70% |
| 右侧栏调整方式 | 拖动右侧栏左边框 |

右侧栏拖动后的宽度建议保存到 localStorage，刷新页面后保持用户上次布局。

---

## 5. 交易页：左侧账户文件夹栏

### 5.1 核心结构

左侧首先显示账户文件夹，账户文件夹内包含 sessions。

```text
账户 A
  - Session 1
  - Session 2

账户 B
  - Session 3
  - Session 4
```

确定要求：

```text
同一个账户文件夹内的 sessions 使用同一个账户。
每个 session 可以使用不同模型。
允许多 session 并行运行。
```

### 5.2 概念关系

```text
Account = 资金、持仓、资产归属。
Session = 一条独立 LLM 对话和交易实验线程。
Model = Session 级配置，不强制跟账户绑定。
```

一个账户下可以有多个 Session：

```text
Account A
  ├─ Session A：DeepSeek V4 Pro
  ├─ Session B：OpenAI-Compatible 模型
  └─ Session C：DeepSeek V4 Flash
```

### 5.3 左侧显示内容

账户文件夹显示：

```text
账户名
当前总资产
今日收益
当前运行中 session 数量
```

Session 条目显示：

```text
Session 名称
模型名
运行状态 (idle/running/error)
最后运行时间
是否有触发器  ← 未实现
```

状态建议（实际实现）：

| 状态 | 表现 |
|---|---|
| idle | 灰点 ✓ |
| running | 蓝点 ✓ |
| queued | 未实现 |
| error | 红点 ✓ |
| has trigger | 未实现 (小钟图标) |

### 5.4 左侧操作

```text
新建 Session          ← 已实现
搜索 Session          ← 未实现
复制 Session          ← 未实现
归档 Session          ← 未实现
切换 Session          ← 已实现
折叠账户文件夹        ← 已实现
```

新建 Session 时需要选择或继承（实际实现）：

```text
账户                     ← 已实现
模型（隐式 Provider）    ← 已实现
Skill                    ← 未实现 (skill_id 列预留但无效)
是否启用默认触发器       ← 未实现
```

---

## 6. 交易页：中间 LLM 线性流程

### 6.1 目标

中间区域类似常见 LLM 交互页面，但必须展示交易 Agent 的完整执行链。

线性流程包含：

```text
用户消息
定时事件消息
LLM 可见推理
Tool Call
Tool Result
下单结果
最终回复
错误
```

### 6.2 Session Header

中间顶部需要显示当前 Session 信息：

```text
Session 名称
当前账户
当前模型
当前 Provider（由模型隐式决定）
当前 Skill
当前模式：实时 / 回放
当前状态：空闲 / 运行中 / 排队 / 报错
```

快捷按钮：

```text
运行一次
停止当前 run
查看触发器摘要
跳转修改 Session 配置
```

### 6.3 Timeline 消息类型

Timeline 中的元素包括（实际实现）：

| 类型 | 说明 |
|---|---|
| UserMessage | 用户人工输入 ✓ |
| EventMessage | 定时触发器注入的事件消息（未实现） |
| AssistantMessage | LLM 最终回复 ✓（含可见推理折叠卡） |
| ReasoningBlock | Provider 返回的可见推理（内联在 AssistantMessage 中） ✓ |
| ToolCallCard | 工具调用卡片（结果内联在同一卡片中，非独立 ResultCard） ✓ |
| ToolResultCard | **设计中为独立项，实际结果内联在 ToolCallCard 中** |
| OrderResultCard | 买入 / 卖出 / 撤单结果（Renderer 已有，后端未实现） |
| ErrorCard | Provider、工具、撮合、数据源错误 ✓ |

注：实际 `TimelineItem` 类型不含独立 `ToolResultItem`，工具结果通过 `ToolCallCard` 展开时由 `ToolResultRenderer` 渲染。

### 6.4 不展示完整 CoT

系统需要支持 OpenAI、DeepSeek 等大厂 API 特性，但不包含完整 CoT。

UI 不应使用以下命名：

```text
完整思考链
完整 CoT
```

应使用：

```text
可见推理
推理摘要
Reasoning
模型思考输出
```

规则：

```text
如果 Provider 返回可见 reasoning，则展示。
如果 Provider 不返回，则显示“无可见推理”。
前端不能伪造 reasoning。
```

### 6.5 Tool Call 默认折叠

确定要求：

```text
tool call 详情默认折叠，只显示调用了什么工具。
```

默认展示示例：

```text
[Tool Call] tavily.search
[Tool Call] market.quote
[Tool Call] order.buy
```

建议可额外显示极短参数摘要，但不展开 JSON：

```text
[Tool Call] tavily.search：宁德时代 今日公告
[Tool Call] market.quote：600519
[Tool Call] order.buy：600519 / 100股
```

展开后显示：

```text
调用参数
调用状态
耗时
错误信息
原始 JSON
```

### 6.6 Tool Result 必须人类可读

工具结果不能只显示 JSON。

前端需要按工具类型渲染结果：

```text
搜索结果 → 标题 + 网站名列表。
价格查询 → 一行价格信息。
历史行情 → 图表。
订单结果 → 订单卡片。
账户状态 → 数字面板。
公告结果 → 公告列表。
```

同时必须保留：

```text
查看详情
查看原始 JSON
```

---

## 7. Tool Result 渲染规则

**前端 Renderer 实现状态：5 个 Renderer 均已创建，但仅部分有对应后端工具**

| Renderer | 前端文件 | 后端工具 | 可实际渲染 |
|---|---|---|---|
| TavilySearchRenderer | ✓ | tavily.search (未实现) | ✗ |
| MarketQuoteRenderer | ✓ | market_quote (已实现) | ✓ |
| MarketHistoryChartRenderer | ✓ | market_history (已实现) | ✓ |
| PortfolioStateRenderer | ✓ | portfolio.* (未实现) | ✗ |
| OrderResultRenderer | ✓ | order.* (未实现) | ✗ |

### 7.1 Tavily 搜索结果 ← Renderer 已实现，后端未实现

确定要求：

```text
搜索获取到的内容需要每一项一行，
展示标题和网站名，
网站名显示顶级到 3 级域名。
```

默认展示：

```text
1. 宁德时代发布关于回购股份事项的公告
   cninfo.com.cn

2. A股三大指数午后拉升，新能源板块走强
   finance.eastmoney.com

3. 券商称电池产业链景气度出现修复
   research.stock.example.com
```

默认不展示摘要和完整 URL。  
点击单项后展开：

```text
摘要
URL
发布时间
相关度
原始结果字段
```

域名显示规则：

```text
尽量显示顶级到 3 级域名。
例如：
www.cninfo.com.cn -> cninfo.com.cn
finance.eastmoney.com -> finance.eastmoney.com
research.stock.example.com -> stock.example.com 或 research.stock.example.com，按域名解析库结果确定。
```

建议使用公共后缀解析库处理 `com.cn`、`gov.cn` 等情况，避免简单 split 导致主体域名裁剪错误。

### 7.2 股票价格查询

查看价格时必须展示一行 compact quote：

```text
贵州茅台 600519 | ¥1680.50 | +12.30 +0.74% | 今开 1668.00 | 最高 1688.00 | 最低 1659.00 | 成交额 35.2亿
```

A 股颜色习惯：

```text
红色 = 上涨
绿色 = 下跌
灰色 = 平盘
```

### 7.3 股票历史记录

查看股票历史数据必须渲染图：

```text
K 线图
分钟图
成交量柱状图
```

图表要求：

```text
显示股票代码和名称。
显示周期：日线 / 分钟线。
显示复权方式。
显示成交量。
可展开查看大图。
```

重要规则：

```text
中间 timeline 中的图表是当次 tool result 的快照，不能随着未来行情刷新而改变。
```

### 7.4 订单结果

订单结果展示为卡片：

```text
买入成功 / 买入失败 / 部分成交
股票：600519 贵州茅台
数量：100 股
委托价：1680.50
成交价：1680.30
手续费：¥5.00
状态：已成交
来源 Session：xxx
来源模型：xxx
```

### 7.5 账户状态

账户状态展示为数字网格：

```text
总资产
现金
持仓市值
今日收益
累计收益
浮动盈亏
可用资金
冻结资金
```

---

## 8. 交易页：右侧账户观察栏

### 8.1 目标

右侧栏用于持续观察当前选中 Session 所属账户。

由于每个 Session 可以使用不同模型，右侧顶部必须明确显示：

```text
当前账户：账户 A
当前 Session：短线实验 001
当前模型：DeepSeek V4 Pro
当前 Skill：short_term_trader
```

### 8.2 内容模块（实现状态）

右侧栏包含：

```text
当前账户信息         ← 已实现（account context strip + metrics grid）
资产变化折线图       ← 已实现（SVG 折线 + 高/中/低纵向标尺）
数字信息面板         ← 已实现（资金、收益、交易统计）
持仓股票列表，可展开 ← 已实现（当前为紧凑列表，含可用数量、成本、现价、市值、浮盈亏率）
交易记录折叠栏       ← 已实现（最近成交列表，可定位到对应 tool call）
```

当前 Skill 显示：未实现（skill_id 列预留但无效）。

### 8.3 当前账户信息

显示：

```text
账户名
当前 Session
当前模型
当前 Skill
初始资金
当前总资产
现金
持仓市值
今日收益
累计收益
```

### 8.4 资产变化折线图

右侧显示当前账户资产曲线。

内容：

```text
总资产曲线
可选现金曲线
可选持仓市值曲线
```

这是实时观察图，可以随账户更新而刷新。

当前交易页右侧栏使用轻量 SVG 折线：只绘制总资产曲线，并显示最高值、中位值、最低值三档纵向标尺；点数不足时保持 EmptyState，不合成占位数据。

### 8.5 数字信息面板

需要将相关数字全部列出来。

建议分组：

```text
资金类：初始资金、现金、可用资金、冻结资金、持仓市值、总资产。
收益类：今日收益、今日收益率、累计收益、累计收益率、浮动盈亏、已实现盈亏。
交易类：今日买入次数、今日卖出次数、总交易次数、今日成交额、累计手续费、累计印花税。
LLM 类：今日 run 次数、今日 tool call 次数、今日 Tavily 搜索次数、今日 token、今日成本估算。
```

### 8.6 持仓股票列表

折叠状态显示：

```text
600519 贵州茅台 | 100股 | 市值 ¥168,050 | 浮盈 +2.3%
```

展开后显示：

```text
股票名称
代码
持仓数量
可卖数量
平均成本
现价
市值
浮动盈亏
浮动盈亏率
今日涨跌幅
买入来源 Session
最近一次 LLM 理由
小型价格走势图
```

### 8.7 交易记录折叠栏

分组：

```text
今日交易
历史交易
未成交订单
已撤销订单
```

每条记录显示：

```text
时间
买 / 卖
股票
数量
价格
金额
手续费
税费
来源 Session
来源模型
```

交易页右侧栏的紧凑成交行显示为 `买入/卖出 股票名（六位代码）`；当后端未返回股票名时只显示六位代码。价格显示为人民币每股口径，例如 `100 股 @ ¥12.34/股`。

点击交易记录后：

```text
中间 timeline 自动滚动到对应 order.buy / order.sell tool call。
对应卡片高亮显示。
```

---

## 9. 交易页底部输入区

输入区支持（实现状态）：

```text
普通用户消息       ← 已实现
手动事件 prompt    ← 未实现
发送并运行         ← 已实现（"发送"按钮）
只写入不运行       ← 已实现（"Write Only"按钮）
停止当前 run       ← 未实现（按钮存在但 disabled）
```

按钮（实际实现）：

```text
发送                 ← 已实现（发送消息 + 立即 run）
作为事件运行          ← 未实现（按钮存在但 disabled）
只写入              ← 已实现（发送消息不运行）
停止                 ← 未实现（按钮存在但 disabled）
```

快捷事件可选（未实现）：

```text
开盘前观察
盘中检查
尾盘决策
收盘复盘
```

---

## 10. 查看页

**实现状态：7 个子页面均已实现；跨阶段能力以可运行骨架接入**

| 子页面 | 路由 | 状态 |
|---|---|---|
| 总览 | /view/overview | 已实现（账户矩阵、统计指标、综合资产曲线、最近成交/决策/工具/错误） |
| 账号详情 | /view/account-detail | 已实现（资金、持仓、绑定 Session、Session 交易贡献） |
| 股票信息 | /view/stock | 已实现（报价、日线、分钟线、公告、缓存覆盖、拉取保存、发送给 LLM 分析骨架） |
| 交易历史 | /view/trades | 已实现（筛选、成交明细、成本归因字段） |
| 资产曲线 | /view/assets | 已实现（多账户对比、账号显示/隐藏、明细表） |
| 决策日志 | /view/logs | 已实现（交易理由、模型/Session/工具归因） |
| 时间线控制 | /view/timeline | 已实现只读控制骨架（真实 Replay Clock 后续接入） |

路由：

```text
/view
```

### 10.1 查看页定位

查看页不是单纯只读页面，而是：

```text
全局观察、对比分析、行情浏览、模拟时间线控制。
```

查看页重点：

```text
查看所有账号的交易。
查看交易历史。
查看所有账号资产变化对比折线图。
查看所有 session 和账号共用的数据总览。
查看某个账号的详细信息。
查看其他股票的信息。
控制模拟时间线。
```

### 10.2 查看页二级分类

查看页下还有一层分类。

建议子页面：

```text
/view/overview        总览，默认页面
/view/account-detail  账号详情
/view/trades          交易历史
/view/assets          资产曲线
/view/stock           股票信息
/view/logs            决策日志
/view/timeline        时间线控制
```

---

## 11. 查看页：总览

总览是查看页默认页面。

定位：

```text
所有 session 和账号共用的数据总览。
```

内容：

```text
所有账号当前资产
所有账号今日收益
所有账号累计收益
所有账号持仓概览
所有 session 当前状态
最近交易
最近 LLM 决策
最近 tool call
最近错误
```

应包含综合资产曲线：

```text
所有账号资产曲线叠加
默认叠加一层基准曲线
```

基准曲线只用于参考，不需要复杂功能。默认可使用一个全局配置的 A 股指数，例如沪深300。

---

## 12. 查看页：账号详情

账号详情页面专门用于选择账号并查看账号相关详细信息。

功能：

```text
选择账号
查看该账号所有 Sessions
查看该账号资产曲线
查看该账号持仓
查看该账号订单
查看该账号成交
查看该账号交易历史
查看该账号 LLM 成本
查看该账号 tool call 统计
查看该账号不同 Session 的表现对比
```

由于每个 Session 可以使用不同模型，所以账号详情必须展示：

```text
同一账号下不同 Session / 不同模型对该账户的交易贡献。
```

交易和资产变化必须记录归因字段：

```text
account_id
session_id
model
provider
run_id
tool_call_id
```

---

## 13. 查看页：交易历史

交易历史页面用于查看所有账号的交易记录。

字段：

```text
时间
账号
Session
模型
股票
买卖方向
数量
价格
金额
手续费
税费
成交状态
关联 tool call
关联 LLM 回复
```

功能：

```text
按时间筛选
按账号筛选
按 Session 筛选
按模型筛选
按股票筛选
按买卖方向筛选
点击记录跳转到交易页对应 tool call
```

---

## 14. 查看页：资产曲线

资产曲线页面用于比较所有账号的资产变化。

核心功能：

```text
所有账号资产曲线对比
默认叠加一层基准曲线
支持显示 / 隐藏某个账号
支持按时间范围查看
支持标记大额交易点
支持标记人工修改点
支持标记历史覆盖重跑点
```

图表要求：

```text
多账号折线图
基准曲线默认叠加
鼠标 hover 显示时间点、账号资产、基准值
支持缩放或选择时间范围
```

---

## 15. 查看页：股票信息

股票信息页面用于查看其他股票，不限于当前持仓。

需要集成以下功能：

```text
临时查看某只股票
拉取并保存当前股票数据
从查看页发送给 LLM 分析
加入观察列表
```

### 15.1 基础功能

```text
搜索股票
查看实时价格
查看 K 线图
查看分钟图
查看成交量
查看公告
查看本地缓存覆盖范围
```

### 15.2 拉取并保存数据

可以在股票信息页直接拉取当前股票历史数据并永久保存。

字段：

```text
股票代码
时间范围
周期
复权方式
是否保存到本地缓存
```

展示结果：

```text
新增条数
重复条数
冲突条数
缓存覆盖范围
```

### 15.3 发送给 LLM 分析

在股票信息页点击“发送给 LLM 分析”时：

```text
选择账号
选择模型，默认使用账号默认模型，但允许修改
选择 Skill
在对应账号下新开一条 Session
把当前股票、当前图表、当前行情摘要作为初始事件消息注入
跳转到交易（LLM）页面
```

流程：

```text
股票信息页
→ 点击“发送给 LLM 分析”
→ 选择账号 / 模型 / Skill
→ 创建新 Session
→ 注入股票分析事件消息
→ 跳转到 /trade
```

### 15.4 加入观察列表

观察列表用于后续持续查看或让触发器关注。

记录：

```text
股票代码
股票名称
加入时间
备注
关联账号，可选
关联 Session，可选
```

---

## 16. 查看页：决策日志

决策日志页面用于查看所有 LLM 行为。

筛选条件：

```text
账号
Session
模型
时间范围
工具名
是否下单
是否报错
是否由触发器运行
```

列表字段：

```text
时间
账号
Session
模型
触发来源
tool call 数量
订单动作
成本
结果
```

详情页展示：

```text
完整 messages
可见 reasoning
tool calls
tool results
订单
行情快照
成本
错误
```

---

## 17. 查看页：时间线控制

时间线控制页面用于全局模拟时间线操作。

确定要求：

```text
查看页可以跳转时间点。
重写历史默认覆盖。
跳转时间点是全局跳转。
去除手动修改历史功能。
```

### 17.1 支持操作

```text
查看当前全局模拟时间
全局跳转时间点
暂停
继续
加速
减速
单步推进
从当前时间点覆盖式重跑后续历史
查看覆盖重跑记录
```

### 17.2 全局跳转

全局跳转表示：

```text
所有账号、所有 Session、所有资产曲线和交易视图都切换到该模拟时间点对应状态。
```

### 17.3 覆盖式重跑

重写历史默认覆盖。

这里的“重写历史”定义为：

```text
从某个全局模拟时间点开始，废弃其后的自动运行结果，并重新按触发器 / LLM / 行情流程运行后续模拟。
```

不是手动编辑过去某条订单或成交。

建议实现方式：

```text
前端体验是覆盖。
后端审计上不物理删除旧数据，而是将旧记录标记为 superseded / archived。
默认视图只显示当前有效历史。
```

覆盖式重跑时需要提示：

```text
该操作会从指定时间点后重新触发 LLM 调用，并产生新的 API 成本。
旧历史将在默认视图中被覆盖。
```

---

## 18. 修改页

**实现状态：5 个子页面中 2 个已实现，3 个未实现**

| 子页面 | 状态 |
|---|---|
| 账户信息 | 已实现（创建账户表单） |
| 会话绑定 | 已实现（创建 Session 表单） |
| 余额修改 | 未实现（占位） |
| 持仓修改 | 未实现（占位） |
| 订单修正 | 未实现（占位） |

路由：

```text
/edit
```

修改页用于人工直接修改账户状态或绑定关系。

功能：

```text
修改账户信息
修改余额
修改持仓
修正订单
修改 Session 绑定
```

修改页不处理过去历史记录的逐条手动修改。

### 18.1 建议子页面

```text
/edit/accounts
/edit/balance
/edit/positions
/edit/orders
/edit/session-binding
```

### 18.2 审计要求

所有人工修改必须记录：

```text
修改人
修改时间
修改对象
修改前
修改后
修改原因
影响账号
影响 Session
```

人工修改需要在资产曲线中打标记，防止后续分析时把人工干预误认为 LLM 交易收益。

---

## 19. 管理页

**实现状态：6 个分组中 3 个已实现，3 个未实现**

| 分组 | 状态 |
|---|---|
| 模型与API | 已实现（Provider CRUD + connect test + chat test + 远端模型拉取/勾选） |
| Tools | 已实现（工具测试 + schema 查看） |
| 数据管理 | 已实现（数据拉取 + 缓存状态 + 冲突解决） |
| Skills | 未实现（占位） |
| 触发器 | 未实现（占位） |
| 系统设置 | 未实现（占位） |

路由：

```text
/manage
```

管理页包含剩余配置和系统级管理能力。

建议内部使用左侧二级导航，而不是把所有子功能放到顶部。

### 19.1 管理页分组

```text
模型与 API
  - LLM Provider
  - OpenAI-Compatible
  - DeepSeek
  - Tavily
  - AKShare

Agent 能力
  - Skills
  - Tools
  - Prompts

自动化
  - 触发器

数据
  - 本地行情缓存
  - 手动拉取数据
  - 数据冲突

系统
  - 日志
  - 备份
  - 全局设置
```

### 19.2 LLM 管理

需要支持：

```text
OpenAI-Compatible Provider
DeepSeek Provider
模型能力配置
测试连接
测试 tool call
测试可见 reasoning
```

Provider 卡片信息区显示：

```text
Base URL
Provider 类型
API Key
Token 用量
```

模型列表规则：

```text
不显示旧的“可用模型”压缩摘要行。
连接成功且返回远端模型后，在 Token 用量下方显示模型 checkbox 列表。
勾选模型写入 available_models，作为 Session 可选模型来源。
管理页不提供“单次上限”编辑入口；run_token_limit 仍保留为后端运行时 token cap 能力。
```

### 19.3 Skills 管理

需要支持：

```text
上传 Skill
编辑 Skill Prompt
编辑 Tool 白名单
启用 / 禁用
版本管理
绑定到 Session
```

### 19.4 Tools 管理

需要支持：

```text
查看工具列表
启用 / 禁用工具
查看 tool schema
测试调用
查看最近调用记录
配置超时
```

### 19.5 触发器管理

需要支持：

```text
创建 cron / interval / once 触发器
绑定 Chat Session
编辑 event_prompt
启用 / 禁用
立即运行
查看最近运行状态
```

### 19.6 数据管理

管理页中的数据管理用于批量和系统级数据操作：

```text
批量拉取股票数据
查看本地缓存
处理数据冲突
查看数据覆盖范围
数据导出
数据清理
```

股票信息页中可以做单只股票的临时查看和拉取保存；管理页负责批量管理和维护。

---

## 20. 多 Session 并行规则

### 20.1 确定要求

```text
每个 Session 可以使用不同模型。
支持多 Session 并行。
同一个账户下的多个 Session 使用同一个账户。
```

### 20.2 数据归属

账户是资产归属，Session 是 LLM 运行归属。

```text
账户 A 有 100000 元。
Session 1 和 Session 2 都使用账户 A。
两个 Session 可以同时运行。
它们的订单都影响账户 A。
```

### 20.3 账本一致性

这不是投资风控，但需要保证账本一致性。

后端需要保证：

```text
余额扣减是原子操作。
持仓更新是原子操作。
订单按服务器接收时间排序。
不能出现现金被重复使用。
每笔订单记录来源 Session 和模型。
```

建议规则：

```text
多 Session 可以同时运行；
同一账户的下单 tool call 进入账户级订单队列；
按照 tool call 到达时间串行撮合；
每笔订单记录来源 Session、模型、run_id、tool_call_id。
```

---

## 21. 前端数据模型（实际实现）

### 21.1 TimelineItem（实际类型，src/types/index.ts）

```ts
interface TimelineItem {
  id: string;
  kind: "user" | "event" | "assistant" | "tool-call" | "tool-result" | "error";
  role: "user" | "assistant" | "tool-call" | "tool-result" | "event" | "error";
  time: string;
  title: string;
  body?: string;
  runId?: string | null;
  toolCallId?: string | null;
  toolName?: string | null;
  status?: string | null;
  argsSummary?: string;
  result?: ToolResultPayload;    // classifyToolResult 生成的结构化结果
  raw?: Record<string, unknown>;
  model?: string | null;
  latencyMs?: number | null;
  tps?: number | null;
  tokenCount?: number | null;
  streaming?: boolean;
  reasoning?: string | null;
  reasoningDurationMs?: number | null;
}
```

### 21.2 ToolResultPayload（实际类型）

```ts
type ToolResultPayload =
  | { kind: "quote"; quote: Record<string, unknown> }
  | { kind: "history"; history: Record<string, unknown>; bars: Record<string, unknown>[] }
  | { kind: "fetch-history"; stats: Record<string, unknown> }
  | { kind: "json"; title: string; data: Record<string, unknown> };
```

### 21.3 SessionTimelineItem（API 返回的原始项，src/api/index.ts）

```ts
interface SessionTimelineItem {
  type: "message" | "tool_call" | "tool_result";
  id: string;
  session_id?: string | null;
  role?: string | null;
  message_type?: string | null;
  content?: string | null;
  reasoning_content?: string | null;
  created_at?: string | null;
  run_id?: string | null;
  tool_call_id?: string | null;
  tool_name?: string | null;
  arguments_json?: string | null;
  result_json?: string | null;
  status?: string | null;
  error?: string | null;
}
```

### 21.4 数据模型说明

- 实际类型为扁平结构，非文档初稿中的联合类型定义
- `ToolResultPayload` 通过 `classifyToolResult()` 函数按工具名分发构造
- 前端的 `Account`/`Session` 等类型定义在 `src/api/index.ts` 和 `src/stores/*.ts` 中，字段比初稿设计更精简
- `Trade` 类型未在前端定义（后端模拟器未实现）

---

## 22. WebSocket 实时更新

交易页需要实时显示：

```text
LLM streaming 输出 (assistant_token)         ← 已实现
可见 reasoning streaming (assistant_reasoning) ← 已实现
Tool call started (tool_call_started)         ← 已实现
Tool call finished (tool_call_finished)       ← 已实现
订单创建 (order_created)                      ← 已实现
成交创建 (trade_created)                      ← 已实现
账户更新 (portfolio_updated)                  ← 已实现
资产曲线更新                                  ← 已实现（通过账户 snapshot 防抖刷新）
错误 (error)                                  ← 已实现
```

实际 WebSocket 事件类型（下划线命名，与后端一致）：

```ts
// 由 app/sessions/runtime.py 推送，前端 tradeStore._connectWs() 消费
type WsEventType =
  | "run_started"
  | "assistant_token"       // LLM 逐 token 流式输出
  | "assistant_reasoning"   // DeepSeek thinking 内容
  | "tool_call_started"
  | "tool_call_finished"
  | "order_created"
  | "trade_created"
  | "portfolio_updated"
  | "assistant_message"     // 最终助手消息（无更多 tool calls 时）
  | "run_finished"
  | "error";
```

注：文档初稿中的点号命名 (`llm.delta`、`tool.started` 等) 与实际下划线命名不一致，以实际代码为准。

`error` 事件会携带 `error` 字段；前端会把该字段写入 `runError`。当 LLM Provider 连接失败时，后端同时把 run 置为 `error`，并让 `POST /api/sessions/{session_id}/run` 返回 `502 Bad Gateway`，避免未处理异常堆栈泄漏到 ASGI 层。

---

## 23. 前端性能要求

长期运行后，一个 Session 可能包含大量：

```text
消息
可见 reasoning
tool calls
搜索结果
K 线图
订单
错误
```

因此需要（实现状态）：

```text
Timeline 虚拟列表        ← @tanstack/react-virtual 已安装但未使用
按 run 分组折叠           ← 未实现
默认加载最近 N 条         ← 当前默认加载全部
历史按需加载             ← 未实现
图表懒渲染              ← 未实现
长 JSON 懒加载           ← 未实现
```

当前实现为全量渲染 `getTimeline()`，通过 CSS `overflow-auto` 滚动。

## 24. 实际组件结构

```text
src/
├─ app/
│  ├─ App.tsx
│  └─ routes.tsx
├─ layouts/
│  ├─ AppShell.tsx
│  └─ TopNavigation.tsx
├─ pages/
│  ├─ trade/
│  │  └─ TradePage.tsx
│  ├─ view/
│  │  └─ ViewPage.tsx
│  ├─ edit/
│  │  └─ EditPage.tsx
│  └─ manage/
│     └─ ManagePage.tsx
├─ features/
│  ├─ trade/
│  │  ├─ AccountSessionSidebar.tsx
│  │  ├─ LLMLinearTimeline.tsx
│  │  ├─ AccountInspectorPanel.tsx
│  │  ├─ ChatInputBox.tsx
│  │  ├─ SessionHeader.tsx
│  │  ├─ MessageBubble.tsx          ← 合并了 ReasoningBlock + AssistantReply
│  │  ├─ ToolCallCard.tsx
│  │  ├─ ToolResultRenderer.tsx     ← 按 kind/toolName 分发
│  │  └─ tool-renderers/
│  │     ├─ TavilySearchRenderer.tsx
│  │     ├─ MarketQuoteRenderer.tsx
│  │     ├─ MarketHistoryChartRenderer.tsx
│  │     ├─ PortfolioStateRenderer.tsx
│  │     └─ OrderResultRenderer.tsx
│  ├─ view/                          ← 目录存在但为空（ViewPage 内联实现）
│  ├─ edit/                          ← 目录存在但为空（EditPage 内联实现）
│  └─ manage/                        ← 目录存在但为空（ManagePage 内联实现）
├─ components/
│  └─ ui/
│     ├─ Button.tsx
│     ├─ Card.tsx
│     ├─ Input.tsx
│     └─ Shared.tsx                  ← Spinner, LoadingDots, Metric, InfoGrid 等
├─ hooks/                            ← 目录为空（0 文件）
├─ stores/
│  ├─ dataStore.ts
│  ├─ marketStore.ts
│  ├─ tradeStore.ts
│  └─ uiStore.ts
├─ api/
│  └─ index.ts
├─ lib/
│  └─ utils.ts
├─ types/
│  └─ index.ts
└─ styles/
   └─ index.css
```

与初稿的主要差异：
- `TimelineItem.tsx` + `ReasoningBlock.tsx` 合并为 `MessageBubble.tsx`
- 新增 `SessionHeader.tsx`（中间栏顶部 Session 信息和快捷按钮）
- 新增 `ToolResultRenderer.tsx`（工具结果分发器）
- `features/{view,edit,manage}/` 实际为空，页面逻辑放在 `pages/` 内联
- 新增 `stores/` 目录（zustand 4 store）
- `providers.tsx` 未创建

## 25. 当前仍需后续确认的问题

### 25.1 基准曲线默认用哪个？

资产曲线默认叠加一层基准曲线。

候选：

```text
沪深300
上证指数
中证500
创业板指
```

建议默认：沪深300。

### 25.2 查看页发送给 LLM 分析股票时，默认模型如何选择？

建议：

```text
选择账号后，默认使用该账号的默认模型；
但弹窗允许用户切换为其他模型。
```

### 25.3 多 Session 并行时，是否允许同时触发同一账户的定时任务？

当前设计允许多 Session 并行。

建议后端保证账户级订单队列串行撮合，前端显示：

```text
该账户当前有 N 个 Session 正在运行。
```

### 25.4 覆盖式重跑是否展示被覆盖历史？

建议：

```text
默认不展示被覆盖历史；
高级筛选中可以查看 archived / superseded 记录。
```

---

## 26. 一句话总结

```text
前端是一个四入口 WebUI：交易、查看、修改、管理。
交易页是三栏 WebChat 工作台，左侧账户与 sessions，中间展示 LLM 线性流程，右侧观察当前账户。
查看页是全局总览和分析中心，默认展示所有账号和 sessions 的数据，并支持账号详情、交易历史、资产曲线、股票信息和时间线控制。
每个 Session 可以使用不同模型，多 Session 可以并行操作同一账户，但每笔订单必须记录来源 Session 和模型。
Tool call 默认折叠，只显示调用了什么工具；Tool result 必须渲染为人类可读内容，例如搜索结果逐行标题 + 域名、价格一行信息、股票历史图表。
```
