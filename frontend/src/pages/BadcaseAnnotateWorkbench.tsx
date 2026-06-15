import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Check, Database } from "lucide-react";
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

// one-line summary of a badcase's model input, per task type
function inputSummary(b: Badcase): string {
  const i = b.input ?? {};
  if (b.task_type === "classification") return i.text ?? "";
  if (b.task_type === "pair") return `${i.text_a ?? ""}  ⟷  ${i.text_b ?? ""}`;
  if (b.task_type === "ner") return (i.tokens ?? []).join("");
  if (b.task_type === "embedding") return i.query ?? "";
  return JSON.stringify(i);
}
function annotationSummary(b: Badcase): string {
  const a = b.annotation ?? {};
  if (b.task_type === "classification" || b.task_type === "pair") return String(a.label ?? "");
  if (b.task_type === "ner") return (a.tags ?? []).join(" ");
  if (b.task_type === "embedding") return `pos: ${(a.pos ?? []).join("、")}`;
  return JSON.stringify(a);
}

// Compact, data-dense row: id · input (truncated, with annotation below) · status on the right.
function BadcaseRow({ b }: { b: Badcase }) {
  const summary = inputSummary(b);
  return (
    <div className="flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-slate-50">
      <span className="w-12 shrink-0 font-mono text-[12px] tabular-nums text-slate-400">#{b.id}</span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13.5px] text-slate-800" title={summary}>{summary}</div>
        {b.annotation && (
          <div className="mt-0.5 truncate text-[12px] text-slate-400" title={annotationSummary(b)}>
            标注 · <span className="text-slate-500">{annotationSummary(b)}</span>
          </div>
        )}
      </div>
      <div className="flex shrink-0 flex-wrap items-center justify-end gap-1">
        {b.fixed_by.length > 0
          ? b.fixed_by.map(f => <Badge key={f.version_label} tone="green" dot>V{f.version_label} 已修复</Badge>)
          : <Badge tone="amber" dot>未修复</Badge>}
      </div>
    </div>
  );
}

function BadcaseList({ items }: { items: Badcase[] }) {
  return (
    <div className="max-w-5xl overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="divide-y divide-slate-100">
        {items.map(b => <BadcaseRow key={b.id} b={b} />)}
      </div>
    </div>
  );
}

type Tab = "pending" | "unfixed" | "fixed";

