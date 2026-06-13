import { useEffect, useState } from "react";
import { listDatasets, createDataset, type Dataset } from "../api/client";

export function DatasetsPage() {
  const [items, setItems] = useState<Dataset[]>([]);
  const [name, setName] = useState("");
  const reload = () => listDatasets().then(setItems);
  useEffect(() => { reload(); }, []);
  return (
    <div>
      <h2>数据集</h2>
      <div>
        <input value={name} onChange={e => setName(e.target.value)} placeholder="名称" />
        <button onClick={() => createDataset({ name, kind: "train", task_type: "classification" }).then(reload)}>
          新建(分类训练集)
        </button>
      </div>
      <ul>
        {items.map(d => <li key={d.id}><a href={`/datasets/${d.id}`}>{d.name}</a> — {d.task_type}</li>)}
      </ul>
    </div>
  );
}
