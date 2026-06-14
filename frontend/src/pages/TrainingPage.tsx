import { useEffect, useState } from "react";
import { Cpu, Play } from "lucide-react";
import { listJobs, createJob, type TrainingJob } from "../api/client";
import { Button, Card, EmptyState, Field, Input, Mono, PageHeader, StatusBadge, TableShell } from "../ui";
import { useAuth } from "../context/AuthContext";

export function TrainingPage() {
  const { can } = useAuth();
  const [jobs, setJobs] = useState<TrainingJob[]>([]);
  const [dvId, setDvId] = useState("");
  const [baseModel, setBaseModel] = useState("prajjwal1/bert-tiny");
  const reload = () => listJobs().then(setJobs);
  useEffect(() => { reload(); const t = setInterval(reload, 3000); return () => clearInterval(t); }, []);

  const submit = () =>
    createJob({
      name: `job-${Date.now()}`, dataset_version_id: Number(dvId), base_model: baseModel,
      task_type: "classification", hyperparams: { epochs: 1, batch_size: 4 },
    }).then(() => { setDvId(""); reload(); });

  return (
    <>
      <PageHeader title="训练任务" subtitle="提交训练后由 GPU worker 执行,完成自动注册到模型版本。列表每 3 秒刷新。" />

      {can("training:run") && (
        <Card className="mb-5 p-4">
          <div className="flex flex-wrap items-end gap-3">
            <Field label="数据集版本 ID"><Input className="w-44" placeholder="如 1" value={dvId} onChange={e => setDvId(e.target.value)} /></Field>
            <div className="grow min-w-[220px]"><Field label="base_model" hint="HuggingFace 模型名,bert-tiny 最快"><Input value={baseModel} onChange={e => setBaseModel(e.target.value)} /></Field></div>
            <Button variant="primary" disabled={!dvId} onClick={submit}><Play size={16} /> 提交训练</Button>
          </div>
        </Card>
      )}

      <TableShell
        empty={jobs.length === 0}
        head={<><th className="w-16">#</th><th>名称</th><th>状态</th><th>错误</th></>}
      >
        {jobs.length === 0 ? (
          <EmptyState icon={<Cpu size={22} />} title="还没有训练任务" hint="填一个数据集版本 ID 提交训练。" />
        ) : jobs.map(j => (
          <tr key={j.id}>
            <td><Mono>{j.id}</Mono></td>
            <td className="font-medium text-slate-800">{j.name}</td>
            <td><StatusBadge status={j.status} /></td>
            <td className="max-w-sm truncate text-[12.5px] text-red-500">{j.error || ""}</td>
          </tr>
        ))}
      </TableShell>
    </>
  );
}
