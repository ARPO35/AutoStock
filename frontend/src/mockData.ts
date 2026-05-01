import type {
  DecisionLog,
  Holding,
  PortfolioPoint,
  ProviderCard,
  TimelineItem,
  TradeRecord,
  UIAccount,
  UISession
} from "./types";

export const demoAccounts: UIAccount[] = [
  {
    id: "acc-alpha",
    name: "Alpha-量化增强",
    broker: "A股全真（深交）",
    initialCash: 10_000_000,
    cash: 3_462_182.55,
    availableCash: 3_298_414.22,
    frozenCash: 163_768.33,
    marketValue: 9_384_138.90,
    totalAsset: 12_846_320.45,
    todayPnl: 198_320.45,
    todayPnlPct: 1.57,
    totalPnl: 2_846_320.45,
    totalPnlPct: 28.46,
    runningSessions: 2
  },
  {
    id: "acc-beta",
    name: "Beta-价值精选",
    broker: "A股全真（深交）",
    initialCash: 8_000_000,
    cash: 3_175_880.66,
    availableCash: 3_050_120.12,
    frozenCash: 125_760.54,
    marketValue: 5_186_233.54,
    totalAsset: 8_362_114.20,
    todayPnl: -35_120.60,
    todayPnlPct: -0.42,
    totalPnl: 362_114.20,
    totalPnlPct: 4.53,
    runningSessions: 1
  },
  {
    id: "acc-gamma",
    name: "Gamma-趋势动量",
    broker: "A股全真（深交）",
    initialCash: 5_000_000,
    cash: 1_245_680.71,
    availableCash: 1_210_420.30,
    frozenCash: 35_260.41,
    marketValue: 4_879_199.46,
    totalAsset: 6_125_880.17,
    todayPnl: 89_440.17,
    todayPnlPct: 1.48,
    totalPnl: 1_125_880.17,
    totalPnlPct: 22.52,
    runningSessions: 1
  }
];

export const demoSessions: UISession[] = [
  {
    id: "ses-alpha-morning",
    accountId: "acc-alpha",
    name: "半导体板块机会分析",
    providerId: "provider-deepseek",
    providerType: "deepseek",
    providerName: "DeepSeek",
    model: "deepseek-reasoner",
    skillId: "short-term",
    skillName: "短线机会分析",
    status: "running",
    lastRunAt: "10:30:16",
    hasTriggers: true,
    mode: "realtime"
  },
  {
    id: "ses-alpha-close",
    accountId: "acc-alpha",
    name: "尾盘组合再平衡",
    providerId: "provider-openai",
    providerType: "openai_compatible",
    providerName: "OpenAI-Compatible",
    model: "gpt-4.1",
    skillId: "rebalance",
    skillName: "组合再平衡",
    status: "idle",
    lastRunAt: "09:45:12",
    hasTriggers: true,
    mode: "realtime"
  },
  {
    id: "ses-beta-value",
    accountId: "acc-beta",
    name: "高股息防御观察",
    providerId: "provider-openai",
    providerType: "openai_compatible",
    providerName: "OpenAI-Compatible",
    model: "gpt-4o-mini",
    skillId: "value",
    skillName: "价值过滤",
    status: "queued",
    lastRunAt: "09:21:08",
    hasTriggers: false,
    mode: "replay"
  },
  {
    id: "ses-gamma-momentum",
    accountId: "acc-gamma",
    name: "动量突破巡检",
    providerId: "provider-deepseek",
    providerType: "deepseek",
    providerName: "DeepSeek",
    model: "deepseek-chat",
    skillId: "momentum",
    skillName: "趋势交易",
    status: "error",
    lastRunAt: "09:12:40",
    hasTriggers: true,
    mode: "realtime"
  }
];

export const demoPortfolio: PortfolioPoint[] = [
  { label: "05-01", total: 10.0, cash: 3.8, market: 6.2, benchmark: 10.0 },
  { label: "05-03", total: 10.4, cash: 3.7, market: 6.7, benchmark: 10.1 },
  { label: "05-05", total: 10.9, cash: 3.6, market: 7.3, benchmark: 10.2 },
  { label: "05-07", total: 11.2, cash: 3.3, market: 7.9, benchmark: 10.0 },
  { label: "05-09", total: 11.7, cash: 3.4, market: 8.3, benchmark: 10.3 },
  { label: "05-11", total: 12.1, cash: 3.5, market: 8.6, benchmark: 10.4 },
  { label: "05-13", total: 12.0, cash: 3.4, market: 8.6, benchmark: 10.2 },
  { label: "05-15", total: 12.5, cash: 3.5, market: 9.0, benchmark: 10.6 },
  { label: "05-16", total: 12.85, cash: 3.46, market: 9.38, benchmark: 10.7 }
];

