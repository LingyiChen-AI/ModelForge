import { useEffect, useState } from "react";
import { Boxes } from "lucide-react";
import { listModelVersions, type ModelVersion } from "../api/client";
import { Badge, EmptyState, Mono, PageHeader, StatusBadge, TableShell } from "../ui";

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
  const [items, setItems] = useState<ModelVersion[]>([]);
  useEffect(() => { listModelVersions().then(setItems); }, []);
  return (
    <>
      <PageHeader title="模型版本" subtitle="训练产出经 MLflow 注册的模型版本。" />
      <TableShell
        empty={items.length === 0}
        head={<><th>名称</th><th className="w-20">版本</th><th>任务</th><th>训练指标</th><th>stage</th></>}
      >
        {items.length === 0 ? (
          <EmptyState icon={<Boxes size={22} />} title="还没有模型版本" hint="训练任务完成后会自动出现在这里。" />
        ) : items.map(m => (
          <tr key={m.id}>
            <td className="font-medium text-slate-800">{m.name}</td>
            <td><Mono className="text-slate-700">v{m.mlflow_version}</Mono></td>
            <td><Badge tone="blue">{m.task_type}</Badge></td>
            <td><Metrics data={m.train_metrics} /></td>
            <td><StatusBadge status={m.stage} /></td>
          </tr>
        ))}
      </TableShell>
    </>
  );
}
