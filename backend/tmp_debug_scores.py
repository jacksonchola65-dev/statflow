from app.semantic.semantic_models import SemanticClassification, SemanticEvidence
from app.semantic.semantic_types import SemanticType, DatasetDomain
from app.semantic.domain_scoring_engine import DomainScoringEngine

def sc(t,c):
    return SemanticClassification(semantic_type=t, confidence=c, evidence=(SemanticEvidence(source='t', score=float(c), description='e'),), detector='d')

cols = [
    [sc(SemanticType.PERSON, 1.0)],
    [sc(SemanticType.AGE, 0.98)],
    [sc(SemanticType.IDENTIFIER, 0.97)],
    [sc(SemanticType.DATE, 0.96)],
    [sc(SemanticType.CATEGORY, 0.95)],
]

scores = DomainScoringEngine.score(cols)
for s in scores[:10]:
    print(s.domain, s.score)
    if s.domain == DatasetDomain.HEALTHCARE:
        print('HEALTHCARE evidence:')
        for e in s.evidence:
            print('  ', e.semantic_type, e.weight, e.description)
