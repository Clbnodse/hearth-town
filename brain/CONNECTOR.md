# Meta Model Api

- `custom.meta-model-api` connects Muse to the Meta Model API REST service at `https://api.meta.ai/v1`. It authenticates with the registered `api_key` credential and calls only `api.meta.ai`.

- Helpers live in `~/workspace/custom-connectors/custom.meta-model-api/bin/`. `meta_api.py` lists models and sends chat completions, using curl for transport because Python urllib is unreliable through this box's egress proxy.

## Connect

- The connection was registered with `credentials.request_api_access` and these details. Reuse them to reconnect:

```json
{
  "provider": "meta-model-api",
  "auth_scheme": "api_key",
  "placement": "bearer_header",
  "api_hosts": ["api.meta.ai"]
}
```

- Before the first change in a conversation, prove access with a harmless read:

```text
python3 ~/workspace/custom-connectors/custom.meta-model-api/bin/meta_api.py models
```

- Verified 2026-10-26: that read returned HTTP 200 with the model list, including `muse-wonder-1.0`, `muse-spark-1.3`, `muse-spark-1.3-contributor`, `muse-image-1.0`, `sam-3.1`, and `muse-voice-transcribe-1.0`. The read spends no tokens.

## Credentials

- The registered connection holds the credential. Helpers import `/opt/muse/skills/custom-connector-setup/bin/dynamic_credentials.py`, which returns an `hsurr:` surrogate and places it where the provider reads the key. Muse swaps in the real credential only on an approved request to a registered host.

- Never put a key, token, password or cookie in this doc, a helper, a command argument, an environment variable or a log. Never ask the user to paste one in chat.

- Keep redirects disabled on authenticated requests.

- On a 401 or 403, check the request first. Confirm that the helper attached the credential, that the host is registered and that the placement and scopes match.

- Only when a request that carried the credential is still rejected, call `credentials.request_api_access` with the details above and `"reconnect": true`.

## List models

- List the models available on the team account. Use it to confirm access and to pick a model id before any generation call.

```text
python3 ~/workspace/custom-connectors/custom.meta-model-api/bin/meta_api.py models
```

- This is a read. It returns the model ids and spends no tokens.

## Send a chat completion

- Send one chat completion. Use it for brain replies and any other generation. This call spends tokens against the team's credits or card.

```text
python3 ~/workspace/custom-connectors/custom.meta-model-api/bin/meta_api.py chat muse-spark-1.3 "Hello" --max-tokens 200
```

- Inputs are the model id and the user message. Optional flags are `--max-tokens`, `--temperature`, and `--reasoning-effort`.

- Verified live 2026-10-26 on `muse-spark-1.3`: with default reasoning the model spent the whole token budget reasoning and returned null content at both 100 and 600 max tokens (finish length). With `--reasoning-effort minimal` and 600 max tokens it returned a finished sentence (154 total tokens, 99 reasoning). Always pass `--reasoning-effort minimal` for short Spark replies.

- Default to Standard model ids. Contributor ids (`-contributor` suffix) are discounted in exchange for Meta training on the prompts and completions, so use one only when the user opts in.

## Recover from errors

- HTTP 401 or 403 means the credential was missing, wrong, or not swapped. Check the helper attached the surrogate, then reconnect only if a request that carried it is still rejected.

- After a failed or timed-out change, check the current state with a read before trying again, because the first request may have completed.

## Limits

- The connector cannot create keys, manage billing, or set spend limits. Those live on dev.meta.ai and stay the user's taps.

- Chat completions are verified live as of 2026-10-26 (see the reasoning effort note above). Spend per call is not yet metered against the $150 credits; the town spend ledger records cost only when the provider returns one, so track token counts until billing shows the credit draw.

## Related skills

- Use `muse.skill_search` to find other skills and `muse.connector_search` to find other connectors.
