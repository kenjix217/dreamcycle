"""Optional local Transformers/PEFT LoRA training and evaluation."""

from __future__ import annotations

import asyncio
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dreamcycle.errors import (
    ConfigurationError,
    EvaluationError,
    OptionalDependencyError,
    TrainingError,
)
from dreamcycle.types import EvaluationResult, TrainingResult


@dataclass(frozen=True)
class TransformersLoRAConfig:
    base_model_path: Path
    rank: int = 16
    alpha: int = 32
    dropout: float = 0.05
    target_modules: tuple[str, ...] = ("q_proj", "v_proj")
    epochs: float = 1.0
    learning_rate: float = 2e-4
    batch_size: int = 1
    gradient_accumulation_steps: int = 8
    max_length: int = 1024
    seed: int = 42

    def __post_init__(self) -> None:
        if not self.base_model_path.expanduser().is_dir():
            raise ConfigurationError(
                f"base_model_path must be a local Hugging Face model directory: "
                f"{self.base_model_path}"
            )
        if self.rank < 1 or self.alpha < 1:
            raise ConfigurationError("LoRA rank and alpha must be positive")
        if not 0 <= self.dropout < 1:
            raise ConfigurationError("LoRA dropout must be between 0 and 1")
        if not self.target_modules:
            raise ConfigurationError("at least one LoRA target module is required")
        if self.epochs <= 0 or self.learning_rate <= 0:
            raise ConfigurationError("epochs and learning_rate must be positive")
        if self.batch_size < 1 or self.gradient_accumulation_steps < 1:
            raise ConfigurationError("batch sizes must be positive")
        if self.max_length < 32:
            raise ConfigurationError("max_length must be at least 32")


@dataclass(frozen=True)
class TransformersEvaluationConfig:
    base_model_path: Path
    max_length: int = 1024
    minimum_perplexity_ratio: float = 0.98

    def __post_init__(self) -> None:
        if not self.base_model_path.expanduser().is_dir():
            raise ConfigurationError(
                f"base_model_path must be a local Hugging Face model directory: "
                f"{self.base_model_path}"
            )
        if self.max_length < 32:
            raise ConfigurationError("max_length must be at least 32")
        if self.minimum_perplexity_ratio <= 0:
            raise ConfigurationError("minimum_perplexity_ratio must be positive")


