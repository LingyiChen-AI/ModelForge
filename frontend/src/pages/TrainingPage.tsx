import { useEffect, useState } from "react";
import { DEFAULT_PAGE_SIZE } from "../constants";
import { Cpu, Play, LineChart, Trash2 } from "lucide-react";
import { listJobsPaged, createJob, deleteJob, listDatasetTree, listModels, getConfig, type TrainingJob, type DatasetNode, type Model } from "../api/client";
import { Button, CascadeSelect, ConfirmDialog, Drawer, EmptyState, Field, Input, Mono, PageHeader, Pagination, Select, StatusBadge, TableShell, Creator, CreatedAt } from "../ui";
import { MetricChips } from "../components/MetricChips";
import { ParamChips } from "../components/ParamChips";
import { toastError } from "../toast";
import { BASE_MODEL_GROUPS } from "../baseModels";
import { useAuth } from "../context/AuthContext";
import { navigate } from "../router";
import { TASK_LABEL, groupByTask } from "../taskGroups";

// Auto job name = compact local timestamp, e.g. 20260614135623 (yyyyMMddHHmmss).
function tsName(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}
function defaultBaseModel(taskType: string): string {
  return BASE_MODEL_GROUPS.find(g => g.tasks.includes(taskType))?.options[0]?.id ?? "prajjwal1/bert-tiny";
}

// Datasets used by a training job (train sets as chips; eval sets as a muted line).
function DatasetCell({ train, evalSets }: { train: string[]; evalSets: string[] }) {
  if (!train?.length && !evalSets?.length) return <span className="text-slate-300">—</span>;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap gap-1">
        {(train ?? []).map(d => (
          <span key={d} className="whitespace-nowrap rounded bg-slate-100 px-1.5 py-0.5 text-[11.5px] text-slate-600">{d}</span>
        ))}
      </div>
      {evalSets?.length > 0 && (
        <div className="text-[11.5px] text-slate-400">评估:{evalSets.join("、")}</div>
      )}
    </div>
  );
}

const LR_OPTIONS = [
  { v: "1e-5", l: "1e-5(更稳)" },
  { v: "2e-5", l: "2e-5" },
  { v: "3e-5", l: "3e-5" },
  { v: "5e-5", l: "5e-5(默认)" },
  { v: "1e-4", l: "1e-4(更快)" },
];
type Hp = { epochs: number; lr: string; batch_size: number; max_length: number };
const defaultHp = (taskType: string): Hp => ({
  epochs: taskType === "embedding" ? 1 : 3, lr: "5e-5", batch_size: 16, max_length: 128,
});

