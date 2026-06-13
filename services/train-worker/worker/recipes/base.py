from dataclasses import dataclass, field

@dataclass
class TrainResult:
    metrics: dict
    artifact_dir: str
    label_names: list[str] = field(default_factory=list)

class Recipe:
    def train(self, df, base_model, hyperparams, output_dir) -> TrainResult:
        raise NotImplementedError
