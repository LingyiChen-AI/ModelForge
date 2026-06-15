import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Check, Database, ChevronLeft, ChevronRight, UserRound, Clock } from "lucide-react";
import {
  listBadcases, listBadcasesPaged, listBadcaseSummary, annotateBadcase, buildBadcaseDataset, listBadcaseLabels,
  type Badcase, type BadcaseSummary,
} from "../api/client";
import { Badge, Button, PageHeader, EmptyState, Pagination, fmtTime } from "../ui";
import { toastError, toastSuccess } from "../toast";
import { navigate } from "../router";
import { BadcaseAnnotateForm, annotationValid } from "./BadcaseAnnotateForm";

const TASK_LABEL: Record<string, string> = {
  classification: "分类", ner: "序列标注", pair: "句对", embedding: "向量检索",
};

function inputSummary(b: Badcase): string {
  const i = b.input ?? {};
  if (b.task_type === "classification") return i.text ?? "";
  if (b.task_type === "pair") return `${i.text_a ?? ""}  ⟷  ${i.text_b ?? ""}`;
  if (b.task_type === "ner") return (i.tokens ?? []).join("");
  if (b.task_type === "embedding") return i.query ?? "";
  return JSON.stringify(i);
}

type Filter = "pending" | "unfixed" | "fixed" | "all";
function StatusPill({ b }: { b: Badcase }) {
  if (b.fixed_by.length > 0) return <Badge tone="green" dot>已修复</Badge>;
  if (b.status === "reported") return <Badge tone="amber" dot>未标注</Badge>;
  return <Badge tone="gray" dot>已标注</Badge>;
}

