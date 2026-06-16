import { useEffect, useState } from "react";
import { DEFAULT_PAGE_SIZE } from "../constants";
import { ArrowLeft, Check, SkipForward } from "lucide-react";
import {
  getPromptEval, listPromptEvalItemsPaged, submitPromptEvalVerdict, getPromptEvalStats,
  type PromptEvalDetail, type PromptEvalItem, type PromptEvalStats,
} from "../api/client";
import { Badge, Button, EmptyState, Pagination } from "../ui";
import { toastError, toastSuccess } from "../toast";
import { navigate } from "../router";
import { PromptEvalStatsView } from "../components/PromptEvalStatsView";

const LETTERS = ["A", "B", "C", "D", "E", "F"];
const BUCKETS = [{ k: "pending", label: "未评" }, { k: "evaluated", label: "已评" }, { k: "all", label: "全部" }];

export function PromptEvalWorkbench({ runId }: { runId: number }) {
  const [run, setRun] = useState<PromptEvalDetail | null>(null);
  const [bucket, setBucket] = useState("pending");
  const [items, setItems] = useState<PromptEvalItem[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [curId, setCurId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState<"eval" | "stats">("eval");
  const [stats, setStats] = useState<PromptEvalStats | null>(null);

  useEffect(() => { getPromptEval(runId).then(setRun).catch(() => toastError("加载失败")); }, [runId]);
  const reload = () => listPromptEvalItemsPaged(runId, { bucket, page, page_size: pageSize })
    .then(res => { setItems(res.items); setTotal(res.total); if (curId == null && res.items.length) setCurId(res.items[0].id); });
  useEffect(() => { setLoading(true); reload().finally(() => setLoading(false)); }, [runId, bucket, page, pageSize]);

  const cur = items.find(i => i.id === curId) ?? null;
  const single = run?.eval_type === "single_prompt";

  const goNext = () => {
    const idx = items.findIndex(i => i.id === curId);
    const next = items[idx + 1];
    if (next) setCurId(next.id);
  };

  const openStats = () => { getPromptEvalStats(runId).then(setStats).catch(() => toastError("加载统计失败")); setView("stats"); };

  const submit = (b: { winner_arm_id?: number; all_bad?: boolean; is_good?: boolean }) => {
    if (!cur) return;
    setBusy(true);
    submitPromptEvalVerdict(cur.id, b)
      .then(async () => {
        toastSuccess("已评估");
        await reload();
        // 标完最后一条 → 右侧直接展示统计结果
        const st = await getPromptEvalStats(runId).catch(() => null);
        if (st) {
          setStats(st);
          if (st.human.evaluated >= st.total) { setView("stats"); return; }
        }
        goNext();
      })
      .catch(e => toastError(e?.response?.data?.detail ?? "提交失败"))
      .finally(() => setBusy(false));
  };

  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <Button variant="subtle" size="sm" onClick={() => navigate("/eval/prompt")}><ArrowLeft size={14} /> 返回</Button>
        <div className="text-[15px] font-semibold text-slate-800">{run?.name ?? `评测 #${runId}`} · 盲测评估</div>
      </div>

      <div className="flex gap-4 h-[calc(100vh-190px)] min-h-[480px]">
        <div className="flex w-72 shrink-0 flex-col rounded-xl ring-1 ring-slate-200">
          <div className="flex gap-1 border-b border-slate-100 p-2">
            {BUCKETS.map(b => (
              <button key={b.k} onClick={() => { setBucket(b.k); setPage(1); setCurId(null); setView("eval"); }}
                className={`rounded-md px-2 py-1 text-[12px] ${bucket === b.k ? "bg-slate-800 text-white" : "text-slate-500 hover:bg-slate-100"}`}>
                {b.label}
              </button>
            ))}
          </div>
          <div className="flex-1 overflow-auto">
            {loading ? <div className="p-3 text-[12px] text-slate-400">加载中…</div> :
              items.length === 0 ? <div className="p-3 text-[12px] text-slate-400">无数据</div> :
                items.map(i => {
                  const raw = Object.values(i.inputs ?? {}).map(v => String(v ?? "")).join(" ").trim();
                  const preview = raw.length > 10 ? raw.slice(0, 10) + "…" : raw;
                  return (
                    <button key={i.id} onClick={() => { setCurId(i.id); setView("eval"); }} title={raw}
                      className={`block w-full border-b border-slate-50 px-3 py-2 text-left text-[13px] ${i.id === curId && view === "eval" ? "bg-brand-50" : "hover:bg-slate-50"}`}>
                      <span className="text-slate-400">#{i.item_index + 1}</span>
                      {preview && <span className="ml-2 text-slate-700">{preview}</span>}
                      {i.evaluated_at && <Check size={12} className="ml-2 inline text-emerald-500" />}
                      {i.ai_evaluated_at && <span className="ml-1 rounded bg-violet-100 px-1 text-[10px] text-violet-600">AI</span>}
                    </button>
                  );
                })}
          </div>
          <div className="border-t border-slate-100 p-2">
            <Pagination page={page} pageSize={pageSize} total={total} onPage={setPage} onPageSize={s => { setPageSize(s); setPage(1); }} />
          </div>
        </div>

        <div className="flex-1 overflow-auto rounded-xl ring-1 ring-slate-200 p-5">
          {/* 评估 / 统计 切换 */}
          <div className="mb-4 flex gap-1">
            <button onClick={() => setView("eval")}
              className={`rounded-md px-3 py-1 text-[12.5px] ${view === "eval" ? "bg-slate-800 text-white" : "text-slate-500 hover:bg-slate-100"}`}>评估</button>
            <button onClick={openStats}
              className={`rounded-md px-3 py-1 text-[12.5px] ${view === "stats" ? "bg-slate-800 text-white" : "text-slate-500 hover:bg-slate-100"}`}>统计</button>
          </div>

          {view === "stats" ? (
            !stats ? <p className="text-[13px] text-slate-400">加载统计中…</p> : (
              <div className="flex flex-col gap-3">
                <div className="text-[13px] text-slate-500">人工 {stats.human.evaluated} · AI {stats.ai.evaluated} / 共 {stats.total}</div>
                <PromptEvalStatsView s={stats} />
              </div>
            )
          ) : !cur ? <EmptyState title="选择左侧一条开始评估" /> : (
            <div className="flex flex-col gap-4">
              <div>
                <div className="label mb-1.5">参数输入</div>
                <div className="rounded-lg bg-slate-50 p-3 text-[13px]">
                  {Object.entries(cur.inputs).map(([k, v]) => (
                    <div key={k}><span className="text-slate-400">{k}:</span> <span className="text-slate-700">{String(v ?? "")}</span></div>
                  ))}
                </div>
              </div>

              {!single && (
                <div className="-mb-1 text-[11.5px] text-slate-400">
                  盲测:界面只显示 A / B / C(隐藏版本)。本轮内 A / B / C 固定对应同一候选(随机分配、不按版本号),所以「总选 A」= 始终选同一个;各版本表现见「统计」。
                </div>
              )}
              <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${single ? 1 : cur.outputs.length}, minmax(0, 1fr))` }}>
                {cur.outputs.map((o, idx) => (
                  <div key={o.id} className="rounded-xl ring-1 ring-slate-200 p-3">
                    {!single && <Badge tone="blue">{LETTERS[idx]}</Badge>}
                    <pre className="mt-2 whitespace-pre-wrap text-[13px] text-slate-700">{o.status === "error" ? `（调用失败:${o.error}）` : o.output_text}</pre>
                  </div>
                ))}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {single ? (
                  <>
                    <Button variant="primary" disabled={busy} onClick={() => submit({ is_good: true })}>好</Button>
                    <Button variant="danger" disabled={busy} onClick={() => submit({ is_good: false })}>坏</Button>
                  </>
                ) : (
                  <>
                    {cur.outputs.map((o, idx) => (
                      <Button key={o.id} variant="primary" disabled={busy} onClick={() => submit({ winner_arm_id: o.arm_id })}>{LETTERS[idx]} 更好</Button>
                    ))}
                    <Button variant="subtle" disabled={busy} onClick={() => submit({ all_bad: true })}>都一样坏</Button>
                  </>
                )}
                <Button variant="subtle" disabled={busy} onClick={goNext}><SkipForward size={14} /> 跳过</Button>
              </div>
              {cur.evaluated_at && (
                <div className="rounded-xl bg-emerald-50 p-3 ring-1 ring-emerald-100">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-emerald-600 px-1.5 py-0.5 text-[11px] font-medium text-white">人工评估</span>
                    <span className="text-[12.5px] text-slate-600">
                      {single
                        ? (cur.is_good === true ? "判定:好" : cur.is_good === false ? "判定:坏" : "未判定")
                        : (cur.all_bad ? "判定:都一样坏"
                            : cur.winner_arm_id != null
                              ? `选了 ${LETTERS[cur.outputs.findIndex(o => o.arm_id === cur.winner_arm_id)] ?? "?"} 更好`
                              : "未判定")}
                    </span>
                    <span className="ml-auto text-[12px] text-slate-400">{cur.annotated_by_name ?? "?"} · {cur.evaluated_at.slice(0, 19).replace("T", " ")}</span>
                  </div>
                </div>
              )}
              {cur.ai_evaluated_at && (
                <div className="rounded-xl bg-violet-50 p-3 ring-1 ring-violet-100">
                  <div className="mb-1 flex items-center gap-2">
                    <span className="rounded bg-violet-600 px-1.5 py-0.5 text-[11px] font-medium text-white">AI 评估</span>
                    <span className="text-[12.5px] text-slate-600">
                      {single
                        ? (cur.ai_is_good === true ? "判定:好" : cur.ai_is_good === false ? "判定:坏" : "未判定")
                        : (cur.ai_all_bad ? "判定:都一样坏"
                            : cur.ai_winner_arm_id != null
                              ? `选了 ${LETTERS[cur.outputs.findIndex(o => o.arm_id === cur.ai_winner_arm_id)] ?? "?"}`
                              : "未判定")}
                    </span>
                  </div>
                  {cur.ai_reasoning && <pre className="whitespace-pre-wrap text-[12px] text-slate-500">{cur.ai_reasoning}</pre>}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
