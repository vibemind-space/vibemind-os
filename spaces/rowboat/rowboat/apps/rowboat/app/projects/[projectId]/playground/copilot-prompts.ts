export const FIX_WORKFLOW_PROMPT = `There is an issue with this turn of chat (index {index}): "{chat_turn}"

Fix the issue by updating necessary agents and tools.`;

export const FIX_WORKFLOW_PROMPT_WITH_FEEDBACK = `There is an issue with this turn of chat (index {index}): "{chat_turn}"

Fix the issue by updating necessary agents and tools.

Here are more details: "{feedback}"`;

export const EXPLAIN_WORKFLOW_PROMPT_ASSISTANT = `Please explain why the assistant responded with the following message (index {index}):\n"{chat_turn}"`;

export const EXPLAIN_WORKFLOW_PROMPT_TOOL = `Please explain why the following tool was called (index {index}):\n"{chat_turn}"`;

export const EXPLAIN_WORKFLOW_PROMPT_TRANSITION = `Please explain why the following agent transition occurred (index {index}):\n"{chat_turn}"`;
