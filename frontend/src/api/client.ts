import axios from "axios";

export const api = axios.create({ baseURL: import.meta.env.VITE_API_URL ?? "http://localhost:8000" });

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
