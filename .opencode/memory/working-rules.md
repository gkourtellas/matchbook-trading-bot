---
name: working-rules
description: How the user wants me to work — short answers, ask before coding, never assume, plan first
metadata:
  type: feedback
---

Rules the user set on 2026-10-22, after I jumped into coding and used assumed defaults.

**Why:** "we dont shoot first, we ask questions first". The user wants to steer the work, not react to it. I picked stake amounts and horse filters out of thin air and started writing code before they had answered anything.

**How to apply:**

1. **Talk less, less jargon.** Short sentences. Plain English. No long tables, no bullet-point essays. Lead with the answer.
2. **When asked a question, answer the question.** In English, in a few sentences. Do not start editing files, running scripts, or investigating. Stop after answering.
3. **Never assume anything.** If a decision was not given to me (stake, which horses, which market, limits, whether to spend money), ask. Do not pick a "sensible default" and proceed.
4. **Nobody is running to get me.** Slow down. Think first, plan, then code. Investigate before acting, and say what I found before doing anything about it.
5. **Search the whole filesystem, not just the working directory.** The user said "check the matchbook folder" — the bet placing code was in `/home/gk/matchbook`, not in the `horses` project I was sitting in. Look where the user probably means before concluding something does not exist.
