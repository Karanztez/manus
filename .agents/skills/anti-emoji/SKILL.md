---
name: anti-emoji
description: Enforce strict elimination of all Unicode emojis, decorative pictographs, and casual icons across all project files, logs, comments, documentation, and agent responses to maintain an enterprise professional standard.
---

# Anti-Emoji Rule & Skill

## Objective
Maintain a clean, enterprise-grade, professional codebase and logging environment by strictly prohibiting emojis and informal pictographs.

## Rules
1. **No Emojis in Code**:
   - Do not include emojis in log messages (`logger.info`, `print`, error traces).
   - Use clean, standard prefixes instead:
     - `[INFO]`, `[WARN]`, `[ERROR]`, `[DEBUG]`, `[OK]`, `[FAILED]`, `[SUCCESS]`
2. **No Emojis in Documentation**:
   - `README.md`, documentation, commit messages, and config comments must remain purely professional without decorative emojis.
3. **No Emojis in Agent Output**:
   - Responses to the user must be concise, structured, and free of emojis.
