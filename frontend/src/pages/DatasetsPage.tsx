import { useEffect, useState } from "react";
import { DEFAULT_PAGE_SIZE } from "../constants";
import { Database, Plus, ChevronRight, Download } from "lucide-react";
import { listDatasetsPaged, createDataset, createPromptDataset, downloadTemplateByType, type Dataset, type TemplateFormat } from "../api/client";
import { Button, Drawer, EmptyState, Field, Input, Select, Badge, PageHeader, Pagination, TableShell, Creator, CreatedAt } from "../ui";
import { toastError } from "../toast";
import { useAuth } from "../context/AuthContext";
import { navigate } from "../router";

const TEMPLATE_FORMATS: { fmt: TemplateFormat; label: string }[] = [
  { fmt: "csv", label: "CSV" }, { fmt: "jsonl", label: "JSONL" }, { fmt: "xlsx", label: "Excel" },
];

const TASK_TONE: Record<string, "blue" | "violet" | "cyan" | "amber"> = {
  classification: "blue", ner: "violet", pair: "cyan", embedding: "amber",
};
const KIND_LABEL: Record<string, string> = { train: "训练集", eval: "评估集", test: "测试集", prompt: "Prompt 测试集" };

export function DatasetsPage() {
  const { can } = useAuth();
  const [items, setItems] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [total, setTotal] = useState(0);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [kind, setKind] = useState("train");
  const [taskType, setTaskType] = useState("classification");
  const reload = () => listDatasetsPaged({ page, page_size: pageSize }).then(res => { setItems(res.items); setTotal(res.total); });
  useEffect(() => { setLoading(true); reload().finally(() => setLoading(false)); }, [page, pageSize]);

  const openDrawer = () => { setName(""); setKind("train"); setTaskType("classification"); setBusy(false); setOpen(true); };
  const create = () => {
    setBusy(true);
    const req = kind === "prompt"
      ? createPromptDataset({ name })
      : createDataset({ name, kind, task_type: taskType });
    req.then(() => { setOpen(false); reload(); })
      .catch(() => toastError("创建失败")).finally(() => setBusy(false));
  };

  return (
    <>
      <PageHeader
        title="数据集"
        subtitle="训练集与评估集统一管理,每次上传生成不可变版本快照。"
        actions={can("dataset:write") && <Button variant="primary" onClick={openDrawer}><Plus size={16} /> 新建数据集</Button>}
      />

      <TableShell
        loading={loading}
        empty={items.length === 0}
        head={<><th>名称</th><th>类型</th><th>任务</th><th>创建者</th><th className="w-36">创建时间</th><th className="w-10"></th></>}
      >
        {items.length === 0 ? (
          <EmptyState icon={<Database size={22} />} title="还没有数据集" hint="新建一个数据集,然后上传 CSV / JSONL 生成第一个版本。" />
        ) : items.map(d => (
          <tr key={d.id} className="cursor-pointer" onClick={() => navigate(`/datasets/${d.id}`)}>
            <td>
              <div className="flex items-center gap-2.5">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 text-slate-400"><Database size={15} /></span>
                <span className="font-medium text-slate-800">{d.name}</span>
              </div>
            </td>
            <td><span className="text-slate-500">{KIND_LABEL[d.kind] ?? d.kind}</span></td>
            <td><Badge tone={TASK_TONE[d.task_type] ?? "gray"}>{d.task_type}</Badge></td>
            <td><Creator name={d.created_by_name} /></td>
            <td><CreatedAt at={d.created_at} /></td>
            <td className="text-slate-300"><ChevronRight size={16} /></td>
          </tr>
        ))}
      </TableShell>
      <Pagination page={page} pageSize={pageSize} total={total} onPage={setPage} onPageSize={s => { setPageSize(s); setPage(1); }} />

      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title="新建数据集"
        subtitle="先创建数据集,再进入详情上传 CSV / JSONL 生成版本。"
        footer={
          <div className="flex items-center justify-end gap-2">
            <Button variant="subtle" disabled={busy} onClick={() => setOpen(false)}>取消</Button>
            <Button variant="primary" disabled={!name} loading={busy} onClick={create}><Plus size={16} /> 创建</Button>
          </div>
        }
      >
        <div className="flex flex-col gap-4">
          <Field label="名称"><Input placeholder="如 intent-train" value={name} onChange={e => setName(e.target.value)} /></Field>
          <Field label="类型"><Select value={kind} onChange={e => setKind(e.target.value)}>
            <option value="train">训练集</option><option value="eval">评估集</option><option value="test">测试集</option>
            <option value="prompt">Prompt 测试集</option>
          </Select></Field>
          {kind === "prompt" && <p className="text-[12px] text-slate-400">Prompt 测试集的列即参数,上传 CSV/JSONL 后自动识别,无需选择任务。</p>}
          {kind !== "prompt" && (
            <Field label="任务"><Select value={taskType} onChange={e => setTaskType(e.target.value)}>
              <option value="classification">分类</option><option value="ner">序列标注</option>
              <option value="pair">句对</option><option value="embedding">向量</option>
            </Select></Field>
          )}

          {kind !== "prompt" && (
            <div className="rounded-lg bg-slate-50 px-3 py-2.5">
              <div className="mb-2 text-[12px] text-slate-500">下载该任务类型的数据模板(列格式按所选任务生成)</div>
              <div className="flex items-center gap-2">
                {TEMPLATE_FORMATS.map(t => (
                  <Button key={t.fmt} size="sm" variant="subtle"
                          onClick={() => downloadTemplateByType(taskType, t.fmt).catch(() => toastError("下载失败"))}>
                    <Download size={13} /> {t.label}
                  </Button>
                ))}
              </div>
            </div>
          )}
        </div>
      </Drawer>
    </>
  );
}
