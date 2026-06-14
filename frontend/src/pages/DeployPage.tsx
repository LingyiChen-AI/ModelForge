import { useEffect, useState } from "react";
import { Rocket, Square, Code2, Copy, Check, Play, Trash2 } from "lucide-react";
import { listDeployments, createDeployment, stopDeployment, startDeployment, deleteDeployment, listModelVersions, type Deployment, type ModelVersion } from "../api/client";
import { Button, ConfirmDialog, Drawer, EmptyState, Field, Mono, PageHeader, Select, StatusBadge, TableShell, Creator, CreatedAt, Badge } from "../ui";
import { toastError } from "../toast";
import { buildApiDoc, type ApiDoc } from "../apiDocs";
import { useAuth } from "../context/AuthContext";

function CopyBtn({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1500); }}
      className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12px] text-slate-300 hover:bg-white/10 hover:text-white cursor-pointer"
    >
      {done ? <Check size={13} /> : <Copy size={13} />} {done ? "已复制" : "复制"}
    </button>
  );
}

function CodeBlock({ code }: { code: string }) {
  return (
    <div className="relative rounded-lg bg-slate-900 p-3">
      <div className="absolute right-1.5 top-1.5"><CopyBtn text={code} /></div>
      <pre className="overflow-x-auto whitespace-pre-wrap break-all pr-16 font-mono text-[12px] leading-relaxed text-slate-100">{code}</pre>
    </div>
  );
}

