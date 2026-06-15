import { useEffect, useState } from "react";
import { DEFAULT_PAGE_SIZE } from "../constants";
import { ArrowLeft, Check, SkipForward } from "lucide-react";
import {
  getPromptEval, listPromptEvalItemsPaged, submitPromptEvalVerdict,
  type PromptEvalDetail, type PromptEvalItem,
} from "../api/client";
import { Badge, Button, EmptyState, Pagination } from "../ui";
import { toastError, toastSuccess } from "../toast";
import { navigate } from "../router";

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

  const submit = (b: { winner_arm_id?: number; all_bad?: boolean; is_good?: boolean }) => {
    if (!cur) return;
    setBusy(true);
    submitPromptEvalVerdict(cur.id, b)
      .then(() => { toastSuccess("已评估"); reload(); goNext(); })
      .catch(e => toastError(e?.response?.data?.detail ?? "提交失败"))
      .finally(() => setBusy(false));
  };

  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <Button variant="subtle" size="sm" onClick={() => navigate("/prompt-evals")}><ArrowLeft size={14} /> 返回</Button>
        <div className="text-[15px] font-semibold text-slate-800">{run?.name ?? `评测 #${runId}`} · 盲测评估</div>
      </div>

      <div className="flex gap-4 h-[calc(100vh-190px)] min-h-[480px]">
        <div className="flex w-72 shrink-0 flex-col rounded-xl ring-1 ring-slate-200">
          <div className="flex gap-1 border-b border-slate-100 p-2">
            {BUCKETS.map(b => (
              <button key={b.k} onClick={() => { setBucket(b.k); setPage(1); setCurId(null); }}
                className={`rounded-md px-2 py-1 text-[12px] ${bucket === b.k ? "bg-slate-800 text-white" : "text-slate-500 hover:bg-slate-100"}`}>
                {b.label}
              </button>
            ))}
          </div>
          <div className="flex-1 overflow-auto">
            {loading ? <div className="p-3 text-[12px] text-slate-400">加载中…</div> :
              items.length === 0 ? <div className="p-3 text-[12px] text-slate-400">无数据</div> :
                items.map(i => (
                  <button key={i.id} onClick={() => setCurId(i.id)}
                    className={`block w-full border-b border-slate-50 px-3 py-2 text-left text-[13px] ${i.id === curId ? "bg-brand-50" : "hover:bg-slate-50"}`}>
                    <span className="text-slate-700">#{i.item_index + 1}</span>
                    {i.evaluated_at && <Check size={12} className="ml-2 inline text-emerald-500" />}
                  </button>
                ))}
          </div>
          <div className="border-t border-slate-100 p-2">
            <Pagination page={page} pageSize={pageSize} total={total} onPage={setPage} onPageSize={s => { setPageSize(s); setPage(1); }} />
          </div>
        </div>

        <div className="flex-1 overflow-auto rounded-xl ring-1 ring-slate-200 p-5">
          {!cur ? <EmptyState title="选择左侧一条开始评估" /> : (
            <div className="flex flex-col gap-4">
              <div>
                <div className="label mb-1.5">参数输入</div>
                <div className="rounded-lg bg-slate-50 p-3 text-[13px]">
                  {Object.entries(cur.inputs).map(([k, v]) => (
                    <div key={k}><span className="text-slate-400">{k}:</span> <span className="text-slate-700">{String(v ?? "")}</span></div>
                  ))}
                </div>
              </div>

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
                {cur.evaluated_at && <span className="ml-auto text-[12px] text-slate-400">已评 · {cur.annotated_by_name ?? "?"} · {cur.evaluated_at.slice(0, 19).replace("T", " ")}</span>}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
