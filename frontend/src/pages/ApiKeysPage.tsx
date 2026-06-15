import { useEffect, useState } from "react";
import { KeyRound, Plus, Copy, Check, Ban } from "lucide-react";
import { listApiKeysPaged, createApiKey, revokeApiKey, type ApiKey } from "../api/client";
import { Badge, Button, ConfirmDialog, Drawer, EmptyState, Field, Input, Mono, PageHeader, Pagination, TableShell, Creator, CreatedAt } from "../ui";
import { toastError, toastSuccess } from "../toast";

const SCOPES = [
  { code: "inference", label: "推理调用(/predict /embed /similarity)" },
  { code: "badcase:report", label: "Badcase 上报(/badcase/report)" },
];

export function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<string[]>([]);
  const [created, setCreated] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [revoke, setRevoke] = useState<ApiKey | null>(null);
  const [revBusy, setRevBusy] = useState(false);
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const copyKey = (k: ApiKey) => {
    navigator.clipboard.writeText(k.plaintext ?? k.key_prefix);
    setCopiedId(k.id);
    setTimeout(() => setCopiedId(c => (c === k.id ? null : c)), 1500);
    toastSuccess(k.plaintext ? "已复制完整 Key" : "该 Key 创建较早无明文,仅复制了前缀");
  };
  const reload = () => listApiKeysPaged({ page, page_size: pageSize }).then(res => { setKeys(res.items); setTotal(res.total); });
  useEffect(() => { reload().finally(() => setLoading(false)); }, [page, pageSize]);

  const openDrawer = () => { setName(""); setScopes([]); setBusy(false); setOpen(true); };
  const toggle = (c: string) => setScopes(s => s.includes(c) ? s.filter(x => x !== c) : [...s, c]);
  const submit = () => {
    setBusy(true);
    createApiKey({ name, scopes }).then(k => { setOpen(false); setCreated(k.plaintext); setCopied(false); reload(); })
      .catch(() => toastError("创建失败")).finally(() => setBusy(false));
  };
  const doRevoke = () => {
    if (!revoke) return;
    setRevBusy(true);
    revokeApiKey(revoke.id).then(() => { setRevoke(null); reload(); })
      .catch(() => toastError("吊销失败")).finally(() => setRevBusy(false));
  };

  return (
    <>
      <PageHeader title="API Key" subtitle="对外鉴权令牌:用于在线推理调用与 Badcase 上报。可随时复制完整明文。"
        actions={<Button variant="primary" onClick={openDrawer}><Plus size={16} /> 新建 Key</Button>} />

      <TableShell loading={loading} empty={keys.length === 0}
        head={<><th>名称</th><th>前缀</th><th>权限范围</th><th>状态</th><th>创建者</th><th className="w-36">创建时间</th><th className="w-44 text-right"></th></>}>
        {keys.length === 0 ? <EmptyState icon={<KeyRound size={22} />} title="还没有 API Key" /> :
          keys.map(k => (
            <tr key={k.id}>
              <td className="font-medium text-slate-800">{k.name}</td>
              <td><Mono>{k.key_prefix}…</Mono></td>
              <td><div className="flex flex-wrap gap-1">{k.scopes.map(s => <span key={s} className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-600">{s}</span>)}</div></td>
              <td>{k.revoked_at ? <Badge tone="gray" dot>已吊销</Badge> : <Badge tone="green" dot>有效</Badge>}</td>
              <td><Creator name={k.created_by_name} /></td>
              <td><CreatedAt at={k.created_at} /></td>
              <td className="text-right">
                <div className="flex items-center justify-end gap-2">
                  <Button size="sm" variant="subtle" onClick={() => copyKey(k)}>
                    {copiedId === k.id ? <Check size={13} /> : <Copy size={13} />} 复制
                  </Button>
                  {!k.revoked_at && <Button size="sm" variant="danger" onClick={() => setRevoke(k)}><Ban size={13} /> 吊销</Button>}
                </div>
              </td>
            </tr>
          ))}
      </TableShell>
      <Pagination page={page} pageSize={pageSize} total={total} onPage={setPage} onPageSize={s => { setPageSize(s); setPage(1); }} />

      <Drawer open={open} onClose={() => setOpen(false)} title="新建 API Key"
        subtitle="选择该 Key 可用于哪些接口。创建后请立即复制保存明文,之后无法再查看。"
        footer={<div className="flex items-center justify-end gap-2">
          <Button variant="subtle" disabled={busy} onClick={() => setOpen(false)}>取消</Button>
          <Button variant="primary" disabled={!name || scopes.length === 0} loading={busy} onClick={submit}><Plus size={16} /> 创建</Button>
        </div>}>
        <div className="flex flex-col gap-4">
          <Field label="名称"><Input placeholder="如 客服系统-生产" value={name} onChange={e => setName(e.target.value)} /></Field>
          <div>
            <div className="label mb-1.5">权限范围</div>
            <div className="flex flex-col gap-1.5">
              {SCOPES.map(s => (
                <label key={s.code} onClick={() => toggle(s.code)}
                  className={`flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 ${scopes.includes(s.code) ? "border-brand-300 bg-brand-50" : "border-slate-200 hover:border-slate-300"}`}>
                  <span className={`flex h-4 w-4 items-center justify-center rounded border ${scopes.includes(s.code) ? "border-brand-500 bg-brand-500 text-white" : "border-slate-300"}`}>{scopes.includes(s.code) && <Check size={12} strokeWidth={3} />}</span>
                  <span className="font-mono text-[12.5px] text-slate-700">{s.code}</span>
                  <span className="ml-auto text-[11.5px] text-slate-400">{s.label}</span>
                </label>
              ))}
            </div>
          </div>
        </div>
      </Drawer>

      <ConfirmDialog open={created !== null} title="API Key 已创建" confirmText="我已保存"
        message={<div className="flex flex-col gap-2">
          <div className="text-[13px] text-slate-600">请立即复制保存,关闭后将无法再次查看:</div>
          <div className="flex items-center gap-2 rounded-lg bg-slate-900 p-3">
            <Mono className="flex-1 break-all text-slate-100">{created}</Mono>
            <Button size="sm" onClick={() => { navigator.clipboard.writeText(created!); setCopied(true); toastSuccess("已复制"); }}>
              {copied ? <Check size={13} /> : <Copy size={13} />}
            </Button>
          </div>
        </div>}
        onCancel={() => setCreated(null)} onConfirm={() => setCreated(null)} />

      <ConfirmDialog open={revoke !== null} title="吊销 API Key" confirmText="吊销" busy={revBusy}
        message={<>确定吊销 <b className="text-slate-700">{revoke?.name}</b>?吊销后该 Key 立即失效(上报与推理两端都实时校验)。</>}
        onCancel={() => setRevoke(null)} onConfirm={doRevoke} />
    </>
  );
}
