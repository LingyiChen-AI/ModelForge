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

export type Dataset = { id: number; name: string; kind: string; task_type: string; created_at: string; created_by_name: string | null };
export type DatasetVersion = { id: number; version_no: number; row_count: number; checksum: string; note: string; created_at: string; created_by_name: string | null };

export const listDatasets = () => api.get<Dataset[]>("/datasets").then(r => r.data);
export const createDataset = (b: { name: string; kind: string; task_type: string }) =>
  api.post<Dataset>("/datasets", b).then(r => r.data);
export const listVersions = (id: number) =>
  api.get<DatasetVersion[]>(`/datasets/${id}/versions`).then(r => r.data);

// Flattened version picker options for a dataset kind (train / eval).
// There is no flat "all versions" endpoint, so we fan out per dataset.
export type VersionOption = { id: number; label: string; taskType: string };
export async function listVersionOptions(kind?: "train" | "eval" | "test"): Promise<VersionOption[]> {
  const datasets = await listDatasets();
  const scoped = kind ? datasets.filter(d => d.kind === kind) : datasets;
  const groups = await Promise.all(
    scoped.map(async d => (await listVersions(d.id)).map(v => ({
      id: v.id, label: `${d.name} · V${v.version_no}`, taskType: d.task_type,
    }))),
  );
  return groups.flat().sort((a, b) => b.id - a.id);
}

// Dataset → versions tree for cascade pickers (training).
export type DatasetNode = {
  id: number; name: string; taskType: string;
  versions: { id: number; version_no: number; row_count: number }[];
};
export async function listDatasetTree(kind?: "train" | "eval" | "test"): Promise<DatasetNode[]> {
  const datasets = await listDatasets();
  const scoped = kind ? datasets.filter(d => d.kind === kind) : datasets;
  return Promise.all(scoped.map(async d => ({
    id: d.id, name: d.name, taskType: d.task_type,
    versions: (await listVersions(d.id)).map(v => ({ id: v.id, version_no: v.version_no, row_count: v.row_count })),
  })));
}
export const uploadVersion = (id: number, file: File, note: string) => {
  const fd = new FormData(); fd.append("file", file); fd.append("note", note);
  return api.post<DatasetVersion>(`/datasets/${id}/versions`, fd).then(r => r.data);
};

export type TemplateFormat = "csv" | "jsonl" | "xlsx";
function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}
export async function downloadTemplate(id: number, fmt: TemplateFormat) {
  const res = await api.get(`/datasets/${id}/template`, { params: { fmt }, responseType: "blob" });
  triggerBlobDownload(res.data as Blob, `dataset-${id}-template.${fmt}`);
}
export async function downloadTemplateByType(taskType: string, fmt: TemplateFormat) {
  const res = await api.get(`/datasets/template`, { params: { task_type: taskType, fmt }, responseType: "blob" });
  triggerBlobDownload(res.data as Blob, `${taskType}-template.${fmt}`);
}
export async function downloadVersion(datasetId: number, versionId: number, versionNo: number, fmt: TemplateFormat) {
  const res = await api.get(`/datasets/${datasetId}/versions/${versionId}/download`, { params: { fmt }, responseType: "blob" });
  triggerBlobDownload(res.data as Blob, `dataset-${datasetId}-v${versionNo}.${fmt}`);
}

export type TrainingJob = { id: number; name: string; model_id: number | null; model_name: string | null; status: string; progress: number; mlflow_run_id: string | null; error: string | null; created_at: string; created_by_name: string | null; train_datasets: string[]; eval_datasets: string[]; metrics: Record<string, number> };
export const getConfig = () => api.get<{ mlflow_url: string }>("/config").then(r => r.data);

export type Stats = Record<string, number>;
export const getStats = () => api.get<Stats>("/stats").then(r => r.data);

export type Charts = {
  jobs_by_status?: Record<string, number>;
  versions_by_task?: Record<string, number>;
  datasets_by_kind?: Record<string, number>;
  deployments_by_status?: Record<string, number>;
};
export const getCharts = () => api.get<Charts>("/stats/charts").then(r => r.data);

// Named model container; each training run adds a version under it.
export type Model = {
  id: number; name: string; task_type: string; description: string;
  version_count: number; latest_version_id: number | null; latest_version: string | null;
  latest_metrics: Record<string, number>; latest_stage: string | null;
  created_at: string; created_by_name: string | null;
};
export const listModels = () => api.get<Model[]>("/models").then(r => r.data);
export const createModel = (b: { name: string; task_type: string; description?: string }) =>
  api.post<Model>("/models", b).then(r => r.data);
export type ModelTraining = { id: number; name: string; status: string; created_at: string; created_by_name: string | null; train_count: number; eval_count: number; train_datasets: string[]; eval_datasets: string[]; version_label: string | null; metrics: Record<string, number> };
export const listModelTrainings = (modelId: number) => api.get<ModelTraining[]>(`/models/${modelId}/trainings`).then(r => r.data);
export type ModelVersion = { id: number; name: string; mlflow_version: string; task_type: string; train_metrics: Record<string, number>; stage: string; created_at: string; created_by_name: string | null };
export const listJobs = () => api.get<TrainingJob[]>("/training-jobs").then(r => r.data);
export const createJob = (b: any) => api.post<TrainingJob>("/training-jobs", b).then(r => r.data);
export const deleteJob = (id: number, cascade: boolean) => api.delete(`/training-jobs/${id}`, { params: { cascade } }).then(r => r.data);
export const deleteModel = (id: number, cascade: boolean) => api.delete(`/models/${id}`, { params: { cascade } }).then(r => r.data);
export const listModelVersions = () => api.get<ModelVersion[]>("/model-versions").then(r => r.data);
export const setModelStage = (id: number, stage: string) =>
  api.patch<ModelVersion>(`/model-versions/${id}`, { stage }).then(r => r.data);

