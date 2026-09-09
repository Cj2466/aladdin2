"""The pre-registered book: mechanical membership, equal-weight composition
on days after inception only, scored through the Dormant pool's own look."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.book import (
    BookError,
    BookManifest,
    MembershipSnapshot,
    book_entry,
    compose_book,
    load_manifest,
    parse_manifest,
    pre_inception_bucket,
    score_book,
)
from app.services.research_lab.dormant_pool import BUCKET_LOW, C_K


def _returns(start, periods, mean=0.0, seed=0, freq="B"):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start=start, periods=periods, freq=freq)
    return pd.Series(rng.standard_normal(periods) * 0.01 + mean, index=idx)


def _manifest(inception="2026-01-02", members=("fam_a/p1", "fam_b/p2"), phi=0.01, bucket=BUCKET_LOW, extra=()):
    snaps = [MembershipSnapshot(date.fromisoformat(inception), tuple(sorted(members)), "fixture")]
    for d, ms in extra:
        snaps.append(MembershipSnapshot(date.fromisoformat(d), tuple(sorted(ms)), "fixture"))
    return BookManifest(inception=date.fromisoformat(inception), phi_hat_pre_inception=phi, bucket=bucket, snapshots=tuple(snaps))


def test_composition_uses_only_post_inception_days_and_only_members_in_force():
    m = _manifest()
    a = _returns("2025-01-01", 600, seed=1)  # spans inception
    b = _returns("2026-03-02", 100, seed=2)  # joins the data later (still a member from inception)
    c = _returns("2025-01-01", 600, seed=3)  # NOT a member
    book = compose_book({"fam_a/p1": a, "fam_b/p2": b, "fam_c/p3": c}, m)
    assert book.index.min() > pd.Timestamp("2026-01-02")
    # on a day where only a has a return, the book equals a (renormalized equal weight)
    day = pd.Timestamp("2026-02-02")
    assert book[day] == pytest.approx(a[day])
    # on a day where both have returns, the book is their mean
    day2 = pd.Timestamp("2026-03-02")
    assert book[day2] == pytest.approx((a[day2] + b[day2]) / 2)
    assert "fam_c/p3" not in m.members_on(date(2026, 3, 2))


def test_a_later_snapshot_adds_a_member_only_from_its_date():
    m = _manifest(extra=[("2026-06-01", ("fam_a/p1", "fam_b/p2", "fam_c/p3"))])
    c = _returns("2026-01-05", 300, mean=0.05, seed=4)  # huge, but must not count before June
    a = _returns("2026-01-05", 300, seed=5)
    book = compose_book({"fam_a/p1": a, "fam_c/p3": c}, m)
    before = pd.Timestamp("2026-05-01")
    after = pd.Timestamp("2026-06-01")
    assert book[before] == pytest.approx(a[before])
    assert book[after] == pytest.approx((a[after] + c[after]) / 2)


def test_bucket_is_fixed_from_pre_inception_data_of_the_first_snapshot_only():
    m = _manifest()
    a = _returns("2024-01-01", 800, seed=6)
    b = _returns("2024-01-01", 800, seed=7)
    phi, bucket = pre_inception_bucket({"fam_a/p1": a, "fam_b/p2": b}, m)
    assert bucket == BUCKET_LOW and abs(phi) < 0.2
    with pytest.raises(BookError, match="pre-inception"):
        pre_inception_bucket({"fam_a/p1": _returns("2026-02-01", 50)}, m)


def test_score_book_goes_through_the_dormant_look_with_the_dormant_boundary():
    members = {f"fam_{i}/p": _returns("2025-01-01", 800, mean=0.004, seed=10 + i) for i in range(20)}
    m2 = _manifest(members=tuple(members))
    r = score_book(members, m2)
    assert r.boundary == C_K[BUCKET_LOW]
    assert r.look_index >= 1  # > 252 post-inception days
    assert r.psr_ext is not None
    assert book_entry(m2).family_key == "book"


def test_book_cannot_be_scored_before_inception_or_bucket_is_declared():
    m = BookManifest(inception=None, phi_hat_pre_inception=None, bucket=None, snapshots=())
    with pytest.raises(BookError, match="inception"):
        compose_book({"fam_a/p1": _returns("2026-01-01", 10)}, m)
    with pytest.raises(BookError):
        book_entry(m)


def test_manifest_parsing_enforces_the_rule():
    base = {"schema": "book/v1", "inception": "2026-01-02", "phi_hat_pre_inception": 0.01, "bucket": BUCKET_LOW,
            "snapshots": [{"membership_date": "2026-01-02", "members": ["fam_a/p1"], "source": "fixture"}]}
    assert parse_manifest(base).members_on(date(2026, 5, 1)) == ("fam_a/p1",)
    bad = dict(base, bucket="HIGH")
    with pytest.raises(BookError, match="never chosen"):
        parse_manifest(bad)
    bad = dict(base, snapshots=[{"membership_date": "2026-02-02", "members": ["fam_a/p1"], "source": "fixture"}])
    with pytest.raises(BookError, match="exactly at inception"):
        parse_manifest(bad)
    bad = dict(base, snapshots=base["snapshots"] + [{"membership_date": "2026-01-02", "members": ["fam_a/p1"], "source": "fixture"}])
    with pytest.raises(BookError, match="strictly increase"):
        parse_manifest(bad)
    bad = dict(base, phi_hat_pre_inception=None)
    with pytest.raises(BookError, match="together"):
        parse_manifest(bad)


def test_the_committed_manifest_parses_and_has_no_inception():
    m = load_manifest()
    assert m.inception is None and m.snapshots == ()
