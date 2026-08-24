## Finalize: open a pull request

The implementation has PASSED review. Finalize and open a pull request:

- Ensure every change is committed. If anything remains in the working tree, make
  a final atomic commit with a Conventional Commits message.
- Make sure the work is on a dedicated `orch/<short-summary>` branch, not the
  default branch. If it is on the default branch, create the branch and move the
  commits there.
- Push the branch to `origin` with `git push -u origin <branch>`.
- Open a pull request with `gh pr create`, giving it a concise title and a body
  that summarises WHAT changed, WHY, and HOW it was validated (include the key
  validation command results). Note any follow-ups.
- Print the resulting pull request URL on its own line as the last thing you output.

Do NOT merge the pull request — leave it open for human review.
