---
description: "Batch address review feedback — find open PRs with actionable reviews and run dev-address-review on each in parallel"
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "Agent", "SendMessage"]
---

# Batch Address Review Feedback

You are the **delivery coordinator** for AgroGame. You discover the set of open
PRs that carry actionable review feedback (tech "request changes", PO "REVISE",
or unaddressed blocking/nit comments) and fan out one isolated
`dev-address-review` agent per PR to fix and respond, then collect the results.
This is the batch wrapper around `/dev-address-review` — the per-PR fix/respond
logic lives there; do not reimplement it.

## Input

`$ARGUMENTS` is optional:
- Empty → address **all** open PRs that have unaddressed actionable feedback.
- A space-separated list of `pr` or `issue #pr` items (e.g. `356 #354`) → address
  exactly those.
- `--all` → include every open PR that has any review, even if it looks already
  addressed (re-run).

## Workflow

### Step 1: Discover the work-set

```bash
unset GITHUB_TOKEN && gh pr list --repo gedejong/agrogame --state open \
  --json number,title,headRefName,body,isDraft,reviewDecision --limit 50
```

A PR has **actionable feedback** if any of these hold:
- `reviewDecision == "CHANGES_REQUESTED"`, or a review whose state is
  `CHANGES_REQUESTED`:
  ```bash
  unset GITHUB_TOKEN && gh api repos/gedejong/agrogame/pulls/<n>/reviews \
    --jq '[.[] | select(.state == "CHANGES_REQUESTED" or (.body | test("Request Changes|Request changes")))] | length'
  ```
- A tech review body matches `Tech Review — Request Changes`, or the linked
  issue has a PO comment matching `PO Review — REVISE` / `PO Review — REJECT`:
  ```bash
  unset GITHUB_TOKEN && gh api repos/gedejong/agrogame/issues/<issue>/comments \
    --jq '[.[] | select(.body | test("PO Review — (REVISE|REJECT)"))] | length'
  ```
- There are inline review comments (`/pulls/<n>/comments`) that constitute nits
  worth addressing.

Resolve each PR's linked issue (branch `feat/<n>-...`, title `feat(#<n>): ...`,
or `Closes #<n>`) so the agent can read PO feedback on the issue.

Unless `--all`, **skip PRs whose feedback is already addressed** — i.e. the PR
has a `## Review feedback addressed` comment newer than the latest review/blocking
comment. Report those as "already addressed — skipped".

If the resulting set is empty, report "No open PRs have unaddressed feedback" and
stop.

### Step 2: Present the plan

List each PR with its resolved issue and the feedback source (tech / PO / nits),
one line each. Proceed straight to fan-out; no confirmation prompt.

### Step 3: Fan out one agent per PR

For each PR, launch a **background** `Agent` with **`isolation: "worktree"`**
(each agent checks out the PR branch, edits code, commits, and pushes — worktrees
are mandatory to keep the working trees from colliding). Launch concurrently in a
single message; cap at ~5 at a time and batch if there are more.

Each agent's prompt must instruct it to:
- Invoke the `dev-address-review` skill (Skill tool) with `<issue> #<pr>` (or the
  bare PR number) as its argument, and follow it end-to-end: gather all feedback,
  categorize, fix blocking + nits, verify, push, and respond on the PR (and the
  issue for PO feedback).
- Work in its own worktree; `gh pr checkout <n>` there and `git push` back to the
  PR's own branch (never force-push without asking).
- Run only the **targeted** tests for the changed code before pushing; the full
  suite runs in CI (per CLAUDE.md) — do not block on a full local `pytest`.
- Fix the root cause, never weaken tests/thresholds to satisfy feedback.
- If a piece of feedback is genuinely wrong or needs a product decision, make the
  safe change and leave a reasoned comment rather than guessing on scope.
- Report back: PR number, issue number, counts (N blocking / M nits / K
  discussion) addressed, one-line summary of the fix, targeted-test result, and
  anything intentionally left unchanged with the reason.

### Step 4: Collect and summarize

When all agents finish, print a table:

```markdown
## Batch address-review — N PRs

| PR | Issue | Blocking | Nits | Discussion | Tests | Notes |
|----|-------|----------|------|------------|-------|-------|
| #356 | #341 | 1 | 2 | 0 | 42 targeted | ready for re-review |
```

Note which PRs are now ready for re-review (`/review-prs`, `/po-reviews`), and
surface anything an agent left unaddressed (with its reason) so you can decide
whether it needs a follow-up issue or a product call.

## Constraints

- **Never merge** any PR — addressing feedback only.
- **Never force-push** without asking the user.
- The base branch is the repo default (`main`); there is no `develop`.
- Don't reimplement fix/respond logic here — delegate to `dev-address-review`.
- If an agent dies or returns nothing, note it as "address-review failed — needs
  a manual re-run" rather than silently claiming the feedback was handled.
