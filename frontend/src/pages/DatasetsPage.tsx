import { useEffect, useState } from "react";
import { Database, Plus, ChevronRight } from "lucide-react";
import { listDatasets, createDataset, type Dataset } from "../api/client";
import { Button, Card, EmptyState, Field, Input, Select, Badge, PageHeader, TableShell } from "../ui";
import { useAuth } from "../context/AuthContext";

const TASK_TONE: Record<string, "blue" | "violet" | "cyan" | "amber"> = {
  classification: "blue", ner: "violet", pair: "cyan", embedding: "amber",
};

export function DatasetsPage() {
  const { can } = useAuth();
  const [items, setItems] = useState<Dataset[]>([]);
  const [name, setName] = useState("");
  const [kind, setKind] = useState("train");
  const [taskType, setTaskType] = useState("classification");
  const reload = () => listDatasets().then(setItems);
  useEffect(() => { reload(); }, []);

  const create = () =>
    createDataset({ name, kind, task_type: taskType }).then(() => { setName(""); reload(); });

  return (
    <>
      <PageHeader title="数据集" subtitle="训练集与评估集统一管理,每次上传生成不可变版本快照。" />

      {can("dataset:write") && (
        <Card className="mb-5 p-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="grow min-w-[200px]"><Field label="名称"><Input placeholder="如 intent-train" value={name} onChange={e => setName(e.target.value)} /></Field></div>
            <Field label="类型"><Select value={kind} onChange={e => setKind(e.target.value)}><option value="train">训练集</option><option value="eval">评估集</option></Select></Field>
            <Field label="任务"><Select value={taskType} onChange={e => setTaskType(e.target.value)}>
              <option value="classification">分类</option><option value="ner">序列标注</option>
              <option value="pair">句对</option><option value="embedding">向量</option>
            </Select></Field>
            <Button variant="primary" disabled={!name} onClick={create}><Plus size={16} /> 新建数据集</Button>
          </div>
        </Card>
      )}

      <TableShell
        empty={items.length === 0}
        head={<><th>名称</th><th>类型</th><th>任务</th><th className="w-10"></th></>}
      >
        {items.length === 0 ? (
          <EmptyState icon={<Database size={22} />} title="还没有数据集" hint="新建一个数据集,然后上传 CSV / JSONL 生成第一个版本。" />
        ) : items.map(d => (
          <tr key={d.id} className="cursor-pointer" onClick={() => (location.href = `/datasets/${d.id}`)}>
            <td>
              <div className="flex items-center gap-2.5">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 text-slate-400"><Database size={15} /></span>
                <span className="font-medium text-slate-800">{d.name}</span>
              </div>
            </td>
            <td><span className="text-slate-500">{d.kind === "eval" ? "评估集" : "训练集"}</span></td>
            <td><Badge tone={TASK_TONE[d.task_type] ?? "gray"}>{d.task_type}</Badge></td>
            <td className="text-slate-300"><ChevronRight size={16} /></td>
          </tr>
        ))}
      </TableShell>
    </>
  );
}
