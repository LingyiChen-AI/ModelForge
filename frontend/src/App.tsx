import { DatasetsPage } from "./pages/DatasetsPage";
import { DatasetDetailPage } from "./pages/DatasetDetailPage";

export default function App() {
  const m = window.location.pathname.match(/^\/datasets\/(\d+)$/);
  if (m) return <DatasetDetailPage id={Number(m[1])} />;
  return <DatasetsPage />;
}
