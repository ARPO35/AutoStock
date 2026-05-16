# 同步事件展示约束

账户观察栏中的 `portfolio_updated` / `估值更新` 事件，事件后方灰字详情必须显示时间戳。

时间戳取值顺序：

1. 优先使用模拟估值时间 `valuation_point.time`。
2. 若 `valuation_point.time` 缺失，回退到 `clock.effective_time`。
3. 若以上字段均缺失，最后回退到 `generated_at`。

展示目标是让 replay 场景看到模拟事件时间，而不是只看到真实广播时间。
