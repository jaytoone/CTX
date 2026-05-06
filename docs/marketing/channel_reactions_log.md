# CTX Channel Reactions Log
Last updated: 2026-05-06

## GeekNews (news.hada.io/topic?id=29124)
- **Points**: 1P
- **Comments**: 3
  - `kurthong`: Technical question — Korean BM25 tokenization (CJK handling, Lindera ko-dic mention) → Answered ✅
  - `nave94` (us): Update notice v0.3.13, plugin install priority
  - `nave94` (us): Video link + Dev.to link
- **"함께 보면 좋은 글"** section showing 5 related posts (claude-mem, context plugin, etc.) — good sign for algorithm

## Hacker News (item?id=47996700)
- **Points**: 0
- **Comments**: 0
- Posted via Dev.to URL (GitHub URL was blocked for new account)
- Low traction — expected for new account

## Dev.to
- **Reactions**: 1
- **Comments**: 0
- URL: dev.to/jaewon_jang_d63fddcf69ac2/ctx-i-gave-claude-code-a-memory-that-actually-works-45id

## LinkedIn
- **Reactions**: 1 (이충훈, 12h after post)
- **Comments**: 0
- Profile views: 21 searches this week, Taehee Kim visited
- Post: "Claude Code 켰는데, 또 처음부터 설명해야 하는..." with video

---

## Reaction Checking Flow (for future automation project)

```
Channel          | Method                    | Auth needed        | URL
-----------------|---------------------------|--------------------|------------------------------
GeekNews         | curl scrape               | None (public)      | news.hada.io/topic?id=29124
HN               | curl scrape               | None (public)      | news.ycombinator.com/item?id=47996700
Dev.to           | /api/articles API         | None (public)      | dev.to/jaewon_jang_d63fddcf69ac2/...
LinkedIn         | Browser (Playwright)      | be2jay67@gmail.com | linkedin.com/feed/
GitHub Issues    | GitHub API                | GITHUB_TOKEN       | github.com/jaytoone/CTX/issues
GitHub Stars     | GitHub API                | GITHUB_TOKEN       | github.com/jaytoone/CTX
GitHub Discussions| GitHub API               | GITHUB_TOKEN       | github.com/jaytoone/CTX/discussions
```

## GitHub Current Status
- **Stars**: check via `curl https://api.github.com/repos/jaytoone/CTX | python3 -c "import sys,json; d=json.load(sys.stdin); print('stars:', d['stargazers_count'])"`
- **Open Issues**: 1 (tunaCtx PR offer from hang-in — awaiting their PR)
- **Forks**: check via API
- **Key signals**: star velocity, issue quality, fork count

## Key Signals to Watch
- GeekNews: votes (algorithm threshold ~10), comments activity
- HN: points (need >3 to surface), self-post comment to seed discussion
- Dev.to: reactions + reading_time_minutes (quality signal)
- **GitHub**: stars/day, issue quality, fork count (strongest signal of real adoption)
- LinkedIn: reactions, comments, profile visits

## Next Actions
- GeekNews kurthong CJK question → consider implementing CJK bigram improvement
- HN: add self-comment with install instructions + benchmark numbers
- LinkedIn: check in 24h for reactions
