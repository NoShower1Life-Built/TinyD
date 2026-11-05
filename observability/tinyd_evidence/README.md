# TinyD Runtime Evidence Collector

This package assembles **observed runtime records** into a trace-correlated evidence bundle. It does not generate Kafka events, Redis operations, prompts, responses, or tool traces. Empty or missing evidence remains missing and is reported as such.

## Input contract

Provide newline-delimited JSON (JSONL) records from the real TinyD services. Each record must contain:

- `trace_id`: stable correlation identifier
- `event_type`: event name such as REQUEST, SCHEDULED, EXECUTING, TOOL_CALL, RESULT, FAILED
- `timestamp`: RFC 3339 timestamp with timezone
- `service`: emitting service
- optional `event_id`, `topic`, `partition`, `offset`, `worker_id`, `tool_name`, `status`, `payload`

Do not put API keys, bearer tokens, passwords, session cookies, or live customer data in test runs. The exporter redacts common secret fields and token patterns, but redaction is a defense-in-depth measure, not permission to collect secrets.

## Run

```bash
python -m tinyd_evidence.cli --events ./runtime-events.jsonl --trace-id <TRACE_ID> --out ./evidence
```

The output directory contains:

- `trace_id.txt`
- `kafka_chain.json` (events with Kafka metadata when present)
- `redis_events.json` (only observed Redis audit events; empty means none were supplied)
- `prompt_response.log` (only observed prompt/response records)
- `worker_execution.log` (only observed worker/tool lifecycle records)
- `manifest.json` (SHA-256 hashes and completeness assessment)

To package it, add `--zip`.

## Runtime integration

Emit one JSONL record at each boundary, retaining the same trace ID:

1. API/gateway accepts the request.
2. Producer publishes the event; include topic, partition and offset when known.
3. Scheduler claims/schedules the work.
4. Worker acquires/releases a lease and performs the idempotency decision.
5. Worker starts/finishes each tool invocation.
6. Worker records result/failure and gateway records the response.

For Redis, instrument the application code that performs lease/idempotency operations. Redis keyspace notifications do not reliably provide the semantic reason for an operation, and `MONITOR` can expose sensitive values; do not use it in production evidence collection.

For Kafka, prefer the application's producer/consumer instrumentation or an audit topic. A consumer-group replay can affect offsets if misconfigured; use a dedicated read-only consumer group and explicit topic allowlists.

## Evidence integrity

The manifest hashes every emitted artifact. Preserve original source logs separately in access-controlled storage if required by your incident process. Record collection time, software revision, environment, and exact reproduction inputs outside this exporter. Never edit evidence after collection; create a new bundle if corrections are needed.

## Limitations

- This tool correlates records; it does not prove that a vulnerability exists.
- A trace missing tool or Redis records is marked incomplete, not successful.
- A TinyD-local failure is not evidence of a vulnerability in OpenAI's systems. A Bugcrowd submission against OpenAI must demonstrate the affected in-scope OpenAI product and its behavior independently.
