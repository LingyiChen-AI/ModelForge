// Per-task API docs for a deployed model (matches services/model-server).
export type ApiField = { name: string; type: string; desc: string };
export type ApiDoc = {
  taskLabel: string;
  method: string;
  url: string;
  reqFields: ApiField[];
  curl: string;
  respExample: string;
  respDesc: string;
};

const TASK_LABEL: Record<string, string> = {
  classification: "分类", ner: "序列标注", pair: "句对", embedding: "向量",
};

function originOf(endpoint: string | null): string {
  try { return new URL(endpoint ?? "").origin; } catch { return "http://localhost:8001"; }
}

function make(base: string, path: string, body: unknown, respExample: unknown,
             respDesc: string, reqFields: ApiField[], taskType: string): ApiDoc {
  const url = `${base}${path}`;
  const curl = `curl -X POST ${url} \\\n  -H 'Content-Type: application/json' \\\n  -d '${JSON.stringify(body)}'`;
  return {
    taskLabel: TASK_LABEL[taskType] ?? taskType,
    method: "POST", url, reqFields, curl,
    // Unified envelope: { code, data, message }. code=0 表示成功。
    respExample: JSON.stringify({ code: 0, data: respExample, message: "success" }, null, 2),
    respDesc,
  };
}

export function buildApiDoc(taskType: string, mvId: number, endpoint: string | null): ApiDoc {
  const base = originOf(endpoint);
  const idField: ApiField = { name: "model_version_id", type: "int", desc: "已部署的模型版本 ID" };

  if (taskType === "classification")
    return make(base, "/predict",
      { model_version_id: mvId, texts: ["这家店的服务怎么样", "我要退货"] },
      { predictions: [{ label: "售前咨询", score: 0.97 }, { label: "售后服务", score: 0.93 }] },
      "data.predictions 与 texts 一一对应,每项含预测类别 label 与置信度 score(0~1)。",
      [idField, { name: "texts", type: "string[]", desc: "待分类文本列表" }], taskType);

  if (taskType === "ner")
    return make(base, "/predict",
      { model_version_id: mvId, texts: ["小明 在 北京 工作"] },
      { predictions: [["B-PER", "I-PER", "O", "B-LOC", "I-LOC", "O", "O"]] },
      "文本按空格切成 token,data.predictions 为每条文本的逐 token 标签序列(与 token 一一对应)。",
      [idField, { name: "texts", type: "string[]", desc: "待识别文本,token 之间用空格分隔" }], taskType);

  if (taskType === "embedding")
    return make(base, "/embed",
      { model_version_id: mvId, texts: ["如何重置密码", "怎么开发票"] },
      { embeddings: [[0.013, -0.021, 0.08], [0.004, 0.067, -0.012]] },
      "data.embeddings 为每条文本的归一化向量(L2=1,维度由模型决定),可直接用内积/余弦做相似检索。",
      [idField, { name: "texts", type: "string[]", desc: "待编码文本列表" }], taskType);

  // pair
  return make(base, "/similarity",
    { model_version_id: mvId, pairs: [["今天天气怎么样", "今天的天气如何"]] },
    { scores: [0.86] },
    "data.scores 为每个句对的相似度打分,与 pairs 一一对应;最外层统一为 {code, data, message},code=0 表示成功。",
    [idField, { name: "pairs", type: "[string, string][]", desc: "句对列表,每项是两段文本" }], taskType);
}
