make regular and focused commits

# Working process: PM, software engineer, QA

Every task from the user goes through three agent roles, defined in `.claude/agents/`:

- **pm**: grooms the task: requirements, scope and testable acceptance criteria (AC). Never writes code.
- **software-engineer**: implements the task against the AC.
- **qa-engineer**: independently verifies every AC. Either **ACCEPT** (all AC pass) or **REJECT** (lists the failing AC with repro).

## Flow for each task
1. The coordinator (the main Claude session) creates a git worktree and branch for the task:
   `git worktree add ../wt/<slug> -b task/<slug>` (from up-to-date `main`). One task = one worktree. All three roles work only inside that worktree.
2. **PM** reads the user's request and writes `.claude/tasks/<slug>.md` in the worktree (the task file is git-ignored).
3. **Software engineer** implements it with focused commits on the task branch and adds implementation notes to the task file.
4. **QA** runs every AC's `Verify:` step and appends its report.
   - ACCEPT: the coordinator reports to the user.
   - REJECT: the engineer fixes exactly the failing AC, then QA re-checks everything. At most 3 rounds, after that the coordinator escalates to the user.
5. After ACCEPT the coordinator asks the user before merging into `main` and before any push. Merge by rebasing the task branch on `main`, then remove the worktree (`git worktree remove ../wt/<slug>`) and the branch once merged.

## Parallel tasks
Independent tasks run at the same time, each in its own worktree and with its own PM / engineer / QA run. Tasks that touch the same files should be sequenced instead. Agents never share a worktree between tasks and never edit the main checkout.

## Guardrails
- Agents never push, never touch deployments or GitHub settings, and never stage unrelated files.
- The user's own uncommitted changes in the main checkout are left alone.
