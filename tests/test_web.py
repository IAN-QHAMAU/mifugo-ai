"""
End to end through the web app, with a scripted model so the test states
exactly what Gemma returned and checks what the farmer and clerk then see.
"""

import html
import io
import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mifugo import config, demo, llm, web
from mifugo.clock import now
from mifugo.store import Store

LABEL = {
    "is_veterinary_label": True,
    "legibility": "clear",
    "product_name": "Test Tube LC",
    "active_ingredients": ["cloxacillin"],
    "milk": {"stated": "period", "value": 84, "unit": "hours", "quote": "Milk: 84 hours"},
    "meat": {"stated": "period", "value": 7, "unit": "days", "quote": "Meat: 7 days"},
    "several_species_listed": False,
}


def log_reply(names, when="yesterday_evening"):
    return {"intent": "log_treatment", "animal_names": names, "product_mention": "",
            "when": when, "days_ago": 0, "clock": ""}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "uploads")
    web.set_store(Store(tmp_path / "t.db"))
    web._model_status["at"] = 0
    yield TestClient(web.app)
    web.set_store(None)
    llm.set_backend(None)


def model(label=LABEL, log=None):
    def reply(system, user, images):
        return label if images else (log or log_reply(["Akinyi"]))
    llm.set_backend(llm.ScriptedBackend(reply))
    web._model_status["at"] = 0


def png():
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), "white").save(buf, format="PNG")
    return buf.getvalue()


def farm(client):
    return web.store().create_farm("Shamba la Test", "0700", "M-1")


def test_home_and_demo(client):
    model()
    assert client.get("/").status_code == 200
    r = client.post("/demo", follow_redirects=True)
    assert r.status_code == 200
    assert "USIUZE maziwa ya Njeri" in r.text          # tube 15 h ago
    assert "Maziwa ya Baraka yanaweza kuuzwa" in r.text
    assert "haujulikani" in r.text                       # Wanjiru's torn label
    assert "Data ya majaribio" in r.text


def test_photo_and_swahili_log_to_a_red_card_and_sms(client):
    model()
    fid = farm(client)
    web.store().add_animal(fid, "Akinyi")
    r = client.post(
        f"/farm/{fid}/treat/read",
        data={"text": "Nimemdunga Akinyi tube jana jioni"},
        files={"photo": ("box.png", png(), "image/png")},
    )
    assert r.status_code == 200
    assert "Milk: 84 hours" in r.text                    # the quote is shown as evidence
    assert 'value="Akinyi" checked' in r.text
    given = re.search(r'name="given_at" value="([^"]+)"', r.text).group(1)
    original = re.search(r'name="original" value="([^"]+)"', r.text).group(1).replace("&#34;", '"')
    image_path = re.search(r'name="image_path" value="([^"]+)"', r.text).group(1)

    r = client.post(f"/farm/{fid}/treat/confirm", data={
        "product_name": "Test Tube LC", "milk_kind": "period", "milk_value": "84", "milk_unit": "hours",
        "milk_quote": "Milk: 84 hours", "meat_kind": "period", "meat_value": "7", "meat_unit": "days",
        "meat_quote": "Meat: 7 days", "animals": ["Akinyi"], "given_at": given,
        "image_path": image_path, "original": original, "text": "Nimemdunga Akinyi tube jana jioni",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert "USIUZE maziwa ya Akinyi" in r.text
    assert "Mifugo: Akinyi ametibiwa" in r.text           # SMS preview
    p = web.store().product(1)
    assert p["source"] == "label_photo"


def test_hand_entered_period_needs_a_confirmer(client):
    llm.set_backend(llm.NoModel())
    fid = farm(client)
    web.store().add_animal(fid, "Akinyi")
    data = {
        "product_name": "X", "milk_kind": "period", "milk_value": "3", "milk_unit": "days",
        "meat_kind": "unknown", "animals": ["Akinyi"],
        "given_at": now().strftime("%Y-%m-%dT%H:%M"), "original": "{}",
    }
    r = client.post(f"/farm/{fid}/treat/confirm", data=data)
    assert r.status_code == 422
    r = client.post(f"/farm/{fid}/treat/confirm", data={**data, "confirmed_by": "Agrovet Mwangi"},
                    follow_redirects=True)
    assert r.status_code == 200
    assert web.store().product(1)["confirmed_by"] == "Agrovet Mwangi"


def test_future_dose_time_is_refused(client):
    llm.set_backend(llm.NoModel())
    fid = farm(client)
    web.store().add_animal(fid, "Akinyi")
    later = (now() + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
    r = client.post(f"/farm/{fid}/treat/confirm", data={
        "milk_kind": "unknown", "meat_kind": "unknown", "animals": ["Akinyi"],
        "given_at": later, "original": "{}",
    })
    assert r.status_code == 422


def test_ask_about_a_cow(client):
    model(log={"intent": "ask_milk", "animal_names": ["Njeri"], "product_mention": "",
               "when": "unknown", "days_ago": 0, "clock": ""})
    ids = demo.seed(web.store())
    r = client.post(f"/farm/{ids[0]}/ask", data={"text": "Naweza kuuza maziwa ya Njeri leo?"})
    assert "USIUZE maziwa ya Njeri" in r.text
    assert "Usichanganye" in r.text


def test_ask_about_an_unknown_cow_lists_the_herd(client):
    model(log={"intent": "ask_milk", "animal_names": ["Kamau"], "product_mention": "",
               "when": "unknown", "days_ago": 0, "clock": ""})
    ids = demo.seed(web.store())
    r = client.post(f"/farm/{ids[0]}/ask", data={"text": "maziwa ya Kamau?"})
    assert "Sijamtambua" in r.text and "Njeri" in r.text


def test_confirming_an_unknown_period_clears_the_block(client):
    llm.set_backend(llm.NoModel())
    ids = demo.seed(web.store())
    r = client.get(f"/farm/{ids[0]}")
    action = re.search(r'action="(/farm/\d+/products/\d+/confirm)"', r.text).group(1)
    r = client.post(action, data={"kind": "period", "value": "1", "unit": "days",
                                  "confirmed_by": "Dr Achieng"}, follow_redirects=True)
    assert "haujulikani" not in r.text
    assert "Maziwa ya Wanjiru yanaweza kuuzwa" in r.text


def test_coop_flags_only_the_risky_deliveries(client):
    llm.set_backend(llm.NoModel())
    ids = demo.seed(web.store())
    r = client.get("/coop")
    assert "<b>2</b>" in r.text                          # Wanjiku and Kiprop, not Otieno
    r = client.get(f"/coop/check/{ids[1]}")
    assert "POKEA" in r.text
    r = client.get(f"/coop/check/{ids[0]}")
    assert "PIMA CHOMBO HIKI" in r.text and "Njeri" in r.text
    r = client.post(f"/coop/check/{ids[0]}", data={"clerk": "Karani Ruth"}, follow_redirects=True)
    assert "Karani Ruth" in r.text


def test_english(client):
    llm.set_backend(llm.NoModel())
    ids = demo.seed(web.store())
    client.cookies.set("lang", "en")
    r = client.get(f"/farm/{ids[0]}")
    assert "DO NOT SELL Njeri's milk" in html.unescape(r.text)


def test_api_status(client):
    llm.set_backend(llm.NoModel())
    ids = demo.seed(web.store())
    data = client.get(f"/api/farm/{ids[0]}/status").json()
    status = {d["animal"]: d["milk_status"] for d in data}
    assert status == {"Baraka": "clear", "Chebet": "clear", "Njeri": "withhold", "Wanjiru": "withhold_unknown"}