export function DeployPage() {
  const { can } = useAuth();
  const [items, setItems] = useState<Deployment[]>([]);
  const [loading, setLoading] = useState(true);
  const [models, setModels] = useState<ModelVersion[]>([]);
  const [open, setOpen] = useState(false);
  const [mvId, setMvId] = useState("");
  const [busy, setBusy] = useState(false);          // drawer deploy
  const [busyId, setBusyId] = useState<number | null>(null);  // per-row start/stop
  const [del, setDel] = useState<Deployment | null>(null);
  const [delBusy, setDelBusy] = useState(false);
  const [apiDoc, setApiDoc] = useState<ApiDoc | null>(null);
  const reload = () => listDeployments().then(setItems);
  useEffect(() => { listModelVersions().then(setModels); }, []);
  useEffect(() => { reload().finally(() => setLoading(false)); const t = setInterval(reload, 3000); return () => clearInterval(t); }, []);

  const openDrawer = () => { setMvId(""); setBusy(false); setOpen(true); };
  const submit = () => {
    setBusy(true);
    createDeployment(Number(mvId))
      .then(() => { setOpen(false); reload(); })
      .catch(err => toastError(err?.response?.data?.detail ?? "部署失败"))
      .finally(() => setBusy(false));
  };
  const act = (id: number, fn: (id: number) => Promise<unknown>) => {
    setBusyId(id);
    fn(id).then(reload).finally(() => setBusyId(null));
  };
  const doDelete = () => {
    if (!del) return;
    setDelBusy(true);
    deleteDeployment(del.id).then(() => { setDel(null); reload(); })
      .catch(() => toastError("删除失败")).finally(() => setDelBusy(false));
  };
  // a model version can only be deployed once — hide versions that already have a deployment
  const deployedIds = new Set(items.map(d => d.model_version_id));
  const available = models.filter(m => !deployedIds.has(m.id));
  const openApi = (d: Deployment) => {
    const m = models.find(x => x.id === d.model_version_id);
    setApiDoc(buildApiDoc(m?.task_type ?? "classification", d.model_version_id, d.endpoint));
  };

  return (
    <>
      <PageHeader
        title="部署"
        subtitle="把模型版本加载到 model-server,对外提供在线推理。列表每 3 秒刷新。"
        actions={can("deploy:write") && <Button variant="primary" onClick={openDrawer}><Rocket size={16} /> 新建部署</Button>}
      />

      <TableShell
        loading={loading}
        empty={items.length === 0}
        head={<><th className="w-14">#</th><th>模型</th><th>状态</th><th>endpoint</th><th>创建者</th><th className="w-36">创建时间</th><th className="w-48"></th></>}
      >
        {items.length === 0 ? (
          <EmptyState icon={<Rocket size={22} />} title="还没有部署" hint="选择一个模型版本一键部署为在线服务。" />
        ) : items.map(d => {
          const m = models.find(x => x.id === d.model_version_id);
          return (
            <tr key={d.id}>
              <td><Mono>{d.id}</Mono></td>
              <td>
                <div className="flex items-center gap-2">
                  <span className="font-medium text-slate-800">{m?.name ?? `#${d.model_version_id}`}</span>
                  {m?.mlflow_version && <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11.5px] text-slate-600">V{m.mlflow_version}</span>}
                </div>
              </td>
              <td><StatusBadge status={d.status} error={d.error} /></td>
              <td><Mono>{d.endpoint || "—"}</Mono></td>
              <td><Creator name={d.created_by_name} /></td>
              <td><CreatedAt at={d.created_at} /></td>
              <td className="text-right">
                <div className="flex items-center justify-end gap-2">
                  {d.status === "running" && (
                    <Button size="sm" onClick={() => openApi(d)}><Code2 size={13} /> API 详情</Button>
                  )}
                  {d.status === "running" && can("deploy:write") && (
                    <Button size="sm" variant="danger" loading={busyId === d.id} onClick={() => act(d.id, stopDeployment)}><Square size={13} /> 停止</Button>
                  )}
                  {d.status !== "running" && can("deploy:write") && (
                    <Button size="sm" variant="primary" loading={busyId === d.id} onClick={() => act(d.id, startDeployment)}><Play size={13} /> 启动</Button>
                  )}
                  {can("deploy:write") && (
                    <Button size="sm" variant="danger" onClick={() => setDel(d)}><Trash2 size={13} /></Button>
                  )}
                </div>
              </td>
            </tr>
          );
        })}
      </TableShell>

      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title="新建部署"
        subtitle="选择一个模型版本,加载到 model-server 提供在线推理。"
        footer={
          <div className="flex items-center justify-end gap-2">
            <Button variant="subtle" disabled={busy} onClick={() => setOpen(false)}>取消</Button>
            <Button variant="primary" disabled={!mvId} loading={busy} onClick={submit}><Rocket size={16} /> {busy ? "部署中…" : "部署"}</Button>
          </div>
        }
      >
        <Field label="模型版本">
          <Select value={mvId} onChange={e => setMvId(e.target.value)} disabled={available.length === 0}>
            <option value="">{available.length === 0 ? "所有模型版本均已部署" : "选择模型版本…"}</option>
            {available.map(m => <option key={m.id} value={m.id}>{m.name} · V{m.mlflow_version}</option>)}
          </Select>
        </Field>
        <p className="mt-2 text-[12px] text-slate-400">每个模型版本只能部署一次;已部署的版本请在列表中启动/停止。</p>
      </Drawer>

      <Drawer
        open={apiDoc !== null}
        onClose={() => setApiDoc(null)}
        title="API 详情"
        subtitle="该模型版本的在线推理接口、调用示例与输入输出说明。"
        width="max-w-xl"
      >
        {apiDoc && (
          <div className="flex flex-col gap-5">
            <div className="flex items-center gap-2">
              <Badge tone="blue">{apiDoc.taskLabel}</Badge>
              <span className="rounded-md bg-slate-100 px-2 py-0.5 font-mono text-[12px] text-slate-600">{apiDoc.method}</span>
              <Mono className="text-slate-700">{apiDoc.url}</Mono>
            </div>

            <div>
              <div className="label mb-1.5">请求参数</div>
              <div className="overflow-hidden rounded-lg border border-slate-200">
                <table className="w-full text-[12.5px]">
                  <thead className="bg-slate-50 text-slate-500">
                    <tr><th className="px-3 py-1.5 text-left font-medium">字段</th><th className="px-3 py-1.5 text-left font-medium">类型</th><th className="px-3 py-1.5 text-left font-medium">说明</th></tr>
                  </thead>
                  <tbody>
                    {apiDoc.reqFields.map(f => (
                      <tr key={f.name} className="border-t border-slate-100">
                        <td className="px-3 py-1.5 font-mono text-slate-700">{f.name}</td>
                        <td className="px-3 py-1.5 font-mono text-slate-500">{f.type}</td>
                        <td className="px-3 py-1.5 text-slate-600">{f.desc}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div>
              <div className="label mb-1.5">cURL 调用示例</div>
              <CodeBlock code={apiDoc.curl} />
            </div>

            <div>
              <div className="label mb-1.5">响应示例</div>
              <CodeBlock code={apiDoc.respExample} />
              <p className="mt-2 text-[12.5px] text-slate-500">{apiDoc.respDesc}</p>
            </div>
          </div>
        )}
      </Drawer>

      <ConfirmDialog
        open={del !== null}
        title="删除部署"
        message={<>确定删除部署 <b className="text-slate-700">#{del?.id}</b>?删除时会从 model-server 卸载该模型,在线服务将不可用。</>}
        busy={delBusy}
        onCancel={() => setDel(null)}
        onConfirm={doDelete}
      />
    </>
  );
}
