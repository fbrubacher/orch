## Version control: atomic commits

This repository uses git. While implementing the plan:

- If you are currently on the default branch (`main` or `master`), FIRST create a
  dedicated working branch named `orch/<short-kebab-summary-of-the-task>` and
  switch to it. Do all work there.
- Commit in small, **atomic** commits — one logical change per commit — instead of
  a single large commit at the end. Commit as you complete each coherent step.
- Write clear [Conventional Commits](https://www.conventionalcommits.org) messages:
  `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`, etc.
- Prefer running the relevant validation before each commit when practical.
- Do NOT push and do NOT open a pull request here — that happens only after the
  change has passed review.
