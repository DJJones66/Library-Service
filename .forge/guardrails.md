# Guardrails (Signs)

> Lessons learned from failures. Read before acting.

## Core Signs

### Sign: Read Before Writing
- **Trigger**: Before modifying any file
- **Instruction**: Read the file first
- **Added after**: Core principle

### Sign: Test Before Commit
- **Trigger**: Before committing changes
- **Instruction**: Run required tests and verify outputs
- **Added after**: Core principle

---

## Learned Signs

### Sign: Account for Run Log Updates
- **Trigger**: When trying to reach a clean git status
- **Instruction**: Expect `.forge/logs/iter-*.raw.txt` to update per command; document the remaining dirty file in progress logs instead of looping commits
- **Added after**: Iteration 2 - run log updates kept git status dirty
