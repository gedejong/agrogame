---
description: "Batch PO review — find open PRs and run po-review against each issue's AC in parallel"
allowed-tools: ["Bash", "Grep", "Read", "Agent", "SendMessage"]
---

# Batch Product-Owner Review

You are the **PO review coordinator** for AgroGame. You discover the set of open
PRs whose delivered work still needs a product-owner review, pair each PR with
its GitHub issue, and fan out one isolated `po-review` agent per pair, then
collect the verdicts. This is the batch wrapper around `/po-review` — the
per-issue evaluation logic (adversarial AC scoring, realism assessment) lives
there; do not reimplement it.

## Input

`$ARGUMENTS` is optional:
- Empty → PO-review **all** open PRs that don't already have a PO review.
- A space-separated list of `issue #pr` pairs or bare PR numbers (e.g. `352 #354`
  or just `354`) → review exactly those. Resolve the issue from the PR branch or
  title when only a PR number is given.
- `--all` → review every open PR, even ones already PO-reviewed.

## Workflow

### Step 1: Discover the work-set

```bash
unset GITHUB_TOKEN && gh pr list --repo gedejong/agrogame --state open \
  --json number,title,headRefName,body,isDraft --limit 50
```

For each PR, resolve the linked GitHub issue number from the branch name
(`feat/<n>-...` / `worktree-...`), the title (`feat(#<n>): ...`), or a `Closes
#<n>` in the body. If no issue can be resolved, note it and skip (PO review
scores against an issue's AC — there's nothing to score without one).

- Drop drafts unless explicitly named.
- Unless `--all`, **skip PRs whose issue already has a PO review**:
  ```bash
  # Already PO-reviewed if an issue comment matches "PO Review —":
  unset GITHUB_TOKEN && gh api repos/gedejong/agrogame/issues/<issue>/comments \
    --jq '[.[] | select(.body | test("PO Review —"))] | length'
  ```

If the resulting set is empty, report "No open PRs need a PO review" and stop.

### Step 2: Present the plan

List each PR with its resolved issue (e.g. `#354 → issue #352 — <title>`), one
line each. Proceed straight to fan-out; no confirmation prompt.

### Step 3: Fan out one agent per PR/issue pair

For each pair, launch a **background** `Agent` with **`isolation: "worktree"`**
(PO review pulls the PR branch and runs realism scenarios / manual before-after
comparisons against `main` — worktrees keep those checkouts and `git stash`
dances from colliding). Launch concurrently in a single message; cap at ~5 at a
time and batch if there are more.

Each agent's prompt must instruct it to:
- Invoke the `po-review` skill (Skill tool) with `<issue> #<pr>` as its argument.
- Follow that skill end-to-end: adversarial AC scoring (read the actual test
  assertions), the deep realism assessment (run `tests/integration/test_realism.py`
  and a before/after scenario itself), scope-creep check, verdict, and post the
  review to both the issue and the PR via `gh`. Apply the In-Test gate logic.
- Work entirely within its own worktree; `gh pr checkout <n>` there.
- Report back: PR number, issue number, verdict (ACCEPT / ACCEPT WITH FOLLOW-UP
  / REVISE / REJECT), AC scorecard as X/Y met, realism OK/CONCERNS/N/A, and any
  follow-up issues it recommends.

### Step 4: Collect and summarize

When all agents finish, print a table:

```markdown
## Batch PO review — N PRs

| PR | Issue | Verdict | AC met | Realism | Follow-ups |
|----|-------|---------|--------|---------|------------|
| #354 | #352 | ACCEPT | 3/3 | OK | none |
| #357 | #351 | ACCEPT WITH FOLLOW-UP | 4/4 | OK | 1 |
```

Call out any **REVISE / REJECT** verdicts with the specific gap, and aggregate
the recommended follow-up issues so they can be filed with `/create-issue`.
Note which issues are now gated to In Test (both PO + tech approved).

## Constraints

- **Skeptical by default** is the per-review skill's job — your job is to make
  sure every open PR actually gets that scrutiny, none skipped.
- The base branch is the repo default (`main`); there is no `develop`.
- Don't reimplement PO logic here — delegate to `po-review` in each agent.
- If an agent dies or returns nothing, note it as "PO review failed — needs a
  manual re-run" rather than silently dropping the PR.
