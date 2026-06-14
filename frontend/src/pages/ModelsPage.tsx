import { useEffect, useState } from "react";
import { Boxes, Plus, Trash2 } from "lucide-react";
import { listModels, createModel, deleteModel, setModelStage, type Model } from "../api/client";
import { Badge, Button, ConfirmDialog, Drawer, EmptyState, Field, Input, Select, PageHeader, TableShell, Creator, CreatedAt } from "../ui";
import { toastError } from "../toast";
import { useAuth } from "../context/AuthContext";

const TASK_TONE: Record<string, "blue" | "violet" | "cyan" | "amber"> = {
  classification: "blue", ner: "violet", pair: "cyan", embedding: "amber",
};
const STAGE: Record<string, { label: string; tone: "gray" | "amber" | "green" }> = {
  none: { label: "未发布", tone: "gray" }, staging: { label: "预发布", tone: "amber" },
  prod: { label: "生产", tone: "green" }, production: { label: "生产", tone: "green" },
  archived: { label: "已归档", tone: "gray" },
};

function Metrics({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data || {});
  if (!entries.length) return <span className="text-slate-300">—</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {entries.slice(0, 5).map(([k, v]) => (
        <span key={k} className="rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[11.5px] text-slate-600">
          {k}=<span className="text-slate-900">{typeof v === "number" ? (Number.isInteger(v) ? v : v.toFixed(3)) : String(v)}</span>
        </span>
      ))}
    </div>
  );
}

export function ModelsPage() {
  const { can } = useAuth();
  const [items, setItems] = useState<Model[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [del, setDel] = useState<Model | null>(null);
  const [delBusy, setDelBusy] = useState(false);
  const [f, setF] = useState({ name: "", task_type: "classification", description: "" });
  const reload = () => listModels().then(setItems);
  useEffect(() => { reload().finally(() => setLoading(false)); }, []);

  const openDrawer = () => { setF({ name: "", task_type: "classification", description: "" }); setBusy(false); setOpen(true); };
  const create = () => {
    setBusy(true);
    createModel(f).then(() => { setOpen(false); reload(); })
      .catch(err => toastError(err?.response?.data?.detail ?? "创建失败(模型名可能已存在)"))
      .finally(() => setBusy(false));
  };
  const changeStage = (vid: number, stage: string) =>
    setModelStage(vid, stage).then(reload).catch(() => toastError("修改失败(需要 model:write 权限)"));
  const doDelete = (cascade: boolean) => {
    if (!del) return;
    setDelBusy(true);
    deleteModel(del.id, cascade).then(() => { setDel(null); reload(); })
      .catch(() => toastError("删除失败")).finally(() => setDelBusy(false));
  };

  return (
    <>
      <PageHeader
        title="模型"
        subtitle="模型是用户命名的容器,每次训练在其下新增一个版本。阶段作用于最新版本(未发布 / 预发布 / 生产 / 已归档)。"
        actions={can("model:write") && <Button variant="primary" onClick={openDrawer}><Plus size={16} /> 新建模型</Button>}
      />

      <TableShell
        loading={loading}
        empty={items.length === 0}
        head={<><th>模型</th><th>任务</th><th>最新版本</th><th>训练指标</th><th className="w-28">阶段</th><th className="w-16">版本数</th><th>创建者</th><th className="w-36">创建时间</th><th className="w-12 text-right"></th></>}
      >
        {items.length === 0 ? (
          <EmptyState icon={<Boxes size={22} />} title="还没有模型" hint="先「新建模型」(命名 + 任务类型),再到「训练」里选它训练出版本。" />
        ) : items.map(m => (
          <tr key={m.id}>
            <td>
              <div className="whitespace-nowrap font-medium text-slate-800">{m.name}</div>
              {m.description && <div className="mt-0.5 max-w-[200px] truncate text-[12px] text-slate-400">{m.description}</div>}
            </td>
            <td><Badge tone={TASK_TONE[m.task_type] ?? "gray"}>{m.task_type}</Badge></td>
            <td>{m.latest_version ? <span className="rounded-md bg-slate-100 px-2 py-0.5 font-mono text-[12.5px] font-medium text-slate-700">V{m.latest_version}</span> : <span className="text-slate-300">—</span>}</td>
            <td><Metrics data={m.latest_metrics} /></td>
            <td>
              {m.latest_version_id == null ? (
                <span className="text-slate-300">—</span>
              ) : can("model:write") ? (
                <Select className="h-8 w-24 text-[13px]" value={m.latest_stage ?? "none"} onChange={e => changeStage(m.latest_version_id!, e.target.value)}>
                  <option value="none">未发布</option><option value="staging">预发布</option>
                  <option value="prod">生产</option><option value="archived">已归档</option>
                </Select>
              ) : (
                <Badge tone={STAGE[m.latest_stage ?? "none"]?.tone ?? "gray"} dot>{STAGE[m.latest_stage ?? "none"]?.label ?? m.latest_stage}</Badge>
              )}
            </td>
            <td className="tnum text-slate-600">{m.version_count}</td>
            <td><Creator name={m.created_by_name} /></td>
            <td><CreatedAt at={m.created_at} /></td>
            <td className="text-right">
              {can("model:write") && <Button size="sm" variant="danger" onClick={() => setDel(m)}><Trash2 size={13} /></Button>}
            </td>
          </tr>
        ))}
      </TableShell>

      <ConfirmDialog
        open={del !== null}
        title="删除模型"
        message={<>确定删除模型 <b className="text-slate-700">{del?.name}</b>(及其 {del?.version_count ?? 0} 个版本)?此操作不可恢复。</>}
        cascadeLabel="同时删除 MLflow 中注册的模型(所有版本)及其评估/部署。不勾选则只删除本系统记录。"
        busy={delBusy}
        onCancel={() => setDel(null)}
        onConfirm={doDelete}
      />

      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title="新建模型"
        subtitle="先命名一个模型容器并选定任务类型,随后在「训练」里把它训练成具体版本。"
        footer={
          <div className="flex items-center justify-end gap-2">
            <Button variant="subtle" disabled={busy} onClick={() => setOpen(false)}>取消</Button>
            <Button variant="primary" disabled={!f.name} loading={busy} onClick={create}><Plus size={16} /> 创建</Button>
          </div>
        }
      >
        <div className="flex flex-col gap-4">
          <Field label="模型名称"><Input placeholder="如 客服意图分类" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="任务类型">
            <Select value={f.task_type} onChange={e => setF({ ...f, task_type: e.target.value })}>
              <option value="classification">分类</option><option value="ner">序列标注</option>
              <option value="pair">句对</option><option value="embedding">向量</option>
            </Select>
          </Field>
          <Field label="描述(可选)"><Input placeholder="用途说明" value={f.description} onChange={e => setF({ ...f, description: e.target.value })} /></Field>
        </div>
      </Drawer>
    </>
  );
}
