"""Task 1.2: test_repo_crud (temp SQLite, best-price logic) + edge cases."""
import pytest

from negagent.store.negotiation_repo import NegotiationRepo


@pytest.fixture
def repo():
    r = NegotiationRepo.open(":memory:")
    yield r
    r.close()


def test_repo_crud(repo):
    # create
    rec = repo.create("L1")
    assert rec["listing_id"] == "L1"
    assert rec["status"] == "active"
    assert rec["current_offer"] is None
    assert rec["turns"] == []

    # append two turns (one with an explicit ts, one auto-stamped)
    repo.append_turn(
        "L1", "buyer", 100.0, "Would you take $100?", ts="2026-01-01T00:00:00+00:00"
    )
    rec = repo.append_turn("L1", "seller", 130.0, "I can do $130.")
    assert len(rec["turns"]) == 2
    assert rec["turns"][0] == {
        "role": "buyer",
        "amount": 100.0,
        "message": "Would you take $100?",
        "ts": "2026-01-01T00:00:00+00:00",
    }
    assert rec["turns"][1]["role"] == "seller"
    assert rec["turns"][1]["ts"]  # auto-generated, non-empty

    # update status + current offer
    rec = repo.update_state("L1", "needs_human", current_offer=120.0)
    assert rec["status"] == "needs_human"
    assert rec["current_offer"] == 120.0

    # read back via a fresh get
    rec = repo.get("L1")
    assert rec["status"] == "needs_human"
    assert len(rec["turns"]) == 2


def test_set_best_price_only_lowers(repo):
    repo.create("L1")
    assert repo.get("L1")["best_price_found"] is None

    assert repo.set_best_price("L1", 500.0)["best_price_found"] == 500.0  # first seen
    assert repo.set_best_price("L1", 450.0)["best_price_found"] == 450.0  # lower -> set
    assert repo.set_best_price("L1", 480.0)["best_price_found"] == 450.0  # higher -> keep
    assert repo.set_best_price("L1", 450.0)["best_price_found"] == 450.0  # equal -> keep


def test_create_duplicate_raises(repo):
    repo.create("L1")
    with pytest.raises(ValueError):
        repo.create("L1")


def test_get_missing_returns_none(repo):
    assert repo.get("nope") is None


def test_update_missing_raises(repo):
    with pytest.raises(KeyError):
        repo.update_state("ghost", "active")


def test_invalid_status_raises(repo):
    repo.create("L1")
    with pytest.raises(ValueError):
        repo.update_state("L1", "bogus")
    with pytest.raises(ValueError):
        repo.create("L2", status="bogus")


def test_update_state_preserves_current_offer_when_unset(repo):
    repo.create("L1", current_offer=99.0)
    rec = repo.update_state("L1", "walked")  # no current_offer kwarg
    assert rec["status"] == "walked"
    assert rec["current_offer"] == 99.0  # untouched


def test_persists_to_file_and_reopens(tmp_path):
    db = tmp_path / "neg.db"
    r1 = NegotiationRepo.open(db)
    r1.create("L1", current_offer=200.0)
    r1.append_turn("L1", "buyer", 180.0, "offer")
    r1.set_best_price("L1", 180.0)
    r1.close()

    # Reopen the same file: rows + JSON turns must survive.
    r2 = NegotiationRepo.open(db)
    rec = r2.get("L1")
    assert rec["current_offer"] == 200.0
    assert rec["best_price_found"] == 180.0
    assert rec["turns"][0]["amount"] == 180.0
    r2.close()
