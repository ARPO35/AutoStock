import { formatValue } from "@/lib/utils";

export function OrderResultRenderer({ data }: { data: Record<string, unknown> }) {
  const direction = formatValue(data.direction ?? data.side ?? data["方向"]);
  const symbol = formatValue(data.symbol ?? data["股票代码"]);
  const name = formatValue(data.name ?? data.stock_name ?? data["股票名称"]);
  const quantity = formatValue(data.quantity ?? data.qty ?? data["数量"]);
  const orderPrice = formatValue(data.order_price ?? data.price ?? data["委托价"]);
  const tradePrice = formatValue(data.trade_price ?? data.filled_price ?? data.price ?? data["成交价"]);
  const turnover = formatValue(data.turnover ?? data.amount ?? data["成交额"]);
  const fee = formatValue(data.fee ?? data.total_fee ?? data.commission ?? data["手续费"]);
  const netAmount = formatValue(data.total_cost ?? data.total_proceeds ?? data["总成本"] ?? data["到账金额"]);
  const status = formatValue(data.status ?? data.order_status ?? data["状态"]);
  const sourceSession = formatValue(data.session_id ?? data.source_session ?? data["来源Session"]);
  const sourceModel = formatValue(data.model ?? data.source_model ?? data["来源模型"]);
  const netAmountLabel = data.total_proceeds != null || data["到账金额"] != null ? "到账金额" : "总成本";
  const stockLabel = name !== "--" ? `${name}（${symbol}）` : symbol;

  return (
    <div className="mt-2 p-3 border border-hairline rounded-lg bg-surface-canvas/40">
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <div>
          <span className="block text-text-muted text-xs">方向</span>
          <strong className="text-text-on-dark">{direction}</strong>
        </div>
        <div>
          <span className="block text-text-muted text-xs">股票</span>
          <strong className="text-text-on-dark">
            {stockLabel}
          </strong>
        </div>
        <div>
          <span className="block text-text-muted text-xs">数量</span>
          <strong className="text-text-on-dark">{quantity}</strong>
        </div>
        <div>
          <span className="block text-text-muted text-xs">委托价</span>
          <strong className="text-text-on-dark">{orderPrice}</strong>
        </div>
        <div>
          <span className="block text-text-muted text-xs">成交价</span>
          <strong className="text-text-on-dark">{tradePrice}</strong>
        </div>
        <div>
          <span className="block text-text-muted text-xs">手续费</span>
          <strong className="text-text-on-dark">{fee}</strong>
        </div>
        <div>
          <span className="block text-text-muted text-xs">成交额</span>
          <strong className="text-text-on-dark">{turnover}</strong>
        </div>
        <div>
          <span className="block text-text-muted text-xs">{netAmountLabel}</span>
          <strong className="text-text-on-dark">{netAmount}</strong>
        </div>
        <div>
          <span className="block text-text-muted text-xs">状态</span>
          <strong className="text-text-on-dark">{status}</strong>
        </div>
        <div>
          <span className="block text-text-muted text-xs">来源Session</span>
          <strong className="text-text-on-dark truncate">{sourceSession}</strong>
        </div>
      </div>
      <div className="mt-2">
        <span className="block text-text-muted text-xs">来源模型</span>
        <strong className="text-text-on-dark block truncate">{sourceModel}</strong>
      </div>
    </div>
  );
}
