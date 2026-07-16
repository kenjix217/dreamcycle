import json

import pytest

from dreamcycle.dataset import DatasetBuilder, DatasetBuilderConfig
from dreamcycle.errors import InsufficientTrainingData
from dreamcycle.types import TrainingCandidate


class CandidateSource:
    def __init__(self, candidates):
        self.candidates = candidates

    def training_candidates(self, limit=200):
        return self.candidates[:limit]


def candidate(conversation_id: str, suffix: str) -> TrainingCandidate:
    return TrainingCandidate(
        instruction=f"question {suffix}",
        output=f"answer {suffix}",
        conversation_id=conversation_id,
        trace_id=f"trace-{suffix}",
        source_ids=(f"user-{suffix}", f"assistant-{suffix}"),
    )


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_dataset_split_is_deterministic_and_conversation_is_held_out(tmp_path):
    source = CandidateSource(
        [
            candidate("conversation-a", "a1"),
            candidate("conversation-a", "a2"),
            candidate("conversation-b", "b1"),
            candidate("conversation-c", "c1"),
        ]
    )
    first = DatasetBuilder(source, DatasetBuilderConfig(output_dir=tmp_path / "first")).build(
        "cycle"
    )
    second = DatasetBuilder(source, DatasetBuilderConfig(output_dir=tmp_path / "second")).build(
        "cycle"
    )

    first_train = read_jsonl(first.train_path)
    first_eval = read_jsonl(first.eval_path)
    assert first_train == read_jsonl(second.train_path)
    assert first_eval == read_jsonl(second.eval_path)

    train_conversations = {row["metadata"]["conversation_id"] for row in first_train}
    eval_conversations = {row["metadata"]["conversation_id"] for row in first_eval}
    assert train_conversations.isdisjoint(eval_conversations)
    assert first.train_samples + first.eval_samples == 4


def test_dataset_requires_two_conversations(tmp_path):
    builder = DatasetBuilder(
        CandidateSource([candidate("only-one", "1"), candidate("only-one", "2")]),
        DatasetBuilderConfig(output_dir=tmp_path),
    )

    with pytest.raises(InsufficientTrainingData, match="two conversations"):
        builder.build("cycle")


def test_dataset_skips_empty_candidates(tmp_path):
    empty = TrainingCandidate(
        instruction="",
        output="answer",
        conversation_id="conversation-a",
        trace_id="trace",
        source_ids=("one", "two"),
    )
    builder = DatasetBuilder(
        CandidateSource([empty, candidate("conversation-b", "b")]),
        DatasetBuilderConfig(output_dir=tmp_path),
    )

    with pytest.raises(InsufficientTrainingData):
        builder.build("cycle")
