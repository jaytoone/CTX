"""
Trigger classifier for CTX experiment.

Classifies input prompts into trigger types using regex + keyword matching.
No LLM API calls -- purely local processing.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class TriggerType(Enum):
    EXPLICIT_SYMBOL = "EXPLICIT_SYMBOL"
    SEMANTIC_CONCEPT = "SEMANTIC_CONCEPT"
    TEMPORAL_HISTORY = "TEMPORAL_HISTORY"
    IMPLICIT_CONTEXT = "IMPLICIT_CONTEXT"


@dataclass
class Trigger:
    """A detected trigger from input text."""
    trigger_type: TriggerType
    value: str
    confidence: float
    source_span: Optional[str] = None


# Patterns for explicit symbol detection
SYMBOL_PATTERNS = [
    # Function/method references: function_name( — call syntax
    re.compile(r'\b([a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)?\s*\()', re.IGNORECASE),
    # Class references: CamelCase words
    re.compile(r'\b([A-Z][a-zA-Z0-9]+(?:[A-Z][a-zA-Z0-9]+)*)\b'),
    # Quoted identifiers
    re.compile(r'[`"\']([a-zA-Z_][a-zA-Z0-9_.]+)[`"\']'),
    # File paths
    re.compile(r'(?:file|module|path)\s+([a-zA-Z0-9_/]+\.py)', re.IGNORECASE),
    # Explicit function/method declaration: "function snake_case_name"
    # Requires underscore in name (snake_case signal) to avoid matching common English words
    # e.g. "Find the function run_migration" ✓, "how does the function handles X" ✗
    re.compile(r'\b(?:function|method|def)\s+([a-z_][a-z0-9_]*_[a-z][a-z0-9_]*)\b', re.IGNORECASE),
]

# Keywords that indicate explicit symbol lookup
EXPLICIT_KEYWORDS = [
    "function", "method", "class", "variable", "constant",
    "definition", "implementation", "signature", "declaration",
    "find the function", "show the class", "where is", "locate",
]

# Keywords that indicate semantic/concept queries
SEMANTIC_KEYWORDS = [
    "related to", "about", "concept", "how does", "explain",
    "all code", "everything about", "functionality", "feature",
    "module for", "handles", "responsible for", "deals with",
    "authentication", "database", "caching", "logging", "security",
    "api", "endpoint", "configuration", "testing", "scheduling",
]

# Keywords that indicate temporal/history references
TEMPORAL_KEYWORDS = [
    "previously", "before", "last time", "earlier", "remember",
    "discussed", "mentioned", "we talked", "history", "past",
    "previous session", "ago", "recent", "lately", "prior",
]

# Keywords that indicate implicit context inference
IMPLICIT_KEYWORDS = [
    "needed to", "understand", "dependencies", "depends on",
    "required by", "imports", "calls", "uses", "affects",
    "impact", "connected", "related modules", "fully understand",
]


class TriggerClassifier:
    """Classifies input prompts into trigger types."""

    def classify(self, prompt: str) -> List[Trigger]:
        """Extract and classify triggers from a prompt.

        Args:
            prompt: The input text to analyze

        Returns:
            List of detected triggers, sorted by confidence (highest first)
        """
        triggers = []
        prompt_lower = prompt.lower()

        # 1. Detect explicit symbols
        triggers.extend(self._detect_explicit_symbols(prompt, prompt_lower))

        # 2. Detect semantic concepts
        triggers.extend(self._detect_semantic_concepts(prompt_lower))

        # 3. Detect temporal references
        triggers.extend(self._detect_temporal_refs(prompt_lower))

        # 4. Detect implicit context
        triggers.extend(self._detect_implicit_context(prompt_lower))

        # If no triggers found, default to semantic concept with the full prompt
        if not triggers:
            triggers.append(Trigger(
                trigger_type=TriggerType.SEMANTIC_CONCEPT,
                value=prompt,
                confidence=0.3,
            ))

        # Sort by confidence descending
        triggers.sort(key=lambda t: t.confidence, reverse=True)

        return triggers

    def classify_primary(self, prompt: str) -> TriggerType:
        """Return the primary (highest-confidence) trigger type for a prompt."""
        triggers = self.classify(prompt)
        return triggers[0].trigger_type if triggers else TriggerType.SEMANTIC_CONCEPT

    # Common English words that look like CamelCase but are NOT code symbols
    _COMMON_WORDS = frozenset({
        "find", "show", "get", "list", "what", "where", "how", "why",
        "the", "all", "for", "and", "but", "not", "can", "will", "are",
        "from", "this", "that", "with", "have", "has", "was", "were",
        "code", "file", "module", "function", "class", "method", "test",
        "write", "make", "use", "add", "see", "look", "need", "want",
    })

    # Patterns to extract actual concept word from semantic queries
    _CONCEPT_EXTRACT_PATTERNS = [
        re.compile(r'related\s+to\s+([a-z_][a-z0-9_]*)', re.IGNORECASE),
        re.compile(r'everything\s+about\s+([a-z_][a-z0-9_]+)', re.IGNORECASE),
        re.compile(r'about\s+([a-z_][a-z0-9_]{2,})', re.IGNORECASE),
        re.compile(r'handles?\s+([a-z_][a-z0-9_]+)', re.IGNORECASE),
        re.compile(r'responsible\s+for\s+([a-z_][a-z0-9_]+)', re.IGNORECASE),
        re.compile(r'deals?\s+with\s+([a-z_][a-z0-9_]+)', re.IGNORECASE),
    ]

    def _detect_explicit_symbols(self, prompt: str, prompt_lower: str) -> List[Trigger]:
        """Detect explicit symbol references (function names, class names, etc.)."""
        triggers = []

        # Check for explicit keywords
        has_explicit_keyword = any(kw in prompt_lower for kw in EXPLICIT_KEYWORDS)

        for pattern in SYMBOL_PATTERNS:
            matches = pattern.findall(prompt)
            for match in matches:
                # Clean up match
                symbol = match.rstrip("(").strip()
                if len(symbol) < 2:
                    continue
                # Filter out common English words that happen to match patterns
                if symbol.lower() in self._COMMON_WORDS:
                    continue

                confidence = 0.9 if has_explicit_keyword else 0.7
                triggers.append(Trigger(
                    trigger_type=TriggerType.EXPLICIT_SYMBOL,
                    value=symbol,
                    confidence=confidence,
                    source_span=match,
                ))

        return triggers

    def _detect_semantic_concepts(self, prompt_lower: str) -> List[Trigger]:
        """Detect semantic concept references."""
        triggers = []

        matched_keywords = [kw for kw in SEMANTIC_KEYWORDS if kw in prompt_lower]
        if matched_keywords:
            # Try to extract the actual concept word (e.g., "routing" from "related to routing")
            concept = None
            for pat in self._CONCEPT_EXTRACT_PATTERNS:
                m = pat.search(prompt_lower)
                if m:
                    candidate = m.group(1)
                    if len(candidate) > 2 and candidate not in self._COMMON_WORDS:
                        concept = candidate
                        break

            # Fallback: use the longest matched semantic keyword
            if concept is None:
                concept = max(matched_keywords, key=len)

            # Higher confidence when explicit semantic marker ("related to", "all code") is present
            has_explicit_marker = any(kw in prompt_lower for kw in ("related to", "all code", "everything about"))
            if has_explicit_marker:
                confidence = min(0.85, 0.70 + len(matched_keywords) * 0.03)
            else:
                confidence = min(0.85, 0.50 + len(matched_keywords) * 0.10)

            triggers.append(Trigger(
                trigger_type=TriggerType.SEMANTIC_CONCEPT,
                value=concept,
                confidence=confidence,
            ))

        return triggers

    def _detect_temporal_refs(self, prompt_lower: str) -> List[Trigger]:
        """Detect temporal/history references."""
        triggers = []

        matched = [kw for kw in TEMPORAL_KEYWORDS if kw in prompt_lower]
        if matched:
            confidence = min(0.9, 0.5 + len(matched) * 0.15)
            triggers.append(Trigger(
                trigger_type=TriggerType.TEMPORAL_HISTORY,
                value=max(matched, key=len),
                confidence=confidence,
            ))

        return triggers

    def _detect_implicit_context(self, prompt_lower: str) -> List[Trigger]:
        """Detect implicit context inference needs."""
        triggers = []

        matched = [kw for kw in IMPLICIT_KEYWORDS if kw in prompt_lower]
        if matched:
            confidence = min(0.8, 0.4 + len(matched) * 0.12)
            triggers.append(Trigger(
                trigger_type=TriggerType.IMPLICIT_CONTEXT,
                value=max(matched, key=len),
                confidence=confidence,
            ))

        return triggers

    # --- Query intent detection (over-anchoring prevention) ---

    # English modify/create keywords (substring match — English nouns ≠ verbs)
    _MODIFY_KEYWORDS_EN = frozenset({
        "fix", "change", "update", "replace", "refactor", "rewrite",
        "correct", "improve", "modify", "rename", "move", "delete",
        "remove", "edit", "patch", "repair", "convert", "migrate",
    })
    _CREATE_KEYWORDS_EN = frozenset({
        "create", "implement", "write", "add new", "generate", "make",
        "build", "new function", "new class", "new method",
    })

    # Korean: verb-ending anchored regex to avoid noun-context false positives.
    # Korean nouns (수정, 추가, 생성...) only signal intent when paired with a
    # verb ending (해줘, 하다, 할, etc.). Inherently-verb forms (고쳐, 바꿔)
    # are matched directly.
    _VERB_ENDINGS = r'(?:\s*)(?:해줘|해주|해야|해봐|합니다|할게|해라|하자|하면|해서|해도|하고|하다|할|했|해)'

    _KO_MODIFY_RE = re.compile(
        # Stem + explicit verb ending (highest precision)
        r'(?:수정|변경|개선|삭제|제거|이동|교체|수리|패치|리팩토링|리팩터)'
        + r'(?:\s*)(?:해줘|해주|해야|해봐|합니다|할게|해라|하자|하면|해서|해도|하고|하다|할|했|해)'
        # Stem at end-of-sentence: Korean implicit imperative (어미 생략 명령형)
        # e.g. "retrieve 함수 수정" = "수정해줘" in ellipsis form
        + r'|(?:수정|변경|개선|삭제|제거|이동|교체|수리|패치|리팩토링)\s*$'
        # Inherently-verb forms (no suffix needed)
        + r'|고쳐|고치(?:다|고|면|어|세요)'
        + r'|바꿔|바꾸(?:다|고|면|어|세요)'
    )

    _KO_CREATE_RE = re.compile(
        # Stem + explicit verb ending
        r'(?:추가|생성|작성|구현)'
        + r'(?:\s*)(?:해줘|해주|해야|해봐|합니다|할게|해라|하자|하면|해서|해도|하고|하다|할|했|해)'
        # Stem at end-of-sentence (implicit imperative)
        + r'|(?:추가|생성|작성|구현|만들)\s*$'
        + r'|만들어(?!진|졌)'   # 만들어줘 ✓  만들어진 ✗  만들어졌 ✗
        + r'|만들(?:고|면|어야|어줘|어주)'
    )

    def classify_intent(self, prompt: str) -> str:
        """Classify query intent as 'modify', 'create', or 'read'.

        Returns:
            'modify': Fix/Replace/Refactor — over-anchoring risk.
            'create': New code generation — low anchoring risk.
            'read':   Information retrieval — no anchoring risk (default).

        Korean nouns (수정, 추가, 생성…) require a verb ending suffix to avoid
        noun-context false positives (e.g. "추가 설명해줘" → read, not create).
        """
        prompt_lower = prompt.lower()

        # English: simple keyword match (English noun/verb forms rarely overlap)
        if any(kw in prompt_lower for kw in self._MODIFY_KEYWORDS_EN):
            return "modify"
        if any(kw in prompt_lower for kw in self._CREATE_KEYWORDS_EN):
            return "create"

        # Korean: verb-ending anchored regex
        if self._KO_MODIFY_RE.search(prompt):
            return "modify"
        if self._KO_CREATE_RE.search(prompt):
            return "create"

        return "read"
