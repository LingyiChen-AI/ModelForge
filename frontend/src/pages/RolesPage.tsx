import { useEffect, useState } from "react";
import { ShieldCheck, Plus, Trash2, Lock } from "lucide-react";
import { listRoles, createRole, deleteRole, listPermissions, type Role, type Permission } from "../api/client";
import { Badge, Button, Card, EmptyState, Field, Input, Select, PageHeader, TableShell, cx } from "../ui";

export function RolesPage() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [perms, setPerms] = useState<Permission[]>([]);
  const [name, setName] = useState("");
  const [scope, setScope] = useState("own");
  const [sel, setSel] = useState<string[]>([]);
  const reload = () => { listRoles().then(setRoles); listPermissions().then(setPerms); };
  useEffect(() => { reload(); }, []);
  const toggle = (c: string) => setSel(s => s.includes(c) ? s.filter(x => x !== c) : [...s, c]);

  const create = () =>
    createRole({ name, description: "", data_scope: scope, permission_codes: sel })
      .then(() => { setName(""); setSel([]); reload(); })
      .catch(() => alert("创建失败(角色名可能已存在)"));

  return (
    <>
      <PageHeader title="角色管理" subtitle="自定义角色 = 固定权限目录的自由组合 + 数据范围(全部 / 仅自己)。" />

      <Card className="mb-5 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="角色名"><Input className="w-44" placeholder="如 labeler" value={name} onChange={e => setName(e.target.value)} /></Field>
          <Field label="数据范围"><Select value={scope} onChange={e => setScope(e.target.value)}>
            <option value="own">own · 仅自己</option><option value="all">all · 全部</option>
          </Select></Field>
        </div>
        <div className="mt-3">
          <div className="label mb-1.5">权限</div>
          <div className="flex flex-wrap gap-2">
            {perms.filter(p => p.code !== "*").map(p => {
              const on = sel.includes(p.code);
              return (
                <button key={p.code} type="button" onClick={() => toggle(p.code)}
                  className={cx("rounded-lg px-2.5 py-1 font-mono text-[12px] ring-1 transition cursor-pointer",
                    on ? "bg-brand-50 text-brand-700 ring-brand-300" : "bg-white text-slate-500 ring-slate-200 hover:ring-slate-300")}>
                  {p.code}
                </button>
              );
            })}
          </div>
        </div>
        <div className="mt-4">
          <Button variant="primary" disabled={!name} onClick={create}><Plus size={16} /> 新建角色</Button>
        </div>
      </Card>

      <TableShell
        empty={roles.length === 0}
        head={<><th>角色</th><th className="w-28">数据范围</th><th>权限</th><th className="w-20 text-right"></th></>}
      >
        {roles.length === 0 ? (
          <EmptyState icon={<ShieldCheck size={22} />} title="还没有角色" />
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
            <td className="text-right">
              {!r.is_builtin && (
                <Button size="sm" variant="danger" onClick={() => deleteRole(r.id).then(reload).catch(() => alert("删除失败(可能被用户引用)"))}>
                  <Trash2 size={13} />
                </Button>
              )}
            </td>
          </tr>
        ))}
      </TableShell>
    </>
  );
}
