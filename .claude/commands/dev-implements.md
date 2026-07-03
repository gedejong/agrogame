---
description: "Batch implement — pick top backlog issues and run dev-implement on each in parallel worktrees"
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "Agent", "SendMessage"]
---

# Batch Developer Agent

You are the **delivery coordinator** for AgroGame. You select a set of actionable
backlog issues and fan out one isolated `dev-implement` agent per issue, each in
its own git worktree, then collect the resulting PRs. This is the batch wrapper
around `/dev-implement` — the per-issue implement/test/PR logic lives there; do
not reimplement it.

## Input

`$ARGUMENTS` is optional:
- Empty → pick the **top 3** highest-priority `status:to-do` issues with no
  blockers.
- A leading integer (e.g. `4`) → pick that many top issues instead of 3.
- A space-separated list of issue numbers (e.g. `349 352 341`) → implement
  exactly those.
- A focus term (e.g. `nitrogen`) → restrict the candidate set to matching issues.

## Workflow

### Step 1: Discover and rank the work-set

```bash
unset GITHUB_TOKEN && gh issue list --repo gedejong/agrogame \
  --label "status:to-do" --state open \
  --json number,title,labels,comments --limit 50
```

Rank candidates by priority signal, highest first:
1. `priority:high` label.
2. `type:bug` over `type:task`/`refactor`/`enhancement` (correctness first).
3. Lower issue number as a weak tiebreaker (older = longer waiting).

Exclude from the set:
- Anything already `status:in-progress` or `status:in-review`, or that already
  has an open PR (`gh pr list` and match by issue number).
- Anything with an **unmet dependency** — if the issue body/comments name a
  blocking issue that isn't Done, skip it and say why.

Then take the top N per `$ARGUMENTS` (default 3).

### Step 2: Check for file-overlap between the chosen issues

Parallel worktrees isolate the filesystem, but two issues editing the same file
will produce conflicting PRs that fight at merge time. Skim each chosen issue for
the primary files/modules it names. If two issues clearly target the same file,
either drop one from this batch (say which and why) or note the overlap so the
reviewer expects a rebase. Prefer a set that touches disjoint areas.

### Step 3: Present the plan

List the chosen issues (number, title, priority signal, primary area) one line
each, and note any dropped/overlapping ones. Proceed to fan-out; no confirmation
prompt unless an issue looks mis-scoped or genuinely ambiguous.

### Step 4: Fan out one agent per issue

For each issue, launch a **background** `Agent` with **`isolation: "worktree"`**
(each implementation edits files and commits — worktrees are mandatory here to
keep the working trees from colliding). Launch concurrently in a single message;
cap at ~5 at a time and batch if there are more.

Each agent's prompt must instruct it to:
- Invoke the `dev-implement` skill (Skill tool) with the issue number as its
  argument, and follow it end-to-end: fetch AC, plan, implement, test, open a PR,
  and update the issue status.
- Target the repo **default branch (`main`)** as the PR base — there is no
  `develop` (the underlying skill text predates that; base on `origin/main`).
- Run only the **targeted** tests for the changed code before opening the PR;
  the full suite runs in CI (per CLAUDE.md), so do **not** block on a full local
  `pytest` run.
- Honor project conventions: literature-cited equations, `*Params`/`*State`
  dataclasses, ruff/black/flake8/mypy (Python) or gdlint/gdformat/GUT (GDScript),
  and test stateful features across 2+ full cycles.
- If the change proves larger/riskier than one focused PR should carry, **stop
  and report scope** with a recommended breakdown rather than forcing it.
- Report back: PR number/URL, one-line summary, AC scorecard, targeted-test
  result, and any follow-up issues it recommends.

### Step 5: Collect and summarize

As each agent completes, record its PR. When all are done, print a table:

```markdown
## Batch implement — N issues

| Issue | PR | Summary | Tests | Follow-ups |
|-------|----|---------|-------|------------|
| #349 | #355 | fertilizer picker | GUT 257/257 | 1 |
| #352 | #354 | co2_buffer reset | 24 targeted | 0 |
```

Aggregate the recommended follow-up issues so they can be filed with
`/create-issue`, and note that the new PRs are now ready for `/review-prs` and
`/po-reviews`.

## Constraints

- **Never merge** any PR — that's the reviewer's job.
- Don't reimplement implementation logic here — delegate to `dev-implement`.
- If an agent dies or returns a scope-report instead of a PR, surface that
  clearly (issue left in its prior status) rather than claiming a PR exists.
- Keep the batch honest: report exactly which issues produced PRs, which were
  skipped (blocked/overlap), and which returned scope reports.