export type EvalRun = { id: number; model_version_id: number; model_name: string | null; model_version_label: string | null; dataset_version_id: number; dataset_name: string | null; dataset_version_no: number | null; status: string; progress: number; results: Record<string, number>; error: string | null; created_at: string; created_by_name: string | null };
export const listEvalRuns = (datasetVersionId?: number) =>
  api.get<EvalRun[]>("/eval-runs", { params: datasetVersionId ? { dataset_version_id: datasetVersionId } : {} }).then(r => r.data);
export const createEvalRun = (b: { model_version_id: number; dataset_version_id: number }) =>
  api.post<EvalRun>("/eval-runs", b).then(r => r.data);
export const deleteEvalRun = (id: number) => api.delete(`/eval-runs/${id}`).then(r => r.data);

export type Deployment = { id: number; model_version_id: number; status: string; endpoint: string | null; error: string | null; created_at: string; created_by_name: string | null };
export const listDeployments = () => api.get<Deployment[]>("/deployments").then(r => r.data);
export const createDeployment = (model_version_id: number) =>
  api.post<Deployment>("/deployments", { model_version_id }).then(r => r.data);
export const stopDeployment = (id: number) => api.post<Deployment>(`/deployments/${id}/stop`, {}).then(r => r.data);
export const startDeployment = (id: number) => api.post<Deployment>(`/deployments/${id}/start`, {}).then(r => r.data);
export const deleteDeployment = (id: number) => api.delete(`/deployments/${id}`).then(r => r.data);

export type AdminUser = { id: number; name: string; email: string; role_id: number | null; is_active: boolean; created_at: string };
export type Role = { id: number; name: string; description: string; data_scope: string; is_system: boolean; is_builtin: boolean; permissions: string[]; created_at: string };
export type Permission = { code: string; description: string };
export const listUsers = () => api.get<AdminUser[]>("/users").then(r => r.data);
export const createUser = (b: { name: string; email: string; password: string; role_id: number | null }) => api.post<AdminUser>("/users", b).then(r => r.data);
export const updateUser = (id: number, b: { role_id?: number | null; is_active?: boolean }) => api.patch<AdminUser>(`/users/${id}`, b).then(r => r.data);
export const resetPassword = (id: number, password: string) => api.post(`/users/${id}/reset-password`, { password }).then(r => r.data);
export const listRoles = () => api.get<Role[]>("/roles").then(r => r.data);
export const createRole = (b: { name: string; description: string; data_scope: string; permission_codes: string[] }) => api.post<Role>("/roles", b).then(r => r.data);
export const updateRole = (id: number, b: { name?: string; permission_codes?: string[]; data_scope?: string; description?: string }) => api.patch<Role>(`/roles/${id}`, b).then(r => r.data);
export const deleteRole = (id: number) => api.delete(`/roles/${id}`).then(r => r.data);
export const listPermissions = () => api.get<Permission[]>("/permissions").then(r => r.data);

export type ApiKey = { id: number; name: string; key_prefix: string; scopes: string[]; created_by_name: string | null; last_used_at: string | null; revoked_at: string | null; created_at: string };
export const listApiKeys = () => api.get<ApiKey[]>("/api-keys").then(r => r.data);
export const createApiKey = (b: { name: string; scopes: string[] }) => api.post<ApiKey & { plaintext: string }>("/api-keys", b).then(r => r.data);
export const revokeApiKey = (id: number) => api.delete(`/api-keys/${id}`).then(r => r.data);

export type Badcase = {
  id: number;
  model_version_id: number;
  model_name: string | null;
  model_version_label: string | null;
  task_type: string;
  input: Record<string, any>;
  inference: Record<string, any>;
  category: string | null;
  source: string | null;
  source_ref: string | null;
  status: string;
  annotation: Record<string, any> | null;
  dataset_version_id: number | null;
  fixed_by: { model_version_id: number; version_label: string; at?: string }[];
  created_at: string;
};
export const listBadcases = (p?: { model_version_id?: number; status?: string; category?: string }) =>
  api.get<Badcase[]>("/badcases", { params: p ?? {} }).then(r => r.data);
export const getBadcase = (id: number) => api.get<Badcase>(`/badcases/${id}`).then(r => r.data);
export const annotateBadcase = (id: number, annotation: Record<string, any>) =>
  api.patch<Badcase>(`/badcases/${id}/annotate`, { annotation }).then(r => r.data);
export const buildBadcaseDataset = (badcase_ids: number[], name?: string) =>
  api.post<{ dataset_id: number; dataset_name: string; version_id: number; version_no: number; row_count: number }>(
    "/badcases/build-dataset",
    { badcase_ids, name },
  ).then(r => r.data);
export const listBadcaseRules = () => api.get<{ rules: any[] }>("/badcase/rules").then(r => r.data.rules);
export type BadcaseSummary = {
  model_version_id: number;
  model_name: string | null;
  model_version_label: string | null;
  task_type: string;
  reported: number;
  annotated: number;
  used: number;
  pending: number;
  fixed: number;
  fixed_versions: string[];
};
export const listBadcaseSummary = () =>
  api.get<BadcaseSummary[]>("/badcases/summary").then(r => r.data);
