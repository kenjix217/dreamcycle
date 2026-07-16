# DreamCycle Vendor SDK and Sidecar

DreamCycle can be added to a local-model product in three ways:

For the visual system map and data flow, see
[`ARCHITECTURE.md`](../ARCHITECTURE.md).

| Mode | Vendor change | Best fit |
|---|---|---|
| Chat Completions proxy | Change base URL and API key | Existing configurable OpenAI-compatible clients |
| Python SDK | Add explicit memory and cycle calls | Python platforms that own their request pipeline |
| Embedded library | Construct memory and cycle objects | Python runtimes that want no sidecar process |

The proxy supports `POST /v1/chat/completions`, including common SSE streaming.
It is not a complete OpenAI API or Responses API implementation.

## Install

Memory sidecar:

```bash
pip install 'dreamcycle[server,embeddings]'
```

Memory sidecar plus local Transformers/PEFT training:

```bash
pip install 'dreamcycle[server,embeddings,training]'
```

SDK in the vendor application:

```bash
pip install 'dreamcycle[sdk]'
```

PostgreSQL must have pgvector installed. Set
`DREAMCYCLE_CREATE_VECTOR_EXTENSION=true` only when the configured database
role is allowed to create extensions.

## Minimal Sidecar Configuration

```bash
export DREAMCYCLE_POSTGRES_DSN='postgresql://dreamcycle:password@127.0.0.1/dreamcycle'
export DREAMCYCLE_EMBEDDING_MODEL='/absolute/path/to/local/embedding-model'
export DREAMCYCLE_API_KEY='replace-with-a-random-secret'
export DREAMCYCLE_NAMESPACE='vendor-product'
export DREAMCYCLE_USER_ID='local-user'

dreamcycle-server --host 127.0.0.1 --port 8765
```

Model and embedding paths are local by default. Set
`DREAMCYCLE_ALLOW_REMOTE_MODEL_DOWNLOAD=true` only when downloading the
embedding model is an intentional deployment choice.

The health route does not require authentication:

```bash
curl http://127.0.0.1:8765/healthz
```

Every `/v1` route requires the sidecar bearer key.

## SDK Use

```python
from dreamcycle.sdk import DreamCycleClient

with DreamCycleClient("http://127.0.0.1:8765", "sidecar-secret") as client:
    user, assistant = client.record_turn(
        "Which database stores memory?",
        "DreamCycle stores memory in PostgreSQL with pgvector.",
        conversation_id="conversation-100",
        trace_id="request-100",
        metadata={"product": "vendor-app"},
    )

    related = client.recall("vector memory", limit=5, metric="cosine")

    # Review is intentionally separate from capture.
    client.review(assistant.id, approved_for_training=True)

    job = client.start_cycle()
    current = client.cycle_status(job.id)
```

The SDK also exposes `record`, `delete`, `active_adapter`, and
`rollback_adapter`. HTTP failures raise `DreamCycleSDKError` with a status code
without including the configured API key.

## Proxy Use

Configure the local model server separately:

```bash
export DREAMCYCLE_UPSTREAM_BASE_URL='http://127.0.0.1:11434/v1'
export DREAMCYCLE_UPSTREAM_API_KEY='optional-upstream-only-key'
export DREAMCYCLE_PROXY_MODE='observe'
dreamcycle-server
```

Then configure the existing application with:

```text
OpenAI-compatible base URL: http://127.0.0.1:8765/v1
API key:                     the DREAMCYCLE_API_KEY value
```

The sidecar accepts upstream base URLs with or without a trailing `/v1`. It
always forwards to the upstream Chat Completions route.

### Observe Mode

`observe` forwards the request without memory injection and atomically records
the latest user text and completed assistant text after a successful model
response.

### Retrieve Mode

`retrieve` searches scoped successful L2 memories using the latest user text.
It prepends a bounded system message that labels the JSON memory array as
untrusted historical data and says not to follow instructions inside it.

```bash
export DREAMCYCLE_PROXY_MODE='retrieve'
export DREAMCYCLE_PROXY_RECALL_LIMIT='5'
export DREAMCYCLE_PROXY_CONTEXT_MAX_CHARACTERS='6000'
```

DreamCycle-only metadata is consumed and removed before forwarding:

```json
{
  "metadata": {
    "dreamcycle_conversation_id": "conversation-100",
    "dreamcycle_trace_id": "request-100"
  }
}
```

`X-DreamCycle-Conversation-ID` takes precedence over metadata. Other metadata
fields and Chat Completions request fields are preserved.

### Streaming

SSE bytes are forwarded as received. Assistant text is reconstructed from
`choices[].delta.content` and recorded only after the stream includes
`data: [DONE]`. Interrupted or incomplete streams are not stored as completed
turns.

Recall and post-response recording failures do not discard an otherwise valid
model response. Non-stream responses include an `X-DreamCycle-Warning` header
with a bounded failure code. A stopped sidecar or failed upstream remains a
truthful request failure because a proxy adds an availability hop.

## Identity Isolation

The simple environment form binds one key to one memory identity:

