"""Deterministic case generator for differential validation tests (backend tests path).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Optional
import random


@dataclass(frozen=True)
class ColumnCase:
    case_id: str
    column_name: Optional[str]
    values: Tuple[Optional[str], ...]


CURATED: List[ColumnCase] = []


def _mk(cid: str, name: Optional[str], vals: List[Optional[str]]) -> ColumnCase:
    return ColumnCase(case_id=cid, column_name=name, values=tuple(vals))


# curated boundary cases
CURATED.extend([
    _mk("cur-001", "value", ["", "", ""]),
    _mk("cur-002", "count", [None, None, None]),
    _mk("cur-003", "amount_usd", ["1", "2", "3"]),
    _mk("cur-004", "-amount", ["-1", "-2", "-3"]),
    _mk("cur-005", "ratio", ["0.1", ".25", "1e-2"]),
    _mk("cur-006", "year", ["1999", "2000", "2020"]),
    _mk("cur-007", "date", ["2020-01-01", "1999-12-31"]),
    _mk("cur-008", "email_address", ["a@x.com", "b@y.org"]),
    _mk("cur-009", "phone-number", ["+14155552671", "4155552672"]),
    _mk("cur-010", "url", ["http://example.com", "https://x.co"]),
    _mk("cur-011", "id", ["ABC-123", "XYZ-789"]),
    _mk("cur-012", "mixed", ["12a", "34b", "56"]),
    _mk("cur-013", "unicode_", ["café", "naïve"]),
    _mk("cur-014", "high_card", [str(i) for i in range(100)]),
    _mk("cur-015", "null_heavy", [None] * 9 + ["1"]),
    _mk("cur-016", "  Leading ", ["a", "b"]),
    _mk("cur-017", "trailing  ", ["c", "d"]),
    _mk("cur-018", "with_underscore", ["x", "y"]),
    _mk("cur-019", "with-hyphen", ["p", "q"]),
    _mk("cur-020", "123suffix", ["1", "2"]),
    _mk("cur-021", "", ["emptyname"]),
])


def generate_random_cases(seed: int, n: int, min_vals: int = 0, max_vals: int = 50) -> List[ColumnCase]:
    rnd = random.Random(seed)
    names = [
        "value",
        "count",
        "amount",
        "total_value",
        "user_id",
        "email",
        "phone",
        "signup_date",
        "score",
        "rating",
        "description",
        "温度",
        "имя",
        "pi",
    ]

    def rnd_value(kind: int) -> Optional[str]:
        if kind == 0:
            return None if rnd.random() < 0.5 else ""
        if kind == 1:
            return str(rnd.randint(-1000, 100000))
        if kind == 2:
            return f"{rnd.uniform(-1000,100000):.6f}"
        if kind == 3:
            return f"{rnd.uniform(1e-6, 1e6):.2e}"
        if kind == 4:
            l = rnd.randint(1, 3)
            return " ".join(rnd.choice(["foo", "bar", "baz", "qux", "テスト", "ñ"]) for _ in range(l))
        if kind == 5:
            return f"user{rnd.randint(1,1000)}@example.com"
        if kind == 6:
            return f"http://{rnd.choice(['a','b','c'])}.{rnd.choice(['com','org','io'])}/{rnd.randint(1,999)}"
        if kind == 7:
            return f"+1{rnd.randint(2000000000,9999999999)}"
        if kind == 8:
            return rnd.choice(["naïve", "café", "東京", "россия"])
        return None

    cases: List[ColumnCase] = []
    for i in range(n):
        cid = f"gen-{i:04d}"
        name = rnd.choice(names)
        if rnd.random() < 0.2:
            name = name.upper()
        if rnd.random() < 0.15:
            name = f" {name} "
        if rnd.random() < 0.1:
            name = name.replace("_", "-")

        count = rnd.randint(min_vals, max_vals)
        vals = []
        for _ in range(count):
            kind = rnd.choices(range(9), weights=[0.05,0.2,0.15,0.05,0.25,0.05,0.05,0.15,0.05])[0]
            vals.append(rnd_value(kind))
        cases.append(_mk(cid, name, vals))

    return cases


def all_cases(seed: int = 12345, generated: int = 1000) -> List[ColumnCase]:
    gen = generate_random_cases(seed, generated, min_vals=0, max_vals=50)
    return CURATED + gen
