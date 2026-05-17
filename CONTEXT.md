# Domain Context

- Session：一次用户与交易助理的对话容器，绑定模型、提示词角色和可选模拟账户。
- Run：一次 Session 执行全过程，从用户触发开始到完成、失败或取消为止；一次 Run 可能包含多次 Provider Call 和多个 Tool Call。
- Provider Call：Run 内一次向 LLM Provider 发起的模型请求，负责产生 assistant 内容、reasoning 和可能的 tool call 请求。
- Tool Call：Provider Call 要求执行的单个工具调用，包含工具名、JSON 参数、执行结果或错误。
- Simulated Account：用于回放或实盘模拟的账户上下文，Tool Call 可基于它产生订单、成交和资产事件。
- 估值点：账户资产在某一时刻的持仓市值、未实现盈亏、现金和总资产快照。
- 当前时钟视图：资产线只展示不晚于账户当前时钟的点；live 账户使用当前真实时钟，replay 账户使用 replay effective_time。
- 未来估值点：时间晚于账户当前时钟的估值点，回放回拨后仍保留在历史中，但不进入当前时钟视图。
- 收盘锚点：账户时钟跨过交易日 15:00 后生成的固定收盘估值点。
- 持有上次价格：持仓当前缺少行情报价时，沿用该持仓上一次已记录的市值和未实现盈亏。
