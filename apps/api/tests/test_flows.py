"""M11 — Playlist Export + DJ Workflow tests."""
import json
import pytest
from app.models import Track, ProviderTrack, SavedFlow, SavedFlowTrack, FlowExport
from app.db import get_session_factory


# ─── Helpers ───

def _make_track(session, idx, bpm=120, key="C major", energy=0.6, artist=None):
    if artist is None:
        artist = f"Art{idx}"
    t = Track(canonical_title=f"t{idx}")
    session.add(t); session.flush()
    pt = ProviderTrack(
        track_id=t.id,
        provider="spotify",
        provider_track_id=f"sp-m11-{idx}-{t.id}",
        raw_title=f"t{idx}",
        artist_display=artist,
        provider_uri=f"spotify:track:sp-m11-{idx}-{t.id}",
    )
    session.add(pt); session.flush()
    from app.enrichment import EnrichmentResult
    from app.enrichment.persistence import persist_enrichment
    res = EnrichmentResult(
        source="soundcharts", status="matched",
        tempo_bpm=bpm, musical_key=key, time_signature=4,
        energy=energy, danceability=0.6, valence=0.5,
        acousticness=0.2, instrumentalness=0.0, liveness=0.1,
        loudness_db=-8, speechiness=0.05,
        source_identifier="u",
    )
    persist_enrichment(
        session, track_id=t.id, result=res,
        source_type="catalog_api", source_name="soundcharts",
        analysis_version="m4c-soundcharts-v1",
    )
    session.commit()
    return t


def _mock_flow_response(tracks, energy_shape="maintain"):
    """Build a mock SmartFlowResponse dict."""
    seq = []
    for i, t in enumerate(tracks):
        item = {
            "position": i + 1,
            "track": {
                "track_id": t.id,
                "title": f"t{t.id}",
                "artist": f"Art{t.id}",
                "bpm": 120 + i,
                "camelot": "1A",
                "energy": 0.5 + i * 0.05,
                "dominant_mood": "euphoric",
                "dominant_vibe": "driving",
            },
            "transition_from_previous": None,
        }
        if i > 0:
            item["transition_from_previous"] = {
                "score": 85 + i,
                "components": {"harmonic": 90, "tempo": 85},
                "reasons": ["compatible keys", "similar tempo"],
                "warnings": [],
            }
        seq.append(item)
    return {
        "sequence": seq,
        "overall_sequence_score": 88,
        "average_transition_score": 90.5,
        "minimum_transition_score": 85,
        "energy_shape": energy_shape,
        "energy_profile": [0.6] * len(tracks),
        "actual_energies": [0.5 + i * 0.05 for i in range(len(tracks))],
        "warnings": [],
        "status": "ok",
        "candidate_pool_size": len(tracks),
        "generation_time_ms": 42.0,
        "beam_width": 20,
        "target_track_count": len(tracks),
    }


# ─── Save Flow ───

def test_save_flow(session):
    tracks = [_make_track(session, i, artist=f"Art{i}") for i in range(5)]
    resp = _mock_flow_response(tracks)
    from app.flows import save_flow
    flow = save_flow(
        session,
        name="Test Flow",
        description="A test",
        flow_response=resp,
        request_params={"target_track_count": 5, "energy_shape": "maintain"},
    )
    assert flow.id is not None
    assert flow.name == "Test Flow"
    assert len(flow.tracks) == 5
    assert flow.overall_sequence_score == 88
    assert flow.energy_shape == "maintain"
    # Check order preserved
    positions = [t.position for t in sorted(flow.tracks, key=lambda t: t.position)]
    assert positions == [1, 2, 3, 4, 5]


def test_save_flow_preserves_track_order(session):
    tracks = [_make_track(session, i, artist=f"Art{i}") for i in range(6)]
    resp = _mock_flow_response(tracks)
    from app.flows import save_flow
    flow = save_flow(session, name="Order Test", description=None, flow_response=resp, request_params={"target_track_count": 6, "energy_shape": "build"})
    from app.flows import get_flow
    detail = get_flow(session, flow.id)
    assert detail is not None
    seq = detail["sequence"]
    assert len(seq) == 6
    assert [s["position"] for s in seq] == [1, 2, 3, 4, 5, 6]
    # Check track IDs match original order
    for i, item in enumerate(seq):
        assert item["track"]["track_id"] == tracks[i].id


def test_save_flow_transition_data(session):
    tracks = [_make_track(session, i, artist=f"Art{i}") for i in range(3)]
    resp = _mock_flow_response(tracks)
    from app.flows import save_flow
    flow = save_flow(session, name="Trans Test", description=None, flow_response=resp, request_params={"target_track_count": 3, "energy_shape": "maintain"})
    from app.flows import get_flow
    detail = get_flow(session, flow.id)
    # First track has no transition
    assert detail["sequence"][0]["transition_from_previous"] is None
    # Second track has transition
    t1 = detail["sequence"][1]["transition_from_previous"]
    assert t1 is not None
    assert t1["score"] == 86
    assert t1["components"]["harmonic"] == 90


# ─── CRUD ───

