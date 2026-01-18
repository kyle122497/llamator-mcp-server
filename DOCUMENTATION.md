# Technical documentation

This document specifies configuration, interfaces, payloads, and operational behavior of the service.

## Scope

The service exposes LLAMATOR test execution as:

- an HTTP API suitable for automation and CI/CD integration;
- an MCP server suitable for agent/tooling integrations over Streamable HTTP.

Execution is asynchronous. Runs are enqueued via ARQ and persisted in Redis. Artifacts are uploaded to MinIO and
are accessed through presigned URLs.

## High-level architecture

### HTTP layer (FastAPI)

Responsibilities:

- Public healthcheck endpoints.
- Protected job endpoints:
    - job creation;
    - job state retrieval;
    - artifacts listing;
    - artifacts download URL resolution.
- OpenAPI schema generation with API-key security scheme.
- Prometheus metrics exposure at `/metrics`.

Authentication:

- Optional API key via `X-API-Key`.
- If the key is not configured, the authentication layer is effectively disabled.

### MCP layer (Streamable HTTP)

Responsibilities:

- Tool exposure for LLAMATOR runs.
- Integration-friendly JSON-RPC responses.

Implementation notes:

- The MCP app is mounted under `LLAMATOR_MCP_MCP_MOUNT_PATH` (default `/mcp`).
- An ASGI wrapper converts single-message SSE responses to `application/json` for POST requests when the upstream
  returns `text/event-stream` with `data: <json>` blocks. This improves compatibility with clients that expect JSON
  responses without SSE parsing.

Authentication:

- Protected by the same `LLAMATOR_MCP_API_KEY` value and `X-API-Key` header as the HTTP API.

### Worker layer (ARQ)

Responsibilities:

- Deserialize and validate job payloads.
- Resolve effective LLAMATOR run configuration.
- Execute LLAMATOR via `llamator.start_testing(...)`.
- Persist terminal state in Redis (result or error).
- Upload artifacts to the storage backend.
- Perform best-effort cleanup of local artifacts.

Empty result handling:

- If LLAMATOR returns an empty aggregated result (no tests executed), the job is marked as failed with error type
  `EmptyAggregatedResultError`.

### Artifacts storage (MinIO)

Responsibilities:

- Upload job artifacts to MinIO.
- List objects under a job prefix.
- Resolve presigned URLs for downloads.

Current implementation details:

- The MinIO backend uploads the archive `artifacts.zip` per job. The object key is `<job_id>/artifacts.zip`.
- Listing typically returns a single entry (`artifacts.zip`), unless additional objects were written by a future
  backend implementation.

## Configuration reference

All configuration is provided via environment variables with prefix `LLAMATOR_MCP_`.

### Redis

- `LLAMATOR_MCP_REDIS_DSN`
    - Default: `redis://redis:6379/0`
    - Redis DSN used for:
        - HTTP API job store;
        - ARQ queue backend;
        - worker job store.

### HTTP server

- `LLAMATOR_MCP_HTTP_HOST`
    - Default: `0.0.0.0`
    - Bind host for the HTTP server.

- `LLAMATOR_MCP_HTTP_PORT`
    - Default: `8000`
    - Bind port for the HTTP server.

- `LLAMATOR_MCP_UVICORN_LOG_LEVEL`
    - Default: `info`
    - Uvicorn log level.

### Logging

- `LLAMATOR_MCP_LOG_LEVEL`
    - Default: `INFO`
    - Root Python logging level for both API and worker processes.

### API security

- `LLAMATOR_MCP_API_KEY`
    - Default: empty
    - Behavior:
        - empty: API key checks are disabled;
        - non-empty: protected HTTP routes and the MCP app require `X-API-Key` header.

### MCP server mounting

- `LLAMATOR_MCP_MCP_MOUNT_PATH`
    - Default: `/mcp`
    - FastAPI mount path for the MCP ASGI application.

- `LLAMATOR_MCP_MCP_STREAMABLE_HTTP_PATH`
    - Default: `/`
    - Streamable HTTP path exposed by the MCP app.

### Job storage and execution

- `LLAMATOR_MCP_JOB_TTL_SECONDS`
    - Default: `604800` (7 days)
    - TTL for job records stored in Redis.

- `LLAMATOR_MCP_RUN_TIMEOUT_SECONDS`
    - Default: `3600` (1 hour)
    - ARQ worker job timeout.

- `LLAMATOR_MCP_REPORT_LANGUAGE`
    - Default: `en`
    - Default LLAMATOR report language when user config does not override.
    - Allowed values: `en`, `ru`.

