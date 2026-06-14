import { useState } from "react";
import { LogIn } from "lucide-react";
import { login } from "../auth";
import { useAuth } from "../context/AuthContext";
import { Button, Field, Input } from "../ui";
import { navigate } from "../router";
import { Logo } from "../components/Logo";

export function LoginPage() {
  const { setMe } = useAuth();
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setErr(""); setBusy(true);
    try { const me = await login(email, pw); setMe(me); navigate("/"); }
    catch { setErr("邮箱或密码不正确"); }
    finally { setBusy(false); }
  };

  return (
    <div className="grid min-h-dvh place-items-center bg-ink-900 px-4
                    [background-image:radial-gradient(60rem_40rem_at_70%_-10%,rgba(34,197,94,.14),transparent),radial-gradient(50rem_30rem_at_-10%_110%,rgba(56,189,248,.10),transparent)]">
      <div className="w-full max-w-sm">
        <div className="mb-7 flex flex-col items-center text-center">
          <Logo size={56} className="mb-4 shadow-lg shadow-black/30 rounded-2xl" />
          <h1 className="text-xl font-semibold text-white">ModelForge</h1>
          <p className="mt-1 text-[13px] text-slate-400">NLP 模型训练与服务平台</p>
        </div>

        <div className="rounded-2xl bg-white p-6 shadow-2xl ring-1 ring-black/5">
          <form
            className="flex flex-col gap-4"
            onSubmit={e => { e.preventDefault(); if (!busy) submit(); }}
          >
            <Field label="邮箱">
              <Input type="email" autoComplete="username" placeholder="admin@modelforge.local"
                     value={email} onChange={e => setEmail(e.target.value)} autoFocus />
            </Field>
            <Field label="密码">
              <Input type="password" autoComplete="current-password" placeholder="••••••••"
                     value={pw} onChange={e => setPw(e.target.value)} />
            </Field>
            {err && (
              <div className="rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600 ring-1 ring-red-100">{err}</div>
            )}
            <Button type="submit" variant="primary" disabled={!email || !pw} loading={busy} className="h-10 mt-1">
              <LogIn size={16} /> {busy ? "登录中…" : "登录"}
            </Button>
          </form>
        </div>
        <p className="mt-5 text-center text-[11.5px] text-slate-500">© ModelForge · 内部使用</p>
      </div>
    </div>
  );
}
