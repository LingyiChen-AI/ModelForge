import { useEffect, useState } from "react";
import { BarChart3, FlaskConical } from "lucide-react";
import { listEvalRuns, createEvalRun, type EvalRun } from "../api/client";
import { Button, Card, EmptyState, Field, Input, Mono, PageHeader, StatusBadge, TableShell } from "../ui";
import { useAuth } from "../context/AuthContext";

function Metrics({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data || {});
  if (!entries.length) return <span className="text-slate-300">—</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {entries.slice(0, 6).map(([k, v]) => (
        <span key={k} className="rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[11.5px] text-slate-600">
          {k}=<span className="text-slate-900">{typeof v === "number" ? (Number.isInteger(v) ? v : v.toFixed(3)) : String(v)}</span>
        </span>
      ))}
    </div>
  );
}

export function EvalPage() {
  const { can } = useAuth();
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [mvId, setMvId] = useState("");
  const [dvId, setDvId] = useState("");
  const reload = () => listEvalRuns(dvId ? Number(dvId) : undefined).then(setRuns);
  useEffect(() => { reload(); const t = setInterval(reload, 3000); return () => clearInterval(t); }, [dvId]);

  return (
    <>
      <PageHeader title="评估" subtitle="在评估集上对模型版本批量推理算指标;按评估集版本过滤即得 Leaderboard。" />

      {can("eval:run") && (
        <Card className="mb-5 px-4 pt-4 pb-8">
          <div className="flex flex-wrap items-end gap-3">
            <Field label="模型版本 ID"><Input className="w-40" placeholder="如 1" value={mvId} onChange={e => setMvId(e.target.value)} /></Field>
            <Field label="评估集版本 ID" hint="留空显示全部"><Input className="w-40" placeholder="如 2" value={dvId} onChange={e => setDvId(e.target.value)} /></Field>
            <Button variant="primary" disabled={!mvId || !dvId} onClick={() =>
              createEvalRun({ model_version_id: Number(mvId), dataset_version_id: Number(dvId) }).then(reload)}>
              <FlaskConical size={16} /> 发起评估
            </Button>
          </div>
        </Card>
      )}

      <TableShell
        empty={runs.length === 0}
        head={<><th className="w-14">#</th><th>模型版本</th><th>评估集版本</th><th>状态</th><th>指标</th></>}
      >
        {runs.length === 0 ? (
          <EmptyState icon={<BarChart3 size={22} />} title="还没有评估记录" hint="填模型版本与评估集版本 ID 发起评估。" />
        ) : runs.map(r => (
          <tr key={r.id}>
            <td><Mono>{r.id}</Mono></td>
            <td><Mono className="text-slate-700">#{r.model_version_id}</Mono></td>
            <td><Mono className="text-slate-700">#{r.dataset_version_id}</Mono></td>
            <td><StatusBadge status={r.status} />{r.error && <span className="ml-2 text-[12px] text-red-500">{r.error}</span>}</td>
            <td><Metrics data={r.results} /></td>
          </tr>
        ))}
      </TableShell>
    </>
  );
}
