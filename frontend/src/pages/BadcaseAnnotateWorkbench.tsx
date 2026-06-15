import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Check, Database, ChevronLeft, ChevronRight } from "lucide-react";
import {
  listBadcases, listBadcaseSummary, annotateBadcase, buildBadcaseDataset, listBadcaseLabels,
  type Badcase, type BadcaseSummary,
} from "../api/client";
import { Badge, Button, PageHeader, EmptyState } from "../ui";
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

type Filter = "all" | "pending" | "unfixed" | "fixed";
const statusOf = (b: Badcase): Filter =>
  b.status === "reported" ? "pending" : b.fixed_by.length > 0 ? "fixed" : "unfixed";

// small status pill shown on each list row + in the editor header
function StatusPill({ b }: { b: Badcase }) {
  const s = statusOf(b);
  if (s === "fixed") return <Badge tone="green" dot>已修复</Badge>;
  if (s === "pending") return <Badge tone="amber" dot>未标注</Badge>;
  return <Badge tone="gray" dot>已标注</Badge>;
}

export function BadcaseAnnotateWorkbench({ modelVersionId }: { modelVersionId: number }) {
  const [all, setAll] = useState<Badcase[]>([]);
  const [sum, setSum] = useState<BadcaseSummary | null>(null);
  const [filter, setFilter] = useState<Filter>("pending");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [val, setVal] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [labelOptions, setLabelOptions] = useState<string[]>([]);

  const reloadSummary = () =>
    listBadcaseSummary().then(s => setSum(s.find(x => x.model_version_id === modelVersionId) ?? null));

  useEffect(() => {
    setLoading(true);
    listBadcaseLabels(modelVersionId).then(setLabelOptions).catch(() => setLabelOptions([]));
    Promise.all([listBadcases({ model_version_id: modelVersionId }), reloadSummary()])
      .then(([rows]) => {
        setAll(rows);
        const pending = rows.filter(b => b.status === "reported");
        setFilter(pending.length ? "pending" : "all");
        setSelectedId((pending[0] ?? rows[0])?.id ?? null);
      })
      .finally(() => setLoading(false));
  }, [modelVersionId]); // eslint-disable-line react-hooks/exhaustive-deps

  const counts = useMemo(() => ({
    all: all.length,
    pending: all.filter(b => statusOf(b) === "pending").length,
    unfixed: all.filter(b => statusOf(b) === "unfixed").length,
    fixed: all.filter(b => statusOf(b) === "fixed").length,
  }), [all]);

  const list = useMemo(
    () => (filter === "all" ? all : all.filter(b => statusOf(b) === filter)),
    [all, filter],
  );
  const selected = all.find(b => b.id === selectedId) ?? null;
  const idxInList = list.findIndex(b => b.id === selectedId);

  // keep a valid selection when the filter/list changes
  useEffect(() => {
    if (!list.find(b => b.id === selectedId)) setSelectedId(list[0]?.id ?? null);
  }, [filter]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setVal(selected?.annotation ?? {}); }, [selectedId]); // eslint-disable-line react-hooks/exhaustive-deps

  const valid = selected ? annotationValid(selected.task_type, val) : false;

  const goto = (i: number) => { if (list[i]) setSelectedId(list[i].id); };

  const save = (advance: boolean) => {
    if (!selected) return;
    setBusy(true);
    annotateBadcase(selected.id, val)
      .then(updated => {
        toastSuccess("已保存标注");
        setAll(a => a.map(b => (b.id === updated.id ? updated : b)));
        reloadSummary();
        if (advance) {
          const next = list[idxInList + 1];
          if (next) setSelectedId(next.id);
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
      const rows = await listBadcases({ model_version_id: modelVersionId });
      setAll(rows); reloadSummary();
    } catch {
      toastError("生成训练集失败");
    } finally {
      setBusy(false);
    }
  };

  const title = sum ? `${sum.model_name ?? sum.model_version_id} · V${sum.model_version_label ?? "?"}` : "数据标注工作台";
  const pct = sum && sum.reported > 0 ? Math.round((sum.annotated / sum.reported) * 100) : 0;

  const TABS: { key: Filter; label: string }[] = [
    { key: "pending", label: "未标注" },
    { key: "unfixed", label: "未修复" },
    { key: "fixed", label: "已修复" },
    { key: "all", label: "全部" },
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

      {/* progress bar */}
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
          <div className="flex w-[300px] shrink-0 flex-col border-r border-slate-200">
            <div className="flex shrink-0 gap-1 border-b border-slate-200 p-2">
              {TABS.map(t => (
                <button
                  key={t.key} onClick={() => setFilter(t.key)}
                  className={"flex-1 rounded-md px-1.5 py-1.5 text-[12px] transition cursor-pointer " +
                    (filter === t.key ? "bg-brand-50 font-medium text-brand-700" : "text-slate-500 hover:bg-slate-50")}
                >
                  {t.label}<span className="ml-1 text-[11px] opacity-70">{counts[t.key]}</span>
                </button>
              ))}
            </div>
            <div className="flex-1 overflow-y-auto">
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
          </div>

          {/* ── right: annotation editor ── */}
          <div className="flex min-w-0 flex-1 flex-col">
            {selected ? (
              <>
                <div className="flex shrink-0 items-center justify-between gap-2 border-b border-slate-100 px-5 py-3">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[13px] text-slate-500">Badcase #{selected.id}</span>
                    <StatusPill b={selected} />
                    {selected.fixed_by.map(f => <Badge key={f.version_label} tone="green">V{f.version_label}</Badge>)}
                  </div>
                  <div className="flex items-center gap-1 text-[12px] text-slate-400">
                    <button className="rounded p-1 hover:bg-slate-100 disabled:opacity-30 cursor-pointer" disabled={idxInList <= 0} onClick={() => goto(idxInList - 1)}><ChevronLeft size={16} /></button>
                    <span className="tabular-nums">{idxInList + 1} / {list.length}</span>
                    <button className="rounded p-1 hover:bg-slate-100 disabled:opacity-30 cursor-pointer" disabled={idxInList >= list.length - 1} onClick={() => goto(idxInList + 1)}><ChevronRight size={16} /></button>
                  </div>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto p-5">
                  <BadcaseAnnotateForm badcase={selected} val={val} onChange={setVal} labelOptions={labelOptions} />
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
