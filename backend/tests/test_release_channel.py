"""Anmerkung 90: „läuft hier ein Release oder das :main-Gleis?"

Die Regel ist bewusst streng — Gleichheit von BUILD_REF und APP_VERSION, nicht
„sieht aus wie ein Tag". Der Test hält beide Richtungen fest, weil ein Fehler
hier still ist: ein Testimage, das sich als Release ausgibt, sieht genau so aus
wie ein Release.
"""
import pytest

from app.version import APP_VERSION, display_version, release_channel


@pytest.mark.parametrize("ref", [f"v{APP_VERSION}", APP_VERSION])
def test_matching_tag_is_a_release(monkeypatch, ref):
    monkeypatch.setenv("BUILD_REF", ref)
    assert release_channel() == "release"
    assert display_version() == APP_VERSION


@pytest.mark.parametrize("ref", [
    "main",             # das Testgleis
    "v0.0.1",           # ein Tag, aber nicht dieser
    "feature/foo",
    "",                 # lokal gestartet / selbst gebaut
])
def test_everything_else_is_dev(monkeypatch, ref):
    monkeypatch.setenv("BUILD_REF", ref)
    assert release_channel() == "dev"
    assert display_version() == f"{APP_VERSION}-dev"


def test_unset_build_ref_is_dev(monkeypatch):
    monkeypatch.delenv("BUILD_REF", raising=False)
    assert release_channel() == "dev"


def test_health_reports_all_three(monkeypatch):
    """/health trennt Maschinenfeld (`version`) und Menschenfeld bewusst."""
    monkeypatch.setenv("BUILD_REF", "main")
    from app.main import health

    out = health()
    assert out["version"] == APP_VERSION          # bleibt reines SemVer
    assert out["channel"] == "dev"
    assert out["display_version"] == f"{APP_VERSION}-dev"
