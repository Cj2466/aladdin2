from sqlalchemy.orm import sessionmaker

from app.models.screening_candidate import ScreeningCandidate
from app.models.screening_job import ScreeningJob
from app.services.research_lab.system_account import get_or_create_system_user
from app.services.research_lab.ticker_universe import SCREENING_UNIVERSE


def test_create_screening_job_requires_auth(client):
    response = client.post("/api/research-lab/screening", json={"strategy_name": "momentum_v1"})
    assert response.status_code == 401


def test_create_screening_job_returns_queued_status_and_universe_size(client, register_and_verify):
    register_and_verify(client)
    response = client.post("/api/research-lab/screening", json={"strategy_name": "momentum_v1"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert body["universe_size"] == len(SCREENING_UNIVERSE)
    assert body["strategy_name"] == "momentum_v1"
    assert body["n_tickers_resolved"] == 0
    assert body["n_candidates_found"] == 0


def test_create_screening_job_rejects_unknown_strategy_name(client, register_and_verify):
    register_and_verify(client)
    response = client.post("/api/research-lab/screening", json={"strategy_name": "not_a_real_strategy"})
    assert response.status_code == 422


def test_list_screening_jobs_requires_auth(client):
    response = client.get("/api/research-lab/screening")
    assert response.status_code == 401


def test_list_screening_jobs_is_user_scoped(client, register_and_verify):
    from fastapi.testclient import TestClient

    from app.main import app

    register_and_verify(client, email="screening_user_a@example.com")
    created = client.post("/api/research-lab/screening", json={"strategy_name": "ou_pairs_v1"})
    assert created.status_code == 201

    other_client = TestClient(app)
    register_and_verify(other_client, email="screening_user_b@example.com")
    listed = other_client.get("/api/research-lab/screening")
    assert listed.json() == []

    own_listed = client.get("/api/research-lab/screening")
    assert len(own_listed.json()) == 1


def test_get_screening_job_404_for_other_users_job(client, register_and_verify):
    from fastapi.testclient import TestClient

    from app.main import app

    register_and_verify(client, email="screening_owner@example.com")
    created = client.post("/api/research-lab/screening", json={"strategy_name": "momentum_v1"})
    job_id = created.json()["id"]

    other_client = TestClient(app)
    register_and_verify(other_client, email="screening_intruder@example.com")
    response = other_client.get(f"/api/research-lab/screening/{job_id}")
    assert response.status_code == 404


def test_get_screening_job_detail_includes_candidates_and_notes(client, register_and_verify, test_db_engine):
    register_and_verify(client)
    created = client.post("/api/research-lab/screening", json={"strategy_name": "momentum_v1"})
    job_id = created.json()["id"]

    # Manually complete the job + insert candidate rows, mirroring what
    # ScreeningRunner would do — this test is about the detail endpoint's
    # response shape, not the runner (covered separately).
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        job = db.get(ScreeningJob, job_id)
        job.status = "completed"
        job.n_tickers_resolved = len(SCREENING_UNIVERSE)
        job.n_candidates_found = 1
        db.add(ScreeningCandidate(job_id=job_id, ticker_a="AAPL", ticker_b="AAPL", score=3.5, direction="long"))
        db.commit()

    response = client.get(f"/api/research-lab/screening/{job_id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert len(body["candidates"]) == 1
    assert body["candidates"][0]["ticker_a"] == "AAPL"
    assert body["candidates"][0]["direction"] == "long"
    assert str(len(SCREENING_UNIVERSE)) in body["methodology_note"]
    assert body["is_system"] is False


def _seed_system_owned_job(test_db_engine, *, status: str = "completed") -> int:
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        system_user = get_or_create_system_user(db)
        job = ScreeningJob(
            user_id=system_user.id,
            strategy_name="momentum_v1",
            universe_size=len(SCREENING_UNIVERSE),
            n_tickers_resolved=len(SCREENING_UNIVERSE),
            n_candidates_found=0,
            status=status,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job.id


def test_screening_router_lists_system_jobs_alongside_own_and_flags_is_system(
    client, register_and_verify, test_db_engine
):
    register_and_verify(client)
    own = client.post("/api/research-lab/screening", json={"strategy_name": "ou_pairs_v1"})
    assert own.status_code == 201

    system_job_id = _seed_system_owned_job(test_db_engine)

    listed = client.get("/api/research-lab/screening")
    assert listed.status_code == 200
    by_id = {row["id"]: row for row in listed.json()}
    assert by_id[own.json()["id"]]["is_system"] is False
    assert by_id[system_job_id]["is_system"] is True


def test_screening_router_detail_endpoint_visible_for_system_job(client, register_and_verify, test_db_engine):
    register_and_verify(client)
    system_job_id = _seed_system_owned_job(test_db_engine)

    response = client.get(f"/api/research-lab/screening/{system_job_id}")
    assert response.status_code == 200, response.text
    assert response.json()["is_system"] is True
