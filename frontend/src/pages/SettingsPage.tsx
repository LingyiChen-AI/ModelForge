import { useEffect, useState } from "react";
import { DEFAULT_PAGE_SIZE } from "../constants";
import { SlidersHorizontal, Plus, Trash2, FlaskConical, X, Power } from "lucide-react";
import {
  listLlmProvidersPaged, createLlmProvider, updateLlmProvider, deleteLlmProvider,
  addLlmModel, deleteLlmModel, testLlmModel,
  getAiEvalPrompt, setAiEvalPrompt, resetAiEvalPrompt,
  type LlmProvider, type LlmTestResult,
} from "../api/client";
import {
  Badge, Button, ConfirmDialog, Drawer, EmptyState, Field, Input, Mono,
  PageHeader, Pagination, TableShell, Creator, CreatedAt,
} from "../ui";
import { toastError, toastSuccess } from "../toast";
import { useAuth } from "../context/AuthContext";

type TestState = Record<number, "loading" | LlmTestResult>;

export function SettingsPage() {
  const { can } = useAuth();
  const canLlm = can("llm:manage");           // LLM 供应商配置(管理员)
  const canAi = can("prompteval:annotate");   // AI 评判 Prompt(谁评测谁配)
  const [items, setItems] = useState<LlmProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [total, setTotal] = useState(0);

  const [open, setOpen] = useState(false);
  const [edit, setEdit] = useState<LlmProvider | null>(null);
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [modelIds, setModelIds] = useState<string[]>([""]);
  const [busy, setBusy] = useState(false);

  const [del, setDel] = useState<LlmProvider | null>(null);
  const [delBusy, setDelBusy] = useState(false);
  const [tests, setTests] = useState<TestState>({});

  const reload = () => listLlmProvidersPaged({ page, page_size: pageSize })
    .then(res => { setItems(res.items); setTotal(res.total); });
  useEffect(() => {
    if (!canLlm) { setLoading(false); return; }
    setLoading(true); reload().finally(() => setLoading(false));
  }, [page, pageSize, canLlm]);

  const openNew = () => {
    setEdit(null); setName(""); setBaseUrl(""); setApiKey(""); setModelIds([""]);
    setBusy(false); setOpen(true);
  };
  const openEdit = (p: LlmProvider) => {
    setEdit(p); setName(p.name); setBaseUrl(p.base_url); setApiKey(""); setModelIds([]);
    setBusy(false); setOpen(true);
  };

  const submit = async () => {
    setBusy(true);
    try {
      const ids = modelIds.map(s => s.trim()).filter(Boolean);
      if (edit) {
        await updateLlmProvider(edit.id, { name, base_url: baseUrl, ...(apiKey ? { api_key: apiKey } : {}) });
      } else {
        await createLlmProvider({ name, base_url: baseUrl, api_key: apiKey, model_ids: ids });
      }
      setOpen(false); reload();
    } catch {
      toastError("保存失败");
    } finally {
      setBusy(false);
    }
  };

  const toggleEnabled = (p: LlmProvider) =>
    updateLlmProvider(p.id, { enabled: !p.enabled }).then(reload).catch(() => toastError("切换失败"));

  const doDelete = (_cascade: boolean) => {
    if (!del) return;
    setDelBusy(true);
    deleteLlmProvider(del.id).then(() => { setDel(null); reload(); })
      .catch(() => toastError("删除失败")).finally(() => setDelBusy(false));
  };

  const addModel = (p: LlmProvider, mid: string) => {
    const v = mid.trim();
    if (!v) return;
    addLlmModel(p.id, v).then(reload).catch(() => toastError("添加失败(可能重复)"));
  };
  const removeModel = (modelId: number) =>
    deleteLlmModel(modelId).then(reload).catch(() => toastError("删除失败"));
  const runTest = (modelId: number) => {
    setTests(t => ({ ...t, [modelId]: "loading" }));
    testLlmModel(modelId)
      .then(res => setTests(t => ({ ...t, [modelId]: res })))
      .catch(() => setTests(t => ({ ...t, [modelId]: { ok: false, reply: null, latency_ms: 0, error: "请求失败" } })));
  };

  return (
    <>
      <PageHeader
        title="设置"
        subtitle="配置 OpenAI 协议的大模型供应商(下挂多个 model-id),供 Prompt 评测选用。"
        actions={canLlm ? <Button variant="primary" onClick={openNew}><Plus size={16} /> 新建供应商</Button> : undefined}
      />

      {canLlm && <>
      <TableShell
        loading={loading}
        empty={items.length === 0}
        head={<><th>名称</th><th>base_url</th><th>API Key</th><th>模型</th><th>状态</th><th>创建者</th><th className="w-36">创建时间</th><th className="w-44 text-right"></th></>}
      >
        {items.length === 0 ? (
          <EmptyState icon={<SlidersHorizontal size={22} />} title="还没有供应商" hint="新建一个大模型供应商,填 base_url / api_key / model-id。" />
        ) : items.map(p => (
          <tr key={p.id} className="align-top">
            <td className="font-medium text-slate-800">{p.name}</td>
            <td><Mono>{p.base_url}</Mono></td>
            <td><Mono>{p.masked_key}</Mono></td>
            <td className="min-w-[300px]">
              <div className="flex flex-col gap-2">
                {p.models.map(m => {
                  const st = tests[m.id];
                  return (
                    <div key={m.id} className="flex items-center gap-2 rounded-lg bg-slate-50/70 px-2 py-1 ring-1 ring-slate-100">
                      <span className="whitespace-nowrap font-mono text-[12.5px] text-slate-700">{m.model_id}</span>
                      <Button size="sm" loading={st === "loading"} onClick={() => runTest(m.id)}>
                        <FlaskConical size={12} /> 测试
                      </Button>
                      {st && st !== "loading" && (
                        <span
                          className={`whitespace-nowrap text-[12px] font-medium ${st.ok ? "text-emerald-600" : "text-red-500"}`}
                          title={st.ok ? `回复:${st.reply}` : (st.error ?? "")}>
                          {st.ok ? "✓ 连通" : "✗ 失败"} · {st.latency_ms}ms
                        </span>
                      )}
                      <button onClick={() => removeModel(m.id)} className="ml-auto text-slate-300 hover:text-red-500" title="删除该 model">
                        <X size={14} />
                      </button>
                    </div>
                  );
                })}
                <AddModelInline onAdd={mid => addModel(p, mid)} />
              </div>
            </td>
            <td>
              <button onClick={() => toggleEnabled(p)} title="点击切换">
                <Badge tone={p.enabled ? "green" : "gray"}><Power size={11} /> {p.enabled ? "启用" : "停用"}</Badge>
              </button>
            </td>
            <td><Creator name={p.created_by_name} /></td>
            <td><CreatedAt at={p.created_at} /></td>
            <td className="text-right">
              <div className="flex items-center justify-end gap-2">
                <Button size="sm" onClick={() => openEdit(p)}>编辑</Button>
                <Button size="sm" variant="danger" onClick={() => setDel(p)}><Trash2 size={13} /></Button>
              </div>
            </td>
          </tr>
        ))}
      </TableShell>
      <Pagination page={page} pageSize={pageSize} total={total} onPage={setPage} onPageSize={s => { setPageSize(s); setPage(1); }} />
      </>}

      {canAi && <AiEvalPromptCard />}

      {canLlm && <>
      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title={edit ? "编辑供应商" : "新建供应商"}
        subtitle="OpenAI 协议:base_url 形如 https://api.openai.com/v1。"
        footer={
          <div className="flex items-center justify-end gap-2">
            <Button variant="subtle" disabled={busy} onClick={() => setOpen(false)}>取消</Button>
            <Button variant="primary" disabled={!name || !baseUrl || (!edit && !apiKey)} loading={busy} onClick={submit}>保存</Button>
          </div>
        }
      >
        <div className="flex flex-col gap-4">
          <Field label="名称"><Input value={name} onChange={e => setName(e.target.value)} placeholder="OpenAI 官方 / 内网 vLLM" /></Field>
          <Field label="base_url"><Input value={baseUrl} onChange={e => setBaseUrl(e.target.value)} placeholder="https://api.openai.com/v1" /></Field>
          <Field label={edit ? "API Key(留空=不修改)" : "API Key"}>
            <Input value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder={edit ? (edit.masked_key || "sk-…") : "sk-…"} />
          </Field>
          {!edit && (
            <Field label="model-id(可多个)">
              <div className="flex flex-col gap-2">
                {modelIds.map((m, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <Input value={m} onChange={e => setModelIds(arr => arr.map((x, j) => j === i ? e.target.value : x))} placeholder="gpt-4o-mini" />
                    {modelIds.length > 1 && (
                      <button onClick={() => setModelIds(arr => arr.filter((_, j) => j !== i))} className="text-slate-400 hover:text-red-500"><X size={15} /></button>
                    )}
                  </div>
                ))}
                <button onClick={() => setModelIds(arr => [...arr, ""])} className="self-start text-[13px] text-brand-600 hover:underline">+ 再加一个</button>
              </div>
            </Field>
          )}
          {edit && <p className="text-[12px] text-slate-400">model-id 在列表里逐个增删。</p>}
        </div>
      </Drawer>

      <ConfirmDialog
        open={del !== null}
        title="删除供应商"
        message={<>确定删除供应商 <b className="text-slate-700">{del?.name}</b>?其下所有 model-id 一并删除。</>}
        busy={delBusy}
        onCancel={() => setDel(null)}
        onConfirm={doDelete}
      />
      </>}
    </>
  );
}

