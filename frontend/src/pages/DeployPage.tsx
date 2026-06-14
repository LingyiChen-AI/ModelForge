import { useEffect, useState } from "react";
import { Rocket, Square } from "lucide-react";
import { listDeployments, createDeployment, stopDeployment, type Deployment } from "../api/client";
import { Button, Card, EmptyState, Field, Input, Mono, PageHeader, StatusBadge, TableShell } from "../ui";
import { useAuth } from "../context/AuthContext";

export function DeployPage() {
  const { can } = useAuth();
  const [items, setItems] = useState<Deployment[]>([]);
  const [mvId, setMvId] = useState("");
  const reload = () => listDeployments().then(setItems);
  useEffect(() => { reload(); const t = setInterval(reload, 3000); return () => clearInterval(t); }, []);

  return (
    <>
      <PageHeader title="部署" subtitle="把模型版本加载到 model-server,对外提供在线推理。列表每 3 秒刷新。" />

      {can("deploy:write") && (
        <Card className="mb-5 p-4">
          <div className="flex flex-wrap items-end gap-3">
            <Field label="模型版本 ID"><Input className="w-44" placeholder="如 1" value={mvId} onChange={e => setMvId(e.target.value)} /></Field>
            <Button variant="primary" disabled={!mvId} onClick={() => createDeployment(Number(mvId)).then(() => { setMvId(""); reload(); })}>
              <Rocket size={16} /> 部署
            </Button>
          </div>
        </Card>
      )}

      <TableShell
        empty={items.length === 0}
        head={<><th className="w-14">#</th><th>模型版本</th><th>状态</th><th>endpoint</th><th className="w-24"></th></>}
      >
        {items.length === 0 ? (
          <EmptyState icon={<Rocket size={22} />} title="还没有部署" hint="填模型版本 ID 一键部署为在线服务。" />
        ) : items.map(d => (
          <tr key={d.id}>
            <td><Mono>{d.id}</Mono></td>
            <td><Mono className="text-slate-700">#{d.model_version_id}</Mono></td>
            <td><StatusBadge status={d.status} />{d.error && <span className="ml-2 text-[12px] text-red-500">{d.error}</span>}</td>
            <td><Mono>{d.endpoint || "—"}</Mono></td>
            <td className="text-right">
              {d.status === "running" && can("deploy:write") && (
                <Button size="sm" variant="danger" onClick={() => stopDeployment(d.id).then(reload)}><Square size={13} /> 停止</Button>
              )}
            </td>
          </tr>
        ))}
      </TableShell>
    </>
  );
}
