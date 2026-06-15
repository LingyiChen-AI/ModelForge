import { useEffect, useState } from "react";
import { DEFAULT_PAGE_SIZE } from "../constants";
import { MessageSquareText, Plus, History, GitBranch } from "lucide-react";
import {
  listPromptsPaged, createPrompt, addPromptVersion, getPrompt, validatePrompt,
  type Prompt, type PromptDetail,
} from "../api/client";
import {
  Badge, Button, Drawer, EmptyState, Field, Input, PageHeader, Pagination,
  TableShell, Creator, CreatedAt,
} from "../ui";
import { toastError, toastSuccess } from "../toast";

function ParamChips({ params }: { params: string[] }) {
  if (params.length === 0) return <span className="text-slate-400">无参数</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {params.map(p => <Badge key={p} tone="blue">{p}</Badge>)}
    </div>
  );
}

function Editor({
  edit, onClose, onSaved,
}: { edit: { mode: "new" } | { mode: "version"; prompt: Prompt }; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState("");
  const [sys, setSys] = useState("");
  const [usr, setUsr] = useState("");
  const [params, setParams] = useState<string[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      validatePrompt({ system_prompt: sys, user_prompt: usr })
        .then(r => { setParams(r.params); setErrors(r.errors); })
        .catch(() => {});
    }, 300);
    return () => clearTimeout(t);
  }, [sys, usr]);

  const save = async () => {
    setBusy(true);
    try {
      if (edit.mode === "new") {
        await createPrompt({ name, system_prompt: sys, user_prompt: usr });
      } else {
        await addPromptVersion(edit.prompt.id, { system_prompt: sys, user_prompt: usr });
      }
      toastSuccess("已保存");
      onSaved(); onClose();
    } catch (e: any) {
      toastError(e?.response?.data?.detail ?? "保存失败");
    } finally {
      setBusy(false);
    }
  };

  const canSave = errors.length === 0 && (edit.mode === "version" || name.trim().length > 0);

  return (
    <Drawer
      open
      onClose={onClose}
      title={edit.mode === "new" ? "新建 Prompt" : `为「${edit.prompt.name}」新增版本`}
      subtitle="参数写法:{{ 参数名 }}(支持中文)。system 与 user 的参数取并集。"
      width="max-w-2xl"
      footer={
        <div className="flex items-center justify-end gap-2">
          <Button variant="subtle" disabled={busy} onClick={onClose}>取消</Button>
          <Button variant="primary" disabled={!canSave} loading={busy} onClick={save}>保存为新版本</Button>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        {edit.mode === "new" && (
          <Field label="名称"><Input value={name} onChange={e => setName(e.target.value)} placeholder="如:售前意图分类 prompt" /></Field>
        )}
        <Field label="System Prompt">
          <textarea value={sys} onChange={e => setSys(e.target.value)} rows={5}
            className="w-full rounded-lg bg-white px-3 py-2 text-sm text-slate-900 ring-1 ring-slate-200 outline-none transition focus:ring-2 focus:ring-brand-500 placeholder:text-slate-400 font-mono"
            placeholder="你是一个{{ 角色 }}…" />
        </Field>
        <Field label="User Prompt">
          <textarea value={usr} onChange={e => setUsr(e.target.value)} rows={6}
            className="w-full rounded-lg bg-white px-3 py-2 text-sm text-slate-900 ring-1 ring-slate-200 outline-none transition focus:ring-2 focus:ring-brand-500 placeholder:text-slate-400 font-mono"
            placeholder="请处理:{{ 输入 }}" />
        </Field>
        <div>
          <div className="label mb-1.5">识别到的参数</div>
          <ParamChips params={params} />
        </div>
        {errors.length > 0 && (
          <div className="rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600 ring-1 ring-red-100">
            {errors.map((e, i) => <div key={i}>{e}</div>)}
          </div>
        )}
      </div>
    </Drawer>
  );
}

function HistoryDrawer({ promptId, onClose }: { promptId: number; onClose: () => void }) {
  const [detail, setDetail] = useState<PromptDetail | null>(null);
  useEffect(() => { getPrompt(promptId).then(setDetail).catch(() => toastError("加载失败")); }, [promptId]);
  return (
    <Drawer open onClose={onClose} title="版本历史" subtitle={detail?.name} width="max-w-2xl">
      <div className="flex flex-col gap-3">
        {(detail?.versions ?? []).slice().reverse().map(v => (
          <div key={v.id} className="rounded-xl border border-slate-200 p-3">
            <div className="mb-2 flex items-center gap-2">
              <Badge tone="gray">V{v.version_no}</Badge>
              <ParamChips params={v.params} />
              <span className="ml-auto text-[12px] text-slate-400"><CreatedAt at={v.created_at} /></span>
            </div>
            {v.system_prompt && <pre className="mb-1 whitespace-pre-wrap rounded bg-slate-50 p-2 text-[12px] text-slate-700">[system] {v.system_prompt}</pre>}
            <pre className="whitespace-pre-wrap rounded bg-slate-50 p-2 text-[12px] text-slate-700">[user] {v.user_prompt}</pre>
          </div>
        ))}
      </div>
    </Drawer>
  );
}

export function PromptsPage() {
  const [items, setItems] = useState<Prompt[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [total, setTotal] = useState(0);
  const [editor, setEditor] = useState<{ mode: "new" } | { mode: "version"; prompt: Prompt } | null>(null);
  const [historyId, setHistoryId] = useState<number | null>(null);

  const reload = () => listPromptsPaged({ page, page_size: pageSize })
    .then(res => { setItems(res.items); setTotal(res.total); });
  useEffect(() => { setLoading(true); reload().finally(() => setLoading(false)); }, [page, pageSize]);

  return (
    <>
      <PageHeader
        title="Prompt"
        subtitle="管理带 {{ 参数 }} 的 system / user prompt,版本化,供 Prompt 评测选用。"
        actions={<Button variant="primary" onClick={() => setEditor({ mode: "new" })}><Plus size={16} /> 新建 Prompt</Button>}
      />

      <TableShell
        loading={loading}
        empty={items.length === 0}
        head={<><th>名称</th><th>最新版本</th><th>参数</th><th>创建者</th><th className="w-36">创建时间</th><th className="w-48 text-right"></th></>}
      >
        {items.length === 0 ? (
          <EmptyState icon={<MessageSquareText size={22} />} title="还没有 Prompt" hint="新建一个带 {{ 参数 }} 的 prompt。" />
        ) : items.map(p => (
          <tr key={p.id}>
            <td className="font-medium text-slate-800">{p.name}</td>
            <td>{p.latest_version_no ? <Badge tone="gray">V{p.latest_version_no}</Badge> : "—"}</td>
            <td className="wrap"><ParamChips params={p.latest_params} /></td>
            <td><Creator name={p.created_by_name} /></td>
            <td><CreatedAt at={p.created_at} /></td>
            <td className="text-right">
              <div className="flex items-center justify-end gap-2">
                <Button size="sm" onClick={() => setEditor({ mode: "version", prompt: p })}><GitBranch size={13} /> 新增版本</Button>
                <Button size="sm" onClick={() => setHistoryId(p.id)}><History size={13} /> 历史</Button>
              </div>
            </td>
          </tr>
        ))}
      </TableShell>
      <Pagination page={page} pageSize={pageSize} total={total} onPage={setPage} onPageSize={s => { setPageSize(s); setPage(1); }} />

      {editor && <Editor edit={editor} onClose={() => setEditor(null)} onSaved={reload} />}
      {historyId !== null && <HistoryDrawer promptId={historyId} onClose={() => setHistoryId(null)} />}
    </>
  );
}
