# [expert-research] PC 포맷 전 완전 백업 인벤토리
**Date**: 2026-04-27  **Skill**: expert-research (Quick Mode — local audit)

## Original Question
desktop-8hiuju8 (Windows host + WSL2 Ubuntu) 포맷 전 완전 백업 인벤토리 작성

## Audit Results

### WSL2 Side

**SSH Keys** (`~/.ssh/`):
- `id_ed25519` (primary, Mar 22)
- `id_container`, `id_container_nipa_fresh`, `id_container_nipa_new`
- `aether-b200-v28-1_key` (Apr 12)
- `DCTN-0413110535-1_key`, `DCTN-0417120013-1_key`, `DCTN-0417120013-2_key`

**vault.db**: 418MB — irreplaceable chat memory

**~/.claude/**: hooks 3.3MB / skills 2.3MB / env 28KB — GitHub private repo에 백업됨

**Systemd (enabled)**: claude-client-bootstrap, claude-code-router, session-migration

**Python**: torch 2.10, transformers 4.57, sentence-transformers, rank-bm25, anthropic, openai

**Node**: v22.19.0 (nvm)

**미push 리포 (긴급)**:
| 프로젝트 | 미커밋 | 미push |
|---------|--------|--------|
| CTX | 98 | **246** |
| Entity | 13 | **102** |
| Miro | 3 | 21 |
| FRWP | 106 | 2 |
| Clone | 85 | 1 |

### Windows Host Side

**SSH Keys** (`C:\Users\Jayone\.ssh\`): id_ed25519, id_container, authorized_keys

**D:\Project git 상태**:
| 프로젝트 | 미커밋 | 미push |
|---------|--------|--------|
| ASI | 250 | 0 |
| shortd-next | 67 | **15** |
| BnT | NO GIT | — |
| ManualTrade | NO GIT | — |
| PacketAnalyzer | NO GIT | — |
| SystemTrade | NO GIT | — |

**VS Code**: 34개 확장 (anthropic.claude-code, ms-vscode-remote.* 등)

**npm globals**: @railway/cli, vercel, typescript-language-server, claude-code-monitoring-agent

**설치 앱**: Tailscale 1.96.3, Docker Desktop 4.43.1, NVM 1.2.2, Python 3.8/3.11, Node 18.12.1

## Final Conclusion

### 최우선 처리 항목
1. CTX 246 + Entity 102 + shortd-next 15 unpushed 커밋 → `git push`
2. BnT/ManualTrade/PacketAnalyzer/SystemTrade → 외장 드라이브 복사 (No git)
3. vault.db (418MB) → 외장 드라이브

### 포맷 전 작업 순서
1. git push 미push repos (CTX, Entity, shortd-next, Miro)
2. git commit + push (ASI 250미커밋, FRWP, Clone)
3. No-git 프로젝트 외장 복사
4. `wsl --export Ubuntu backup.tar`
5. ~/.ssh/ 복사 (WSL2 + Windows)
6. vault.db 복사
7. ~/.claude/env/ 복사
8. `code --list-extensions > vscode-ext.txt`

### 포맷 후 복구
- WSL2: `wsl --import` or `wsl --install` + git clone all repos
- 클라이언트: `irm http://100.66.30.40:9955/bootstrap | iex` (SSH config 자동 설정 포함)
- hooks: github.com/jaytoone/claude-client-bootstrap (private) 에서 복원
