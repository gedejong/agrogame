---
description: "Batch tech review — find open PRs and run review-pr on each in parallel"
allowed-tools: ["Read", "Glob", "Grep", "Bash", "Agent", "SendMessage"]
---

# Batch Tech Review

You are the **review coordinator** for AgroGame. You discover the set of open PRs
that still need a technical review and fan out one isolated `review-pr` agent per
PR, then collect the verdicts. This is the batch wrapper around `/review-pr` —
the per-PR review logic lives there; do not reimplement it.

## Input

`$ARGUMENTS` is optional:
- Empty → review **all** open PRs that don't already have a tech review.
- A space-separated list of PR numbers (e.g. `354 356`) → review exactly those.
- `--all` → review every open PR, even ones already tech-reviewed (re-review).

## Workflow

### Step 1: Discover the work-set

```bash
unset GITHUB_TOKEN && gh pr list --repo gedejong/agrogame --state open \
  --json number,title,headRefName,isDraft --limit 50
```

- Drop draft PRs unless explicitly named in `$ARGUMENTS`.
- Unless `--all` is passed, **skip PRs that already carry a tech review** (avoid
  duplicate reviews):
  ```bash
  # A PR is already tech-reviewed if a review body matches "Tech Review —":
  unset GITHUB_TOKEN && gh api repos/gedejong/agrogame/pulls/<n>/reviews \
    --jq '[.[] | select(.body | test("Tech Review —"))] | length'
  ```
- If specific numbers were given in `$ARGUMENTS`, use exactly those (still honor
  the skip rule unless `--all`).

If the resulting set is empty, report "No open PRs need a tech review" and stop.

### Step 2: Present the plan

List the PRs you're about to review (number + title). Keep it to one line each.
No confirmation prompt needed — proceed straight to fan-out.

### Step 3: Fan out one agent per PR

For each PR, launch a **background** `Agent` with **`isolation: "worktree"`**
(each reviewer checks out the PR branch to read files and run realism scenarios;
worktrees keep those checkouts from colliding). Launch them in a single message
so they run concurrently. Cap concurrency at ~5 at a time; if there are more,
launch the first batch, wait for completions, then launch the next.

Each agent's prompt must instruct it to:
- Invoke the `review-pr` skill (Skill tool) with the PR number as its argument.
- Follow that skill end-to-end: gather context, review all dimensions, post the
  review to the PR via `gh`, and apply the In-Test gate logic.
- Work entirely within its own worktree; `gh pr checkout <n>` there if it needs
  the PR's file versions.
- Report back: PR number, verdict (Approve / Request changes), a one-line
  rationale, and the count of blocking findings + nits.

### Step 4: Collect and summarize

As each agent completes, record its verdict. When all are done, print a table:

```markdown
## Batch tech review — N PRs

| PR | Title | Verdict | Blocking | Nits |
|----|-------|---------|----------|------|
| #354 | ... | Approve | 0 | 2 |
| #356 | ... | Request changes | 1 | 0 |
```

Then call out any **Request changes** PRs explicitly with their blocking issue,
and note which PRs are now gated to In Test (both tech + PO approved).

## Constraints

- **Never merge** any PR — reviewing only.
- The base branch is the repo default (`main`); there is no `develop`.
- Don't reimplement review logic here — delegate to `review-pr` in each agent.
- If an agent dies or returns nothing, note it as "review failed — needs a
  manual re-run" rather than silently dropping the PR.
