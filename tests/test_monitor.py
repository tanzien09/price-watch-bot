import json
from pathlib import Path

import pytest

import monitor
import portfolio_bot
from tg import esc, truncate

SAMPLE = json.loads(
    (Path(__file__).with_name("sample_api_response.json")).read_text(encoding="utf-8")
)


# --- extract_value ------------------------------------------------------


def test_extract_from_saved_sample():
    assert monitor.extract_value(SAMPLE, "bitcoin.usd") == 78724.0


def test_extract_list_index():
    assert monitor.extract_value({"rates": [{"v": 1.5}, {"v": 2.5}]}, "rates.1.v") == 2.5


@pytest.mark.parametrize(
    "data,path",
    [
        (SAMPLE, "bitcoin.eur"),  # missing key
        (SAMPLE, "bitcoin.usd.deeper"),  # descending into a number
        ({"rates": [1]}, "rates.9"),  # index out of range
        ({"v": "not-a-number"}, "v"),  # non-numeric value
    ],
)
def test_extract_bad_paths_raise(data, path):
    with pytest.raises(ValueError):
        monitor.extract_value(data, path)


# --- should_alert -------------------------------------------------------


def test_first_run_always_alerts():
    assert monitor.should_alert("change", 10.0, None, None)
    assert monitor.should_alert("threshold_above", 10.0, None, 99.0)


def test_change_mode():
    assert monitor.should_alert("change", 10.0, 9.0, None)
    assert not monitor.should_alert("change", 10.0, 10.0, None)


def test_threshold_alerts_only_on_crossing():
    # crosses upward -> alert; stays above -> silent (no spam every 30 min)
    assert monitor.should_alert("threshold_above", 101.0, 99.0, 100.0)
    assert not monitor.should_alert("threshold_above", 102.0, 101.0, 100.0)
    assert monitor.should_alert("threshold_below", 99.0, 101.0, 100.0)
    assert not monitor.should_alert("threshold_below", 98.0, 99.0, 100.0)


def test_report_mode_always_alerts():
    assert monitor.should_alert("report", 10.0, 10.0, None)


# --- state round-trip ---------------------------------------------------


def test_state_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(monitor, "STATE_FILE", tmp_path / "state.json")
    assert monitor.read_state() is None  # missing file -> first run
    monitor.write_state(123.45)
    assert monitor.read_state() == 123.45


def test_corrupt_state_treated_as_first_run(tmp_path, monkeypatch):
    state = tmp_path / "state.json"
    state.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(monitor, "STATE_FILE", state)
    assert monitor.read_state() is None


# --- security helpers ---------------------------------------------------


def test_html_is_escaped():
    assert esc("<script>&") == "&lt;script&gt;&amp;"


def test_truncate_respects_limit():
    assert len(truncate("x" * 5000, 4096)) == 4096


# --- portfolio bot validation ------------------------------------------


def test_shipped_projects_json_is_valid():
    projects = portfolio_bot.load_projects()
    assert len(projects) >= 1


def test_bad_project_id_rejected(tmp_path):
    bad = tmp_path / "projects.json"
    bad.write_text(
        json.dumps({"projects": [{"id": "../evil", "title": "t", "description": "d"}]}),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        portfolio_bot.load_projects(bad)


def test_non_https_link_rejected(tmp_path):
    bad = tmp_path / "projects.json"
    bad.write_text(
        json.dumps(
            {"projects": [{"id": "a", "title": "t", "description": "d", "url": "http://x"}]}
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        portfolio_bot.load_projects(bad)
