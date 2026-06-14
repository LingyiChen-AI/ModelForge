import { useEffect, useState } from "react";
import { listRoles, createRole, deleteRole, listPermissions,
         type Role, type Permission } from "../api/client";

export function RolesPage() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [perms, setPerms] = useState<Permission[]>([]);
  const [name, setName] = useState(""); const [scope, setScope] = useState("own");
  const [sel, setSel] = useState<string[]>([]);
  const reload = () => { listRoles().then(setRoles); listPermissions().then(setPerms); };
  useEffect(() => { reload(); }, []);
  const toggle = (c: string) => setSel(s => s.includes(c) ? s.filter(x => x !== c) : [...s, c]);
  return (
    <div>
      <h2>角色管理</h2>
      <div style={{ marginBottom: 12 }}>
        <input placeholder="角色名" value={name} onChange={e => setName(e.target.value)} />
        <select value={scope} onChange={e => setScope(e.target.value)}>
          <option value="own">own</option><option value="all">all</option>
        </select>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, margin: "8px 0" }}>
          {perms.filter(p => p.code !== "*").map(p =>
            <label key={p.code}><input type="checkbox" checked={sel.includes(p.code)} onChange={() => toggle(p.code)} />{p.code}</label>)}
        </div>
        <button disabled={!name} onClick={() =>
          createRole({ name, description: "", data_scope: scope, permission_codes: sel })
            .then(() => { setName(""); setSel([]); reload(); })}>新建角色</button>
      </div>
      <table><thead><tr><th>角色</th><th>scope</th><th>权限</th><th></th></tr></thead>
        <tbody>{roles.map(r => <tr key={r.id}>
          <td>{r.name}{r.is_system ? " (系统)" : ""}</td><td>{r.data_scope}</td>
          <td style={{ maxWidth: 360 }}>{r.permissions.join(", ")}</td>
          <td>{!r.is_system && <button onClick={() => deleteRole(r.id).then(reload).catch(() => alert("删除失败(可能被用户引用)"))}>删除</button>}</td>
        </tr>)}</tbody>
      </table>
    </div>
  );
}
