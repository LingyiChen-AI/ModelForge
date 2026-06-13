import { useEffect, useState } from "react";
import { listEvalRuns, createEvalRun, type EvalRun } from "../api/client";

export function EvalPage() {
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [mvId, setMvId] = useState("");
  const [dvId, setDvId] = useState("");
  const reload = () => listEvalRuns(dvId ? Number(dvId) : undefined).then(setRuns);
  useEffect(() => { reload(); const t = setInterval(reload, 3000); return () => clearInterval(t); }, [dvId]);
  return (
    <div>
      <h2>评估</h2>
      <div>
        <input placeholder="model_version_id" value={mvId} onChange={e => setMvId(e.target.value)} />
        <input placeholder="eval dataset_version_id" value={dvId} onChange={e => setDvId(e.target.value)} />
        <button disabled={!mvId || !dvId} onClick={() =>
          createEvalRun({ model_version_id: Number(mvId), dataset_version_id: Number(dvId) }).then(reload)}>
          发起评估
        </button>
      </div>
      <table><thead><tr><th>#</th><th>模型版本</th><th>评估集版本</th><th>状态</th><th>指标</th></tr></thead>
        <tbody>{runs.map(r => <tr key={r.id}>
          <td>{r.id}</td><td>{r.model_version_id}</td><td>{r.dataset_version_id}</td>
          <td><b>{r.status}</b>{r.error ? ` (${r.error})` : ""}</td>
          <td>{JSON.stringify(r.results)}</td></tr>)}</tbody>
      </table>
    </div>
  );
}
