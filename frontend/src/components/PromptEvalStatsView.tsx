import { User, Sparkles } from "lucide-react";
import { Badge } from "../ui";
import type { PromptEvalStats, PromptEvalMetrics } from "../api/client";

// 单组指标(多臂胜率 / 单 prompt 好率 + 对比)
function Metrics({ m, evalType }: { m: PromptEvalMetrics; evalType: string }) {
  if (m.evaluated === 0) return <p className="text-[12.5px] text-slate-400">暂无评估数据。</p>;
  if (evalType === "single_prompt") {
    return (
      <div className="flex flex-col gap-3">
        <div className="rounded-lg ring-1 ring-slate-200 p-3">
          <div className="text-[12px] text-slate-500">好率</div>
          <div className="text-[20px] font-semibold text-slate-800">{Math.round((m.good_rate ?? 0) * 100)}%</div>
          <div className="text-[12px] text-slate-400">好 {m.good ?? 0} · 坏 {m.bad ?? 0} · 已评 {m.evaluated}</div>
        </div>
        {m.comparison && (
          <div className="rounded-lg ring-1 ring-slate-200 p-3">
            <div className="mb-1 text-[12.5px] text-slate-500">对比上一版本:{m.comparison.compare_version_label}</div>
            <div className="text-[12.5px] text-emerald-600">变好率 {Math.round(m.comparison.improved_rate * 100)}%({m.comparison.improved} 条)</div>
            <div className="text-[12.5px] text-red-600">变坏率 {Math.round(m.comparison.regressed_rate * 100)}%({m.comparison.regressed} 条)</div>
            <div className="text-[11.5px] text-slate-400">可对比 {m.comparison.comparable} 条</div>
          </div>
        )}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      {(m.arms ?? []).map(a => (
        <div key={a.arm_id} className="rounded-lg ring-1 ring-slate-200 p-2.5">
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-medium text-slate-800">{a.label}</span>
            {a.arm_id === m.best_arm_id && <Badge tone="green">最优</Badge>}
            <span className="ml-auto text-[12.5px] text-slate-600">胜率 {Math.round(a.win_rate * 100)}% · {a.wins} 胜</span>
          </div>
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-100">
            <div className="h-full bg-brand-500" style={{ width: `${Math.round(a.win_rate * 100)}%` }} />
          </div>
        </div>
      ))}
      <div className="text-[11.5px] text-slate-400">都一样坏 {m.all_bad ?? 0} 条 · 已评 {m.evaluated}</div>
    </div>
  );
}

// 两个指标并列:人工标注 + AI 评估
export function PromptEvalStatsView({ s }: { s: PromptEvalStats }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <div className="rounded-xl ring-1 ring-emerald-100 bg-emerald-50/40 p-4">
        <div className="mb-3 flex items-center gap-1.5 text-[13px] font-semibold text-emerald-700">
          <User size={15} /> 人工标注
        </div>
        <Metrics m={s.human} evalType={s.eval_type} />
      </div>
      <div className="rounded-xl ring-1 ring-violet-100 bg-violet-50/40 p-4">
        <div className="mb-3 flex items-center gap-1.5 text-[13px] font-semibold text-violet-700">
          <Sparkles size={15} /> AI 评估
        </div>
        <Metrics m={s.ai} evalType={s.eval_type} />
      </div>
    </div>
  );
}
