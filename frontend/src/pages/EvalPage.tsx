import { useEffect, useState } from "react";
import { DEFAULT_PAGE_SIZE } from "../constants";
import { BarChart3, FlaskConical, Trash2 } from "lucide-react";
import { listEvalRunsPaged, createEvalRun, deleteEvalRun, listModelVersions, listVersionOptions, type EvalRun, type ModelVersion, type VersionOption } from "../api/client";
import { Button, ConfirmDialog, Drawer, EmptyState, Field, Mono, PageHeader, Pagination, Select, StatusBadge, TableShell, Creator, CreatedAt } from "../ui";
import { toastError } from "../toast";
import { MetricChips as Metrics } from "../components/MetricChips";
import { useAuth } from "../context/AuthContext";

const TASK_LABEL: Record<string, string> = {
  classification: "分类", ner: "序列标注", pair: "句对", embedding: "向量",
};

export function EvalPage() {
  const { can } = useAuth();
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [total, setTotal] = useState(0);
  const [models, setModels] = useState<ModelVersion[]>([]);
  const [evalVersions, setEvalVersions] = useState<VersionOption[]>([]);
  const [filterDv, setFilterDv] = useState("");   // list / leaderboard filter
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [mvId, setMvId] = useState("");            // drawer: model version
  const [formDv, setFormDv] = useState("");        // drawer: test set version
  const [del, setDel] = useState<EvalRun | null>(null);
  const [delBusy, setDelBusy] = useState(false);
  const reload = () => listEvalRunsPaged({ page, page_size: pageSize, ...(filterDv ? { dataset_version_id: Number(filterDv) } : {}) }).then(res => { setRuns(res.items); setTotal(res.total); });
  useEffect(() => { listModelVersions().then(setModels); listVersionOptions("test").then(setEvalVersions); }, []);
  useEffect(() => { reload().finally(() => setLoading(false)); const t = setInterval(reload, 3000); return () => clearInterval(t); }, [page, pageSize, filterDv]);

  const openDrawer = () => { setMvId(""); setFormDv(""); setBusy(false); setOpen(true); };
  // test set is linked to the chosen model version's task type
  const selectedMv = models.find(m => String(m.id) === mvId);
  const compatVersions = mvId ? evalVersions.filter(v => v.taskType === selectedMv?.task_type) : [];
  const changeMv = (id: string) => { setMvId(id); setFormDv(""); };
  const submit = () => {
    setBusy(true);
    createEvalRun({ model_version_id: Number(mvId), dataset_version_id: Number(formDv) })
      .then(() => { setOpen(false); reload(); })
      .catch(() => toastError("发起测试失败"))
      .finally(() => setBusy(false));
  };
  const doDelete = () => {
    if (!del) return;
    setDelBusy(true);
    deleteEvalRun(del.id).then(() => { setDel(null); reload(); })
      .catch(() => toastError("删除失败")).finally(() => setDelBusy(false));
  };

  return (
    <>
      <PageHeader
        title="模型测试"
        subtitle="在测试集上对模型版本批量推理算指标;按测试集版本过滤即得 Leaderboard。"
        actions={can("eval:run") && <Button variant="primary" onClick={openDrawer}><FlaskConical size={16} /> 发起测试</Button>}
      />

      <div className="mb-4 flex items-center gap-2.5">
        <span className="text-[13px] text-slate-500">筛选</span>
        <Select className="h-9 w-60" value={filterDv} onChange={e => { setFilterDv(e.target.value); setPage(1); }}>
          <option value="">全部测试集版本</option>
          {evalVersions.map(v => <option key={v.id} value={v.id}>{v.label}</option>)}
        </Select>
      </div>

      <TableShell
        loading={loading}
        empty={runs.length === 0}
        head={<><th className="w-14">#</th><th>模型</th><th>测试集</th><th>状态</th><th className="w-36">进度</th><th>指标</th><th>创建者</th><th className="w-36">创建时间</th><th className="w-12 text-right"></th></>}
      >
        {runs.length === 0 ? (
          <EmptyState icon={<BarChart3 size={22} />} title="还没有测试记录" hint="点击右上角「发起测试」选择模型与测试集版本。" />
        ) : runs.map(r => (
          <tr key={r.id}>
            <td><Mono>{r.id}</Mono></td>
            <td className="whitespace-nowrap">
              <span className="font-medium text-slate-800">{r.model_name ?? `#${r.model_version_id}`}</span>
              {r.model_version_label && <span className="ml-1.5 rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11.5px] text-slate-600">V{r.model_version_label}</span>}
            </td>
            <td className="whitespace-nowrap">
              <span className="text-slate-700">{r.dataset_name ?? `#${r.dataset_version_id}`}</span>
              {r.dataset_version_no != null && <span className="ml-1.5 rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11.5px] text-slate-600">V{r.dataset_version_no}</span>}
            </td>
            <td><StatusBadge status={r.status} error={r.error} /></td>
            <td>
              {r.status === "running" ? (
                <div className="flex items-center gap-2">
                  <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full rounded-full bg-brand-500 transition-all duration-500" style={{ width: `${Math.round((r.progress || 0) * 100)}%` }} />
                  </div>
                  <span className="tnum text-[12px] text-slate-500">{Math.round((r.progress || 0) * 100)}%</span>
                </div>
              ) : r.status === "succeeded" ? (
                <span className="tnum text-[12px] text-slate-400">100%</span>
              ) : <span className="text-slate-300">—</span>}
            </td>
            <td><Metrics data={r.results} /></td>
            <td><Creator name={r.created_by_name} /></td>
            <td><CreatedAt at={r.created_at} /></td>
            <td className="text-right">
              {can("eval:run") && <Button size="sm" variant="danger" onClick={() => setDel(r)}><Trash2 size={13} /></Button>}
            </td>
          </tr>
        ))}
      </TableShell>
      <Pagination page={page} pageSize={pageSize} total={total} onPage={setPage} onPageSize={s => { setPageSize(s); setPage(1); }} />

      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title="发起测试"
        subtitle="选择一个模型版本与测试集版本,批量推理并计算指标。"
        footer={
          <div className="flex items-center justify-end gap-2">
            <Button variant="subtle" disabled={busy} onClick={() => setOpen(false)}>取消</Button>
            <Button variant="primary" disabled={!mvId || !formDv} loading={busy} onClick={submit}><FlaskConical size={16} /> 发起测试</Button>
          </div>
        }
      >
        <div className="flex flex-col gap-4">
          <Field label="模型版本">
            <Select value={mvId} onChange={e => changeMv(e.target.value)}>
              <option value="">选择模型版本…</option>
              {models.map(m => <option key={m.id} value={m.id}>{m.name} · V{m.mlflow_version} · {TASK_LABEL[m.task_type] ?? m.task_type}</option>)}
            </Select>
          </Field>
          <Field label="测试集版本">
            <Select value={formDv} onChange={e => setFormDv(e.target.value)} disabled={!mvId}>
              <option value="">{!mvId ? "请先选择模型版本" : (compatVersions.length ? "选择测试集版本…" : "没有匹配该任务类型的测试集")}</option>
              {compatVersions.map(v => <option key={v.id} value={v.id}>{v.label}</option>)}
            </Select>
          </Field>
        </div>
      </Drawer>

      <ConfirmDialog
        open={del !== null}
        title="删除测试记录"
        message={<>确定删除测试记录 <b className="text-slate-700">#{del?.id}</b>?该记录的指标结果将被移除,此操作不可恢复。</>}
        busy={delBusy}
        onCancel={() => setDel(null)}
        onConfirm={doDelete}
      />
    </>
  );
}