### Local artifacts behavior

- `LLAMATOR_MCP_ARTIFACTS_ROOT`
    - Default: `/data/artifacts`
    - Local root directory used by the worker for job artifacts.

- `LLAMATOR_MCP_ARTIFACTS_LOCAL_TTL_SECONDS`
    - Default: `86400` (1 day)
    - Local artifacts retention. Best-effort cleanup is executed at worker startup.

### Presigned URLs and retention

- `LLAMATOR_MCP_ARTIFACTS_PRESIGN_EXPIRES_SECONDS`
    - Default: `900` (15 minutes)
    - TTL for presigned download URLs returned by the service.

- `LLAMATOR_MCP_ARTIFACTS_MINIO_TTL_SECONDS`
    - Default: `604800` (7 days)
    - MinIO retention TTL. The backend may delete expired objects during list/download operations.

### Upload retries

- `LLAMATOR_MCP_ARTIFACTS_UPLOAD_MAX_RETRIES`
    - Default: `3`
    - Maximum number of upload attempts in the worker.

- `LLAMATOR_MCP_ARTIFACTS_UPLOAD_RETRY_DELAY_SECONDS`
    - Default: `1.0`
    - Delay between attempts (seconds).

### MinIO connectivity

- `LLAMATOR_MCP_MINIO_ENDPOINT_URL`
    - Default: `http://minio:9000`
    - Internal MinIO endpoint used by API and worker.

- `LLAMATOR_MCP_MINIO_PUBLIC_ENDPOINT_URL`
    - Default: `None` (empty treated as None)
    - Optional public endpoint used for presigned URL generation (useful when internal endpoint is not reachable
      from clients).

- `LLAMATOR_MCP_MINIO_ACCESS_KEY_ID`
    - Default: `minioadmin`
    - MinIO access key id.

- `LLAMATOR_MCP_MINIO_SECRET_ACCESS_KEY`
    - Default: `minioadmin`
    - MinIO secret access key.

- `LLAMATOR_MCP_MINIO_BUCKET`
    - Default: `llamator-artifacts`
    - Bucket for job objects.

- `LLAMATOR_MCP_MINIO_SECURE`
    - Default: `false`
    - Controls TLS for the internal MinIO client.
    - Consistency requirements:
        - `https` endpoint requires `true`
        - `http` endpoint requires `false`

### Attack model (OpenAI-compatible)

These variables configure the LLAMATOR "attack" model.

- `LLAMATOR_MCP_ATTACK_OPENAI_BASE_URL`
    - Default: `http://localhost:1234/v1`
    - OpenAI-compatible base URL.

- `LLAMATOR_MCP_ATTACK_OPENAI_MODEL`
    - Default: `model-identifier`
    - Model identifier.

- `LLAMATOR_MCP_ATTACK_OPENAI_API_KEY`
    - Default: `lm-studio`
    - API key for the attack model. May be empty.

- `LLAMATOR_MCP_ATTACK_OPENAI_TEMPERATURE`
    - Default: `0.5`
    - Temperature range: `[0.0, 2.0]`.

- `LLAMATOR_MCP_ATTACK_OPENAI_SYSTEM_PROMPTS`
    - Default: JSON array with a single prompt.
    - Accepted formats:
        - JSON array string (preferred): `["prompt1", "prompt2"]`
        - newline-separated string.

### Judge model (OpenAI-compatible)

These variables configure the LLAMATOR "judge" model.

- `LLAMATOR_MCP_JUDGE_OPENAI_BASE_URL`
    - Default: `http://localhost:1234/v1`
    - OpenAI-compatible base URL.

- `LLAMATOR_MCP_JUDGE_OPENAI_MODEL`
    - Default: `model-identifier`
    - Model identifier.

- `LLAMATOR_MCP_JUDGE_OPENAI_API_KEY`
    - Default: `lm-studio`
    - API key for the judge model. May be empty.

- `LLAMATOR_MCP_JUDGE_OPENAI_TEMPERATURE`
    - Default: `0.1`
    - Temperature range: `[0.0, 2.0]`.

- `LLAMATOR_MCP_JUDGE_OPENAI_SYSTEM_PROMPTS`
    - Default: JSON array with a single prompt.
    - Same accepted formats as attack prompts.

## HTTP API

Base URL:

- Default local compose: `http://localhost:8000`

Content type:

- Requests and responses are JSON unless stated otherwise.

Authentication:

- Header: `X-API-Key: <value>` when `LLAMATOR_MCP_API_KEY` is configured.

### Healthcheck

Endpoints:

- `GET /health`
- `GET /v1/health`

Response:

- 200
    - `{"status":"ok"}`

Errors:

- None (authentication is not applied to healthcheck endpoints).

### Create run

Endpoint:

- `POST /v1/tests/runs`

Purpose:

- Validate a run request and enqueue a job for asynchronous execution.

Request body:

- `LlamatorTestRunRequest`

Payload shape:

- `tested_model` (required)
    - `kind`: `"openai"`
    - `base_url`: http(s) URL with a host, e.g. `http://host:port/v1`
    - `model`: non-empty string
    - `api_key`: optional, non-empty when provided
    - `temperature`: optional float in `[0.0, 2.0]`
    - `system_prompts`: optional array of non-empty strings
    - `model_description`: optional string

- `run_config` (optional)
    - `enable_logging`: optional boolean
    - `enable_reports`: optional boolean
    - `artifacts_path`: optional safe relative path (no absolute paths and no `..`)
    - `debug_level`: optional int, one of `0 | 1 | 2`
    - `report_language`: optional `en | ru`

- `plan` (required)
    - `preset_name`: optional non-empty string (e.g. `all`, `rus`, `owasp:llm01`)
    - `num_threads`: optional integer, `>= 1`
    - `basic_tests`: optional array of built-in tests
        - `code_name`: non-empty string
        - `params`: optional array of `{name, value}` objects; parameter names must be unique within the test
    - `custom_tests`: optional array of custom tests
        - `import_path`: fully qualified import path; restricted to prefixes `llamator.` and `llamator_mcp_server.`
        - `params`: optional array of `{name, value}` objects; parameter names must be unique within the test

Response:

- 200 `LlamatorTestRunResponse`
    - `job_id`: string (uuid4 hex, 32 characters)
    - `status`: `queued | running | succeeded | failed`
    - `created_at`: ISO datetime (UTC)

Errors:

- 400
    - Validation errors (e.g. duplicated parameter names within a test spec).
- 401
    - API key required but missing/invalid.

Persistence and redaction:

- The service persists a redacted representation of the request:
    - API keys are not stored;
    - `api_key_present` boolean flags are stored instead.

Example:

```bash
curl -sS -X POST "http://localhost:8000/v1/tests/runs" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <optional>" \
  -d '{
    "tested_model": {
      "kind": "openai",
      "base_url": "http://host.docker.internal:1234/v1",
      "model": "llm",
      "api_key": "lm-studio"
    },
    "run_config": { "enable_reports": false },
    "plan": { "preset_name": "owasp:llm10", "num_threads": 1 }
  }'
```

### Get run

Endpoint:

- `GET /v1/tests/runs/{job_id}`

Purpose:

- Retrieve the current job state and, if terminal, the result or error information.

Response:

- 200 `LlamatorJobInfo`
    - `job_id`: string
    - `status`: `queued | running | succeeded | failed`
    - `created_at`: ISO datetime (UTC)
    - `updated_at`: ISO datetime (UTC)
    - `request`: redacted request payload
    - `result`: optional (`status == succeeded`)
        - `aggregated`: dict[str, dict[str, int]]
        - `finished_at`: ISO datetime (UTC)
    - `error`: optional (`status == failed`)
        - `error_type`: string
        - `message`: string
        - `occurred_at`: ISO datetime (UTC)
    - `error_notice`: optional compact user-facing string (format: `error_type: message` or `error_type` if message is
      empty)

Errors:

- 404
    - Job not found.
- 401
    - API key required but missing/invalid.

### List artifacts

Endpoint:

- `GET /v1/tests/runs/{job_id}/artifacts`

Purpose:

- List artifact objects stored under the job prefix.

Response:

- 200 `ArtifactsListResponse`
    - `job_id`: string
    - `files`: array of `ArtifactFileInfo`
        - `path`: relative path inside job prefix
        - `size_bytes`: integer
        - `mtime`: unix timestamp (seconds)

Errors:

- 404
    - Job not found.
- 502
    - Artifacts backend error (MinIO communication/parsing).
- 401
    - API key required but missing/invalid.

Retention notes:

- The backend may delete expired objects during listing. Retention is governed by
  `LLAMATOR_MCP_ARTIFACTS_MINIO_TTL_SECONDS`.

### Resolve artifact download URL

Endpoint:

- `GET /v1/tests/runs/{job_id}/artifacts/{path:path}`

Purpose:

- Resolve a presigned URL for the requested artifact object.

Response:

- 200 `ArtifactDownloadResponse`
    - `job_id`: string
    - `path`: requested relative path
    - `download_url`: presigned URL