export const demoHoldings: Holding[] = [
  {
    symbol: "600519",
    name: "贵州茅台",
    quantity: 100,
    sellable: 100,
    cost: 1650.12,
    price: 1680.50,
    marketValue: 168_050,
    pnl: 3_038,
    pnlPct: 1.84,
    todayPct: 0.74,
    sourceSession: "尾盘组合再平衡",
    latestReason: "资金回流白酒龙头，低波动仓位用于压低组合回撤。",
    sparkline: [10, 12, 11, 14, 13, 15, 17]
  },
  {
    symbol: "688256",
    name: "寒武纪-U",
    quantity: 300,
    sellable: 300,
    cost: 310.35,
    price: 342.88,
    marketValue: 102_864,
    pnl: 9_759,
    pnlPct: 10.48,
    todayPct: 5.50,
    sourceSession: "半导体板块机会分析",
    latestReason: "国产算力链成交放大，公告与行业新闻共振。",
    sparkline: [8, 9, 11, 10, 14, 16, 19]
  },
  {
    symbol: "300750",
    name: "宁德时代",
    quantity: 200,
    sellable: 150,
    cost: 201.35,
    price: 210.83,
    marketValue: 42_166,
    pnl: 1_896,
    pnlPct: 4.71,
    todayPct: 1.42,
    sourceSession: "动量突破巡检",
    latestReason: "新能源链修复，量能未衰减，继续观察。",
    sparkline: [12, 11, 13, 15, 16, 15, 18]
  }
];

export const demoTrades: TradeRecord[] = [
  {
    id: "trd-001",
    time: "10:31:42",
    accountId: "acc-alpha",
    sessionId: "ses-alpha-morning",
    model: "deepseek-reasoner",
    symbol: "688256",
    name: "寒武纪-U",
    side: "buy",
    quantity: 100,
    price: 342.88,
    amount: 34_288,
    fee: 5,
    tax: 0,
    status: "已成交",
    toolCallId: "call-order-001"
  },
  {
    id: "trd-002",
    time: "10:22:18",
    accountId: "acc-gamma",
    sessionId: "ses-gamma-momentum",
    model: "deepseek-chat",
    symbol: "300750",
    name: "宁德时代",
    side: "buy",
    quantity: 200,
    price: 186.35,
    amount: 37_270,
    fee: 5,
    tax: 0,
    status: "已成交",
    toolCallId: "call-order-002"
  },
  {
    id: "trd-003",
    time: "09:57:04",
    accountId: "acc-beta",
    sessionId: "ses-beta-value",
    model: "gpt-4o-mini",
    symbol: "601318",
    name: "中国平安",
    side: "sell",
    quantity: 500,
    price: 48.31,
    amount: 24_155,
    fee: 5,
    tax: 24.16,
    status: "已成交",
    toolCallId: "call-order-003"
  }
];

