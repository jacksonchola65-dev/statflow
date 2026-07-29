from dataclasses import dataclass, field
from typing import Sequence, Tuple, Iterable, List, Dict
import math

from .semantic_models import SemanticClassification, SemanticEvidence
from .semantic_types import SemanticType
from .entity_models import EntityCandidate, EntityKeyCandidate, RelationshipCandidate


KEY_TYPES = {SemanticType.IDENTIFIER, SemanticType.INTEGER, SemanticType.TEXT}

_SUFFIXES = {"id", "identifier", "code", "key"}


def _normalize_name(s: str) -> str:
    if not isinstance(s, str):
        raise TypeError("string expected")
    t = s.strip()
    t = t.replace("_", " ").replace("-", " ")
    t = " ".join(t.split())
    return t.lower()


def _strip_one_suffix(name: str) -> str:
    parts = name.split()
    if parts and parts[-1] in _SUFFIXES:
        new = " ".join(parts[:-1]).strip()
        if new:
            return new
    return name


@dataclass(frozen=True)
class RelationshipColumnInput:
    column_name: str
    classifications: Tuple[SemanticClassification, ...] = field(default_factory=tuple)
    uniqueness_ratio: float = 0.0
    null_ratio: float = 0.0

    def __post_init__(self):
        if not isinstance(self.column_name, str):
            raise TypeError("column_name must be a string")
        cn = self.column_name.strip()
        if not cn:
            raise ValueError("column_name must be non-empty")
        object.__setattr__(self, "column_name", cn)

        if not isinstance(self.classifications, Iterable):
            raise TypeError("classifications must be iterable")
        cls = tuple(self.classifications)
        for c in cls:
            if not isinstance(c, SemanticClassification):
                raise TypeError("classifications must contain SemanticClassification instances")
        object.__setattr__(self, "classifications", cls)

        if not isinstance(self.uniqueness_ratio, (int, float)):
            raise TypeError("uniqueness_ratio must be numeric")
        ur = float(self.uniqueness_ratio)
        if not math.isfinite(ur) or ur < 0.0 or ur > 1.0:
            raise ValueError("uniqueness_ratio must be within [0.0,1.0]")
        object.__setattr__(self, "uniqueness_ratio", ur)

        if not isinstance(self.null_ratio, (int, float)):
            raise TypeError("null_ratio must be numeric")
        nr = float(self.null_ratio)
        if not math.isfinite(nr) or nr < 0.0 or nr > 1.0:
            raise ValueError("null_ratio must be within [0.0,1.0]")
        object.__setattr__(self, "null_ratio", nr)