Errors:

- 400
    - Invalid or unsafe path (path traversal protection).
- 404
    - Job not found or file not found.
- 502
    - Artifacts backend error.
- 401
    - API key required but missing/invalid.

Behavior:

- The endpoint returns JSON and does not perform redirects.

## MCP interface

Mount location:

- `LLAMATOR_MCP_MCP_MOUNT_PATH` (default `/mcp`)

Transport:

- Streamable HTTP.

Common request headers:

- `Accept: application/json, text/event-stream`
- `MCP-Protocol-Version: <version>`
- `Origin: <origin>`
- Optional `Mcp-Session-Id: <session>` after initialization.
- Optional `X-API-Key: <value>` when API key is configured.

### Tools

#### create_llamator_run

Purpose:

- Submit a run and block until the job reaches a terminal state, returning aggregated results and optional artifacts
  link.

Input:

- `req`: `LlamatorTestRunRequest`

Output schema (`LlamatorRunToolResponse`):

- `job_id`: string (uuid4 hex, 32 characters)
- `aggregated`: dict[str, dict[str, int]] (empty dict `{}` on failure)
- `artifacts_download_url`: string or null (presigned link for `artifacts.zip` if available)
- `error_notice`: string or null (user-facing error message if job failed)

Timeout:

- Wait limit is `LLAMATOR_MCP_RUN_TIMEOUT_SECONDS`.

Error conditions:

- `ValueError`: Invalid request payload or test specifications.
- `TimeoutError`: Job did not complete within the configured timeout.
- `KeyError`: Job not found in store (should not occur in normal flow).
- `RuntimeError`: Job succeeded but result is missing (internal inconsistency).

#### get_llamator_run

Purpose:

- Retrieve aggregated results for a finished job.

Input:

- `job_id`: string

Output schema (`LlamatorRunToolResponse`):

- `job_id`: string
- `aggregated`: dict[str, dict[str, int]]
- `artifacts_download_url`: string or null
- `error_notice`: string or null

Error conditions:

- `KeyError`: Job does not exist.
- `ValueError`: Job is not in a terminal state (still queued or running).
- `RuntimeError`: Job succeeded but result is missing (internal inconsistency).

## Artifacts

### Local artifacts directory layout

Worker writes artifacts under:

- `LLAMATOR_MCP_ARTIFACTS_ROOT/<job_id>/...`

If `run_config.artifacts_path` is provided:

- It is treated as a relative path inside the job root.
- Absolute paths and paths containing `..` are rejected.
- Escaping the job directory is rejected.

### Upload process

After execution:

- The worker uploads artifacts to the configured backend.
- Current MinIO backend uploads the archive:
    - file name: `artifacts.zip`
    - object key: `<job_id>/artifacts.zip`

Upload retries:

- attempts: `LLAMATOR_MCP_ARTIFACTS_UPLOAD_MAX_RETRIES`
- delay: `LLAMATOR_MCP_ARTIFACTS_UPLOAD_RETRY_DELAY_SECONDS`

Local cleanup:

- If upload succeeds, the worker deletes the local job directory.

Upload timing:

- Artifacts are uploaded regardless of job success or failure.
- Upload occurs before job state is persisted to Redis to ensure artifacts availability.

### Retention behavior

MinIO retention:

- Controlled by `LLAMATOR_MCP_ARTIFACTS_MINIO_TTL_SECONDS`.
- Expired objects may be deleted during list/download operations.

Local retention:

- Controlled by `LLAMATOR_MCP_ARTIFACTS_LOCAL_TTL_SECONDS`.
- Best-effort cleanup is executed at worker startup.

## Metrics

Endpoint:

- `GET /metrics`

Purpose:

- Expose Prometheus metrics via `prometheus_fastapi_instrumentator`.

## Error handling

### Job failure scenarios

Jobs can fail for several reasons:

1. **Empty aggregated result**: LLAMATOR executed but no tests ran (e.g., unreachable tested model, invalid preset).
   Error type: `EmptyAggregatedResultError`.

2. **LLAMATOR execution error**: Exception raised during `llamator.start_testing()`. Error type matches the exception
   class name.

3. **Validation error**: Invalid job payload structure or values. Error type matches the validation exception.

### Error notice format

The `error_notice` field provides a compact user-facing message:

- Format: `{error_type}: {message}` when message is non-empty.
- Format: `{error_type}` when message is empty.

This field is available in both HTTP API (`LlamatorJobInfo.error_notice`) and MCP tool responses
(`LlamatorRunToolResponse.error_notice`).