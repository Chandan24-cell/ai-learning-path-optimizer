from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import app.services.recommender as recommender


def test_missing_model_artifacts_use_fallback(
    client: TestClient, user_factory, headers_factory, tmp_path: Path, monkeypatch
) -> None:
    _assert_fallback_with_test_artifacts(
        client,
        user_factory,
        headers_factory,
        tmp_path / "missing",
        monkeypatch,
        corrupt=False,
    )


def test_corrupted_model_artifacts_use_fallback(
    client: TestClient, user_factory, headers_factory, tmp_path: Path, monkeypatch
) -> None:
    _assert_fallback_with_test_artifacts(
        client,
        user_factory,
        headers_factory,
        tmp_path / "corrupt",
        monkeypatch,
        corrupt=True,
    )


def _assert_fallback_with_test_artifacts(
    client: TestClient,
    user_factory,
    headers_factory,
    artifact_root: Path,
    monkeypatch,
    *,
    corrupt: bool,
) -> None:
    original_assets = dict(recommender._ASSETS) if recommender._ASSETS is not None else None
    predictor_dir = artifact_root / "predictor"
    q_table_path = artifact_root / "q_table.json"
    predictor_dir.mkdir(parents=True)
    if corrupt:
        (predictor_dir / "meta.json").write_text("{not valid json", encoding="utf-8")
        q_table_path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(recommender, "PREDICTOR_DIR", str(predictor_dir))
    monkeypatch.setattr(recommender, "Q_TABLE_PATH", str(q_table_path))
    recommender._ASSETS = None
    try:
        auth = user_factory("missing_models" if not corrupt else "corrupt_models")
        headers = headers_factory(auth)
        mode = client.get("/api/meta")
        recommendations = client.get("/api/recommend?top_k=5", headers=headers)
        assert mode.status_code == 200
        assert mode.json()["recommender_mode"] == "zpd-fallback"
        assert recommendations.status_code == 200
        assert 1 <= len(recommendations.json()["recommendations"]) <= 5
    finally:
        recommender._ASSETS = original_assets
