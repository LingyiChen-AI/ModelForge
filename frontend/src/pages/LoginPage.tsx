import { useState } from "react";
import { login } from "../auth";
import { useAuth } from "../context/AuthContext";

export function LoginPage() {
  const { setMe } = useAuth();
  const [email, setEmail] = useState(""); const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const submit = async () => {
    try { const me = await login(email, pw); setMe(me); location.href = "/"; }
    catch { setErr("登录失败"); }
  };
  return (
    <div style={{ maxWidth: 320, margin: "80px auto" }}>
      <h2>登录 ModelForge</h2>
      <input placeholder="email" value={email} onChange={e => setEmail(e.target.value)} style={{ display: "block", width: "100%", marginBottom: 8 }} />
      <input placeholder="password" type="password" value={pw} onChange={e => setPw(e.target.value)} style={{ display: "block", width: "100%", marginBottom: 8 }} />
      <button onClick={submit}>登录</button>
      {err && <p style={{ color: "red" }}>{err}</p>}
    </div>
  );
}
