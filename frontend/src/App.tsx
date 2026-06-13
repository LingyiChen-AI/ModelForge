import { DatasetsPage } from "./pages/DatasetsPage";
import { DatasetDetailPage } from "./pages/DatasetDetailPage";
import { TrainingPage } from "./pages/TrainingPage";
import { ModelsPage } from "./pages/ModelsPage";
import { EvalPage } from "./pages/EvalPage";

export default function App() {
  const path = window.location.pathname;
  const m = path.match(/^\/datasets\/(\d+)$/);
  let page = <DatasetsPage />;
  if (m) page = <DatasetDetailPage id={Number(m[1])} />;
  else if (path === "/training") page = <TrainingPage />;
  else if (path === "/models") page = <ModelsPage />;
  else if (path === "/eval") page = <EvalPage />;
  return (
    <div>
      <nav style={{ display: "flex", gap: 12, marginBottom: 16 }}>
        <a href="/">数据集</a><a href="/training">训练</a><a href="/models">模型</a><a href="/eval">评估</a>
      </nav>
      {page}
    </div>
  );
}
