#!/usr/bin/env python3
"""
G1 Fair Evaluation - BM25 Structural Bias Removal

Goal:
  Measure how much of BM25 Structural Recall@7=1.000 is due to
  token overlap between queries and ground-truth commit subjects.

Approach:
  1. Load 59 Type1 QA pairs (original: "When did we implement X?")
  2. Paraphrase each query to remove keyword overlap via MiniMax M2.5
  3. Generate 20 Type2/3/4 (why/what/rationale) queries from commit bodies
  4. Run BM25 Structural Recall@7 on: original vs paraphrase vs type2-4
  5. Report the bias gap
"""

import json
import os
import re
import time
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional

REPO_PATH = Path(__file__).parent.parent.parent
RESULTS_DIR = REPO_PATH / "benchmarks" / "results"
QA_PAIRS_FILE = RESULTS_DIR / "g1_qa_pairs.json"
DECISION_COMMITS_FILE = RESULTS_DIR / "g1_decision_commits.json"
OUTPUT_FILE = RESULTS_DIR / "g1_fair_eval_results.json"


def get_llm_client():
    try:
        import anthropic
        minimax_key = os.environ.get("MINIMAX_API_KEY", "")
        minimax_url = os.environ.get("MINIMAX_BASE_URL", "")
        if minimax_key and minimax_url:
            return anthropic.Anthropic(api_key=minimax_key, base_url=minimax_url)
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if key:
            return anthropic.Anthropic(api_key=key)
    except ImportError:
        pass
    return None


def call_llm(client, system: str, user: str, model: str = "", max_tokens: int = 2048) -> str:
    if not model:
        model = os.environ.get("MINIMAX_MODEL") or "MiniMax-Text-01"
    if client is None:
        return "[NO-CLIENT]"
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": user}],
            system=system,
        )
        for block in resp.content:
            if getattr(block, "type", "") == "text" and hasattr(block, "text"):
                return block.text.strip()
        for block in resp.content:
            if hasattr(block, "text"):
                return block.text.strip()
        return "[NO-TEXT-BLOCK]"
    except Exception as exc:
        return f"[LLM-ERROR] {exc}"


def build_bm25_index(commit_corpus: List[Dict]):
    from rank_bm25 import BM25Okapi

    def tokenize(text: str) -> List[str]:
        return re.findall(r'\b\w+\b', text.lower())

    subjects = [c.get('subject', '') for c in commit_corpus]
    tokenized = [tokenize(s) for s in subjects]
    bm25 = BM25Okapi(tokenized)
    return bm25, subjects


def bm25_structural_recall(
    query: str,
    gt_commit_hash: str,
    commit_corpus: List[Dict],
    bm25,
    k: int = 7
) -> Tuple[bool, float, int]:
    def tokenize(text: str) -> List[str]:
        return re.findall(r'\b\w+\b', text.lower())

    clean_q = re.sub(
        r'^(when did we implement|when did we|why did we|what (?:is|was|were)|how did|when was)\s+',
        '', query.lower(), flags=re.IGNORECASE
    )
    query_tokens = tokenize(clean_q)
    scores = bm25.get_scores(query_tokens)

    gt_idx = None
    for i, c in enumerate(commit_corpus):
        h = c.get('hash', '')
        if h.startswith(gt_commit_hash[:7]) or gt_commit_hash.startswith(h[:7]):
            gt_idx = i
            break

    if gt_idx is None:
        return False, 0.0, -1

    top_k_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    gt_score = float(scores[gt_idx])
    all_ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    gt_rank = all_ranked.index(gt_idx) + 1
    in_top_k = gt_idx in top_k_indices
    return in_top_k, gt_score, gt_rank


def compute_token_overlap(query: str, gt_subject: str) -> float:
    def tokenize(text: str) -> set:
        stop_words = {'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'and', 'or',
                      'but', 'is', 'are', 'was', 'were', 'did', 'we', 'when', 'why', 'what',
                      'how', 'implement', 'implemented', 'add', 'added'}
        words = re.findall(r'\b\w+\b', text.lower())
        return set(w for w in words if w not in stop_words and len(w) > 2)

    q_tokens = tokenize(query)
    s_tokens = tokenize(gt_subject)
    if not q_tokens or not s_tokens:
        return 0.0
    return len(q_tokens & s_tokens) / len(q_tokens | s_tokens)


