"""
The Streamlit front end (app.py), driven headlessly with Streamlit's AppTest.
It shares views.py with the FastAPI app, so these tests check the wiring:
that the same verdicts appear and the same save rules apply.
"""

import html
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from mifugo import config, llm

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "s.db")
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "uploads")
    llm.set_backend(llm.NoModel())
    st.cache_resource.clear()
    st.cache_data.clear()
    at = AppTest.from_file(APP, default_timeout=30)
    yield at
    llm.set_backend(None)
    st.cache_resource.clear()


def text_of(at):
    return html.unescape(" ".join(m.value for m in at.markdown))


def test_hosted_app_starts_with_demo_farms(app):
    app.run()
    assert not app.exception
    page = text_of(app)
    assert "USIUZE maziwa ya Njeri" in page
    assert "haujulikani" in page                      # Wanjiru's torn label


def test_ask_about_a_cow(app):
    app.session_state["view"] = "ask"
    app.run()
    app.text_input[0].input("Naweza kuuza maziwa ya Njeri leo?")
    app.button[0].click().run()
    assert not app.exception
    assert "USIUZE maziwa ya Njeri" in text_of(app)


def test_clerk_sees_which_deliveries_to_test(app):
    app.run()
    app.sidebar.radio[1].set_value("clerk").run()
    assert not app.exception
    assert app.metric[0].value == "2 kati ya 3"
    assert "PIMA CHOMBO HIKI" in text_of(app)


def test_log_by_hand_needs_a_confirmer_then_saves(app):
    app.session_state["view"] = "log"
    app.run()
    app.text_area[0].input("Nimemdunga Chebet sindano jana jioni")
    app.button[0].click().run()                        # Soma
    assert not app.exception
    app.selectbox(key="milk_kind").set_value("period")
    app.text_input(key="milk_value").input("3")
    app.selectbox(key="milk_unit").set_value("days")
    app.run()
    assert "Chebet" in app.multiselect[0].value        # read from the message
    save = next(b for b in app.button if b.label == "Hifadhi")
    save.click().run()
    assert any("thibitisha" in e.value for e in app.error)   # no confirmer yet

    confirmer = next(w for w in app.text_input if "Imethibitishwa" in w.label)
    confirmer.input("Agrovet Mwangi")
    next(b for b in app.button if b.label == "Hifadhi").click().run()
    assert not app.exception
    page = text_of(app) + " ".join(s.value for s in app.success)
    assert "USIUZE maziwa ya Chebet" in page
    assert "Mifugo: Chebet ametibiwa" in page          # SMS preview