export function TrainingPage() {
  const { can } = useAuth();
  const [jobs, setJobs] = useState<TrainingJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [total, setTotal] = useState(0);
  const [tree, setTree] = useState<DatasetNode[]>([]);
  const [evalTree, setEvalTree] = useState<DatasetNode[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [mlflowUrl, setMlflowUrl] = useState("");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [del, setDel] = useState<TrainingJob | null>(null);
  const [delBusy, setDelBusy] = useState(false);
  const [modelId, setModelId] = useState("");
  const [baseModel, setBaseModel] = useState("");
  const [dvIds, setDvIds] = useState<string[]>([]);     // train set versions (merged)
  const [evalDvIds, setEvalDvIds] = useState<string[]>([]);  // eval set versions (merged)
  const [hp, setHp] = useState<Hp>(defaultHp(""));
  const reload = () => listJobsPaged({ page, page_size: pageSize }).then(res => { setJobs(res.items); setTotal(res.total); });
  const runUrl = (runId: string) => `${mlflowUrl}/#/experiments/0/runs/${runId}`;
  useEffect(() => {
    listDatasetTree("train").then(setTree);
    listDatasetTree("eval").then(setEvalTree);
    listModels().then(setModels);
    getConfig().then(c => setMlflowUrl(c.mlflow_url)).catch(() => {});
  }, []);
  useEffect(() => { setLoading(true); reload().finally(() => setLoading(false)); const t = setInterval(reload, 3000); return () => clearInterval(t); }, [page, pageSize]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const v = params.get("badcase_version");
    if (v) {
      setOpen(true);
      setDvIds([v]);  // preselect the badcase train-set version (user still picks model + eval set)
      window.history.replaceState({}, "", "/training");
    }
  }, []);

  const openDrawer = () => { setModelId(""); setBaseModel(""); setDvIds([]); setEvalDvIds([]); setHp(defaultHp("")); setBusy(false); setOpen(true); };
  const changeModel = (id: string) => {
    setModelId(id);
    const m = models.find(x => String(x.id) === id);
    setBaseModel(m ? defaultBaseModel(m.task_type) : "");
    setDvIds([]); setEvalDvIds([]);
    setHp(defaultHp(m?.task_type ?? ""));  // epochs default depends on task type (embedding=1)
  };

  const selectedModel = models.find(m => String(m.id) === modelId);
  const taskType = selectedModel?.task_type ?? "";
  // base models limited to families that support this model's task type
  const baseGroups = BASE_MODEL_GROUPS.filter(g => g.tasks.includes(taskType));
  // datasets limited to the model's task type
  const toGroups = (nodes: DatasetNode[]) => nodes.filter(d => d.taskType === taskType).map(d => ({
    key: String(d.id), label: d.name, count: d.versions.length,
    items: [...d.versions].sort((a, b) => b.version_no - a.version_no).map(v => ({
      value: String(v.id), label: `V${v.version_no}`, hint: `${v.row_count.toLocaleString()} 行`,
    })),
  }));
  const groups = toGroups(tree);
  const evalGroups = toGroups(evalTree);

  const doDelete = (cascade: boolean) => {
    if (!del) return;
    setDelBusy(true);
    deleteJob(del.id, cascade).then(() => { setDel(null); reload(); })
      .catch(() => toastError("删除失败")).finally(() => setDelBusy(false));
  };
  const submit = () => {
    setBusy(true);
    createJob({
      name: tsName(), model_id: Number(modelId),
      dataset_version_ids: dvIds.map(Number),
      eval_dataset_version_ids: evalDvIds.map(Number),
      base_model: baseModel,
      // embedding recipe only consumes epochs/batch_size; the others also use lr/max_length
      hyperparams: taskType === "embedding"
        ? { epochs: hp.epochs, batch_size: hp.batch_size }
        : { epochs: hp.epochs, lr: Number(hp.lr), batch_size: hp.batch_size, max_length: hp.max_length },
    }).then(() => { setOpen(false); reload(); })
      .catch(() => toastError("提交失败"))
      .finally(() => setBusy(false));
  };

  return (
    <>
      <PageHeader
        title="训练任务"
        subtitle="训练需绑定一个模型(在其下产出版本)。提交后由 worker 执行,完成自动注册。"
        actions={can("training:run") && <Button variant="primary" onClick={openDrawer}><Play size={16} /> 新建训练任务</Button>}
      />

      <TableShell
        loading={loading}
        empty={jobs.length === 0}
        head={<><th className="w-16">#</th><th>模型</th><th>任务名</th><th>数据集</th><th>参数</th><th>状态</th><th className="w-40">进度</th><th>指标</th><th>训练人</th><th className="w-36">训练时间</th><th className="w-12 text-right"></th></>}
      >
        {jobs.length === 0 ? (
          <EmptyState icon={<Cpu size={22} />} title="还没有训练任务" hint="先在「模型」页创建模型,再来这里选模型 + 数据集训练。" />
        ) : jobs.map(j => (
          <tr key={j.id}>
            <td><Mono>{j.id}</Mono></td>
            <td>
              <div className="flex items-center gap-2">
                <span className="font-medium text-slate-800">{j.model_name ?? "—"}</span>
                {j.mlflow_run_id && mlflowUrl && (
                  <a href={runUrl(j.mlflow_run_id)} target="_blank" rel="noreferrer"
                     className="inline-flex items-center gap-0.5 text-[11.5px] font-normal text-brand-600 hover:text-brand-700">
                    <LineChart size={12} /> MLflow
                  </a>
                )}
              </div>
            </td>
            <td><Mono className="text-slate-500">{j.name}</Mono></td>
            <td><DatasetCell train={j.train_datasets} evalSets={j.eval_datasets} /></td>
            <td className="wrap"><ParamChips data={j.hyperparams} /></td>
            <td><StatusBadge status={j.status} error={j.error} /></td>
            <td>
              {j.status === "running" ? (
                <div className="flex items-center gap-2">
                  <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full rounded-full bg-brand-500 transition-all duration-500" style={{ width: `${Math.round((j.progress || 0) * 100)}%` }} />
                  </div>
                  <span className="tnum text-[12px] text-slate-500">{Math.round((j.progress || 0) * 100)}%</span>
                </div>
              ) : j.status === "succeeded" ? (
                <span className="tnum text-[12px] text-slate-400">100%</span>
              ) : <span className="text-slate-300">—</span>}
            </td>
            <td className="wrap"><MetricChips data={j.metrics} /></td>
            <td><Creator name={j.created_by_name} /></td>
            <td><CreatedAt at={j.created_at} /></td>
            <td className="text-right">
              {can("training:run") && (
                <Button size="sm" variant="danger" onClick={() => setDel(j)}><Trash2 size={13} /></Button>
              )}
            </td>
          </tr>
        ))}
      </TableShell>
      <Pagination page={page} pageSize={pageSize} total={total} onPage={setPage} onPageSize={s => { setPageSize(s); setPage(1); }} />

      <ConfirmDialog
        open={del !== null}
        title="删除训练任务"
        message={<>确定删除训练任务 <b className="text-slate-700">{del?.model_name} · {del?.name}</b>?此操作不可恢复。</>}
        cascadeLabel="同时删除 MLflow 中的实验记录,以及该任务产出的模型版本(及其评估/部署)。不勾选则只删除本条训练记录。"
        busy={delBusy}
        onCancel={() => setDel(null)}
        onConfirm={doDelete}
      />

      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title="新建训练任务"
        subtitle="先选模型(决定任务类型),基础模型与数据集随之联动。"
        footer={
          <div className="flex items-center justify-end gap-2">
            <Button variant="subtle" disabled={busy} onClick={() => setOpen(false)}>取消</Button>
            <Button variant="primary" disabled={!modelId || dvIds.length === 0 || evalDvIds.length === 0} loading={busy} onClick={submit}><Play size={16} /> 提交训练</Button>
          </div>
        }
      >
        {models.length === 0 ? (
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-6 text-center text-[13px] text-slate-500">
            还没有模型。请先到
            <button className="mx-1 font-medium text-brand-600 hover:text-brand-700 cursor-pointer" onClick={() => { setOpen(false); navigate("/models"); }}>「模型」页</button>
            创建一个模型,再来训练。
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <Field label="① 模型">
              <Select value={modelId} onChange={e => changeModel(e.target.value)}>
                <option value="">选择模型…</option>
                {groupByTask(models, m => m.task_type, m => m.name).map(g => (
                  <optgroup key={g.task} label={g.label}>
                    {g.items.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
                  </optgroup>
                ))}
              </Select>
            </Field>

            <Field label="② 基础模型 (base_model)">
              <Select value={baseModel} onChange={e => setBaseModel(e.target.value)} disabled={!modelId}>
                {baseGroups.map(g => (
                  <optgroup key={g.group} label={g.group}>
                    {g.options.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
                  </optgroup>
                ))}
              </Select>
            </Field>

            <div>
              <div className="label mb-1.5">
                ③ 训练集版本
                {taskType && <span className="ml-2 font-normal text-slate-400">可多选,多选自动合并;仅显示 {TASK_LABEL[taskType] ?? taskType} 训练集</span>}
              </div>
              <CascadeSelect
                groups={modelId ? groups : []}
                value={dvIds}
                onChange={setDvIds}
                placeholder="选择训练集版本(可多选)"
                searchPlaceholder="搜索数据集 / 版本…"
                emptyHint={modelId ? "没有匹配的训练集,请先到「数据集」上传训练集" : "请先选择模型"}
              />
              {dvIds.length > 1 && <div className="mt-1.5 text-[12px] text-slate-400">已选 {dvIds.length} 个版本,训练时合并为一个训练集</div>}
            </div>

            <div>
              <div className="label mb-1.5">
                ④ 评估集版本
                {taskType && <span className="ml-2 font-normal text-slate-400">可多选,多选自动合并;训练中用于验证,仅显示 {TASK_LABEL[taskType] ?? taskType} 评估集</span>}
              </div>
              <CascadeSelect
                groups={modelId ? evalGroups : []}
                value={evalDvIds}
                onChange={setEvalDvIds}
                placeholder="选择评估集版本(可多选)"
                searchPlaceholder="搜索数据集 / 版本…"
                emptyHint={modelId ? "没有匹配的评估集,请先到「数据集」上传评估集" : "请先选择模型"}
              />
              {evalDvIds.length > 1 && <div className="mt-1.5 text-[12px] text-slate-400">已选 {evalDvIds.length} 个版本,验证时合并为一个评估集</div>}
            </div>

            <div>
              <div className="label mb-1.5">
                ⑤ 训练参数
                <span className="ml-2 font-normal text-slate-400">已填合理默认值,可按需调整</span>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="训练轮数 (epochs)">
                  <Input type="number" min={1} max={50} value={hp.epochs}
                    onChange={e => setHp(h => ({ ...h, epochs: Math.min(50, Math.max(1, Math.floor(Number(e.target.value) || 1))) }))} />
                </Field>
                <Field label="批大小 (batch size)">
                  <Select value={String(hp.batch_size)} onChange={e => setHp(h => ({ ...h, batch_size: Number(e.target.value) }))}>
                    {[4, 8, 16, 32, 64].map(b => <option key={b} value={b}>{b}</option>)}
                  </Select>
                </Field>
                {taskType !== "embedding" && (
                  <Field label="学习率 (learning rate)">
                    <Select value={hp.lr} onChange={e => setHp(h => ({ ...h, lr: e.target.value }))}>
                      {LR_OPTIONS.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
                    </Select>
                  </Field>
                )}
                {taskType !== "embedding" && (
                  <Field label="最大长度 (max length)">
                    <Select value={String(hp.max_length)} onChange={e => setHp(h => ({ ...h, max_length: Number(e.target.value) }))}>
                      {[64, 128, 256, 512].map(m => <option key={m} value={m}>{m}</option>)}
                    </Select>
                  </Field>
                )}
              </div>
            </div>
          </div>
        )}
      </Drawer>
    </>
  );
}
