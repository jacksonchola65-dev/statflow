from app.semantic.semantic_models import SemanticClassification, SemanticEvidence
from app.semantic.semantic_types import SemanticType, DatasetDomain
from app.semantic.domain_scoring_engine import DomainScoringEngine
from app.semantic.domain_signatures import DOMAIN_SIGNATURES

def domain_sigs_map():
    m = {}
    for s in DOMAIN_SIGNATURES:
        m.setdefault(s.domain, []).append(s)
    return m

def sc(t,c):
    return SemanticClassification(semantic_type=t, confidence=c, evidence=(SemanticEvidence(source='t', score=float(c), description='e'),), detector='d')

cases = {
    'healthcare': [
        [sc(SemanticType.PERSON, 1.0)],
        [sc(SemanticType.AGE, 0.98)],
        [sc(SemanticType.AGE, 0.99)],
        [sc(SemanticType.IDENTIFIER, 0.97)],
        [sc(SemanticType.DATE, 0.96)],
        [sc(SemanticType.CATEGORY, 0.95)],
    ],
    'education': [
        [sc(SemanticType.PERSON, 1.0)],
        [sc(SemanticType.AGE, 0.2)],
        [sc(SemanticType.IDENTIFIER, 1.0)],
        [sc(SemanticType.DATE, 1.0)],
        [sc(SemanticType.CATEGORY, 1.0)],
    ]
}

for name, cols in cases.items():
    print('---', name)
    scores = DomainScoringEngine.score(cols)
    for s in scores[:6]:
        print(s.domain, s.score)
        ds_map = domain_sigs_map()
        # compute raw contributions and normalization for top two domains
        for dom in [DatasetDomain.EDUCATION, DatasetDomain.HEALTHCARE]:
            sigs = ds_map.get(dom, [])
            total_w = sum(float(s.weight) for s in sigs)
            raw = 0.0
            for s in sigs:
                # find best conf
                best_conf = None
                for col in cols:
                    for it in col:
                        if it.semantic_type == s.semantic_type:
                            if best_conf is None or it.confidence > best_conf:
                                best_conf = it.confidence
                if best_conf is not None:
                    raw += float(s.weight) * float(best_conf)
            norm = raw / total_w if total_w else 0.0
            print(dom, 'total_w', total_w, 'raw', raw, 'norm', norm)
    print()
