import { useState } from "react";
import { Boxes, Rocket, Bug, ShieldCheck, ArrowRight } from "lucide-react";
import { login } from "../auth";
import { useAuth } from "../context/AuthContext";
import { Button, Field, Input } from "../ui";
import { navigate } from "../router";
import { Logo } from "../components/Logo";

const FEATURES = [
  { icon: Boxes, title: "数据 · 训练一站式", desc: "上传数据集、版本化管理,分类 / 序列标注 / 句对 / 向量检索一键开练。" },
  { icon: Rocket, title: "一键部署在线推理", desc: "训练好的模型版本秒级加载为 HTTP 服务,X-Api-Key 鉴权对外提供 API。" },
  { icon: Bug, title: "Badcase 闭环修复", desc: "线上坏例自动归集、标注、回流训练,按版本统计修复率,模型持续进化。" },
];

function BrandPanel() {
  return (
    <div className="relative hidden overflow-hidden bg-ink-950 lg:flex lg:flex-col lg:justify-between lg:p-14
                    [background-image:radial-gradient(45rem_30rem_at_85%_-10%,rgba(34,197,94,.18),transparent),radial-gradient(40rem_28rem_at_-15%_115%,rgba(56,189,248,.12),transparent)]">
      {/* texture grid */}
      <div className="pointer-events-none absolute inset-0 opacity-[0.5]
                      [background-image:linear-gradient(rgba(148,163,184,.06)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,.06)_1px,transparent_1px)]
                      [background-size:38px_38px] [mask-image:radial-gradient(60rem_40rem_at_50%_30%,#000,transparent)]" />
      {/* drifting glow blobs */}
      <div className="mf-drift pointer-events-none absolute -right-24 top-10 h-72 w-72 rounded-full bg-brand-500/20 blur-3xl" />
      <div className="mf-drift pointer-events-none absolute -left-20 bottom-8 h-64 w-64 rounded-full bg-sky-400/10 blur-3xl" style={{ animationDelay: "2s" }} />

      {/* brand mark */}
      <div className="relative mf-rise flex items-center gap-3">
        <Logo size={44} className="rounded-2xl shadow-lg shadow-black/40" />
        <div>
          <div className="text-[17px] font-semibold leading-tight text-white">ModelForge</div>
          <div className="text-[12px] text-slate-400">NLP 模型训练与服务平台</div>
        </div>
      </div>

      {/* headline + features */}
      <div className="relative max-w-md">
        <h2 className="mf-rise text-[30px] font-semibold leading-[1.25] tracking-tight text-white" style={{ animationDelay: "60ms" }}>
          把模型<span className="text-brand-400">锻造</span>成
          <br />随时可用的在线服务
        </h2>
        <p className="mf-rise mt-3 text-[13.5px] leading-relaxed text-slate-400" style={{ animationDelay: "120ms" }}>
          从数据到训练、评估、部署与坏例修复,一条流水线贯穿模型的完整生命周期。
        </p>

        <div className="mt-9 flex flex-col gap-4">
          {FEATURES.map((f, i) => (
            <div key={f.title} className="mf-rise flex items-start gap-3.5" style={{ animationDelay: `${180 + i * 80}ms` }}>
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white/5 ring-1 ring-white/10 backdrop-blur">
                <f.icon size={18} className="text-brand-400" />
              </div>
              <div>
                <div className="text-[14px] font-medium text-slate-100">{f.title}</div>
                <div className="mt-0.5 text-[12.5px] leading-relaxed text-slate-400">{f.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* footer note */}
      <div className="relative mf-rise flex items-center gap-2 text-[12px] text-slate-500" style={{ animationDelay: "440ms" }}>
        <ShieldCheck size={14} className="text-slate-500" />
        基于角色的权限管控 · 内部使用
      </div>
    </div>
  );
}

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
    <div className="grid min-h-dvh lg:grid-cols-[1.05fr_1fr] xl:grid-cols-[1.15fr_1fr]">
      <BrandPanel />

      {/* form side */}
      <div className="relative grid place-items-center bg-slate-50 px-5 py-10
                      [background-image:radial-gradient(36rem_24rem_at_120%_-10%,rgba(34,197,94,.06),transparent)]">
        <div className="mf-rise w-full max-w-sm">
          {/* compact brand for mobile (brand panel hidden) */}
          <div className="mb-8 flex flex-col items-center text-center lg:hidden">
            <Logo size={48} className="mb-3 rounded-2xl shadow-lg shadow-black/20" />
            <h1 className="text-lg font-semibold text-slate-900">ModelForge</h1>
            <p className="mt-0.5 text-[12.5px] text-slate-500">NLP 模型训练与服务平台</p>
          </div>

          <div className="mb-6 hidden lg:block">
            <h1 className="text-[22px] font-semibold tracking-tight text-slate-900">欢迎回来</h1>
            <p className="mt-1 text-[13px] text-slate-500">登录以继续使用 ModelForge 控制台。</p>
          </div>

          <div className="rounded-2xl bg-white p-6 shadow-xl shadow-slate-200/60 ring-1 ring-slate-200/70 sm:p-7">
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
              <Button type="submit" variant="primary" disabled={!email || !pw} loading={busy} className="mt-1 h-10 w-full justify-center">
                {busy ? "登录中…" : <>登录 <ArrowRight size={16} /></>}
              </Button>
            </form>
          </div>

          <p className="mt-6 text-center text-[11.5px] text-slate-400">© ModelForge · 内部使用</p>
        </div>
      </div>
    </div>
  );
}
