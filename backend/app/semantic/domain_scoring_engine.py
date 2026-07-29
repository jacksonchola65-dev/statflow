from typing import Sequence, Tuple, Iterable, Dict, Set
from collections import defaultdict
import time

from .semantic_models import SemanticClassification
from .domain_models import DomainScore, DomainEvidence
from .domain_signatures import DOMAIN_SIGNATURES
from .semantic_types import DatasetDomain, SemanticType


# Precompute domain grouping and total weights for performance and determinism
_DOMAIN_TO_SIGS: Dict[DatasetDomain, list[DomainEvidence]] = defaultdict(list)
_DOMAIN_ORDER: list[DatasetDomain] = []
_DOMAIN_TOTAL_WEIGHTS: Dict[DatasetDomain, float] = {}

for _sig in DOMAIN_SIGNATURES:
    if _sig.domain not in _DOMAIN_TO_SIGS:
        _DOMAIN_ORDER.append(_sig.domain)
    _DOMAIN_TO_SIGS[_sig.domain].append(_sig)

for _d, _sigs in _DOMAIN_TO_SIGS.items():
    _DOMAIN_TOTAL_WEIGHTS[_d] = sum(float(s.weight) for s in _sigs)


class DomainScoringEngine:
    @staticmethod
    def score(columns: Sequence[Sequence[SemanticClassification]]) -> Tuple[DomainScore, ...]:
        # Validate input
        if not isinstance(columns, Iterable):
            raise TypeError("columns must be an iterable of column classification iterables")

        # Build per-column best-by-type maps and also track which columns support which type
        per_column_best: list[Dict[SemanticType, float]] = []
        type_column_support: Dict[SemanticType, Set[int]] = defaultdict(set)

        for col_idx, col in enumerate(columns):
            if not isinstance(col, Iterable):
                raise TypeError("each column must be an iterable of SemanticClassification")
            best: Dict[SemanticType, float] = {}
            for item in col:
                if not isinstance(item, SemanticClassification):
                    raise TypeError("all items must be SemanticClassification instances")
                st = item.semantic_type
                conf = float(item.confidence)
                # keep highest confidence for this semantic type within the column
                prev = best.get(st)
                if prev is None or conf > prev:
                    best[st] = conf
            # record column support
            for st in best.keys():
                type_column_support[st].add(col_idx)
            per_column_best.append(best)

        results: list[DomainScore] = []

        # For each domain, compute score (use precomputed signature groups)
        for domain in _DOMAIN_ORDER:
            sigs = _DOMAIN_TO_SIGS[domain]
            total_weight = float(_DOMAIN_TOTAL_WEIGHTS.get(domain, 0.0))

            matched_types: Set[SemanticType] = set()
            matched_evidence: list[DomainEvidence] = []
            raw_score = 0.0

            # For deterministic evidence ordering, follow registry order (sigs)
            for s in sigs:
                st = s.semantic_type
                # find highest confidence across all columns for this semantic type
                best_conf = None
                supporting_cols = 0
                if st in type_column_support:
                    supporting_cols = len(type_column_support[st])
                    # highest across per_column_best
                    for col_map in per_column_best:
                        if st in col_map:
                            c = col_map[st]
                            if best_conf is None or c > best_conf:
                                best_conf = c

                if best_conf is not None:
                    matched_types.add(st)
                    contribution = float(s.weight) * float(best_conf)
                    raw_score += contribution
                    desc = f"type={st.value}; confidence={best_conf:.4f}; weight={float(s.weight):.4f}; supporting_columns={supporting_cols}"
                    matched_evidence.append(DomainEvidence(domain=domain, semantic_type=st, weight=float(s.weight), description=desc))

            # Apply dataset-wide evidence rules
            # require at least 2 distinct matched semantic types
            # require supporting evidence from at least 2 different columns across matched types
            total_supporting_columns = set()
            for st in matched_types:
                total_supporting_columns.update(type_column_support.get(st, set()))

            normalized = 0.0
            if len(matched_types) >= 2 and len(total_supporting_columns) >= 2:
                if total_weight > 0:
                    normalized = raw_score / float(total_weight)
                    if normalized < 0.0:
                        normalized = 0.0
                    if normalized > 1.0:
                        normalized = 1.0

            # If evidence rules not met, normalized remains 0.0 but matched_evidence still returned
            results.append(DomainScore(domain=domain, score=float(normalized), evidence=tuple(matched_evidence)))

        # Sort results by descending score then domain value
        results.sort(key=lambda d: (-float(d.score), d.domain.value))

        return tuple(results)
