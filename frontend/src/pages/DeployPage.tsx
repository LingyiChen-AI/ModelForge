import { useEffect, useState } from "react";
import { listDeployments, createDeployment, stopDeployment, type Deployment } from "../api/client";

export function DeployPage() {
  const [items, setItems] = useState<Deployment[]>([]);
  const [mvId, setMvId] = useState("");
  const reload = () => listDeployments().then(setItems);
  useEffect(() => { reload(); const t = setInterval(reload, 3000); return () => clearInterval(t); }, []);
  return (
    <div>
      <h2>部署</h2>
      <input placeholder="model_version_id" value={mvId} onChange={e => setMvId(e.target.value)} />
      <button disabled={!mvId} onClick={() => createDeployment(Number(mvId)).then(reload)}>部署</button>
      <table><thead><tr><th>#</th><th>模型版本</th><th>状态</th><th>endpoint</th><th></th></tr></thead>
        <tbody>{items.map(d => <tr key={d.id}>
          <td>{d.id}</td><td>{d.model_version_id}</td>
          <td><b>{d.status}</b>{d.error ? ` (${d.error})` : ""}</td><td>{d.endpoint}</td>
          <td>{d.status === "running" && <button onClick={() => stopDeployment(d.id).then(reload)}>停止</button>}</td>
        </tr>)}</tbody>
      </table>
    </div>
  );
}
