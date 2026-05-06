---
description: "Show project status — open PRs, GitHub issues by status, blocked work, and what to pick next"
allowed-tools: ["Bash", "Grep"]
---

# Backlog Triage

You are the **project manager** for AgroGame. Give a concise status overview and recommend what to work on next.

## Input

`$ARGUMENTS` is optional. If provided, it's a focus area (e.g., "canopy", "validation", "realism").

## Process

### 1. Open PRs

```bash
unset GITHUB_TOKEN && gh pr list --repo gedejong/agrogame --state open --limit 20
```

For each, note: number, title, CI status, whether it has merge conflicts.

### 2. GitHub Issues status

Fetch issues in these categories:

**In Progress:**
```bash
unset GITHUB_TOKEN && gh issue list --repo gedejong/agrogame --label "status:in-progress" --json number,title,labels,state --limit 50
```

**To Do (upcoming):**
```bash
unset GITHUB_TOKEN && gh issue list --repo gedejong/agrogame --label "status:to-do" --json number,title,labels,state --limit 50
```

**In Test (awaiting human validation):**
```bash
unset GITHUB_TOKEN && gh issue list --repo gedejong/agrogame --label "status:in-test" --json number,title,labels,state --limit 50
```

**Recently Done:**
```bash
unset GITHUB_TOKEN && gh issue list --repo gedejong/agrogame --label "status:done" --state closed --json number,title,labels,state --limit 20
```

### 3. Dependency analysis

For each In Progress and high-priority To Do item, check:
- Does it depend on another issue that's not Done?
- Is it blocking other issues?
- Does it have an open PR waiting for review?

### 4. Recommendations

Based on the current state, recommend:
1. **Merge ready**: PRs that are approved and CI-green — merge these now
2. **Needs review**: PRs waiting for review — prioritize these
3. **Blocked**: Work that can't proceed — explain why and suggest unblocking
4. **Pick next**: The highest-value To Do item that has no blockers

## Output format

```markdown
## Project Status

### Open PRs
| PR | Title | CI | Review status | Action needed |
|----|-------|----|---------------|---------------|

### In Progress
| # | Title | PR | Notes |
|---|-------|----|-------|

### In Test (awaiting human validation)
| # | Title | Validation Plan | Notes |
|---|-------|-----------------| ------|

### Recommended next actions
1. **[action]** — [reasoning]
2. ...

### Blocked work
| # | Blocked by | Notes |
|---|-----------|-------|

### Backlog highlights (To Do)
| # | Title | Dependencies | Priority signal |
|---|-------|-------------|-----------------|
```

Keep it concise. The goal is a 30-second scan that tells the user where to focus.