class TransformersLoRATrainer:
    def __init__(self, config: TransformersLoRAConfig) -> None:
        self.config = config

    async def train(self, dataset_path: Path, eval_path: Path, output_path: Path) -> TrainingResult:
        return await asyncio.to_thread(self._train_sync, dataset_path, eval_path, output_path)

    def _train_sync(self, dataset_path: Path, eval_path: Path, output_path: Path) -> TrainingResult:
        torch, peft, transformers = _training_imports()
        records = _read_examples(dataset_path)
        if not records:
            raise TrainingError("training dataset is empty")
        if not _read_examples(eval_path):
            raise TrainingError("held-out evaluation dataset is empty")

        base_path = self.config.base_model_path.expanduser().resolve()
        output_path = output_path.resolve()
        output_path.mkdir(parents=True, exist_ok=True)
        trainer_output = output_path / ".trainer"
        shutil.rmtree(trainer_output, ignore_errors=True)

        try:
            tokenizer = transformers.AutoTokenizer.from_pretrained(
                str(base_path), local_files_only=True
            )
            _ensure_padding_token(tokenizer)
            model = transformers.AutoModelForCausalLM.from_pretrained(
                str(base_path),
                local_files_only=True,
                torch_dtype="auto",
            )
            model.config.use_cache = False
            lora_config = peft.LoraConfig(
                task_type=peft.TaskType.CAUSAL_LM,
                r=self.config.rank,
                lora_alpha=self.config.alpha,
                lora_dropout=self.config.dropout,
                target_modules=list(self.config.target_modules),
                bias="none",
            )
            model = peft.get_peft_model(model, lora_config)
            train_dataset = _tokenize_records(
                records, tokenizer, torch, max_length=self.config.max_length
            )
            arguments = transformers.TrainingArguments(
                output_dir=str(trainer_output),
                num_train_epochs=self.config.epochs,
                per_device_train_batch_size=self.config.batch_size,
                gradient_accumulation_steps=self.config.gradient_accumulation_steps,
                learning_rate=self.config.learning_rate,
                save_strategy="no",
                logging_strategy="steps",
                logging_steps=1,
                report_to=[],
                remove_unused_columns=False,
                fp16=bool(torch.cuda.is_available()),
                seed=self.config.seed,
            )
            trainer = transformers.Trainer(
                model=model,
                args=arguments,
                train_dataset=train_dataset,
                data_collator=_causal_collator(torch, tokenizer.pad_token_id),
            )
            outcome = trainer.train()
            model.save_pretrained(output_path, safe_serialization=True)
            tokenizer.save_pretrained(output_path)
            metrics = _json_scalars(outcome.metrics)
            manifest = {
                "format_version": 1,
                "base_model_path": str(base_path),
                "dataset_path": str(dataset_path.resolve()),
                "eval_path": str(eval_path.resolve()),
                "training_samples": len(records),
                "lora": {
                    "rank": self.config.rank,
                    "alpha": self.config.alpha,
                    "dropout": self.config.dropout,
                    "target_modules": list(self.config.target_modules),
                },
                "metrics": metrics,
            }
            (output_path / "dreamcycle-training.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            return TrainingResult(adapter_path=output_path, metrics=metrics)
        except (OSError, RuntimeError, ValueError) as exc:
            raise TrainingError(f"Transformers LoRA training failed: {exc}") from exc
        finally:
            shutil.rmtree(trainer_output, ignore_errors=True)


class TransformersPerplexityEvaluator:
    """Compare base and adapter perplexity on the held-out dataset."""

    def __init__(self, config: TransformersEvaluationConfig) -> None:
        self.config = config

    async def evaluate(self, adapter_path: Path, eval_path: Path) -> EvaluationResult:
        return await asyncio.to_thread(self._evaluate_sync, adapter_path, eval_path)

    def _evaluate_sync(self, adapter_path: Path, eval_path: Path) -> EvaluationResult:
        torch, peft, transformers = _training_imports()
        records = _read_examples(eval_path)
        if not records:
            raise EvaluationError("held-out evaluation dataset is empty")
        adapter_path = adapter_path.resolve()
        if not (adapter_path / "adapter_config.json").is_file():
            raise EvaluationError(f"PEFT adapter_config.json is missing from {adapter_path}")

        base_path = self.config.base_model_path.expanduser().resolve()
        try:
            tokenizer = transformers.AutoTokenizer.from_pretrained(
                str(base_path), local_files_only=True
            )
            _ensure_padding_token(tokenizer)
            dataset = _tokenize_records(
                records, tokenizer, torch, max_length=self.config.max_length
            )

            baseline_model = transformers.AutoModelForCausalLM.from_pretrained(
                str(base_path), local_files_only=True, torch_dtype="auto"
            )
            baseline_loss = _average_loss(torch, baseline_model, dataset)
            del baseline_model
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            candidate_base = transformers.AutoModelForCausalLM.from_pretrained(
                str(base_path), local_files_only=True, torch_dtype="auto"
            )
            candidate_model = peft.PeftModel.from_pretrained(
                candidate_base, str(adapter_path), is_trainable=False
            )
            candidate_loss = _average_loss(torch, candidate_model, dataset)

            baseline_perplexity = math.exp(min(baseline_loss, 50.0))
            candidate_perplexity = math.exp(min(candidate_loss, 50.0))
            ratio = baseline_perplexity / candidate_perplexity
            return EvaluationResult(
                score=ratio,
                baseline_score=1.0,
                passed=math.isfinite(ratio) and ratio >= self.config.minimum_perplexity_ratio,
                perplexity=candidate_perplexity,
                baseline_perplexity=baseline_perplexity,
                metrics={
                    "candidate_loss": candidate_loss,
                    "baseline_loss": baseline_loss,
                    "perplexity_ratio": ratio,
                    "samples": len(dataset),
                },
            )
        except EvaluationError:
            raise
        except (OSError, RuntimeError, ValueError) as exc:
            raise EvaluationError(f"Transformers perplexity evaluation failed: {exc}") from exc


def _training_imports() -> tuple[Any, Any, Any]:
    try:
        import peft
        import torch
        import transformers
    except ImportError as exc:
        raise OptionalDependencyError(
            "local LoRA training requires 'pip install dreamcycle[training]'"
        ) from exc
    return torch, peft, transformers


def _read_examples(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ConfigurationError(f"dataset file does not exist: {path}")
    records: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ConfigurationError(f"invalid JSONL at {path}:{line_number}") from exc
            instruction = str(value.get("instruction") or "").strip()
            output = str(value.get("output") or "").strip()
            if not instruction or not output:
                raise ConfigurationError(
                    f"instruction and output are required at {path}:{line_number}"
                )
            records.append({"instruction": instruction, "output": output})
    return records


def _ensure_padding_token(tokenizer: Any) -> None:
    if tokenizer.pad_token_id is None:
        if tokenizer.eos_token_id is None:
            raise ConfigurationError("tokenizer requires either a pad token or EOS token")
        tokenizer.pad_token = tokenizer.eos_token


def _tokenize_records(
    records: list[dict[str, str]], tokenizer: Any, torch: Any, *, max_length: int
) -> list[dict[str, Any]]:
    tokenized: list[dict[str, Any]] = []
    eos = tokenizer.eos_token or ""
    for record in records:
        prompt = f"### Instruction:\n{record['instruction']}\n\n### Response:\n"
        full_text = prompt + record["output"] + eos
        full = tokenizer(
            full_text,
            add_special_tokens=True,
            truncation=True,
            max_length=max_length,
        )
        prompt_tokens = tokenizer(
            prompt,
            add_special_tokens=True,
            truncation=True,
            max_length=max_length,
        )["input_ids"]
        input_ids = list(full["input_ids"])
        labels = list(input_ids)
        prompt_length = min(len(prompt_tokens), len(labels))
        labels[:prompt_length] = [-100] * prompt_length
        if not any(value != -100 for value in labels):
            raise ConfigurationError(
                "max_length truncates every response token; increase max_length"
            )
        tokenized.append(
            {
                "input_ids": torch.tensor(input_ids, dtype=torch.long),
                "attention_mask": torch.ones(len(input_ids), dtype=torch.long),
                "labels": torch.tensor(labels, dtype=torch.long),
            }
        )
    return tokenized


def _causal_collator(torch: Any, pad_token_id: int) -> Any:
    def collate(features: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "input_ids": torch.nn.utils.rnn.pad_sequence(
                [item["input_ids"] for item in features],
                batch_first=True,
                padding_value=pad_token_id,
            ),
            "attention_mask": torch.nn.utils.rnn.pad_sequence(
                [item["attention_mask"] for item in features],
                batch_first=True,
                padding_value=0,
            ),
            "labels": torch.nn.utils.rnn.pad_sequence(
                [item["labels"] for item in features],
                batch_first=True,
                padding_value=-100,
            ),
        }

    return collate


def _average_loss(torch: Any, model: Any, dataset: list[dict[str, Any]]) -> float:
    model.eval()
    device = next(model.parameters()).device
    total_loss = 0.0
    with torch.no_grad():
        for item in dataset:
            outputs = model(
                input_ids=item["input_ids"].unsqueeze(0).to(device),
                attention_mask=item["attention_mask"].unsqueeze(0).to(device),
                labels=item["labels"].unsqueeze(0).to(device),
            )
            total_loss += float(outputs.loss.detach().cpu())
    if not math.isfinite(total_loss):
        raise EvaluationError("model evaluation produced a non-finite loss")
    return total_loss / len(dataset)


def _json_scalars(values: dict[str, Any]) -> dict[str, Any]:
    converted: dict[str, Any] = {}
    for key, value in values.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            converted[str(key)] = value
        elif hasattr(value, "item"):
            converted[str(key)] = value.item()
        else:
            converted[str(key)] = str(value)
    return converted
