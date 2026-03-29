"""
TriggerClassifier.classify_intent — 한국어/영어 단위 테스트

Coverage:
  - 한국어 modify intent (수정, 고쳐, 변경, 바꿔, 리팩토링, 개선, 삭제)
  - 한국어 create intent (만들어, 작성, 구현, 생성, 추가, 새로운)
  - 한국어 read intent (설명, 분석, 보여줘, 어떻게)
  - 영어 기존 동작 회귀 방지
  - 혼합 문장 (한국어+영어 키워드 공존)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.trigger.trigger_classifier import TriggerClassifier


@pytest.fixture
def clf():
    return TriggerClassifier()


# ── 한국어 MODIFY ──────────────────────────────────────────────────────────────

class TestKoreanModify:
    def test_수정(self, clf):
        assert clf.classify_intent("이 함수 수정해줘") == "modify"

    def test_수정_standalone(self, clf):
        assert clf.classify_intent("retrieve 함수 수정") == "modify"

    def test_고쳐(self, clf):
        assert clf.classify_intent("이 코드 고쳐줘") == "modify"

    def test_변경(self, clf):
        assert clf.classify_intent("변경해서 재실행해") == "modify"

    def test_바꿔(self, clf):
        assert clf.classify_intent("로직 바꿔줘") == "modify"

    def test_리팩토링(self, clf):
        assert clf.classify_intent("전체 리팩토링 해줘") == "modify"

    def test_개선(self, clf):
        assert clf.classify_intent("성능 개선해줘") == "modify"

    def test_삭제(self, clf):
        assert clf.classify_intent("이 코드 삭제해줘") == "modify"

    def test_제거(self, clf):
        assert clf.classify_intent("중복 코드 제거해줘") == "modify"

    def test_버그_수정(self, clf):
        assert clf.classify_intent("retrieve 함수의 버그를 수정해줘") == "modify"


# ── 한국어 CREATE ──────────────────────────────────────────────────────────────

class TestKoreanCreate:
    def test_만들어(self, clf):
        assert clf.classify_intent("새로운 함수 만들어줘") == "create"

    def test_만들_standalone(self, clf):
        assert clf.classify_intent("클래스 만들어") == "create"

    def test_작성(self, clf):
        assert clf.classify_intent("테스트 코드 작성해줘") == "create"

    def test_구현(self, clf):
        assert clf.classify_intent("BFS 알고리즘 구현해줘") == "create"

    def test_구현_standalone(self, clf):
        assert clf.classify_intent("구현해줘") == "create"

    def test_생성(self, clf):
        assert clf.classify_intent("새 파일 생성해줘") == "create"

    def test_추가(self, clf):
        assert clf.classify_intent("기능 추가해줘") == "create"

    def test_새로운(self, clf):
        assert clf.classify_intent("새로운 retriever 클래스 만들어줘") == "create"


# ── 한국어 READ (default) ──────────────────────────────────────────────────────

class TestKoreanRead:
    def test_설명(self, clf):
        assert clf.classify_intent("어떻게 동작하는지 설명해줘") == "read"

    def test_분석(self, clf):
        assert clf.classify_intent("이 코드 분석해줘") == "read"

    def test_어떻게(self, clf):
        assert clf.classify_intent("AdaptiveTriggerRetriever 어떻게 사용해?") == "read"

    def test_보여줘(self, clf):
        assert clf.classify_intent("classify 함수 보여줘") == "read"

    def test_뭐야(self, clf):
        assert clf.classify_intent("BM25L이 뭐야") == "read"


# ── 영어 회귀 방지 ──────────────────────────────────────────────────────────────

class TestEnglishRegression:
    def test_fix(self, clf):
        assert clf.classify_intent("fix the bug in retrieve") == "modify"

    def test_update(self, clf):
        assert clf.classify_intent("update the threshold value") == "modify"

    def test_refactor(self, clf):
        assert clf.classify_intent("refactor this module") == "modify"

    def test_create(self, clf):
        assert clf.classify_intent("create a new retriever class") == "create"

    def test_implement(self, clf):
        assert clf.classify_intent("implement BFS traversal") == "create"

    def test_how_works(self, clf):
        assert clf.classify_intent("how does this function work") == "read"

    def test_explain(self, clf):
        assert clf.classify_intent("explain the scoring logic") == "read"


# ── 혼합 문장 ─────────────────────────────────────────────────────────────────

class TestMixedLanguage:
    def test_ko_modify_en_context(self, clf):
        assert clf.classify_intent("retrieve function 수정해줘") == "modify"

    def test_en_fix_ko_context(self, clf):
        assert clf.classify_intent("fix 해줘 이 버그") == "modify"

    def test_ko_create_en_noun(self, clf):
        assert clf.classify_intent("BM25 retriever 만들어줘") == "create"
