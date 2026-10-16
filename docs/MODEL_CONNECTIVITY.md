# Model connectivity: direct server or localhost gateway

This project uses an **OpenAI-compatible chat/completions** endpoint for the
production candidate workflow. No hosted model, credential, gateway, GPU,
or private infrastructure is bundled with this repository.

The model may be accessed directly through a server you control or via a local
OpenAI-compatible gateway. Both modes use the **same frozen claim and strict
story-first verifier**. Changing the route cannot waive market coverage,
originality, independent reviews, or final verification.

## Configure your own endpoint

The recommended setup is to copy the project-root `.env.example` to `.env` and enter your
own `MODEL_BASE_URL`, `MODEL_ID` and, if needed, `MODEL_API_KEY`. The project
automatically loads the untracked `.env` when running `scripts/candidate.py execute`,
so a shell-level export is **optional** rather than the required first step.
Run `python scripts/model.py status` (redacted) or `python scripts/model.py check`
(one real readiness request). See [Quickstart](QUICKSTART.md) and
[Agent Skills setup](AGENT_INTEGRATION.md).

The commands below are alternative manual diagnostics if you have already
configured environment variables. Never put secrets in Git, command-line flags
or shared bug reports.

~~~bash
# Local model gateway; use the configured model ID.
python examples/check_model_endpoint.py \
  --base-url "$MODEL_BASE_URL" \
  --model "$MODEL_ID" --max-tokens 1024

# Optional directly reachable private model server:
python examples/check_model_endpoint.py \
  --base-url "$MODEL_BASE_URL" \
  --model "$MODEL_ID" --api-key-env MODEL_API_KEY \
  --bypass-proxy --max-tokens 1024
~~~

The checker and candidate executor use the standard Chat Completions request
fields (`model`, `messages`, `max_tokens`, `stream`) by default;
provider-specific parameters such as `thinking` are not injected automatically.
A successful readiness probe does not establish that long-context candidate
generation and structured review will pass.

The checker makes an authenticated **POST /v1/chat/completions** request.
It exits 0 only when assistant message content is nonempty. It exits 2
when readiness cannot be established. It prints status, model, character
counts, finish reason, and timing, **never the credential or generated text**.
It does not assume /health, /metrics or /version exist on every server.

For reasoning models, HTTP 200 with empty content and
finish_reason=length may just mean a low output-token budget consumed by
reasoning; it is not proof of model outage. Check reasoning_chars and retry
the diagnostic with a reasonable max_tokens, without weakening production
quality requirements.

The --bypass-proxy flag applies **only to the diagnostic**. Check proxy
rules separately for the actual candidate executor, gateway upstream, and
any private-network forwarder. The diagnostic does not change system proxy
settings.

## Resume the same existing run

~~~bash
# With project-local .env already configured, only the claim is required.
python scripts/candidate.py execute --claim YOUR_EXISTING_CLAIM.json

# Advanced: explicit per-run override when using environment variables.
python scripts/candidate.py execute --claim YOUR_EXISTING_CLAIM.json \
  --base-url "$MODEL_BASE_URL" --model "$MODEL_ID" \
  --api-key-env MODEL_API_KEY --max-concurrency 1 --timeout 780 --max-tokens 9000
~~~

Use the original claim path after a transport error. **Never** initialize
a duplicate claim, silently restart acquisition, replace the frozen packet,
or inject fabricated content to work around inference availability.
Before resuming, confirm that no executor owns an active lease.

The generic command assumes the controller state file is not locked by
another application. On Windows, if a reader prevents atomic state-file
replacement, safely release that reader's handle rather than forcibly
terminating unrelated software or editing the frozen production engine.
Local emergency adapters are not part of the distributable project.

After successful candidate generation and independent reviews, explicitly
run the final verification:

~~~bash
python scripts/candidate.py verify \
  --claim YOUR_EXISTING_CLAIM.json
~~~

Only a real verified passed result with no failures qualifies as a
complete production run. Offline synthetic demonstrations do not substitute
for real-source scans and actual model-backed review.

## What specific errors do and do not prove

| Observation | Interpretation |
| --- | --- |
| A model-list endpoint responds | Discovery works; inference readiness is not established |
| HTTP 200, reasoning text, no content, finish_reason=length | May be an insufficient output allowance |
| 502 or reset via a gateway | A request through that gateway failed; model failure not yet isolated |
| Both authorized direct and gateway calls reset | Merely bypassing the gateway is insufficient |
| Candidate JSON does not satisfy its Schema | An actual content-contract failure, not a connection failure |

Shared remote servers, forwarded connections, and user proxy settings
must not be changed without proper operator authorization. Website access,
a rights-cleared platform-specific font decoder and a usable model server
remain environment-specific requirements, not packaged guarantees.
