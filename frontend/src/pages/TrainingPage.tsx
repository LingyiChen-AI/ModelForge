import { useEffect, useState } from "react";
import { listJobs, createJob, type TrainingJob } from "../api/client";

export function TrainingPage() {
  const [jobs, setJobs] = useState<TrainingJob[]>([]);
  const [dvId, setDvId] = useState("");
  const reload = () => listJobs().then(setJobs);
  useEffect(() => { reload(); const t = setInterval(reload, 3000); return () => clearInterval(t); }, []);
  return (
    <div>
      <h2>训练任务</h2>
      <input placeholder="dataset_version_id" value={dvId} onChange={e => setDvId(e.target.value)} />
      <button onClick={() => createJob({ name: `job-${Date.now()}`, dataset_version_id: Number(dvId),
        base_model: "prajjwal1/bert-tiny", task_type: "classification",
        hyperparams: { epochs: 1, batch_size: 4 } }).then(reload)}>提交训练</button>
      <ul>{jobs.map(j => <li key={j.id}>#{j.id} {j.name} — <b>{j.status}</b>{j.error ? ` (${j.error})` : ""}</li>)}</ul>
    </div>
  );
}
