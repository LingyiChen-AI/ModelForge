import { DashboardPage } from "./pages/DashboardPage";
import { DatasetsPage } from "./pages/DatasetsPage";
import { DatasetDetailPage } from "./pages/DatasetDetailPage";
import { TrainingPage } from "./pages/TrainingPage";
import { ModelsPage } from "./pages/ModelsPage";
import { EvalPage } from "./pages/EvalPage";
import { DeployPage } from "./pages/DeployPage";
import { LoginPage } from "./pages/LoginPage";
import { UsersPage } from "./pages/UsersPage";
import { RolesPage } from "./pages/RolesPage";
import { ApiKeysPage } from "./pages/ApiKeysPage";
import { useAuth } from "./context/AuthContext";
import { AppShell } from "./components/AppShell";
import { Spinner } from "./ui";
import { usePath } from "./router";

export default function App() {
  const { me, loading } = useAuth();
  const path = usePath();

  if (path === "/login") return <LoginPage />;
  if (loading) {
    return (
      <div className="grid min-h-dvh place-items-center bg-slate-50 text-slate-400">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }
  if (!me) { window.location.href = "/login"; return null; }

  const detail = path.match(/^\/datasets\/(\d+)$/);
  let page = <DashboardPage />;
  if (detail) page = <DatasetDetailPage id={Number(detail[1])} />;
  else if (path === "/datasets") page = <DatasetsPage />;
  else if (path === "/training") page = <TrainingPage />;
  else if (path === "/models") page = <ModelsPage />;
  else if (path === "/eval") page = <EvalPage />;
  else if (path === "/deploy") page = <DeployPage />;
  else if (path === "/users") page = <UsersPage />;
  else if (path === "/roles") page = <RolesPage />;
  else if (path === "/api-keys") page = <ApiKeysPage />;

  return <AppShell path={path}>{page}</AppShell>;
}
