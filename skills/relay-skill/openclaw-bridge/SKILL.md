---
name: relay-skill-openclaw-bridge
description: 'Bridge to an OpenClaw agent. Use when user says "Ask OpenClaw", "OpenClaw
  mode on/off", or wants to relay a question or task to the OpenClaw agent. Any capabilities,
  skills, or tools available on the OpenClaw agent become accessible from within Claude
  Code. Also supports relay mode: when the user says "OpenClaw mode on", ALL subsequent
  messages should be relayed to OpenClaw until the user says "OpenClaw mode off".'
app: relay-skill
requires_approval: true
agents:
- '*'
inputs: []
expected_state:
  description: Imported skill — behavior matches source repo
  verification_tool: none
confidence: 1.0
attempts: 0
successes: 0
last_adjusted: '2026-05-11T21:59:42+00:00'
---

# OpenClaw Bridge

Relay the user's request to the OpenClaw agent via its OpenAI-compatible API and return the response verbatim.

## Required Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENCLAW_BASE_URL` | yes | Base URL for the OpenClaw API (e.g. `http://127.0.0.1:18789/v1`) |
| `OPENCLAW_MODEL` | yes | Model identifier (e.g. `openclaw:main`) |
| `OPENCLAW_API_KEY` | yes | API key for authentication |
| `OPENCLAW_ASSISTANT_NAME` | no | Display name for the assistant (defaults to `OpenClaw`) |

## Instructions

Follow these steps exactly:

### 1. Validate environment variables

Run a single bash command to check that the three required env vars are set:

```bash
echo "BASE_URL=${OPENCLAW_BASE_URL:-MISSING} MODEL=${OPENCLAW_MODEL:-MISSING} API_KEY=${OPENCLAW_API_KEY:+SET}"
```

If any required variable is `MISSING` or the API key is empty, stop and tell the user which variables need to be set. Do not proceed.

### 2. Determine the assistant display name

Use `$OPENCLAW_ASSISTANT_NAME` if set, otherwise default to `OpenClaw`.

### 3. Extract the user's question

Take the user's message. If it starts with a trigger phrase like "Ask OpenClaw" or similar, strip that prefix to get the actual question. If the message is just the trigger with no question, ask the user what they'd like to ask.

### 4. Send the request

Use curl to POST to the chat completions endpoint. Do NOT inject a system prompt -- the OpenClaw agent has its own.

```bash
curl -sS -w "\n%{http_code}" \
  "${OPENCLAW_BASE_URL}/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${OPENCLAW_API_KEY}" \
  -d '{
    "model": "'"${OPENCLAW_MODEL}"'",
    "messages": [
      {"role": "user", "content": "USER_QUESTION_HERE"}
    ]
  }' 2>&1
```

Replace `USER_QUESTION_HERE` with the actual user question (properly JSON-escaped).

### 5. Handle errors

Check the HTTP status code (last line of output from `-w "\n%{http_code}"`):

- **Connection refused / curl error**: Tell the user the OpenClaw agent is not reachable at the configured URL. Suggest checking that the service is running.
- **401 or 403**: Tell the user the API key was rejected. Suggest checking `OPENCLAW_API_KEY`.
- **404**: Tell the user the endpoint was not found. Suggest checking `OPENCLAW_BASE_URL`.
- **500+**: Tell the user the OpenClaw agent returned a server error. Include the status code.
- **Malformed JSON**: Tell the user the response was not valid JSON. Show the raw response for debugging.

### 6. Display the response

On success (HTTP 200), extract `.choices[0].message.content` from the JSON response. Display it verbatim, prefixed with the assistant name in bold:

```
**[<assistant name>]:** <response content here>
```

Do NOT summarize, reformat, or editorialize the response. Show it exactly as returned.

## Relay Mode (Session Toggle)

The user can toggle **relay mode** on and off during a session:

- **"OpenClaw mode on"** (or "relay mode on"): Activates relay mode. From this point, **every message** the user sends should be relayed to the OpenClaw agent using the steps above (steps 1-6). No need for the user to say "Ask OpenClaw" each time. Confirm activation with:
  ```
  **[OpenClaw relay mode: ON]** -- All messages will be forwarded to <assistant name>. Say "OpenClaw mode off" to stop.
  ```

- **"OpenClaw mode off"** (or "relay mode off"): Deactivates relay mode. Return to normal Claude Code behavior. Confirm with:
  ```
  **[OpenClaw relay mode: OFF]** -- Returning to normal mode.
  ```

- This toggle is **session-scoped only** -- it does not persist across sessions.
- While relay mode is active, if the user says something clearly directed at Claude Code itself (e.g., "read this file", "edit this code", "git status"), use your judgment -- those should NOT be relayed. Only relay messages that are questions or tasks for the OpenClaw agent.

## Important

- No system prompt is injected -- OpenClaw manages its own persona and context.
- No multi-turn state is maintained here -- OpenClaw manages its own conversation history.
- The response is displayed verbatim with no summarization.