def generate_paraphrases_batch(client, qa_pairs: List[Dict], batch_size: int = 10) -> List[str]:
    paraphrases = []
    for i in range(0, len(qa_pairs), batch_size):
        batch = qa_pairs[i:i + batch_size]
        n_batches = (len(qa_pairs) - 1) // batch_size + 1
        print(f"  Paraphrasing batch {i//batch_size + 1}/{n_batches} ({len(batch)} pairs)...")

        items = []
        for j, qa in enumerate(batch):
            gt_subject = qa['ground_truth']['subject']
            query = qa['query']
            items.append(f"{j+1}. Query: {query}\n   GT commit: {gt_subject}")

        batch_text = "\n\n".join(items)

        system = (
            "You are a query paraphrase expert for retrieval benchmark construction. "
            "Your task: paraphrase queries to remove token overlap with ground-truth documents, "
            "while preserving the semantic intent. "
            "Rules: keep same question intent, avoid exact keywords from GT commit, "
            "use synonyms/descriptions/indirect references, keep question natural. "
            "Respond with JSON array ONLY."
        )

        user = (
            f"Paraphrase these queries to remove keyword overlap with their GT commits.\n"
            f"The paraphrase must NOT contain the main technical keywords from the GT commit.\n\n"
            f"{batch_text}\n\n"
            f'Respond with JSON array: [{{"original": "...", "paraphrase": "..."}}]\n'
            f"One entry per query, in same order."
        )

        response = call_llm(client, system, user, max_tokens=3000)

        try:
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                batch_paraphrases = [p.get('paraphrase', batch[k]['query']) for k, p in enumerate(parsed)]
            else:
                batch_paraphrases = [qa['query'] for qa in batch]
                print(f"    [WARN] JSON parse failed, using originals")
        except (json.JSONDecodeError, IndexError, KeyError):
            batch_paraphrases = [qa['query'] for qa in batch]
            print(f"    [WARN] JSON error, using originals")

        paraphrases.extend(batch_paraphrases)
        if i + batch_size < len(qa_pairs):
            time.sleep(1)

    return paraphrases


