import { useEffect, useState } from "react";
import { Users, UserPlus, KeyRound } from "lucide-react";
import { listUsers, createUser, updateUser, resetPassword, listRoles, type AdminUser, type Role } from "../api/client";
import { Badge, Button, Card, EmptyState, Field, Input, Mono, PageHeader, Select, TableShell } from "../ui";

export function UsersPage() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [f, setF] = useState({ name: "", email: "", password: "", role_id: "" });
  const reload = () => { listUsers().then(setUsers); listRoles().then(setRoles); };
  useEffect(() => { reload(); }, []);

  const create = () =>
    createUser({ name: f.name, email: f.email, password: f.password, role_id: f.role_id ? Number(f.role_id) : null })
      .then(() => { setF({ name: "", email: "", password: "", role_id: "" }); reload(); })
      .catch(() => alert("创建失败(邮箱可能已存在)"));

  return (
    <>
      <PageHeader title="用户管理" subtitle="创建用户、分配角色、启停账号、重置密码。" />

      <Card className="mb-5 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="姓名"><Input className="w-36" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></Field>
          <div className="grow min-w-[180px]"><Field label="邮箱"><Input value={f.email} onChange={e => setF({ ...f, email: e.target.value })} /></Field></div>
          <Field label="初始密码"><Input className="w-36" value={f.password} onChange={e => setF({ ...f, password: e.target.value })} /></Field>
          <Field label="角色"><Select value={f.role_id} onChange={e => setF({ ...f, role_id: e.target.value })}>
            <option value="">(无角色)</option>
            {roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
          </Select></Field>
          <Button variant="primary" disabled={!f.name || !f.email || !f.password} onClick={create}><UserPlus size={16} /> 新建用户</Button>
        </div>
      </Card>

      <TableShell
        empty={users.length === 0}
        head={<><th className="w-12">#</th><th>姓名</th><th>邮箱</th><th className="w-44">角色</th><th>状态</th><th className="w-44 text-right">操作</th></>}
      >
        {users.length === 0 ? (
          <EmptyState icon={<Users size={22} />} title="还没有用户" />
        ) : users.map(u => (
          <tr key={u.id}>
            <td><Mono>{u.id}</Mono></td>
            <td className="font-medium text-slate-800">{u.name}</td>
            <td className="text-slate-500">{u.email}</td>
            <td>
              <Select className="h-8 text-[13px]" value={u.role_id ?? ""} onChange={e =>
                updateUser(u.id, { role_id: e.target.value ? Number(e.target.value) : null }).then(reload)}>
                <option value="">(无)</option>
                {roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
              </Select>
            </td>
            <td>{u.is_active ? <Badge tone="green" dot>在职</Badge> : <Badge tone="gray" dot>停用</Badge>}</td>
            <td>
              <div className="flex items-center justify-end gap-2">
                <Button size="sm" variant={u.is_active ? "danger" : "subtle"}
                        onClick={() => updateUser(u.id, { is_active: !u.is_active }).then(reload).catch(() => alert("操作失败(最后一个超管不可停用)"))}>
                  {u.is_active ? "停用" : "启用"}
                </Button>
                <Button size="sm" onClick={() => { const p = prompt("新密码"); if (p) resetPassword(u.id, p).then(() => alert("已重置")); }}>
                  <KeyRound size={13} /> 改密
                </Button>
              </div>
            </td>
          </tr>
        ))}
      </TableShell>
    </>
  );
}
