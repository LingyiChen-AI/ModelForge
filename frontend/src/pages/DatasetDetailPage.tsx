import { useEffect, useState } from "react";
import { listVersions, uploadVersion, type DatasetVersion } from "../api/client";

export function DatasetDetailPage({ id }: { id: number }) {
  const [versions, setVersions] = useState<DatasetVersion[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const reload = () => listVersions(id).then(setVersions);
  useEffect(() => { reload(); }, [id]);
  return (
    <div>
      <h2>版本</h2>
      <input type="file" accept=".csv,.jsonl" onChange={e => setFile(e.target.files?.[0] ?? null)} />
      <button disabled={!file} onClick={() => file && uploadVersion(id, file, "").then(reload)}>上传新版本</button>
      <table><thead><tr><th>版本</th><th>行数</th><th>checksum</th></tr></thead>
        <tbody>{versions.map(v => <tr key={v.id}><td>v{v.version_no}</td><td>{v.row_count}</td><td>{v.checksum.slice(0,12)}</td></tr>)}</tbody>
      </table>
    </div>
  );
}
