# CTX Telemetry Schema

| 항목 | 값 |
|---|---|
| 작성일 | 2026-05-05 |
| 스키마 버전 | 1 |
| 로그 경로 | `~/.claude/ctx-telemetry.jsonl` |
| 활성화 | `CTX_TELEMETRY=1` env 또는 `~/.claude/ctx-telemetry.enabled` 파일 |
| 비활성화 | 위 조건 없으면 zero overhead (early return) |
| 비차단 | 모든 emit은 `try/except Exception: pass` 로 감싸짐 — telemetry 오류가 hook 을 죽이지 않음 |

## 레코드 공통 필드

모든 이벤트 레코드에 포함:

| 필드 | 타입 | 설명 |
|---|---|---|
| `ts` | int | Unix timestamp (초) |
| `schema` | int | 스키마 버전 (현재 1) |
| `project` | str | CWD 마지막 세그먼트 (≤40자) — 경로 노출 방지 |
| `ab_group` | str | `control` / `treatment` / `ungrouped` |
| `type` | str | 이벤트 타입 (아래 표 참조) |

## 이벤트 타입별 필드

### `hook_complete` (bm25-memory 주요 메트릭)

bm25-memory.py 가 매 호출마다 종료 직전에 emit. **주 분석 대상.**

| 필드 | 타입 | 설명 |
|---|---|---|
| `hook` | str | `"bm25-memory"` |
| `latency_ms` | int | 전체 hook 처리 시간 (ms) |
| `exit_code` | int | 정상 종료 시 `0` |
| `query_type` | str | `_classify_query_type()` 결과 (keyword / korean / etc.) |
| `g1_count` | int | G1 에서 반환된 decision 수 |
| `g2_docs_count` | int | G2-DOCS 에서 반환된 chunk 수 |
| `g2_code_count` | int | G2-CODE (graph 또는 grep) 에서 반환된 파일/노드 수 |
| `g2_hooks_count` | int | G2-HOOKS 에서 반환된 hook 파일 수 |
| `g1_top_score_bm25` | float | G1 BM25 최고 점수 (있을 때만) |
| `g1_top_score_dense` | float | G1 dense 최고 점수 (있을 때만) |
| `fallback_reasons` | str | comma-separated: `vec_daemon_down`, `bge_daemon_down`, `mcp_db_stale`, `mcp_db_missing` |
| `blocks_fired` | str | comma-separated: 실제 출력된 block 태그 (`g1`, `g2_docs`, `g2_prefetch`, `g2_grep`, `g2_hooks`) |

### `prompt_received` (bm25-memory 선택적, 진입 직후)

| 필드 | 타입 | 설명 |
|---|---|---|
| `hook` | str | `"bm25-memory"` |
| `query_type` | str | 분류 결과 |
| `prompt_len` | int | prompt 문자 수 |

### `g1_done` (bm25-memory, G1 완료 시)

| 필드 | 타입 | 설명 |
|---|---|---|
| `hook` | str | `"bm25-memory"` |
| `g1_count` | int | 반환 건수 |
| `g1_top_score_bm25` | float | BM25 최고 점수 (있을 때만) |
| `g1_top_score_dense` | float | dense 최고 점수 (있을 때만) |
| `duration_ms` | int | G1 단계 소요 시간 |

### `g2_docs_done` (bm25-memory, G2-DOCS 완료 시)

| 필드 | 타입 | 설명 |
|---|---|---|
| `hook` | str | `"bm25-memory"` |
| `g2_docs_count` | int | 반환 chunk 수 |
| `top_score` | float | 최고 점수 (있을 때만) |
| `duration_ms` | int | 소요 시간 |

### `g2_code_done` (bm25-memory, G2-CODE 완료 시)

| 필드 | 타입 | 설명 |
|---|---|---|
| `hook` | str | `"bm25-memory"` |
| `g2_code_count` | int | 반환 수 |
| `fallback_reason` | str | `"grep_fallback"` (DB 없을 때) |
| `duration_ms` | int | 소요 시간 |

### `g2_hooks_done` (bm25-memory, G2-HOOKS 완료 시)

| 필드 | 타입 | 설명 |
|---|---|---|
| `hook` | str | `"bm25-memory"` |
| `g2_hooks_count` | int | 반환 hook 파일 수 |
| `duration_ms` | int | 소요 시간 |

### `block_fired` (bm25-memory, 레거시 — 블록 단위)

| 필드 | 타입 | 설명 |
|---|---|---|
| `hook` | str | `"bm25-memory"` |
| `block` | str | `g1_decisions` / `g2_docs` / `g2_prefetch` / `g2_grep` / `g2_hooks` |
| `count` | int | 항목 수 |
| `duration_ms` | int | 소요 시간 |

### `hook_invoked` (bm25-memory, 레거시 호환용)

dashboard 하위호환을 위해 유지. `hook_complete` 로 마이그레이션 권장.

| 필드 | 타입 | 설명 |
|---|---|---|
| `hook` | str | `"bm25-memory"` |
| `duration_ms` | int | 전체 소요 시간 |
| `prompt_len` | int | prompt 길이 |

### chat-memory 이벤트 (기존, 변경 없음)

| 타입 | 설명 |
|---|---|
| `mode_switch` | hybrid ↔ bm25-only 전환 |
| `warning_fired` | daemon_down 등 경고 |
| `auto_index` | 인덱스 자동 업데이트 |
| `utility_measured` | Stop hook utility rate 측정 |
| `wow_fired` | high-utility + old-decision recall 달성 |

### 기타 공통 이벤트

| 타입 | hook | 설명 |
|---|---|---|
| `decision_captured` | memory-keyword-trigger | 키워드 감지로 결정 기록 유도 |
| `grep_signal` | g2-fallback | Grep 결과 빈약 감지 |
| `ab_skipped` | bm25-memory / chat-memory | A/B control arm skip |

## 프라이버시 계약

- prompt 내용, 파일 내용, 검색 결과 텍스트, 키워드, DB 행 **절대 기록 안 함**.
- 카운트, 시간, 점수, 분류 태그만 기록.
- 로컬 전용 — 네트워크 전송 없음.
- whitelist 기반 sanitize: `_ALLOWED_KEYS` 에 없는 필드는 자동 제거.