def generate_type234_queries(client, decision_commits: List[Dict], n: int = 20) -> List[Dict]:
    with_body = [c for c in decision_commits if len(c.get('body', '').strip()) > 30]
    step = max(1, len(with_body) // n)
    sampled = with_body[::step][:n]

    print(f"  Generating Type2/3/4 queries for {len(sampled)} commits...")
    type234_pairs = []

    system = (
        "You generate evaluation queries for a retrieval system indexing git commits. "
        "Given a commit subject+body, generate a question that: "
        "1) can only be answered from the body (not just subject), "
        "2) does NOT repeat exact keywords from subject, "
        "3) is natural. "
        "Respond with JSON only."
    )

    for i, commit in enumerate(sampled):
        subject = commit.get('subject', '')
        body = commit.get('body', '').strip()[:400]
        commit_hash = commit.get('hash', '')
        query_type = ['type2', 'type3', 'type4'][i % 3]

        type_desc = {
            'type2': "why question: 'Why did we...' asking for rationale/motivation",
            'type3': "what question: 'What were the key findings/results of...' asking for outcomes",
            'type4': "rationale question: 'What drove the decision to...' asking for decision reasoning",
        }[query_type]

        user = (
            f"Generate a {type_desc} for this commit.\n\n"
            f"Commit subject: {subject}\n"
            f"Commit body: {body}\n\n"
            f"Rules: avoid main technical keywords from subject, answerable from body.\n"
            f'Respond with JSON: {{"query": "...", "answer_hint": "..."}}'
        )

        response = call_llm(client, system, user, max_tokens=500)

        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                query = parsed.get('query', '')
                if query:
                    type234_pairs.append({
                        'query': query,
                        'query_type': query_type,
                        'ground_truth': {
                            'commit_hash': commit_hash,
                            'subject': subject,
                            'body': body,
                        },
                        'age_bucket': commit.get('age_bucket', 'unknown'),
                    })
        except (json.JSONDecodeError, KeyError):
            pass

        if i % 5 == 4:
            time.sleep(1)

    print(f"  Generated {len(type234_pairs)} Type2/3/4 queries")
    return type234_pairs


def run_fair_eval():
    print("=" * 60)
    print("G1 Fair Evaluation - BM25 Structural Bias Removal")
    print("=" * 60)

    print("\n[1] Loading QA pairs and decision commits...")
    with open(QA_PAIRS_FILE) as f:
        qa_pairs = json.load(f)
    with open(DECISION_COMMITS_FILE) as f:
        decision_commits = json.load(f)

    print(f"  QA pairs: {len(qa_pairs)}")
    print(f"  Decision commits (corpus): {len(decision_commits)}")

    print("\n[2] Building BM25 index...")
    bm25, subjects = build_bm25_index(decision_commits)
    print(f"  Index built: {len(subjects)} documents")

    # Phase A: Original Type1 queries
    print("\n[3] Computing BM25 Structural Recall@7 - Original Type1 queries...")
    original_results = []
    for qa in qa_pairs:
        gt_hash = qa['ground_truth']['commit_hash']
        gt_subject = qa['ground_truth']['subject']
        query = qa['query']

        in_top7, gt_score, gt_rank = bm25_structural_recall(
            query, gt_hash, decision_commits, bm25, k=7
        )
        overlap = compute_token_overlap(query, gt_subject)
        original_results.append({
            'query': query,
            'query_type': 'type1_original',
            'gt_hash': gt_hash,
            'gt_subject': gt_subject,
            'age_bucket': qa['age_bucket'],
            'in_top7': in_top7,
            'gt_score': gt_score,
            'gt_rank': gt_rank,
            'token_overlap': overlap,
        })

    original_recall = sum(1 for r in original_results if r['in_top7']) / len(original_results)
    avg_overlap_original = sum(r['token_overlap'] for r in original_results) / len(original_results)
    print(f"  Original Structural Recall@7: {original_recall:.3f} ({sum(1 for r in original_results if r['in_top7'])}/{len(original_results)})")
    print(f"  Average token overlap: {avg_overlap_original:.3f}")

    # Phase B: Paraphrased queries
    print("\n[4] Generating paraphrased queries via MiniMax M2.5...")
    client = get_llm_client()
    if client is None:
        print("  [ERROR] No LLM client. Set MINIMAX_API_KEY + MINIMAX_BASE_URL")
        sys.exit(1)

    paraphrases = generate_paraphrases_batch(client, qa_pairs, batch_size=10)
    assert len(paraphrases) == len(qa_pairs)

    print("\n[5] Computing BM25 Structural Recall@7 - Paraphrased queries...")
    paraphrase_results = []
    for i, (qa, para_query) in enumerate(zip(qa_pairs, paraphrases)):
        gt_hash = qa['ground_truth']['commit_hash']
        gt_subject = qa['ground_truth']['subject']

        in_top7, gt_score, gt_rank = bm25_structural_recall(
            para_query, gt_hash, decision_commits, bm25, k=7
        )
        overlap = compute_token_overlap(para_query, gt_subject)
        paraphrase_results.append({
            'original_query': qa['query'],
            'paraphrased_query': para_query,
            'query_type': 'type1_paraphrase',
            'gt_hash': gt_hash,
            'gt_subject': gt_subject,
            'age_bucket': qa['age_bucket'],
            'in_top7': in_top7,
            'gt_score': gt_score,
            'gt_rank': gt_rank,
            'token_overlap': overlap,
            'overlap_delta': overlap - original_results[i]['token_overlap'],
        })

    para_recall = sum(1 for r in paraphrase_results if r['in_top7']) / len(paraphrase_results)
    avg_overlap_para = sum(r['token_overlap'] for r in paraphrase_results) / len(paraphrase_results)
    n_para_pass = sum(1 for r in paraphrase_results if r['in_top7'])
    print(f"  Paraphrase Structural Recall@7: {para_recall:.3f} ({n_para_pass}/{len(paraphrase_results)})")
    print(f"  Average token overlap: {avg_overlap_para:.3f}")
    print(f"  Structural bias (original - paraphrase): {original_recall - para_recall:.3f}")

    # Phase C: Type2/3/4 queries
    print("\n[6] Generating Type2/3/4 (why/what/rationale) queries...")
    type234_pairs = generate_type234_queries(client, decision_commits, n=20)

    print("\n[7] Computing BM25 Structural Recall@7 - Type2/3/4 queries...")
    type234_results = []
    for qa in type234_pairs:
        gt_hash = qa['ground_truth']['commit_hash']
        gt_subject = qa['ground_truth']['subject']
        query = qa['query']

        in_top7, gt_score, gt_rank = bm25_structural_recall(
            query, gt_hash, decision_commits, bm25, k=7
        )
        overlap = compute_token_overlap(query, gt_subject)
        type234_results.append({
            'query': query,
            'query_type': qa['query_type'],
            'gt_hash': gt_hash,
            'gt_subject': gt_subject,
            'age_bucket': qa.get('age_bucket', 'unknown'),
            'in_top7': in_top7,
            'gt_score': gt_score,
            'gt_rank': gt_rank,
            'token_overlap': overlap,
        })

    type234_recall = 0.0
    avg_overlap_234 = 0.0
    if type234_results:
        type234_recall = sum(1 for r in type234_results if r['in_top7']) / len(type234_results)
        avg_overlap_234 = sum(r['token_overlap'] for r in type234_results) / len(type234_results)
        n_234_pass = sum(1 for r in type234_results if r['in_top7'])
        print(f"  Type2/3/4 Structural Recall@7: {type234_recall:.3f} ({n_234_pass}/{len(type234_results)})")
        print(f"  Average token overlap: {avg_overlap_234:.3f}")

    # Summary
    combined_count = len(paraphrase_results) + len(type234_results)
    combined_pass = (sum(1 for r in paraphrase_results if r['in_top7']) +
                     sum(1 for r in type234_results if r['in_top7']))
    combined_recall = combined_pass / max(1, combined_count)

    print("\n" + "=" * 60)
    print("FAIR EVAL SUMMARY")
    print("=" * 60)
    print(f"Type1 Original   Recall@7: {original_recall:.3f}  (token overlap: {avg_overlap_original:.3f})")
    print(f"Type1 Paraphrase Recall@7: {para_recall:.3f}  (token overlap: {avg_overlap_para:.3f})")
    print(f"Type2/3/4        Recall@7: {type234_recall:.3f}  ({len(type234_results)} queries, overlap: {avg_overlap_234:.3f})")
    print(f"Combined fair    Recall@7: {combined_recall:.3f}  ({combined_count} queries)")
    print(f"\nBM25 Structural Bias: {original_recall - para_recall:.3f}")
    print(f"  (recall drop when query keywords are removed from Type1 queries)")

    failed_para = [r for r in paraphrase_results if not r['in_top7']]
    if failed_para:
        print(f"\nParaphrase failures ({len(failed_para)}/{len(paraphrase_results)}):")
        for r in failed_para[:5]:
            print(f"  GT rank {r['gt_rank']}: {r['paraphrased_query'][:70]}")
            print(f"           GT: {r['gt_subject'][:60]}")

    output = {
        'fair_eval_type': 'g1_bm25_structural_bias_removal',
        'date': time.strftime('%Y-%m-%d %H:%M:%S'),
        'corpus_size': len(decision_commits),
        'summary': {
            'type1_original': {
                'recall_at_7': original_recall,
                'count': len(original_results),
                'avg_token_overlap': avg_overlap_original,
            },
            'type1_paraphrase': {
                'recall_at_7': para_recall,
                'count': len(paraphrase_results),
                'avg_token_overlap': avg_overlap_para,
                'structural_bias': original_recall - para_recall,
            },
            'type234': {
                'recall_at_7': type234_recall,
                'count': len(type234_results),
                'avg_token_overlap': avg_overlap_234,
            },
            'combined_fair': {
                'recall_at_7': combined_recall,
                'count': combined_count,
            },
        },
        'original_results': original_results,
        'paraphrase_results': paraphrase_results,
        'type234_pairs': type234_pairs,
        'type234_results': type234_results,
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nResults saved to: {OUTPUT_FILE}")
    return output


if __name__ == '__main__':
    env_file = Path.home() / '.claude' / 'env' / 'shared.env'
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    run_fair_eval()