export function BadcaseAnnotateWorkbench({ modelVersionId }: { modelVersionId: number }) {
  const [all, setAll] = useState<Badcase[]>([]);
  const [queue, setQueue] = useState<Badcase[]>([]);   // pending items to annotate this session
  const [sum, setSum] = useState<BadcaseSummary | null>(null);
  const [val, setVal] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [labelOptions, setLabelOptions] = useState<string[]>([]);
  const [tab, setTab] = useState<Tab>("pending");

  const reloadSummary = () =>
    listBadcaseSummary().then(s => setSum(s.find(x => x.model_version_id === modelVersionId) ?? null));

  const loadAll = () =>
    listBadcases({ model_version_id: modelVersionId }).then(rows => {
      setAll(rows);
      setQueue(rows.filter(b => b.status === "reported"));
      return rows;
    });

  useEffect(() => {
    setLoading(true);
    listBadcaseLabels(modelVersionId).then(setLabelOptions).catch(() => setLabelOptions([]));
    Promise.all([loadAll(), reloadSummary()])
      .then(([rows]) => {
        // open the first non-empty tab
        const pending = rows.filter(b => b.status === "reported").length;
        const fixed = rows.filter(b => b.fixed_by.length > 0).length;
        setTab(pending > 0 ? "pending" : fixed > 0 ? "fixed" : "unfixed");
      })
      .finally(() => setLoading(false));
  }, [modelVersionId]); // eslint-disable-line react-hooks/exhaustive-deps

  const unfixed = useMemo(() => all.filter(b => b.status !== "reported" && b.fixed_by.length === 0), [all]);
  const fixed = useMemo(() => all.filter(b => b.fixed_by.length > 0), [all]);

  const current = queue[0] ?? null;
  useEffect(() => { setVal(current?.annotation ?? {}); }, [current]);
  const valid = current ? annotationValid(current.task_type, val) : false;

  const save = () => {
    if (!current) return;
    setBusy(true);
    annotateBadcase(current.id, val)
      .then(updated => {
        toastSuccess("已标注");
        setQueue(q => q.slice(1));
        setAll(a => a.map(b => (b.id === updated.id ? updated : b)));   // -> moves into 未修复
        reloadSummary();
      })
      .catch(() => toastError("标注失败"))
      .finally(() => setBusy(false));
  };

  const build = async () => {
    setBusy(true);
    try {
      const cases = await listBadcases({ model_version_id: modelVersionId, status: "annotated" });
      if (cases.length === 0) { toastError("没有已标注未生成的 badcase"); return; }
      const res = await buildBadcaseDataset(cases.map(c => c.id));
      toastSuccess(`已生成训练集 ${res.dataset_name}`);
      await loadAll(); reloadSummary();
    } catch {
      toastError("生成训练集失败");
    } finally {
      setBusy(false);
    }
  };

  const title = useMemo(
    () => sum ? `${sum.model_name ?? sum.model_version_id} · V${sum.model_version_label ?? "?"}` : "标注工作台",
    [sum],
  );

  const TABS: { key: Tab; label: string; count: number }[] = [
    { key: "pending", label: "未标注", count: queue.length },
    { key: "unfixed", label: "未修复", count: unfixed.length },
    { key: "fixed", label: "已修复", count: fixed.length },
  ];

  return (
    <div>
      <PageHeader
        title={title}
        subtitle={sum ? `${TASK_LABEL[sum.task_type] ?? sum.task_type} · 共 ${sum.reported} 条 badcase` : "标注工作台"}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="subtle" onClick={() => navigate("/badcase")}><ArrowLeft size={16} /> 返回</Button>
            <Button variant="primary" disabled={busy || !(sum && sum.annotated > sum.used)} onClick={build}>
              <Database size={16} /> 生成 badcase- 训练集
            </Button>
          </div>
        }
      />

      {/* category tabs */}
      <div className="mb-4 flex items-center gap-1 border-b border-slate-200">
        {TABS.map(t => (
          <button
            key={t.key} onClick={() => setTab(t.key)}
            className={"-mb-px cursor-pointer border-b-2 px-3.5 py-2 text-[13px] transition " +
              (tab === t.key ? "border-brand-500 font-medium text-brand-700" : "border-transparent text-slate-500 hover:text-slate-700")}
          >
            {t.label}
            <span className={"ml-1.5 rounded-full px-1.5 py-0.5 text-[11px] " +
              (tab === t.key ? "bg-brand-50 text-brand-600" : "bg-slate-100 text-slate-500")}>{t.count}</span>
          </button>
        ))}
      </div>

      {loading ? null : tab === "pending" ? (
        current ? (
          <div className="max-w-3xl rounded-xl border border-slate-200 bg-white p-5">
            <div className="mb-3 text-[13px] text-slate-500">Badcase #{current.id} · 剩余待标注 {queue.length}</div>
            <BadcaseAnnotateForm badcase={current} val={val} onChange={setVal} labelOptions={labelOptions} />
            <div className="mt-5 flex items-center justify-end gap-2">
              <Button variant="subtle" disabled={busy} onClick={() => setQueue(q => [...q.slice(1), q[0]])}>跳过</Button>
              <Button variant="primary" disabled={!valid} loading={busy} onClick={save}><Check size={16} /> 保存并下一条</Button>
            </div>
          </div>
        ) : (
          <EmptyState icon={<Check size={20} />} title="全部标注完成" hint="切换到「未修复」或「已修复」查看处理情况。" />
        )
      ) : tab === "unfixed" ? (
        unfixed.length === 0 ? (
          <EmptyState icon={<Check size={20} />} title="暂无未修复 badcase" hint="标注后生成 badcase- 训练集并训练,即可修复。" />
        ) : (
          <BadcaseList items={unfixed} />
        )
      ) : (
        fixed.length === 0 ? (
          <EmptyState icon={<Check size={20} />} title="暂无已修复 badcase" hint="用已标注数据训练模型后,修复的 badcase 会标上版本。" />
        ) : (
          <BadcaseList items={fixed} />
        )
      )}
    </div>
  );
}