function AiEvalPromptCard() {
  const [value, setValue] = useState("");
  const [isCustom, setIsCustom] = useState(false);
  const [busy, setBusy] = useState(false);
  const [resetBusy, setResetBusy] = useState(false);
  useEffect(() => { getAiEvalPrompt().then(r => { setValue(r.value); setIsCustom(r.is_custom); }).catch(() => {}); }, []);
  const save = () => {
    setBusy(true);
    setAiEvalPrompt(value)
      .then(r => { setValue(r.value); setIsCustom(r.is_custom); toastSuccess("已保存"); })
      .catch(() => toastError("保存失败")).finally(() => setBusy(false));
  };
  const restore = () => {
    setResetBusy(true);
    resetAiEvalPrompt()
      .then(r => { setValue(r.value); setIsCustom(r.is_custom); toastSuccess("已还原默认"); })
      .catch(() => toastError("还原失败")).finally(() => setResetBusy(false));
  };
  return (
    <div className="mt-8 rounded-2xl bg-white p-6 ring-1 ring-slate-200/70">
      <div className="mb-1 flex items-center gap-2">
        <span className="text-[15px] font-semibold text-slate-800">AI 评估 Prompt</span>
        <Badge tone={isCustom ? "blue" : "gray"}>{isCustom ? "已自定义" : "默认"}</Badge>
      </div>
      <p className="mb-3 text-[12.5px] text-slate-500">AI 自动评估时给评判模型的系统指令,<b>按用户隔离</b>:你改了就用你的,不影响别人;可一键还原默认。要求模型只输出 JSON(多候选选 winner 序号 / all_bad;单候选 good 真假)。</p>
      <textarea value={value} onChange={e => setValue(e.target.value)} rows={10}
        className="w-full rounded-lg bg-white px-3 py-2 text-sm text-slate-900 ring-1 ring-slate-200 outline-none focus:ring-2 focus:ring-brand-500 font-mono" />
      <div className="mt-3 flex items-center justify-end gap-2">
        <Button variant="subtle" disabled={!isCustom} loading={resetBusy} onClick={restore}>还原默认</Button>
        <Button variant="primary" loading={busy} onClick={save}>保存</Button>
      </div>
    </div>
  );
}

function AddModelInline({ onAdd }: { onAdd: (mid: string) => void }) {
  const [v, setV] = useState("");
  return (
    <div className="flex items-center gap-2 pt-0.5">
      <Input value={v} onChange={e => setV(e.target.value)} placeholder="新增 model-id" className="h-7 w-44 text-[12px]"
             onKeyDown={e => { if (e.key === "Enter") { onAdd(v); setV(""); } }} />
      <button onClick={() => { onAdd(v); setV(""); }}
              className="shrink-0 whitespace-nowrap text-[12px] font-medium text-brand-600 hover:underline">添加</button>
    </div>
  );
}
