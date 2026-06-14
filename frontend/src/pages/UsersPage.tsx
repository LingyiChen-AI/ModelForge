import { useEffect, useState } from "react";
import { Users, UserPlus, KeyRound, Plus } from "lucide-react";
import { listUsers, createUser, updateUser, resetPassword, listRoles, type AdminUser, type Role } from "../api/client";
import { Badge, Button, Drawer, EmptyState, Field, Input, Mono, PageHeader, PromptDialog, Select, TableShell, CreatedAt } from "../ui";
import { toastError, toastSuccess } from "../toast";

export function UsersPage() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [acting, setActing] = useState<number | null>(null);
  const [pwUser, setPwUser] = useState<AdminUser | null>(null);
  const [pwBusy, setPwBusy] = useState(false);
  const [f, setF] = useState({ name: "", email: "", password: "", role_id: "" });
  const reload = () => Promise.all([listUsers().then(setUsers), listRoles().then(setRoles)]);
  useEffect(() => { reload().finally(() => setLoading(false)); }, []);

  const openDrawer = () => { setF({ name: "", email: "", password: "", role_id: "" }); setBusy(false); setOpen(true); };
  const create = () => {
    setBusy(true);
    createUser({ name: f.name, email: f.email, password: f.password, role_id: f.role_id ? Number(f.role_id) : null })
      .then(() => { setOpen(false); reload(); })
      .catch(() => toastError("创建失败(邮箱可能已存在)"))
      .finally(() => setBusy(false));
  };
  const doResetPw = (pw: string) => {
    if (!pwUser) return;
    setPwBusy(true);
    resetPassword(pwUser.id, pw).then(() => { setPwUser(null); toastSuccess("密码已重置"); })
      .catch(() => toastError("重置失败")).finally(() => setPwBusy(false));
  };

  return (
    <>
      <PageHeader
        title="用户管理"
        subtitle="创建用户、分配角色、启停账号、重置密码。"
        actions={<Button variant="primary" onClick={openDrawer}><UserPlus size={16} /> 新建用户</Button>}
      />

      <TableShell
        loading={loading}
        empty={users.length === 0}
        head={<><th className="w-12">#</th><th>姓名</th><th>邮箱</th><th className="w-44">角色</th><th>状态</th><th className="w-36">创建时间</th><th className="w-44 text-right">操作</th></>}
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
            <td><CreatedAt at={u.created_at} /></td>
            <td>
              <div className="flex items-center justify-end gap-2">
                <Button size="sm" variant={u.is_active ? "danger" : "subtle"} loading={acting === u.id}
                        onClick={() => { setActing(u.id); updateUser(u.id, { is_active: !u.is_active }).then(reload).catch(() => toastError("操作失败(最后一个超管不可停用)")).finally(() => setActing(null)); }}>
                  {u.is_active ? "停用" : "启用"}
                </Button>
                <Button size="sm" onClick={() => setPwUser(u)}>
                  <KeyRound size={13} /> 改密
                </Button>
              </div>
            </td>
          </tr>
        ))}
      </TableShell>

      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title="新建用户"
        subtitle="设置初始密码并分配角色,用户登录后可自行使用。"
        footer={
          <div className="flex items-center justify-end gap-2">
            <Button variant="subtle" disabled={busy} onClick={() => setOpen(false)}>取消</Button>
            <Button variant="primary" disabled={!f.name || !f.email || !f.password} loading={busy} onClick={create}><Plus size={16} /> 创建</Button>
          </div>
        }
      >
        <div className="flex flex-col gap-4">
          <Field label="姓名"><Input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="邮箱"><Input type="email" value={f.email} onChange={e => setF({ ...f, email: e.target.value })} /></Field>
          <Field label="初始密码"><Input value={f.password} onChange={e => setF({ ...f, password: e.target.value })} /></Field>
          <Field label="角色"><Select value={f.role_id} onChange={e => setF({ ...f, role_id: e.target.value })}>
            <option value="">(无角色)</option>
            {roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
          </Select></Field>
        </div>
      </Drawer>

      <PromptDialog
        open={pwUser !== null}
        title="重置密码"
        label={`为用户 ${pwUser?.name ?? ""} 设置新密码`}
        placeholder="新密码"
        confirmText="重置"
        busy={pwBusy}
        onCancel={() => setPwUser(null)}
        onConfirm={doResetPw}
      />
    </>
  );
}
