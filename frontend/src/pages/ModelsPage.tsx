import { useEffect, useState } from "react";
import { listModelVersions, type ModelVersion } from "../api/client";

export function ModelsPage() {
  const [items, setItems] = useState<ModelVersion[]>([]);
  useEffect(() => { listModelVersions().then(setItems); }, []);
  return (
    <div>
      <h2>模型版本</h2>
      <table><thead><tr><th>名称</th><th>版本</th><th>任务</th><th>指标</th><th>stage</th></tr></thead>
        <tbody>{items.map(m => <tr key={m.id}>
          <td>{m.name}</td><td>{m.mlflow_version}</td><td>{m.task_type}</td>
          <td>{JSON.stringify(m.train_metrics)}</td><td>{m.stage}</td></tr>)}</tbody>
      </table>
    </div>
  );
}
