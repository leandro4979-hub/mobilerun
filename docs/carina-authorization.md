# CARINA authorization gate

Mobilerun can route every agent tool execution through a CARINA policy endpoint
before the tool is allowed to run.

## Enable

```bash
export CARINA_AUTH_URL="http://127.0.0.1:51001/authorize"
export CARINA_AUTH_TIMEOUT="2.0"
# Optional:
export CARINA_AUTH_TOKEN="..."
```

When `CARINA_AUTH_URL` is unset, Mobilerun behaves exactly as before.

When it is set, Mobilerun sends a POST request before every registered tool call:

```json
{
  "intent": {
    "action": "click",
    "arguments": {"index": 3}
  },
  "context": {
    "platform": "ios",
    "current_app": "Settings"
  },
  "requested_transition": "RESERVED->AUTHORIZED",
  "executor": "mobilerun"
}
```

CARINA must return an explicit authorization signal. Any of the following is
accepted:

```json
{"authorized": true}
```

```json
{"decision": "AUTHORIZED"}
```

```json
{"state": "AUTHORIZED"}
```

A denial, timeout, connection failure, malformed JSON response, or response
without an explicit authorization signal blocks the tool call. The device action
is never invoked in those cases.

This places CARINA at the execution boundary shared by FastAgent,
Manager/Executor, and custom/MCP tools:

```text
INTENT -> CARINA AUTHORIZATION -> MOBILERUN EXECUTION -> OBSERVATION/VERIFICATION
```
