# System Architecture

## Shape

Start as a modular monolith deployed as one FastAPI application and one PostgreSQL database. This preserves transactional simplicity while enforcing boundaries that can later be extracted if scale or ownership requires it.

```text
Web / Mobile clients
        |
   FastAPI routes
        |
Application services
        |
Learning + Conversation domain
   |          |          |
Repositories LLM port  Speech/TTS ports
   |          |          |
PostgreSQL  disabled/provider adapters
```

Routes own HTTP concerns. Services coordinate use cases. Domain code owns provider-independent learning rules. Repositories abstract persistence. Integrations adapt LLM, speech, payment, and object-storage providers. Configuration comes from the environment.

## Modules

Identity and learner profile; curriculum and lessons; conversation sessions and turns; correction/feedback; progress/streaks; and entitlements/subscriptions. Telugu explanation is a learner-support capability exposed through feedback services.

## Evolution

Use PostgreSQL and Alembic when persistence begins. Add an asynchronous job mechanism only for demonstrably slow work. Keep payment and object storage behind future ports. Avoid service extraction until independent scaling, availability, or team ownership provides measurable value.

Provider protocols now isolate tutor/evaluation, transcription, and synthesis. Runtime behavior uses local deterministic implementations. PostgreSQL turn sequencing locks the parent conversation row, calculates the next number, and relies on the unique constraint with bounded retry; SQLite remains deterministic for sequential tests.

Voice routes validate transport, `VoiceService` enforces consent/privacy, repositories own transactions, and protocols isolate fake STT/TTS/pronunciation. Cleanup is deterministic and in-process here; production needs a durable scheduler and authenticated ownership context.
