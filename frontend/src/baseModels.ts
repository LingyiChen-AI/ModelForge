// Curated catalog of fine-tunable base models, by HuggingFace repo id.
// Grouped by which ModelForge task types each family fits:
//   - BERT encoders  → classification / ner / pair
//   - BGE / GTE       → embedding
// Repo ids verified against huggingface.co (google-bert/*, BAAI/*, Alibaba-NLP/* namespaces).
export type BaseModelGroup = { group: string; tasks: string[]; options: { id: string; label: string }[] };

export const BASE_MODEL_GROUPS: BaseModelGroup[] = [
  {
    group: "通用编码器 · 分类 / 序列标注 / 句对",
    tasks: ["classification", "ner", "pair"],
    options: [
      { id: "prajjwal1/bert-tiny", label: "bert-tiny · 快速测试(最快)" },
      { id: "google-bert/bert-base-chinese", label: "BERT 中文 · base" },
      { id: "google-bert/bert-base-multilingual-cased", label: "BERT 多语 · base (cased)" },
      { id: "google-bert/bert-base-uncased", label: "BERT 英文 · base (uncased)" },
      { id: "google-bert/bert-base-cased", label: "BERT 英文 · base (cased)" },
      { id: "google-bert/bert-large-uncased", label: "BERT 英文 · large" },
    ],
  },
  {
    group: "向量模型 · embedding 微调",
    tasks: ["embedding"],
    options: [
      { id: "BAAI/bge-small-zh-v1.5", label: "BGE 中文 · small v1.5" },
      { id: "BAAI/bge-base-zh-v1.5", label: "BGE 中文 · base v1.5" },
      { id: "BAAI/bge-large-zh-v1.5", label: "BGE 中文 · large v1.5" },
      { id: "BAAI/bge-base-en-v1.5", label: "BGE 英文 · base v1.5" },
      { id: "BAAI/bge-large-en-v1.5", label: "BGE 英文 · large v1.5" },
      { id: "BAAI/bge-m3", label: "BGE-M3 · 多语 / 长文本" },
      { id: "thenlper/gte-base", label: "GTE 英文 · base" },
      { id: "thenlper/gte-large", label: "GTE 英文 · large" },
      { id: "Alibaba-NLP/gte-multilingual-base", label: "GTE 多语 · base" },
      { id: "Alibaba-NLP/gte-large-en-v1.5", label: "GTE 英文 · large v1.5" },
    ],
  },
];

// Task types a base model can be fine-tuned on (drives the dataset linkage).
export function tasksForModel(modelId: string): string[] {
  return BASE_MODEL_GROUPS.find(g => g.options.some(o => o.id === modelId))?.tasks ?? [];
}
