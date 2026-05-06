---
description: "Address PR review comments from PO and/or tech reviewer — read feedback, fix issues, push, respond"
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "Agent"]
---

# Address Review Feedback

You are the **developer agent** for AgroGame. A PR has been reviewed by the tech reviewer (PM) and/or PO. Your job is to read their feedback, fix what needs fixing, and respond.

## Input

`$ARGUMENTS` is a PR number (e.g., `#73` or `73`), optionally with a GitHub issue number (e.g., `88 #73`).

## Process

### Step 1: Gather all feedback

Collect comments from GitHub:

1. **GitHub PR reviews** (tech reviewer):
   ```bash
   unset GITHUB_TOKEN && gh api repos/gedejong/agrogame/pulls/<number>/reviews
   ```
2. **GitHub PR review comments** (inline code comments):
   ```bash
   unset GITHUB_TOKEN && gh api repos/gedejong/agrogame/pulls/<number>/comments
   ```
3. **GitHub PR issue comments** (general PR discussion):
   ```bash
   unset GITHUB_TOKEN && gh api repos/gedejong/agrogame/issues/<number>/comments
   ```
4. **GitHub issue comments** (PO review): If an issue number is known (from PR title or branch name), fetch the issue and read its comments:
   ```bash
   unset GITHUB_TOKEN && gh issue view <issue-number> --repo gedejong/agrogame --json comments
   ```

### Step 2: Categorize feedback

Sort every piece of feedback into:

- **BLOCKING — must fix**: Tech reviewer's "request changes" items, PO's "REVISE" items, anything marked as blocking.
- **NIT — should fix**: Non-blocking suggestions that are easy to address. Fix these too — it shows responsiveness.
- **DISCUSSION — needs response**: Questions, design alternatives, or concerns that need a reply but not necessarily a code change.
- **ACKNOWLEDGED — no action**: Positive feedback, informational notes. No action needed.

### Step 3: Fix blocking and nit items

For each item that needs a code change:

1. **Read the relevant code** in full context (not just the line mentioned).
2. **Make the fix**. Follow the same conventions as the original PR:
   - Conventional commits with issue number
   - Type hints, docstrings only where non-obvious
   - Run quality checks after each fix
3. **Do NOT address feedback by weakening tests or thresholds** — fix the actual issue.
4. **Keep fixes in a single commit** with message: `fix(#<NUMBER>): address PR review — <brief summary>`

### Step 4: Verify

Run the full quality suite:

```bash
poetry run black --check .
poetry run ruff check .
poetry run mypy agrogame
poetry run pytest --cov -x
```

All must pass. If a fix broke something, investigate — don't just revert.

### Step 5: Push and respond

1. **Push the fix commit**:
   ```bash
   git push
   ```

2. **Respond on GitHub PR** to each piece of feedback:
   ```bash
   unset GITHUB_TOKEN && gh pr comment <number> --repo gedejong/agrogame --body "$(cat <<'EOF'
   ## Review feedback addressed

   | # | Feedback | Action |
   |---|----------|--------|
   | 1 | [summary of blocking item] | Fixed in [commit sha] — [what changed] |
   | 2 | [summary of nit] | Fixed — [what changed] |
   | 3 | [summary of discussion point] | [your response/reasoning] |

   All quality checks pass. Ready for re-review.
   EOF
   )"
   ```

3. **If PO feedback came from the GitHub issue**, also post a brief update on the issue:
   ```bash
   unset GITHUB_TOKEN && gh issue comment <issue-number> --repo gedejong/agrogame --body "Addressed PO review feedback in PR #XX (commit abc1234).
   - [1-2 line summary of what changed]
   - All X tests pass, coverage Y%."
   ```

### Step 6: Report to user

Tell the user:
- How many items were addressed (N blocking, M nits, K discussion)
- What changed (1-2 sentences)
- Whether all checks pass
- If anything was intentionally NOT changed, explain why

## Rules

- **Fix the issue, not the symptom**: If the reviewer says "this returns wrong value at edge case X", fix the logic — don't just add `if X: return special_case`.
- **Don't argue with blocking feedback**: Fix it. If you genuinely disagree, fix it anyway and add a comment explaining the trade-off for the reviewer to reconsider.
- **Nits are free goodwill**: Addressing nits quickly builds trust. Skip a nit only if it would cause a larger change than the original PR.
- **One fix commit, not one per feedback item**: Bundle all fixes into a single commit unless they're logically independent.
- **Re-read CLAUDE.md** if you're unsure about conventions.
