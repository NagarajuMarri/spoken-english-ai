# AI Conversation

`AIConversationProvider` accepts bounded learning context and returns validated structured feedback. Deterministic generation supports local development and tests. The optional OpenAI-compatible boundary requires an injected client, configured model, timeout, and bounded retry policy; it never reads or logs credentials.

Provider output is rejected for missing fields, excessive lengths, control characters, malicious HTML, prompt leakage, credentials, or authorization material. Raw provider responses are never returned by the API.
