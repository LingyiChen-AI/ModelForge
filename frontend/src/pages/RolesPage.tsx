import { useEffect, useState } from "react";
import { ShieldCheck, Plus, Trash2, Lock, Check, Pencil } from "lucide-react";
import { listRoles, createRole, updateRole, deleteRole, listPermissions, type Role, type Permission } from "../api/client";
import { Badge, Button, Drawer, EmptyState, Field, Input, Select, PageHeader, TableShell, CreatedAt, cx } from "../ui";
import { toastError } from "../toast";

export function RolesPage() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [perms, setPerms] = useState<Permission[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [delId, setDelId] = useState<number | null>(null);
  const [editId, setEditId] = useState<number | null>(null);   // null = create mode
  const [name, setName] = useState("");
  const [scope, setScope] = useState("own");
  const [sel, setSel] = useState<string[]>([]);
  const reload = () => Promise.all([listRoles().then(setRoles), listPermissions().then(setPerms)]);
  useEffect(() => { reload().finally(() => setLoading(false)); }, []);

  const toggle = (c: string) => setSel(s => s.includes(c) ? s.filter(x => x !== c) : [...s, c]);
  const selectable = perms.filter(p => p.code !== "*");
  const allOn = selectable.length > 0 && sel.length === selectable.length;

  const openDrawer = () => { setEditId(null); setName(""); setScope("own"); setSel([]); setBusy(false); setOpen(true); };
  const openEdit = (r: Role) => {
    setEditId(r.id); setName(r.name); setScope(r.data_scope);
    setSel(r.permissions.filter(c => c !== "*")); setBusy(false); setOpen(true);
  };

  const submit = () => {
    setBusy(true);
    const p = editId == null
      ? createRole({ name, description: "", data_scope: scope, permission_codes: sel })
      : updateRole(editId, { name, data_scope: scope, permission_codes: sel });
    p.then(() => { setOpen(false); reload(); })
      .catch(() => toastError(editId == null ? "创建失败(角色名可能已存在)" : "保存失败(角色名可能已存在)"))
      .finally(() => setBusy(false));
  };
  const remove = (id: number) => {
    setDelId(id);
    deleteRole(id).then(reload).catch(() => toastError("删除失败(可能被用户引用)")).finally(() => setDelId(null));
  };

  return (
    <>
      <PageHeader
        title="角色管理"
        subtitle="自定义角色 = 固定权限目录的自由组合 + 数据范围(全部 / 仅自己)。"
        actions={<Button variant="primary" onClick={openDrawer}><Plus size={16} /> 新建角色</Button>}
      />

      <TableShell
        loading={loading}
        empty={roles.length === 0}
        head={<><th>角色</th><th className="w-28">数据范围</th><th>权限</th><th className="w-36">创建时间</th><th className="w-40 text-right"></th></>}
      >
        {roles.length === 0 ? (
          <EmptyState icon={<ShieldCheck size={22} />} title="还没有角色" hint="点击右上角「新建角色」创建第一个自定义角色。" />
        ) : roles.map(r => (
          <tr key={r.id}>
            <td>
              <div className="flex items-center gap-2">
                <span className="font-medium text-slate-800">{r.name}</span>
                {r.is_system
                  ? <Badge tone="gray"><Lock size={10} /> 系统</Badge>
                  : r.is_builtin && <Badge tone="gray"><Lock size={10} /> 内置</Badge>}
              </div>
            </td>
            <td><Badge tone={r.data_scope === "all" ? "blue" : "gray"}>{r.data_scope}</Badge></td>
            <td>
              <div className="flex flex-wrap gap-1">
                {r.permissions.map(c => (
                  <span key={c} className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-500">{c}</span>
                ))}
              </div>
            </td>
            <td><CreatedAt at={r.created_at} /></td>
            <td className="text-right">
              {!r.is_builtin && (
                <div className="flex items-center justify-end gap-2">
                  <Button size="sm" onClick={() => openEdit(r)}><Pencil size={13} /> 编辑</Button>
                  <Button size="sm" variant="danger" loading={delId === r.id} onClick={() => remove(r.id)}>
                    <Trash2 size={13} />
                  </Button>
                </div>
              )}
            </td>
          </tr>
        ))}
      </TableShell>

      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title={editId == null ? "新建角色" : "编辑角色"}
        subtitle="勾选权限并选择数据范围,组合出一个自定义角色。"
        footer={
          <div className="flex items-center justify-between">
            <span className="text-[12px] text-slate-400">已选 {sel.length} 项权限</span>
            <div className="flex items-center gap-2">
              <Button variant="subtle" onClick={() => setOpen(false)}>取消</Button>
              <Button variant="primary" disabled={!name} loading={busy} onClick={submit}>
                {editId == null ? <><Plus size={16} /> 创建</> : <><Check size={16} /> 保存</>}
              </Button>
            </div>
          </div>
        }
      >
        <div className="flex flex-col gap-4">
          <Field label="角色名">
            <Input placeholder="如 labeler" value={name} onChange={e => setName(e.target.value)} />
          </Field>
          <Field label="数据范围">
            <Select value={scope} onChange={e => setScope(e.target.value)}>
              <option value="own">own · 仅自己创建的数据</option>
              <option value="all">all · 全部数据</option>
            </Select>
          </Field>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <span className="label">权限</span>
              <button
                type="button"
                onClick={() => setSel(allOn ? [] : selectable.map(p => p.code))}
                className="text-[12px] font-medium text-brand-600 hover:text-brand-700 cursor-pointer"
              >
                {allOn ? "清空" : "全选"}
              </button>
            </div>
            <div className="flex flex-col gap-1.5">
              {selectable.map(p => {
                const on = sel.includes(p.code);
                return (
                  <label
                    key={p.code}
                    onClick={() => toggle(p.code)}
                    className={cx(
                      "flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 transition",
                      on ? "border-brand-300 bg-brand-50" : "border-slate-200 bg-white hover:border-slate-300")}
                  >
                    <span className={cx(
                      "flex h-4 w-4 shrink-0 items-center justify-center rounded border transition",
                      on ? "border-brand-500 bg-brand-500 text-white" : "border-slate-300 bg-white")}>
                      {on && <Check size={12} strokeWidth={3} />}
                    </span>
                    <span className="font-mono text-[12.5px] text-slate-700">{p.code}</span>
                    {p.description && <span className="ml-auto truncate text-[11.5px] text-slate-400">{p.description}</span>}
                  </label>
                );
              })}
            </div>
          </div>
        </div>
      </Drawer>
    </>
  );
}