export function BadcaseAnnotateWorkbench({ modelVersionId }: { modelVersionId: number }) {
  const [sum, setSum] = useState<BadcaseSummary | null>(null);
  const [filter, setFilter] = useState<Filter>("pending");
  const [list, setList] = useState<Badcase[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [val, setVal] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [labelOptions, setLabelOptions] = useState<string[]>([]);

  const reloadSummary = () =>
    listBadcaseSummary().then(s => setSum(s.find(x => x.model_version_id === modelVersionId) ?? null));

  const fetchList = (f: Filter, p: number, ps: number) =>
    listBadcasesPaged({ model_version_id: modelVersionId, page: p, page_size: ps,
                        ...(f === "all" ? {} : { bucket: f }) });

  // initial load: labels + summary, then pick the first non-empty bucket
  useEffect(() => {
    setLoading(true);
    listBadcaseLabels(modelVersionId).then(setLabelOptions).catch(() => setLabelOptions([]));
    reloadSummary().finally(() => setLoading(false));
  }, [modelVersionId]); // eslint-disable-line react-hooks/exhaustive-deps

  // (re)load the current bucket page whenever filter/page/size change
  useEffect(() => {
    fetchList(filter, page, pageSize).then(res => {
      setList(res.items); setTotal(res.total);
      setSelectedId(prev => (res.items.find(b => b.id === prev) ? prev : res.items[0]?.id ?? null));
    }).catch(() => toastError("加载失败"));
  }, [filter, page, pageSize, modelVersionId]); // eslint-disable-line react-hooks/exhaustive-deps

  const counts = useMemo(() => ({
    pending: sum?.pending ?? 0,
    unfixed: sum ? sum.annotated - sum.fixed : 0,
    fixed: sum?.fixed ?? 0,
    all: sum?.reported ?? 0,
  }), [sum]);

  const selected = list.find(b => b.id === selectedId) ?? null;
  const idxInList = list.findIndex(b => b.id === selectedId);
  useEffect(() => { setVal(selected?.annotation ?? {}); }, [selectedId]); // eslint-disable-line react-hooks/exhaustive-deps

  const valid = selected ? annotationValid(selected.task_type, val) : false;
  const changeFilter = (f: Filter) => { setFilter(f); setPage(1); };

  const save = (advance: boolean) => {
    if (!selected) return;
    const nextId = list[idxInList + 1]?.id ?? null;
    setBusy(true);
    annotateBadcase(selected.id, val)
      .then(async () => {
        toastSuccess("已保存标注");
        const [res] = await Promise.all([fetchList(filter, page, pageSize), reloadSummary()]);
        setList(res.items); setTotal(res.total);
        if (advance) {
          setSelectedId(nextId && res.items.find(b => b.id === nextId) ? nextId : res.items[0]?.id ?? null);
        } else if (!res.items.find(b => b.id === selectedId)) {
          setSelectedId(res.items[0]?.id ?? null);
        }
      })
      .catch(() => toastError("保存失败"))
      .finally(() => setBusy(false));
  };

  const build = async () => {
    setBusy(true);
    try {
      const cases = await listBadcases({ model_version_id: modelVersionId, status: "annotated" });
      if (cases.length === 0) { toastError("没有已标注未生成的 badcase"); return; }
      const res = await buildBadcaseDataset(cases.map(c => c.id));
      toastSuccess(`已生成训练集 ${res.dataset_name}`);
      const [l] = await Promise.all([fetchList(filter, page, pageSize), reloadSummary()]);
      setList(l.items); setTotal(l.total);
    } catch {
      toastError("生成训练集失败");
    } finally {
      setBusy(false);
    }
  };

  const title = sum ? `${sum.model_name ?? sum.model_version_id} · V${sum.model_version_label ?? "?"}` : "数据标注工作台";
  const pct = sum && sum.reported > 0 ? Math.round((sum.annotated / sum.reported) * 100) : 0;
  const TABS: { key: Filter; label: string }[] = [
    { key: "pending", label: "未标注" }, { key: "unfixed", label: "未修复" },
    { key: "fixed", label: "已修复" }, { key: "all", label: "全部" },
  ];

  return (
    <div>
      <PageHeader
        title={title}
        subtitle={sum ? `${TASK_LABEL[sum.task_type] ?? sum.task_type} · 标注进度 ${sum.annotated}/${sum.reported} (${pct}%)` : "数据标注工作台"}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="subtle" onClick={() => navigate("/badcase")}><ArrowLeft size={16} /> 返回</Button>
            <Button variant="primary" disabled={busy || !(sum && sum.annotated > sum.used)} onClick={build}>
              <Database size={16} /> 生成 badcase- 训练集
            </Button>
          </div>
        }
      />

      {sum && (
        <div className="mb-3 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
          <div className="h-full rounded-full bg-brand-500 transition-all duration-500" style={{ width: `${pct}%` }} />
        </div>
      )}

      {loading ? (
        <div className="py-20 text-center text-[13px] text-slate-400">加载中…</div>
      ) : (
        <div className="flex h-[72vh] overflow-hidden rounded-xl border border-slate-200 bg-white">
          {/* ── left: case list ── */}
          <div className="flex w-[320px] shrink-0 flex-col border-r border-slate-200">
            <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-slate-200 p-2">
              {TABS.map(t => (
                <button
                  key={t.key} onClick={() => changeFilter(t.key)}
                  className={"shrink-0 whitespace-nowrap rounded-md px-2.5 py-1.5 text-[12.5px] transition cursor-pointer " +
                    (filter === t.key ? "bg-brand-50 font-medium text-brand-700" : "text-slate-500 hover:bg-slate-50")}
                >
                  {t.label} <span className="text-[11px] opacity-70">{counts[t.key]}</span>
                </button>
              ))}
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto">
              {list.length === 0 ? (
                <div className="py-12 text-center text-[12.5px] text-slate-400">该分类下暂无 badcase</div>
              ) : list.map(b => (
                <button
                  key={b.id} onClick={() => setSelectedId(b.id)}
                  className={"flex w-full items-start gap-2 border-b border-slate-50 px-3 py-2.5 text-left transition cursor-pointer " +
                    (b.id === selectedId ? "bg-brand-50/60" : "hover:bg-slate-50")}
                >
                  <div className="min-w-0 flex-1">
                    <div className="mb-0.5 flex items-center gap-1.5">
                      <span className="font-mono text-[11px] tabular-nums text-slate-400">#{b.id}</span>
                      <StatusPill b={b} />
                    </div>
                    <div className="truncate text-[13px] text-slate-700">{inputSummary(b)}</div>
                  </div>
                </button>
              ))}
            </div>
            <div className="shrink-0 border-t border-slate-100 px-3 py-2">
              <Pagination page={page} pageSize={pageSize} total={total} onPage={setPage} onPageSize={s => { setPageSize(s); setPage(1); }} />
            </div>
          </div>

          {/* ── right: annotation editor ── */}
          <div className="flex min-w-0 flex-1 flex-col">
            {selected ? (
              <>
                <div className="flex shrink-0 items-center justify-between gap-2 border-b border-slate-100 px-5 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-[13px] text-slate-500">Badcase #{selected.id}</span>
                    <StatusPill b={selected} />
                    {selected.fixed_by.map(f => <Badge key={f.version_label} tone="green">V{f.version_label}</Badge>)}
                  </div>
                  <div className="flex shrink-0 items-center gap-1 text-[12px] text-slate-400">
                    <button className="rounded p-1 hover:bg-slate-100 disabled:opacity-30 cursor-pointer" disabled={idxInList <= 0} onClick={() => list[idxInList - 1] && setSelectedId(list[idxInList - 1].id)}><ChevronLeft size={16} /></button>
                    <span className="tabular-nums">{idxInList + 1} / {list.length}</span>
                    <button className="rounded p-1 hover:bg-slate-100 disabled:opacity-30 cursor-pointer" disabled={idxInList >= list.length - 1} onClick={() => list[idxInList + 1] && setSelectedId(list[idxInList + 1].id)}><ChevronRight size={16} /></button>
                  </div>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto p-5">
                  <BadcaseAnnotateForm badcase={selected} val={val} onChange={setVal} labelOptions={labelOptions} />
                  {(selected.annotated_by_name || selected.annotated_at) && (
                    <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-slate-100 pt-3 text-[12px] text-slate-400">
                      {selected.annotated_by_name && <span className="flex items-center gap-1"><UserRound size={13} /> 标注人 {selected.annotated_by_name}</span>}
                      {selected.annotated_at && <span className="flex items-center gap-1"><Clock size={13} /> {fmtTime(selected.annotated_at)}</span>}
                    </div>
                  )}
                </div>
                <div className="flex shrink-0 items-center justify-end gap-2 border-t border-slate-100 px-5 py-3">
                  <Button variant="subtle" disabled={busy || !valid} onClick={() => save(false)}>保存</Button>
                  <Button variant="primary" disabled={busy || !valid} loading={busy} onClick={() => save(true)}>
                    <Check size={16} /> 保存并下一条
                  </Button>
                </div>
              </>
            ) : (
              <EmptyState icon={<Check size={20} />} title="选择左侧一条 badcase 开始标注" hint="未标注、未修复、已修复都可以在这里标注或修改标注。" />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
