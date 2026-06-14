import { DatasetsPage } from "./pages/DatasetsPage";
import { DatasetDetailPage } from "./pages/DatasetDetailPage";
import { TrainingPage } from "./pages/TrainingPage";
import { ModelsPage } from "./pages/ModelsPage";
import { EvalPage } from "./pages/EvalPage";
import { DeployPage } from "./pages/DeployPage";
import { LoginPage } from "./pages/LoginPage";
import { UsersPage } from "./pages/UsersPage";
import { RolesPage } from "./pages/RolesPage";
import { useAuth } from "./context/AuthContext";

export default function App() {
  const { me, loading, can, logout } = useAuth();
  const path = window.location.pathname;
  if (path === "/login") return <LoginPage />;
  if (loading) return <div>加载中…</div>;
  if (!me) { location.href = "/login"; return null; }

  const m = path.match(/^\/datasets\/(\d+)$/);
  let page = <DatasetsPage />;
  if (m) page = <DatasetDetailPage id={Number(m[1])} />;
  else if (path === "/training") page = <TrainingPage />;
  else if (path === "/models") page = <ModelsPage />;
  else if (path === "/eval") page = <EvalPage />;
  else if (path === "/deploy") page = <DeployPage />;
  else if (path === "/users") page = <UsersPage />;
  else if (path === "/roles") page = <RolesPage />;
  return (
    <div>
      <nav style={{ display: "flex", gap: 12, marginBottom: 16, alignItems: "center" }}>
        <a href="/">数据集</a><a href="/training">训练</a><a href="/models">模型</a>
        <a href="/eval">评估</a><a href="/deploy">部署</a>
        {can("user:manage") && <a href="/users">用户</a>}
        {can("role:manage") && <a href="/roles">角色</a>}
        <span style={{ marginLeft: "auto" }}>{me.name} ({me.role}) <button onClick={logout}>登出</button></span>
      </nav>
      {page}
    </div>
  );
}