def test_list_flows(session):
    tracks = [_make_track(session, i, artist=f"Art{i}") for i in range(3)]
    resp = _mock_flow_response(tracks)
    from app.flows import save_flow, list_flows
    save_flow(session, name="Flow A", description=None, flow_response=resp, request_params={"target_track_count": 3, "energy_shape": "maintain"})
    save_flow(session, name="Flow B", description=None, flow_response=resp, request_params={"target_track_count": 3, "energy_shape": "build"})
    flows = list_flows(session)
    assert len(flows) == 2
    names = {f["name"] for f in flows}
    assert "Flow A" in names
    assert "Flow B" in names


def test_get_flow(session):
    tracks = [_make_track(session, i, artist=f"Art{i}") for i in range(3)]
    resp = _mock_flow_response(tracks)
    from app.flows import save_flow, get_flow
    flow = save_flow(session, name="Get Test", description="desc", flow_response=resp, request_params={"target_track_count": 3, "energy_shape": "maintain"})
    detail = get_flow(session, flow.id)
    assert detail is not None
    assert detail["name"] == "Get Test"
    assert detail["description"] == "desc"
    assert detail["track_count"] == 3
    assert len(detail["sequence"]) == 3


def test_delete_flow(session):
    tracks = [_make_track(session, i, artist=f"Art{i}") for i in range(3)]
    resp = _mock_flow_response(tracks)
    from app.flows import save_flow, delete_flow, get_flow
    flow = save_flow(session, name="Del Test", description=None, flow_response=resp, request_params={"target_track_count": 3, "energy_shape": "maintain"})
    fid = flow.id
    assert delete_flow(session, fid) is True
    assert get_flow(session, fid) is None
    # Cascade: tracks should be deleted
    remaining = session.query(SavedFlowTrack).filter_by(flow_id=fid).count()
    assert remaining == 0


def test_rename_flow(session):
    tracks = [_make_track(session, i, artist=f"Art{i}") for i in range(3)]
    resp = _mock_flow_response(tracks)
    from app.flows import save_flow, rename_flow
    flow = save_flow(session, name="Old Name", description=None, flow_response=resp, request_params={"target_track_count": 3, "energy_shape": "maintain"})
    result = rename_flow(session, flow.id, name="New Name", description="updated")
    assert result["name"] == "New Name"


# ─── TEXT EXPORT ───

def test_text_export(session):
    tracks = [_make_track(session, i, artist=f"Art{i}") for i in range(3)]
    resp = _mock_flow_response(tracks)
    from app.flows import save_flow, export_text
    flow = save_flow(session, name="Text Test", description="A text export", flow_response=resp, request_params={"target_track_count": 3, "energy_shape": "maintain"})
    text = export_text(session, flow.id)
    assert text is not None
    assert "AION SMART FLOW" in text
    assert "Text Test" in text
    assert "3 tracks" in text
    assert "01." in text
    assert "02." in text
    assert "03." in text
    assert "Overall: 88" in text
    assert "Energy shape: maintain" in text
    # Check metadata line
    assert "120 BPM" in text
    assert "1A" in text


def test_text_export_not_found(session):
    from app.flows import export_text
    assert export_text(session, 9999) is None


# ─── CSV EXPORT ───

def test_csv_export(session):
    tracks = [_make_track(session, i, artist=f"Art{i}") for i in range(3)]
    resp = _mock_flow_response(tracks)
    from app.flows import save_flow, export_csv
    flow = save_flow(session, name="CSV Test", description=None, flow_response=resp, request_params={"target_track_count": 3, "energy_shape": "maintain"})
    csv_text = export_csv(session, flow.id)
    assert csv_text is not None
    lines = csv_text.strip().split("\n")
    assert len(lines) == 4  # header + 3 rows
    header = lines[0]
    assert "position" in header
    assert "title" in header
    assert "transition_score" in header
    # Check data rows
    assert "1" in lines[1]
    assert "Art" in lines[1]


def test_csv_export_not_found(session):
    from app.flows import export_csv
    assert export_csv(session, 9999) is None


# ─── JSON EXPORT ───

def test_json_export(session):
    tracks = [_make_track(session, i, artist=f"Art{i}") for i in range(3)]
    resp = _mock_flow_response(tracks)
    from app.flows import save_flow, export_json
    flow = save_flow(session, name="JSON Test", description=None, flow_response=resp, request_params={"target_track_count": 3, "energy_shape": "maintain"})
    result = export_json(session, flow.id)
    assert result is not None
    assert result["name"] == "JSON Test"
    assert len(result["sequence"]) == 3


# ─── FILENAME SANITIZATION ───

def test_sanitize_filename():
    from app.flows import _sanitize_filename
    assert _sanitize_filename("My Flow: Test") == "My Flow Test"
    assert _sanitize_filename('<>:"/\\|?*') == "aion-flow"
    assert _sanitize_filename("  .. ") == "aion-flow"
    assert _sanitize_filename("normal-name_v2.1") == "normal-name_v2.1"
    assert _sanitize_filename("a" * 300) == "a" * 200


# ─── CASCADING DELETE ───

