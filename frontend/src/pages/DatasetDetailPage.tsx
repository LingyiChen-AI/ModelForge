import { useEffect, useState } from "react";
import { DEFAULT_PAGE_SIZE } from "../constants";
import { ArrowLeft, Upload, FileSpreadsheet, Layers, Download } from "lucide-react";
import { listVersionsPaged, listDatasets, uploadVersion, downloadTemplate, downloadVersion, type Dataset, type DatasetVersion, type TemplateFormat } from "../api/client";
import { Button, Drawer, EmptyState, Field, Input, Mono, PageHeader, Pagination, TableShell, Creator, CreatedAt } from "../ui";
import { toastError } from "../toast";
import { useAuth } from "../context/AuthContext";
import { navigate } from "../router";

const TEMPLATE_FORMATS: { fmt: TemplateFormat; label: string }[] = [
  { fmt: "csv", label: "CSV" }, { fmt: "jsonl", label: "JSONL" }, { fmt: "xlsx", label: "Excel" },
];

function TemplateButtons({ id }: { id: number }) {
  return (
    <div className="flex items-center gap-2">
      {TEMPLATE_FORMATS.map(t => (
        <Button key={t.fmt} size="sm" variant="subtle" onClick={() => downloadTemplate(id, t.fmt).catch(() => toastError("下载失败"))}>
          <Download size={13} /> {t.label}
        </Button>
      ))}
    </div>
  );
}

export function DatasetDetailPage({ id }: { id: number }) {
  const { can } = useAuth();
  const [versions, setVersions] = useState<DatasetVersion[]>([]);
  const [ds, setDs] = useState<Dataset | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [total, setTotal] = useState(0);
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const reload = () => listVersionsPaged(id, { page, page_size: pageSize }).then(res => { setVersions(res.items); setTotal(res.total); });
  useEffect(() => {
    setLoading(true); reload().finally(() => setLoading(false));
    listDatasets().then(list => setDs(list.find(d => d.id === id) ?? null)).catch(() => {});
  }, [id, page, pageSize]);

  const openDrawer = () => { setFile(null); setNote(""); setOpen(true); };
  const upload = async () => {
    if (!file) return;
    setBusy(true);
    try { await uploadVersion(id, file, note); setOpen(false); await reload(); }
    finally { setBusy(false); }
  };

  return (
    <>
      <a href="/datasets" onClick={(e) => { e.preventDefault(); navigate("/datasets"); }}
         className="mb-4 inline-flex items-center gap-1.5 text-[13px] text-slate-500 hover:text-slate-700 cursor-pointer">
        <ArrowLeft size={15} /> 返回数据集
      </a>
      <PageHeader
        title={ds ? `${ds.name} · 版本` : "数据集 · 版本"}
        subtitle="每次上传都会创建一个不可变快照(parquet + checksum)。"
        actions={can("dataset:write") && <Button variant="primary" onClick={openDrawer}><Upload size={16} /> 上传新版本</Button>}
      />

      <TableShell
        loading={loading}
        empty={versions.length === 0}
        head={<><th className="w-24">版本</th><th>行数</th><th>checksum</th><th>备注</th><th>创建者</th><th className="w-36">创建时间</th><th className="w-20 text-right">原始数据</th></>}
      >
        {versions.length === 0 ? (
          <EmptyState icon={<Layers size={22} />} title="还没有版本" hint="上传一个文件来创建第一个版本快照。" />
        ) : versions.map(v => (
          <tr key={v.id}>
            <td><span className="rounded-md bg-slate-100 px-2 py-0.5 font-mono text-[12.5px] font-medium text-slate-700">V{v.version_no}</span></td>
            <td className="tnum text-slate-700">{v.row_count.toLocaleString()}</td>
            <td><Mono>{v.checksum.slice(0, 16)}…</Mono></td>
            <td className="text-slate-400">{v.note || "—"}</td>
            <td><Creator name={v.created_by_name} /></td>
            <td><CreatedAt at={v.created_at} /></td>
            <td className="text-right">
              <Button size="sm" title="下载原始数据 (CSV)" onClick={() => downloadVersion(id, v.id, v.version_no, "csv").catch(() => toastError("下载失败"))}>
                <Download size={13} /> 下载
              </Button>
            </td>
          </tr>
        ))}
      </TableShell>
      <Pagination page={page} pageSize={pageSize} total={total} onPage={setPage} onPageSize={s => { setPageSize(s); setPage(1); }} />

      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title="上传新版本"
        subtitle="支持 CSV / JSONL / Excel,上传后生成一个不可变版本快照。"
        footer={
          <div className="flex items-center justify-end gap-2">
            <Button variant="subtle" onClick={() => setOpen(false)} disabled={busy}>取消</Button>
            <Button variant="primary" disabled={!file} loading={busy} onClick={upload}>
              <Upload size={16} /> {busy ? "上传中…" : "上传"}
            </Button>
          </div>
        }
      >
        <div className="flex flex-col gap-4">
          <Field label="文件">
            <label className="flex h-10 cursor-pointer items-center gap-2 rounded-lg border border-dashed border-slate-300 bg-slate-50 px-3 text-[13px] font-medium text-slate-600 hover:border-slate-400">
              <FileSpreadsheet size={16} className="text-slate-400" />
              {file ? file.name : "选择 CSV / JSONL / Excel 文件"}
              <input type="file" accept=".csv,.jsonl,.xlsx" className="hidden" onChange={e => setFile(e.target.files?.[0] ?? null)} />
            </label>
          </Field>
          <Field label="备注(可选)">
            <Input placeholder="如 修正标注 / 新增 500 条" value={note} onChange={e => setNote(e.target.value)} />
          </Field>
          {ds?.kind !== "prompt" && (
            <div className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
              <span className="text-[12px] text-slate-500">不确定格式?下载模板</span>
              <TemplateButtons id={id} />
            </div>
          )}
        </div>
      </Drawer>
    </>
  );
}
