---
description: "Create a well-structured GitHub issue from a description or review finding"
allowed-tools: ["Bash", "Grep", "Read"]
---

# Create GitHub Issue

You are the **project manager** for AgroGame. Turn a description or review finding into a well-structured GitHub issue.

## Input

`$ARGUMENTS` is a natural-language description of the issue, e.g.:
- "the canopy model doesn't track stem biomass separately from leaf biomass"
- "we need to normalize rainfall monthly weights in the generator"
- "add irrigation scheduling to the water model"

## Process

### 1. Check for duplicates

Search existing issues:
```bash
unset GITHUB_TOKEN && gh issue list --repo gedejong/agrogame --search "<key terms>" --json number,title,labels,state
```

If a similar issue exists, tell the user and ask whether to update it or create a new one.

### 1b. Ground the issue in concrete graph references (if `graphify-out/graph.json` exists)

Before drafting the body, name the actual symbols and communities the issue is about. Vague issues ("improve the dashboard") get filed and forgotten; grounded issues ("`agrogame.dashboard.app` imports 12 internal-engine types from 6 soil sub-packages") get refined. For architecture, layering, or refactor issues this is mandatory.

```bash
# Identify the central symbol(s) and pull their graph context:
graphify explain "<SymbolName>"       # plain-language summary + 1-hop neighborhood
graphify query "what depends on <SymbolName>"   # all consumers
# Looking at a community? Cite it by id and label from GRAPH_REPORT.md.
```

Use the result to:
- **Quote actual file paths and line numbers** in the Problem section (not "the dashboard" — `agrogame/dashboard/app.py:33`).
- **Enumerate scope concretely**: "this affects 9 runtimes (listed below)" beats "this affects several runtimes".
- **Cite the relevant ADR** if the graph shows the issue touches a community whose entry in `GRAPH_REPORT.md` references one.

If `graphify-out/` is missing, skip — but for any issue with the words "refactor", "layering", "architecture", or "drift" in the description, prefer to run `graphify` first rather than file an under-specified issue.

### 2. Classify the issue

Determine:
- **Type**: Use labels — `type:feature`, `type:bug`, `type:task`
- **Component**: Which module(s) are affected
- **Dependencies**: What other issues must be done first

### 3. Structure the issue

Write the issue with this structure:

```markdown
## Problem
[What's wrong or missing — 2-3 sentences max. Include concrete evidence:
"NL maize simulates 503 g/m² vs expected 1600" not "yields are low"]

## Acceptance Criteria
- [ ] [Specific, testable criterion]
- [ ] [Each criterion should be independently verifiable]
- [ ] [Include at least one test criterion]
- [ ] [Include quantitative targets where possible]

## Validation Plan
[Manual tests a human performs in "In Test" column after reviews pass:]
1. [Step] → Expected: [outcome]
2. [Step] → Expected: [outcome]
3. [Edge case step] → Expected: [outcome]

## Notes
[Implementation hints, dependencies, references — keep brief]
```

Rules for good acceptance criteria:
- **Testable**: "temp_factor at 20°C returns 0.6-0.8" not "temperature response is better"
- **Scoped**: Each criterion is one thing, not a compound requirement
- **Quantitative**: Include numbers where the domain supports it (literature ranges, performance targets)
- **Independent**: Meeting criterion 3 shouldn't depend on criterion 2

### 4. Create the issue

```bash
unset GITHUB_TOKEN && gh issue create --repo gedejong/agrogame --title "<title>" --body "$(cat <<'EOF'
<structured body from step 3>
EOF
)" --label "type:<type>" --label "status:to-refine"
```

### 5. Report

Tell the user:
- Issue number and URL
- Summary of what was created
- Any related existing issues found