def test_cascade_delete_flow_tracks(session):
    tracks = [_make_track(session, i, artist=f"Art{i}") for i in range(5)]
    resp = _mock_flow_response(tracks)
    from app.flows import save_flow
    flow = save_flow(session, name="Cascade Test", description=None, flow_response=resp, request_params={"target_track_count": 5, "energy_shape": "maintain"})
    fid = flow.id
    # Verify tracks exist
    assert session.query(SavedFlowTrack).filter_by(flow_id=fid).count() == 5
    # Delete flow
    session.delete(flow)
    session.commit()
    # Tracks should be gone
    assert session.query(SavedFlowTrack).filter_by(flow_id=fid).count() == 0


# ─── EXPORT HISTORY ───

def test_export_history_recorded(session):
    tracks = [_make_track(session, i, artist=f"Art{i}") for i in range(3)]
    resp = _mock_flow_response(tracks)
    from app.flows import save_flow
    flow = save_flow(session, name="Export History Test", description=None, flow_response=resp, request_params={"target_track_count": 3, "energy_shape": "maintain"})
    # Manually add an export record
    export = FlowExport(
        flow_id=flow.id,
        provider="spotify",
        external_playlist_id="pl_test123",
        external_playlist_url="https://open.spotify.com/playlist/pl_test123",
        external_playlist_name="AION Test",
        exported_track_count=3,
        skipped_track_count=0,
        status="success",
    )
    session.add(export)
    session.commit()
    # Check it shows up in flow detail
    from app.flows import get_flow
    detail = get_flow(session, flow.id)
    assert len(detail["exports"]) == 1
    assert detail["exports"][0]["provider"] == "spotify"
    assert detail["exports"][0]["external_playlist_id"] == "pl_test123"


# ─── API ENDPOINTS ───

def test_api_save_flow(session):
    tracks = [_make_track(session, i, artist=f"Art{i}") for i in range(3)]
    resp = _mock_flow_response(tracks)
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    result = client.post("/flows", json={
        "name": "API Save Test",
        "description": "via API",
        "flow_response": resp,
        "request_params": {"target_track_count": 3, "energy_shape": "maintain"},
    })
    assert result.status_code == 200
    data = result.json()
    assert data["name"] == "API Save Test"
    assert data["track_count"] == 3
    assert "id" in data


def test_api_list_flows(session):
    tracks = [_make_track(session, i, artist=f"Art{i}") for i in range(3)]
    resp = _mock_flow_response(tracks)
    from app.flows import save_flow
    save_flow(session, name="List Test 1", description=None, flow_response=resp, request_params={"target_track_count": 3, "energy_shape": "maintain"})
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    result = client.get("/flows")
    assert result.status_code == 200
    assert result.json()["count"] >= 1


def test_api_get_flow(session):
    tracks = [_make_track(session, i, artist=f"Art{i}") for i in range(3)]
    resp = _mock_flow_response(tracks)
    from app.flows import save_flow
    flow = save_flow(session, name="Get API Test", description=None, flow_response=resp, request_params={"target_track_count": 3, "energy_shape": "maintain"})
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    result = client.get(f"/flows/{flow.id}")
    assert result.status_code == 200
    assert result.json()["name"] == "Get API Test"


def test_api_delete_flow(session):
    tracks = [_make_track(session, i, artist=f"Art{i}") for i in range(3)]
    resp = _mock_flow_response(tracks)
    from app.flows import save_flow
    flow = save_flow(session, name="Del API Test", description=None, flow_response=resp, request_params={"target_track_count": 3, "energy_shape": "maintain"})
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    result = client.delete(f"/flows/{flow.id}")
    assert result.status_code == 200
    assert result.json()["status"] == "deleted"
    # Verify gone
    result2 = client.get(f"/flows/{flow.id}")
    assert result2.status_code == 404


def test_api_text_export(session):
    tracks = [_make_track(session, i, artist=f"Art{i}") for i in range(3)]
    resp = _mock_flow_response(tracks)
    from app.flows import save_flow
    flow = save_flow(session, name="TXT API", description=None, flow_response=resp, request_params={"target_track_count": 3, "energy_shape": "maintain"})
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    result = client.get(f"/flows/{flow.id}/export/text")
    assert result.status_code == 200
    assert "AION SMART FLOW" in result.text
    assert result.headers["content-type"].startswith("text/plain")


def test_api_csv_export(session):
    tracks = [_make_track(session, i, artist=f"Art{i}") for i in range(3)]
    resp = _mock_flow_response(tracks)
    from app.flows import save_flow
    flow = save_flow(session, name="CSV API", description=None, flow_response=resp, request_params={"target_track_count": 3, "energy_shape": "maintain"})
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    result = client.get(f"/flows/{flow.id}/export/csv")
    assert result.status_code == 200
    assert "position,title" in result.text
    assert result.headers["content-type"].startswith("text/csv")


def test_api_get_flow_not_found(session):
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    result = client.get("/flows/9999")
    assert result.status_code == 404


def test_api_delete_flow_not_found(session):
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    result = client.delete("/flows/9999")
    assert result.status_code == 404
