import { useEffect, useState } from "react";
import { ArrowLeft, Upload, FileSpreadsheet, Layers } from "lucide-react";
import { listVersions, uploadVersion, type DatasetVersion } from "../api/client";
import { Button, Card, EmptyState, Mono, PageHeader, TableShell } from "../ui";
import { useAuth } from "../context/AuthContext";
import { navigate } from "../router";

export function DatasetDetailPage({ id }: { id: number }) {
  const { can } = useAuth();
  const [versions, setVersions] = useState<DatasetVersion[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const reload = () => listVersions(id).then(setVersions);
  useEffect(() => { reload(); }, [id]);

  const upload = async () => {
    if (!file) return;
    setBusy(true);
    try { await uploadVersion(id, file, ""); setFile(null); await reload(); }
    finally { setBusy(false); }
  };

  return (
    <>
      <a href="/" onClick={(e) => { e.preventDefault(); navigate("/"); }}
         className="mb-4 inline-flex items-center gap-1.5 text-[13px] text-slate-500 hover:text-slate-700 cursor-pointer">
        <ArrowLeft size={15} /> 返回数据集
      </a>
      <PageHeader title={`数据集 #${id} · 版本`} subtitle="每次上传都会创建一个不可变快照(parquet + checksum)。" />

      {can("dataset:write") && (
        <Card className="mb-5 p-4">
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex h-9 cursor-pointer items-center gap-2 rounded-lg bg-slate-100 px-3 text-[13px] font-medium text-slate-600 hover:bg-slate-200">
              <FileSpreadsheet size={16} className="text-slate-400" />
              {file ? file.name : "选择 CSV / JSONL 文件"}
              <input type="file" accept=".csv,.jsonl" className="hidden" onChange={e => setFile(e.target.files?.[0] ?? null)} />
            </label>
            <Button variant="primary" disabled={!file || busy} onClick={upload}>
              <Upload size={16} /> {busy ? "上传中…" : "上传新版本"}
            </Button>
          </div>
        </Card>
      )}

      <TableShell
        empty={versions.length === 0}
        head={<><th className="w-24">版本</th><th>行数</th><th>checksum</th><th>备注</th></>}
      >
        {versions.length === 0 ? (
          <EmptyState icon={<Layers size={22} />} title="还没有版本" hint="上传一个文件来创建第一个版本快照。" />
        ) : versions.map(v => (
          <tr key={v.id}>
            <td><span className="rounded-md bg-slate-100 px-2 py-0.5 font-mono text-[12.5px] font-medium text-slate-700">v{v.version_no}</span></td>
            <td className="tnum text-slate-700">{v.row_count.toLocaleString()}</td>
            <td><Mono>{v.checksum.slice(0, 16)}…</Mono></td>
            <td className="text-slate-400">{v.note || "—"}</td>
          </tr>
        ))}
      </TableShell>
    </>
  );
}
