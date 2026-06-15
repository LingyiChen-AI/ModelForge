import { useEffect, useState } from "react";
import { DEFAULT_PAGE_SIZE } from "../constants";
import { ClipboardCheck, Plus } from "lucide-react";
import {
  listPromptEvalsPaged, createPromptEval, getPromptEvalOptions,
  type PromptEval, type PromptEvalOptions,
} from "../api/client";
import {
  Badge, Button, Drawer, EmptyState, Field, Input, PageHeader, Pagination,
  Select, StatusBadge, TableShell, Creator, CreatedAt,
} from "../ui";
import { toastError } from "../toast";

const TYPE_LABEL: Record<string, string> = {
  multi_prompt: "多 Prompt 盲测", multi_model: "多模型盲测", single_prompt: "单 Prompt 版本对比",
};

function tsName() {
  const d = new Date(), p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

function MultiCheck({ options, value, onChange }: {
  options: { id: number; label: string }[]; value: number[]; onChange: (v: number[]) => void;
}) {
  const toggle = (id: number) => onChange(value.includes(id) ? value.filter(x => x !== id) : [...value, id]);
  if (options.length === 0) return <p className="text-[12px] text-slate-400">无可选项</p>;
  return (
    <div className="flex max-h-40 flex-col gap-1 overflow-auto rounded-lg ring-1 ring-slate-200 p-2">
      {options.map(o => (
        <label key={o.id} className="flex items-center gap-2 text-[13px] text-slate-700">
          <input type="checkbox" checked={value.includes(o.id)} onChange={() => toggle(o.id)} />
          {o.label}
        </label>
      ))}
    </div>
  );
}

function NewEvalDrawer({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [opts, setOpts] = useState<PromptEvalOptions | null>(null);
  const [evalType, setEvalType] = useState("multi_prompt");
  const [name, setName] = useState(tsName());
  const [pvs, setPvs] = useState<number[]>([]);
  const [models, setModels] = useState<number[]>([]);
  const [datasets, setDatasets] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => { getPromptEvalOptions().then(setOpts).catch(() => toastError("加载选项失败")); }, []);

  const single = <T,>(arr: T[]) => (arr.length ? [arr[0]] : []);
  const onType = (t: string) => {
    setEvalType(t);
    if (t === "multi_model") setPvs(p => single(p));
    if (t === "multi_prompt" || t === "single_prompt") setModels(m => single(m));
    if (t === "single_prompt") setPvs(p => single(p));
  };

  const valid = (() => {
    if (datasets.length < 1 || !name.trim()) return false;
    if (evalType === "multi_prompt") return pvs.length >= 2 && models.length === 1;
    if (evalType === "multi_model") return models.length >= 2 && pvs.length === 1;
    return pvs.length === 1 && models.length === 1;
  })();

  const submit = () => {
    setBusy(true);
    createPromptEval({ eval_type: evalType, name, prompt_version_ids: pvs, model_ids: models, dataset_version_ids: datasets })
      .then(() => { onCreated(); onClose(); })
      .catch(e => toastError(e?.response?.data?.detail ?? "提交失败"))
      .finally(() => setBusy(false));
  };

  const pvOpts = opts?.prompt_versions ?? [];
  const modelOpts = opts?.models ?? [];
  const dsOpts = (opts?.prompt_datasets ?? []).map(d => ({ id: d.version_id, label: d.label }));
  const promptSingle = evalType !== "multi_prompt";
  const modelSingle = evalType !== "multi_model";

  return (
    <Drawer open onClose={onClose} title="新建评测" subtitle="选择评测类型、Prompt 版本、模型与 Prompt 测试集。"
      width="max-w-xl"
      footer={
        <div className="flex items-center justify-end gap-2">
          <Button variant="subtle" disabled={busy} onClick={onClose}>取消</Button>
          <Button variant="primary" disabled={!valid} loading={busy} onClick={submit}>发起评测</Button>
        </div>
      }>
      <div className="flex flex-col gap-4">
        <Field label="评测类型">
          <Select value={evalType} onChange={e => onType(e.target.value)}>
            <option value="multi_prompt">多 Prompt 盲测(多 prompt × 1 模型)</option>
            <option value="multi_model">多模型盲测(1 prompt × 多模型)</option>
            <option value="single_prompt">单 Prompt 版本对比(1 prompt × 1 模型,对比上一版)</option>
          </Select>
        </Field>
        <Field label="名称"><Input value={name} onChange={e => setName(e.target.value)} /></Field>

        <Field label={promptSingle ? "Prompt 版本(选 1)" : "Prompt 版本(多选 ≥2)"}>
          {promptSingle ? (
            <Select value={pvs[0] ?? ""} onChange={e => setPvs(e.target.value ? [Number(e.target.value)] : [])}>
              <option value="">选择 Prompt 版本…</option>
              {pvOpts.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
            </Select>
          ) : <MultiCheck options={pvOpts} value={pvs} onChange={setPvs} />}
        </Field>

        <Field label={modelSingle ? "模型(选 1)" : "模型(多选 ≥2)"}>
          {modelSingle ? (
            <Select value={models[0] ?? ""} onChange={e => setModels(e.target.value ? [Number(e.target.value)] : [])}>
              <option value="">选择模型…</option>
              {modelOpts.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
            </Select>
          ) : <MultiCheck options={modelOpts} value={models} onChange={setModels} />}
        </Field>

        <Field label="Prompt 测试集(多选)">
          <MultiCheck options={dsOpts} value={datasets} onChange={setDatasets} />
        </Field>
      </div>
    </Drawer>
  );
}

export function PromptEvalsPage() {
  const [items, setItems] = useState<PromptEval[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [total, setTotal] = useState(0);
  const [open, setOpen] = useState(false);

  const reload = () => listPromptEvalsPaged({ page, page_size: pageSize })
    .then(res => { setItems(res.items); setTotal(res.total); });
  useEffect(() => {
    setLoading(true); reload().finally(() => setLoading(false));
    const t = setInterval(reload, 3000); return () => clearInterval(t);
  }, [page, pageSize]);

  return (
    <>
      <PageHeader title="Prompt 评测"
        subtitle="发起多 Prompt / 多模型 / 单 Prompt 版本对比评测;跑完进入工作台盲测评估。"
        actions={<Button variant="primary" onClick={() => setOpen(true)}><Plus size={16} /> 新建评测</Button>} />

      <TableShell loading={loading} empty={items.length === 0}
        head={<><th>名称</th><th>类型</th><th>状态</th><th>进度</th><th>创建者</th><th className="w-36">创建时间</th></>}>
        {items.length === 0 ? (
          <EmptyState icon={<ClipboardCheck size={22} />} title="还没有评测" hint="新建一个 Prompt 评测。" />
        ) : items.map(r => (
          <tr key={r.id}>
            <td className="font-medium text-slate-800">{r.name}</td>
            <td><Badge tone="gray">{TYPE_LABEL[r.eval_type] ?? r.eval_type}</Badge></td>
            <td><StatusBadge status={r.status} /></td>
            <td>
              <div className="flex items-center gap-2">
                <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full bg-brand-500" style={{ width: `${Math.round(r.progress * 100)}%` }} />
                </div>
                <span className="text-[12px] text-slate-500">{Math.round(r.progress * 100)}%</span>
              </div>
            </td>
            <td><Creator name={r.created_by_name} /></td>
            <td><CreatedAt at={r.created_at} /></td>
          </tr>
        ))}
      </TableShell>
      <Pagination page={page} pageSize={pageSize} total={total} onPage={setPage} onPageSize={s => { setPageSize(s); setPage(1); }} />

      {open && <NewEvalDrawer onClose={() => setOpen(false)} onCreated={reload} />}
    </>
  );
}