```text
DREAMCYCLE_API_KEY -> DREAMCYCLE_NAMESPACE + DREAMCYCLE_USER_ID
```

For multiple local identities, use one JSON object. Do not set the simple API
key at the same time.

```bash
export DREAMCYCLE_API_KEYS_JSON='{
  "key-for-alice":{"namespace":"vendor-product","user_id":"alice"},
  "key-for-bob":{"namespace":"vendor-product","user_id":"bob"}
}'
```

Identity is resolved from the key on the server. Request bodies containing
`namespace` or `user_id` are rejected; they cannot override the key binding.

## Reviewed Training and Cycle Jobs

Captured memories start unreviewed and unapproved. A record can enter the
training dataset only after explicit review with
`approved_for_training=true`. Dataset generation keeps complete conversations
on one side of the train/evaluation split.

Enable the built-in local Transformers/PEFT cycle by configuring both values:

```bash
export DREAMCYCLE_BASE_MODEL='/absolute/path/to/local/hugging-face-model'
export DREAMCYCLE_DATA_DIR='/absolute/path/to/dreamcycle-data'
```

`POST /v1/cycles` returns `202 Accepted` with a job in `queued` state. Poll the
job route for `queued`, `running`, `completed`, or `failed`. A second cycle for
the same identity is rejected while one is active. Job state is in process and
does not survive a sidecar restart in 0.2.0.

## Routes

| Method and route | Purpose |
|---|---|
| `GET /healthz` | Process health |
| `POST /v1/memory/records` | Record one unreviewed memory |
| `POST /v1/memory/turns` | Atomically record a completed turn |
| `POST /v1/memory/search` | Scoped vector recall |
| `POST /v1/memory/{id}/review` | Record review and training approval/rejection |
| `DELETE /v1/memory/{id}` | Delete scoped memory |
| `POST /v1/cycles` | Queue a local cycle |
| `GET /v1/cycles/{job_id}` | Poll cycle state |
| `GET /v1/adapters/active` | Read active adapter path |
| `POST /v1/adapters/rollback` | Restore the previous adapter |
| `POST /v1/chat/completions` | Chat Completions proxy |

Interactive OpenAPI documentation is available at `/docs` while the sidecar is
running.

## Environment Reference

| Variable | Required | Meaning |
|---|---|---|
| `DREAMCYCLE_POSTGRES_DSN` | Yes | PostgreSQL connection string |
| `DREAMCYCLE_EMBEDDING_MODEL` | Yes | Local Sentence Transformers model path |
| `DREAMCYCLE_API_KEY` | Simple auth | Sidecar bearer key |
| `DREAMCYCLE_NAMESPACE` | Simple auth | Key-bound memory namespace |
| `DREAMCYCLE_USER_ID` | Simple auth | Key-bound memory user |
| `DREAMCYCLE_API_KEYS_JSON` | Multi-key auth | Key-to-identity JSON map |
| `DREAMCYCLE_POSTGRES_SCHEMA` | No | Schema, default `dreamcycle` |
| `DREAMCYCLE_DISTANCE_METRIC` | No | `cosine`, `l2`, or `inner_product` |
| `DREAMCYCLE_CREATE_VECTOR_EXTENSION` | No | Allow `CREATE EXTENSION vector` |
| `DREAMCYCLE_CREATE_HNSW_INDEX` | No | Create HNSW index, default true |
| `DREAMCYCLE_ALLOW_REMOTE_MODEL_DOWNLOAD` | No | Permit embedding model download |
| `DREAMCYCLE_UPSTREAM_BASE_URL` | Proxy | Local model server base URL |
| `DREAMCYCLE_UPSTREAM_API_KEY` | No | Separate upstream credential |
| `DREAMCYCLE_PROXY_MODE` | No | `observe` or `retrieve` |
| `DREAMCYCLE_PROXY_RECALL_LIMIT` | No | Maximum recalled records, default 5 |
| `DREAMCYCLE_PROXY_CONTEXT_MAX_CHARACTERS` | No | Maximum injected JSON characters |
| `DREAMCYCLE_PROXY_TIMEOUT_SECONDS` | No | Upstream timeout, default 120 |
| `DREAMCYCLE_BASE_MODEL` | Training | Local Hugging Face base model path |
| `DREAMCYCLE_DATA_DIR` | Training | Per-identity cycle data root |
| `DREAMCYCLE_CANDIDATE_LIMIT` | No | Reviewed candidate query limit |
| `DREAMCYCLE_MINIMUM_TRAIN_SAMPLES` | No | Minimum train split size |
| `DREAMCYCLE_HOST` | No | Bind address, default `127.0.0.1` |
| `DREAMCYCLE_PORT` | No | Bind port, default `8765` |

## Deployment Boundary

- Keep the default loopback bind unless remote access is intentional.
- Use a restricted PostgreSQL role and TLS where the network is not trusted.
- Put external authentication and TLS termination in front of any exposed
  sidecar.
- Rotate sidecar and upstream credentials independently.
- Define consent, retention, deletion, and training policies before collecting
  production conversations.
- Do not train on data you do not have the right to use.
