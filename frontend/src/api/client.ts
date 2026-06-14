import axios from "axios";

export const api = axios.create({ baseURL: import.meta.env.VITE_API_URL ?? "http://localhost:8000" });

api.interceptors.request.use(cfg => {
  const t = localStorage.getItem("mf_token");
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});
api.interceptors.response.use(r => r, err => {
  if (err.response?.status === 401) {
    localStorage.removeItem("mf_token");
    if (location.pathname !== "/login") location.href = "/login";
  }
  return Promise.reject(err);
});

export type Dataset = { id: number; name: string; kind: string; task_type: string };
export type DatasetVersion = { id: number; version_no: number; row_count: number; checksum: string; note: string };

export const listDatasets = () => api.get<Dataset[]>("/datasets").then(r => r.data);
export const createDataset = (b: { name: string; kind: string; task_type: string }) =>
  api.post<Dataset>("/datasets", b).then(r => r.data);
export const listVersions = (id: number) =>
  api.get<DatasetVersion[]>(`/datasets/${id}/versions`).then(r => r.data);
export const uploadVersion = (id: number, file: File, note: string) => {
  const fd = new FormData(); fd.append("file", file); fd.append("note", note);
  return api.post<DatasetVersion>(`/datasets/${id}/versions`, fd).then(r => r.data);
};

export type TrainingJob = { id: number; name: string; status: string; error: string | null };
export type ModelVersion = { id: number; name: string; mlflow_version: string; task_type: string; train_metrics: Record<string, number>; stage: string };
export const listJobs = () => api.get<TrainingJob[]>("/training-jobs").then(r => r.data);
export const createJob = (b: any) => api.post<TrainingJob>("/training-jobs", b).then(r => r.data);
export const listModelVersions = () => api.get<ModelVersion[]>("/model-versions").then(r => r.data);

export type EvalRun = { id: number; model_version_id: number; dataset_version_id: number; status: string; results: Record<string, number>; error: string | null };
export const listEvalRuns = (datasetVersionId?: number) =>
  api.get<EvalRun[]>("/eval-runs", { params: datasetVersionId ? { dataset_version_id: datasetVersionId } : {} }).then(r => r.data);
export const createEvalRun = (b: { model_version_id: number; dataset_version_id: number }) =>
  api.post<EvalRun>("/eval-runs", b).then(r => r.data);

export type Deployment = { id: number; model_version_id: number; status: string; endpoint: string | null; error: string | null };
export const listDeployments = () => api.get<Deployment[]>("/deployments").then(r => r.data);
export const createDeployment = (model_version_id: number) =>
  api.post<Deployment>("/deployments", { model_version_id }).then(r => r.data);
export const stopDeployment = (id: number) => api.post<Deployment>(`/deployments/${id}/stop`, {}).then(r => r.data);