export const demoTimeline: TimelineItem[] = [
  {
    id: "tl-user-1",
    kind: "user",
    time: "10:30:12",
    title: "用户",
    body: "请分析半导体板块今天的行情，并筛选出短线前 5 的个股。",
    runId: "run-20240516-001"
  },
  {
    id: "tl-event-1",
    kind: "event",
    time: "10:30:13",
    title: "事件",
    body: "已触发用户请求，开始分析半导体板块行情。",
    runId: "run-20240516-001"
  },
  {
    id: "tl-reasoning-1",
    kind: "reasoning",
    time: "10:30:13",
    title: "可见推理",
    body: "用户需要板块级行情和个股筛选。先获取板块报价，再结合新闻与成分股涨跌幅做交叉验证，最后输出可执行观察名单。",
    runId: "run-20240516-001"
  },
  {
    id: "tl-tool-call-1",
    kind: "tool-call",
    time: "10:30:14",
    title: "Tool Call",
    toolName: "market.quote",
    argsSummary: "半导体板块 / 日内行情",
    status: "finished",
    durationMs: 842,
    runId: "run-20240516-001",
    raw: { symbol: "semiconductor", interval: "intraday" }
  },
  {
    id: "tl-tool-call-2",
    kind: "tool-call",
    time: "10:30:14",
    title: "Tool Call",
    toolName: "tavily.search",
    argsSummary: "半导体 今日 公告 资金流",
    status: "finished",
    durationMs: 1240,
    runId: "run-20240516-001",
    raw: { query: "半导体 今日 公告 资金流", max_results: 5 }
  },
  {
    id: "tl-result-quote",
    kind: "tool-result",
    time: "10:30:14",
    title: "工具结果：行情快照",
    toolName: "market.quote",
    result: {
      kind: "quote",
      quote: {
        symbol: "BK1036",
        name: "半导体",
        price: 786.32,
        change: 21.46,
        changePct: 2.81,
        open: 762.10,
        high: 790.44,
        low: 758.02,
        amountText: "786.32亿"
      }
    },
    raw: { source: "market.quote", snapshot: true }
  },
  {
    id: "tl-result-search",
    kind: "tool-result",
    time: "10:30:15",
    title: "工具结果：搜索摘要",
    toolName: "tavily.search",
    result: {
      kind: "search",
      query: "半导体 今日 公告 资金流",
      items: [
        {
          title: "半导体设备板块午后拉升，国产算力链成交放大",
          domain: "finance.eastmoney.com",
          summary: "半导体设备和先进封装方向成交额明显放大，多只个股刷新日内高点。",
          url: "https://finance.eastmoney.com/a/example-1.html",
          publishedAt: "2024-05-16 10:12",
          score: 0.92
        },
        {
          title: "多家公司披露订单进展，晶圆厂扩产节奏延续",
          domain: "cninfo.com.cn",
          summary: "公告显示部分设备与材料公司获得新增订单，交付周期覆盖未来两个季度。",
          url: "https://www.cninfo.com.cn/new/disclosure/example-2",
          publishedAt: "2024-05-16 09:50",
          score: 0.88
        },
        {
          title: "券商称芯片产业链景气度出现边际修复",
          domain: "research.stock.example.com",
          summary: "机构报告认为库存周期接近底部，算力需求拉动先进制程和封装环节。",
          url: "https://research.stock.example.com/report/semiconductor",
          publishedAt: "2024-05-16 08:45",
          score: 0.81
        }
      ]
    }
  },
  {
    id: "tl-result-history",
    kind: "tool-result",
    time: "10:30:15",
    title: "工具结果：成分股行情",
    toolName: "market.history",
    result: {
      kind: "history",
      history: {
        symbol: "688256",
        name: "寒武纪-U",
        period: "分钟线",
        adjust: "不复权",
        candles: [330, 334, 332, 338, 340, 337, 343],
        volumes: [12, 18, 15, 22, 25, 19, 31]
      }
    }
  },
  {
    id: "tl-order-1",
    kind: "order",
    time: "10:31:42",
    title: "下单结果",
    toolName: "order.buy",
    result: {
      kind: "order",
      order: {
        status: "买入成功",
        symbol: "688256",
        name: "寒武纪-U",
        quantity: 100,
        orderPrice: 342.90,
        filledPrice: 342.88,
        fee: 5,
        sourceSession: "半导体板块机会分析",
        sourceModel: "deepseek-reasoner"
      }
    },
    raw: { order_id: "ORD-20240516-001", status: "filled" }
  },
  {
    id: "tl-assistant-1",
    kind: "assistant",
    time: "10:31:50",
    title: "助手",
    body: "半导体板块今日上涨 2.81%，成交额 786.32 亿元。短线候选为寒武纪-U、芯朋微、中微公司、景旺电子、瑞芯微；已按账户级队列买入寒武纪-U 100 股，后续观察成交量是否继续放大。",
    runId: "run-20240516-001"
  }
];

export const demoProviders: ProviderCard[] = [
  {
    id: "provider-openai",
    name: "OpenAI-Compatible",
    type: "OpenAI-Compatible",
    endpoint: "https://api.openai.com/v1",
    modelCount: 6,
    status: "已连接",
    updatedAt: "2024-05-16 10:35:12",
    supportsReasoning: false
  },
  {
    id: "provider-deepseek",
    name: "DeepSeek",
    type: "DeepSeek",
    endpoint: "https://api.deepseek.com",
    modelCount: 4,
    status: "已连接",
    updatedAt: "2024-05-16 10:32:18",
    supportsReasoning: true
  }
];

export const demoDecisions: DecisionLog[] = [
  {
    time: "10:32:15",
    account: "Alpha-量化增强",
    session: "半导体板块机会分析",
    model: "deepseek-reasoner",
    trigger: "用户消息",
    toolCalls: 5,
    action: "买入 688256",
    cost: "¥0.031",
    result: "已成交"
  },
  {
    time: "10:28:42",
    account: "Gamma-趋势动量",
    session: "动量突破巡检",
    model: "deepseek-chat",
    trigger: "盘中检查",
    toolCalls: 4,
    action: "观察 300750",
    cost: "¥0.018",
    result: "已记录"
  },
  {
    time: "10:21:07",
    account: "Beta-价值精选",
    session: "高股息防御观察",
    model: "gpt-4o-mini",
    trigger: "定时事件",
    toolCalls: 3,
    action: "卖出 601318",
    cost: "¥0.012",
    result: "已成交"
  }
];
