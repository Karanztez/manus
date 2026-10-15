# Project Rules: Professional Codebase Standards

1. Strict Anti-Emoji Policy:
   - Do NOT use emojis anywhere in this project: source code, logs, comments, documentation, or commit messages.
   - For console logs and alerts, use standard textual tags such as `[INFO]`, `[OK]`, `[WARN]`, `[ERROR]`, or `[CRITICAL]`.
2. Architecture:
   - Keep logic modularized within `src/` (connectors, analysis, managers).
   - All tests and verification scripts belong in `tests/`.
   - All custom agent skills belong in `.agents/skills/`.
