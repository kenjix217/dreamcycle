"""Record, retrieve, review, and start a cycle through the vendor SDK."""

import os

from dreamcycle.sdk import DreamCycleClient


def main() -> None:
    with DreamCycleClient(
        os.getenv("DREAMCYCLE_URL", "http://127.0.0.1:8765"),
        os.environ["DREAMCYCLE_API_KEY"],
    ) as client:
        user, assistant = client.record_turn(
            "How does this product remember a conversation?",
            "It stores a scoped embedding in PostgreSQL with pgvector.",
            conversation_id="sdk-example",
            metadata={"example": True},
        )
        print("stored", user.id, assistant.id)

        for memory in client.recall("conversation memory", limit=5):
            print(memory.similarity, memory.content)

        client.review(assistant.id, approved_for_training=True)
        knowledge = client.promote_knowledge(
            [assistant.id],
            node_type="validated_response",
            key="conversation-memory",
            content="DreamCycle stores scoped local memories in PostgreSQL with pgvector.",
            confidence=0.8,
        )
        print("l3", knowledge.node_type, knowledge.key)

        job = client.start_cycle()
        print("cycle", job.id, job.status)


if __name__ == "__main__":
    main()