@dataclass(frozen=True)
class RelationshipDetectionInput:
    entities: Tuple[EntityCandidate, ...] = field(default_factory=tuple)
    keys: Tuple[EntityKeyCandidate, ...] = field(default_factory=tuple)
    columns: Tuple[RelationshipColumnInput, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if not isinstance(self.entities, Iterable):
            raise TypeError("entities must be iterable")
        ent = tuple(self.entities)
        for e in ent:
            if not isinstance(e, EntityCandidate):
                raise TypeError("entities must contain EntityCandidate instances")
        object.__setattr__(self, "entities", ent)

        if not isinstance(self.keys, Iterable):
            raise TypeError("keys must be iterable")
        ks = tuple(self.keys)
        for k in ks:
            if not isinstance(k, EntityKeyCandidate):
                raise TypeError("keys must contain EntityKeyCandidate instances")
        object.__setattr__(self, "keys", ks)

        if not isinstance(self.columns, Iterable):
            raise TypeError("columns must be iterable")
        cols = tuple(self.columns)
        for c in cols:
            if not isinstance(c, RelationshipColumnInput):
                raise TypeError("columns must contain RelationshipColumnInput instances")
        object.__setattr__(self, "columns", cols)


class RelationshipDetector:
    @staticmethod
    def discover(input_data: RelationshipDetectionInput) -> Tuple[RelationshipCandidate, ...]:
        if not isinstance(input_data, RelationshipDetectionInput):
            raise TypeError("input_data must be RelationshipDetectionInput")

        entities = list(input_data.entities)
        keys = list(input_data.keys)
        cols = list(input_data.columns)

        if len(entities) == 0 or len(keys) == 0 or len(cols) == 0:
            return tuple()

        # Normalize entity names and build map
        norm_entities = [ _normalize_name(e.name) for e in entities ]
        norm_entities_map = {n: i for i, n in enumerate(norm_entities)}

        # Map entity to its keys
        ent_to_keys: Dict[int, List[EntityKeyCandidate]] = {}
        for k in keys:
            kn = _normalize_name(k.entity_name)
            idx = norm_entities_map.get(kn)
            if idx is not None:
                ent_to_keys.setdefault(idx, []).append(k)

        # Preprocess keys: for each entity index, sort keys per preference
        for idx, klist in ent_to_keys.items():
            def key_pref(k: EntityKeyCandidate):
                is_ident = 0 if k.semantic_type == SemanticType.IDENTIFIER else 1
                return (is_ident, -float(k.confidence), float(k.null_ratio), -float(k.uniqueness_ratio), k.column_name.lower())
            # sort so best key is first
            klist.sort(key=key_pref)

        # Precompute source_column -> entity indices for fast lookup
        source_column_map: Dict[str, List[int]] = {}
        for idx_e, ent in enumerate(entities):
            for sc in ent.source_columns:
                key = sc.strip().lower()
                source_column_map.setdefault(key, []).append(idx_e)

        rels: List[RelationshipCandidate] = []
        seen = []  # for duplicate suppression: store tuples of lowercased fields

        for col in cols:
            # validate
            if not isinstance(col, RelationshipColumnInput):
                raise TypeError("columns must contain RelationshipColumnInput instances")
            # select highest eligible classification
            eligible = [c for c in col.classifications if c.semantic_type in KEY_TYPES and float(c.confidence) >= 0.60]
            if not eligible:
                continue
            # pick top by confidence then semantic_type.value
            eligible_sorted = sorted(eligible, key=lambda c: (-float(c.confidence), c.semantic_type.value))
            src_cl = eligible_sorted[0]
            if float(col.null_ratio) > 0.50:
                continue

            # Determine target and source entity names by parsing normalized column
            norm_col = _normalize_name(col.column_name)
            stripped = _strip_one_suffix(norm_col)
            if not stripped:
                continue

            parts = stripped.split()
            target_idx = None
            src_idx = None

            # optimized finder using maps
            def find_src_candidates_for_name(name_to_match):
                s = name_to_match
                candidates = []
                # exact normalized name match
                idx = norm_entities_map.get(s)
                if idx is not None:
                    candidates.append((idx, False))
                # source_columns membership
                sc_match = source_column_map.get(col.column_name.strip().lower(), [])
                for si in sc_match:
                    # mark as source_columns match; avoid duplicate
                    if si == idx:
                        # already present, mark as source_columns
                        candidates = [(si, True) if c[0] == si else c for c in candidates]
                    else:
                        candidates.append((si, True))
                if not candidates:
                    return None
                candidates.sort(key=lambda t: (0 if t[1] else 1, -len(norm_entities[t[0]]), t[0]))
                return candidates[0][0]

            if len(parts) >= 2:
                # evaluate two possible parses and pick the one that satisfies target key existence
                # candidate A: first token = target, remainder = source
                a_target = parts[0]
                a_source = " ".join(parts[1:])
                a_target_idx = norm_entities_map.get(a_target)
                a_src_idx = find_src_candidates_for_name(a_source)

                # candidate B: last token = target, remainder = source
                b_target = parts[-1]
                b_source = " ".join(parts[:-1])
                b_target_idx = norm_entities_map.get(b_target)
                b_src_idx = find_src_candidates_for_name(b_source)

                # determine which candidate is valid (has target and source and target has keys and not self-relationship)
                def candidate_valid(t_idx, s_idx):
                    if t_idx is None or s_idx is None:
                        return False
                    if t_idx == s_idx:
                        return False
                    if not ent_to_keys.get(t_idx):
                        return False
                    # ensure source column is not the detected key column for its own entity
                    own_keys = ent_to_keys.get(s_idx, [])
                    for k in own_keys:
                        if k.column_name.strip().lower() == col.column_name.strip().lower():
                            return False
                    return True

                a_ok = candidate_valid(a_target_idx, a_src_idx)
                b_ok = candidate_valid(b_target_idx, b_src_idx)

                chosen = None
                if a_ok and not b_ok:
                    chosen = (a_target_idx, a_src_idx)
                elif b_ok and not a_ok:
                    chosen = (b_target_idx, b_src_idx)
                elif a_ok and b_ok:
                    # prefer candidate where source matched by source_columns
                    a_src_by_cols = any(sc.strip().lower() == col.column_name.strip().lower() for sc in entities[a_src_idx].source_columns) if a_src_idx is not None else False
                    b_src_by_cols = any(sc.strip().lower() == col.column_name.strip().lower() for sc in entities[b_src_idx].source_columns) if b_src_idx is not None else False
                    if a_src_by_cols and not b_src_by_cols:
                        chosen = (a_target_idx, a_src_idx)
                    elif b_src_by_cols and not a_src_by_cols:
                        chosen = (b_target_idx, b_src_idx)
                    else:
                        # prefer longer source name
                        a_len = len(norm_entities[a_src_idx]) if a_src_idx is not None else 0
                        b_len = len(norm_entities[b_src_idx]) if b_src_idx is not None else 0
                        if a_len > b_len:
                            chosen = (a_target_idx, a_src_idx)
                        elif b_len > a_len:
                            chosen = (b_target_idx, b_src_idx)
                        else:
                            # deterministic fallback: choose A
                            chosen = (a_target_idx, a_src_idx)
                if chosen is None:
                    # no valid candidate
                    continue
                target_idx, src_idx = chosen
            else:
                # fallback: determine target by exact match of stripped
                target_idx = norm_entities_map.get(stripped)
                # Determine source entity (ownership) by beginswith or source_columns
                src_candidates = []
                for idx_e, en_norm in enumerate(norm_entities):
                    begins = norm_col.startswith(en_norm + " ")
                    in_source_cols = False
                    if entities[idx_e].source_columns:
                        for sc in entities[idx_e].source_columns:
                            if sc.strip().lower() == col.column_name.strip().lower():
                                in_source_cols = True
                                break
                    if begins or in_source_cols:
                        src_candidates.append((idx_e, in_source_cols))
                if src_candidates:
                    src_candidates.sort(key=lambda t: (0 if t[1] else 1, -len(norm_entities[t[0]]), t[0]))
                    src_idx = src_candidates[0][0]

            # Both target and source must be resolved (already set above)

            # Both target and source must be resolved
            if target_idx is None or src_idx is None:
                continue

            # Do not create self-relationship
            if src_idx == target_idx:
                continue

            # ensure source column is not the detected key column for its own entity
            own_keys = ent_to_keys.get(src_idx, [])
            is_key_column_for_source = False
            for k in own_keys:
                if k.column_name.strip().lower() == col.column_name.strip().lower():
                    is_key_column_for_source = True
                    break
            if is_key_column_for_source:
                continue

            # target must have at least one key
            tgt_keys = ent_to_keys.get(target_idx, [])
            if not tgt_keys:
                continue
            # select best target key (already sorted)
            tgt_key = tgt_keys[0]

            # compute confidence
            src_conf = float(src_cl.confidence)
            tgt_conf = float(tgt_key.confidence)
            tgt_ur = float(tgt_key.uniqueness_ratio)
            src_nr = float(col.null_ratio)

            base = 0.35 * src_conf + 0.30 * tgt_conf + 0.20 * tgt_ur + 0.15 * (1.0 - src_nr)
            conf = max(0.0, min(0.99, float(base)))

            # combine evidence: source classification evidence then target key evidence
            evs = []
            for e in src_cl.evidence:
                if not isinstance(e, SemanticEvidence):
                    raise TypeError("evidence items must be SemanticEvidence")
                evs.append(e)
            for e in tgt_key.evidence:
                if not isinstance(e, SemanticEvidence):
                    raise TypeError("evidence items must be SemanticEvidence")
                evs.append(e)

            rel = RelationshipCandidate(
                source_entity=entities[src_idx].name,
                target_entity=entities[target_idx].name,
                source_column=col.column_name,
                target_column=tgt_key.column_name,
                confidence=conf,
                relationship_type="MANY_TO_ONE",
                evidence=tuple(evs),
            )

            key = (rel.source_entity.lower(), rel.target_entity.lower(), rel.source_column.lower(), rel.target_column.lower())
            # duplicate suppression
            existing_idx = None
            for i, k in enumerate(seen):
                if k == key:
                    existing_idx = i
                    break
            if existing_idx is not None:
                # compare with existing rel in rels
                if rel.confidence > rels[existing_idx].confidence:
                    rels[existing_idx] = rel
                    seen[existing_idx] = key
                # on equal confidence keep first-seen (do nothing)
            else:
                seen.append(key)
                rels.append(rel)

        # final sort
        rels.sort(key=lambda r: (-float(r.confidence), r.source_entity.lower(), r.target_entity.lower(), r.source_column.lower(), r.target_column.lower()))

        return tuple(rels)
