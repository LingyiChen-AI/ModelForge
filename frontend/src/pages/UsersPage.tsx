import { useEffect, useState } from "react";
import { listUsers, createUser, updateUser, resetPassword, listRoles,
         type AdminUser, type Role } from "../api/client";

export function UsersPage() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [f, setF] = useState({ name: "", email: "", password: "", role_id: "" });
  const reload = () => { listUsers().then(setUsers); listRoles().then(setRoles); };
  useEffect(() => { reload(); }, []);
  return (
    <div>
      <h2>用户管理</h2>
      <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
        <input placeholder="name" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} />
        <input placeholder="email" value={f.email} onChange={e => setF({ ...f, email: e.target.value })} />
        <input placeholder="password" value={f.password} onChange={e => setF({ ...f, password: e.target.value })} />
        <select value={f.role_id} onChange={e => setF({ ...f, role_id: e.target.value })}>
          <option value="">(角色)</option>
          {roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
        </select>
        <button disabled={!f.name || !f.email || !f.password} onClick={() =>
          createUser({ name: f.name, email: f.email, password: f.password,
                       role_id: f.role_id ? Number(f.role_id) : null })
            .then(() => { setF({ name: "", email: "", password: "", role_id: "" }); reload(); })}>新建用户</button>
      </div>
      <table><thead><tr><th>#</th><th>名称</th><th>email</th><th>角色</th><th>状态</th><th></th></tr></thead>
        <tbody>{users.map(u => <tr key={u.id}>
          <td>{u.id}</td><td>{u.name}</td><td>{u.email}</td>
          <td><select value={u.role_id ?? ""} onChange={e =>
            updateUser(u.id, { role_id: e.target.value ? Number(e.target.value) : null }).then(reload)}>
            <option value="">(无)</option>
            {roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select></td>
          <td>{u.is_active ? "在职" : "停用"}</td>
          <td>
            <button onClick={() => updateUser(u.id, { is_active: !u.is_active }).then(reload)}>{u.is_active ? "停用" : "启用"}</button>
            <button onClick={() => { const p = prompt("新密码"); if (p) resetPassword(u.id, p); }}>改密</button>
          </td></tr>)}</tbody>
      </table>
    </div>
  );
}
