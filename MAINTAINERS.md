# Maintainers

This file lists the maintainers of CTX and how responsibility is divided.

## Active maintainers

| GitHub | Areas of ownership |
|---|---|
| [@jaytoone](https://github.com/jaytoone) | Retrieval algorithm direction, paper alignment, benchmark decisions, releases, overall project direction |
| [@hang-in](https://github.com/hang-in) | BM25 / tokenizer, install machinery, golden fixtures, hook hardening, issue triage (weekday afternoons KST), release notes |

This split reflects strengths rather than hard boundaries — anyone may
review or contribute to any area. The split exists to make it clear who
the default reviewer is for a given change, and who is on point for
release-time decisions in that area.

## Decision protocol

- **In-area changes** — the area owner can land changes after standard
  review. Tests + golden + relevant CI must pass.
- **Cross-area changes** — both maintainers should sign off before
  merge. Examples: a tokenizer change that touches benchmark numbers, an
  install-machinery change that affects the retrieval API.
- **Disagreement** — when maintainers disagree, the change owner writes
  a short note in the PR (one paragraph: what's contested, what each
  side prefers, what data would settle it) and the change is held until
  one side concedes or new data lands. Default to "no merge" rather than
  push-through.
- **External contributions** — first review goes to the area owner of
  the change's primary file path. The other maintainer is auto-tagged on
  PRs that touch retrieval algorithm + benchmark numbers together.

## Responsibilities by area

### Retrieval algorithm direction (jaytoone)

- BM25 / dense / RRF blending decisions
- Trigger classifier behavior
- Whether to add/remove a retrieval strategy
- Paper-facing claims and benchmark methodology

### Hook hardening (hang-in)

- `bm25-memory.py` orchestration and module boundaries
- Tokenizer behavior (post-canonical-entry-point unification)
- Install / uninstall machinery (`src/cli/install.py`,
  `src/cli/settings_patcher.py`)
- Golden fixtures (`tests/golden/`) — drift triage, fixture re-capture
  policy
- Determinism guarantees (sort tiebreaks, deterministic golden runs)

### Issue triage (hang-in)

- First-pass label and route within ~1 weekday (afternoons KST)
- Cross-tag `@jaytoone` on retrieval-algorithm or benchmark-claim issues

### Release notes (hang-in, draft) / releases (jaytoone, ship)

- hang-in drafts release notes from the merged PR queue
- jaytoone reviews and ships the release

## Contact

- **GitHub issues** — primary channel for everything
- **Sensitive reports** (security, license concerns) — via
  GitHub's private vulnerability reporting on this repo

## Open meta-tracks

- **`_bm25/` package boundary** — discussion held in a separate tracked
  issue. Decision on monolith vs decomposed package is on a longer
  timescale than the functional fix cadence; deliberately decoupled to
  reduce blast radius.

## Becoming a maintainer

Open in principle. Path: a sustained contribution record (3+ landed PRs
in an area, helpful issue triage), then nominate yourself in an issue
and the active maintainers vote +1.
