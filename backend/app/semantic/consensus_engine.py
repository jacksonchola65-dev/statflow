from typing import List, Dict
from collections import defaultdict
from functools import reduce
import operator

from app.semantic.detectors.base import DetectorResult
from app.semantic.semantic_models import SemanticClassification, SemanticEvidence
from app.semantic.semantic_types import SemanticType


class ConsensusEngine:
    NAME = "consensus"

    @staticmethod
    def merge(results: List[DetectorResult]) -> List[SemanticClassification]:
        if not results:
            return []

        grouped: Dict[SemanticType, Dict] = {}

        for res in results:
            det_name = res.detector_name
            for cls in res.classifications:
                st = cls.semantic_type
                if st not in grouped:
                    grouped[st] = {"confidences": [], "evidence": [], "detectors": []}
                grouped[st]["confidences"].append(float(cls.confidence))
                # preserve evidence ordering: extend by tuple order
                grouped[st]["evidence"].extend(list(cls.evidence))
                if det_name not in grouped[st]["detectors"]:
                    grouped[st]["detectors"].append(det_name)

        final: List[SemanticClassification] = []

        for st, info in grouped.items():
            confs = info["confidences"]
            if len(confs) == 1:
                combined = confs[0]
            else:
                prod = 1.0
                for c in confs:
                    prod *= (1.0 - float(c))
                combined = 1.0 - prod
            # cap at 0.99
            if combined > 0.99:
                combined = 0.99

            evidence_tuple = tuple(info["evidence"])
            detectors_concat = ",".join(info["detectors"])
            final.append(SemanticClassification(semantic_type=st, confidence=combined, evidence=evidence_tuple, detector=detectors_concat))

        # sort by highest confidence then semantic type name
        final.sort(key=lambda c: (-float(c.confidence), c.semantic_type.name))
        return final
