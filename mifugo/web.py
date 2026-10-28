"""
The phone web app. Two people use it:

  * the farmer, who logs a treatment from the drug box and asks "can I sell?"
  * the co-op collection clerk, who checks a delivery before it is bulked.

This file renders and routes. It decides nothing: verdicts come from
withdrawal.py, sentences from messages.py.

    uvicorn mifugo.web:app --reload
"""

import json
import time as _time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from mifugo import config, demo, llm, messages
from mifugo.clock import aware, now
from mifugo.label_reader import LabelReading, read_label
from mifugo.log_parser import parse
from mifugo.store import Store
from mifugo.withdrawal import (
    Kind,
    Status,
    Treatment,
    Withdrawal,
    animal_status,
    collection_check,
    herd_status,
)

HERE = Path(__file__).resolve().parent

T = {
    "sw": {
        "tagline": "Je, naweza kuuza maziwa haya leo?",
        "farmer": "Mkulima",
        "clerk": "Karani wa ushirika",
        "farms": "Mashamba",
        "new_farm": "Sajili shamba",
        "name": "Jina",
        "phone": "Simu",
        "member": "Nambari ya mwanachama",
        "milking": "Saa za kukamua",
        "create": "Sajili",
        "demo": "Pakia shamba la majaribio",
        "herd": "Ng'ombe wako",
        "add_cow": "Ongeza ng'ombe",
        "add": "Ongeza",
        "log": "Andika tiba",
        "ask": "Uliza",
        "ask_ph": "Naweza kuuza maziwa ya Njeri leo?",
        "ask_btn": "Uliza",
        "answer": "Jibu",
        "photo": "Piga picha ya boksi la dawa",
        "photo_hint": "Hakikisha maandishi ya 'withdrawal' (milk / meat) yanaonekana.",
        "words": "Eleza kwa maneno yako: nani, dawa gani, lini",
        "words_ph": "Nimemdunga Njeri sindano ya mastitis jana jioni",
        "read": "Soma",
        "confirm_title": "Thibitisha tiba",
        "gemma_read": "Gemma imesoma kutoka kwenye boksi",
        "python_checked": "Python imekagua ushahidi",
        "checks_ok": "Nambari na kipimo vimo kwenye maneno yaliyosomwa.",
        "product": "Dawa",
        "milk_w": "Muda wa kusubiri: maziwa",
        "meat_w": "Muda wa kusubiri: nyama",
        "kind_period": "Muda",
        "kind_zero": "Hakuna (sifuri)",
        "kind_nfl": "Isitumike kwa ng'ombe wa maziwa",
        "kind_unknown": "Haijulikani",
        "value": "Kiasi",
        "unit_hours": "saa",
        "unit_days": "siku",
        "unit_milkings": "ukamuaji",
        "confirmed_by": "Imethibitishwa na (agrovet / daktari)",
        "confirmed_by_hint": "Lazima ujaze ikiwa umeandika au kubadilisha muda kwa mkono.",
        "animals": "Ng'ombe waliotibiwa",
        "not_in_herd": "Majina haya hayamo kwenye kundi lako",
        "add_as_new": "Waongeze kama ng'ombe wapya",
        "given_at": "Alitibiwa lini",
        "save": "Hifadhi",
        "preview": "Ukihifadhi",
        "sms": "Ujumbe kwa mkulima (SMS)",
        "sms_note": "Mfano wa ujumbe. Kutuma SMS halisi bado hakujaunganishwa.",
        "history": "Tiba za karibuni",
        "meat": "Nyama",
        "confirm_period": "Weka muda uliothibitishwa",
        "coop_title": "Mapokezi ya maziwa",
        "search": "Tafuta mkulima (nambari, simu, jina)",
        "to_test": "Vyombo vya kupima leo",
        "of": "kati ya",
        "check": "Kagua",
        "log_check": "Rekodi ukaguzi",
        "recent_checks": "Ukaguzi wa karibuni",
        "back": "Rudi",
        "no_model": "Hakuna modeli: andika muda wa kusubiri mwenyewe kutoka kwenye boksi.",
        "time_assumed": "Hukutaja wakati: tumehesabu kuanzia sasa (njia salama).",
        "error_animals": "Chagua angalau ng'ombe mmoja.",
        "error_confirmed": "Andika nani alithibitisha muda huu.",
        "issues": "Kwa nini hatukuamini usomaji huu",
        "footer": "Gemma inasoma lebo na maneno yako. Python inahesabu tarehe na kutoa uamuzi. Mifugo haipendekezi dawa.",
    },
    "en": {
        "tagline": "Can I sell this milk today?",
        "farmer": "Farmer",
        "clerk": "Co-op clerk",
        "farms": "Farms",
        "new_farm": "Register a farm",
        "name": "Name",
        "phone": "Phone",
        "member": "Member number",
        "milking": "Milking times",
        "create": "Register",
        "demo": "Load demo farms",
        "herd": "Your herd",
        "add_cow": "Add a cow",
        "add": "Add",
        "log": "Log a treatment",
        "ask": "Ask",
        "ask_ph": "Can I sell Njeri's milk today?",
        "ask_btn": "Ask",
        "answer": "Answer",
        "photo": "Photograph the medicine box",
        "photo_hint": "Make sure the withdrawal lines (milk / meat) are in the photo.",
        "words": "In your own words: which cow, which medicine, when",
        "words_ph": "Gave Njeri a mastitis tube yesterday evening",
        "read": "Read",
        "confirm_title": "Confirm the treatment",
        "gemma_read": "What Gemma read from the box",
        "python_checked": "Python checked the evidence",
        "checks_ok": "The number and unit appear in the words that were read.",
        "product": "Medicine",
        "milk_w": "Withdrawal: milk",
        "meat_w": "Withdrawal: meat",
        "kind_period": "Period",
        "kind_zero": "None (zero)",
        "kind_nfl": "Not for lactating cows",
        "kind_unknown": "Unknown",
        "value": "Value",
        "unit_hours": "hours",
        "unit_days": "days",
        "unit_milkings": "milkings",
        "confirmed_by": "Confirmed by (agrovet / vet)",
        "confirmed_by_hint": "Required if you typed or changed a period by hand.",
        "animals": "Treated cows",
        "not_in_herd": "These names are not in your herd",
        "add_as_new": "Add them as new cows",
        "given_at": "When was it given",
        "save": "Save",
        "preview": "If you save",
        "sms": "Message to the farmer (SMS)",
        "sms_note": "Message preview. Real SMS sending is not connected yet.",
        "history": "Recent treatments",
        "meat": "Meat",
        "confirm_period": "Enter a confirmed period",
        "coop_title": "Milk intake",
        "search": "Find a farmer (number, phone, name)",
        "to_test": "Deliveries to test today",
        "of": "of",
        "check": "Check",
        "log_check": "Record this check",
        "recent_checks": "Recent checks",
        "back": "Back",
        "no_model": "No model: type the withdrawal period from the box yourself.",
        "time_assumed": "No time given: counted from now (the safe choice).",
        "error_animals": "Choose at least one cow.",
        "error_confirmed": "Say who confirmed this period.",
        "issues": "Why this reading was not trusted",
        "footer": "Gemma reads the label and your words. Python computes the dates and gives the verdict. Mifugo never recommends a medicine.",
    },
}

app = FastAPI(title="Mifugo")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")

_store = None
_model_status = {"at": 0.0, "ok": False}


def store():
    global _store
    if _store is None:
        _store = Store()
    return _store


def set_store(s):
    global _store
    _store = s


def model_status():
    """Cached for 30 s so a page load never waits on a dead model server."""
    if _time.monotonic() - _model_status["at"] > 30:
        b = llm.backend()
        _model_status.update(at=_time.monotonic(), ok=b.available(), label=b.describe())
    return _model_status


def ctx(request, **extra):
    lang = request.cookies.get("lang", "sw")
    lang = lang if lang in T else "sw"
    return {"request": request, "lang": lang, "t": T[lang], "model": model_status(), **extra}


def _status_view(s, lang, product_ids):
    level = {Status.CLEAR: "ok", Status.WITHHOLD: "stop", Status.WITHHOLD_UNKNOWN: "unknown"}[s.milk.status]
    driving = s.milk.driving
    return {
        "animal": s.animal,
        "level": level,
        "milk": messages.milk_line(s, lang, now()),
        "keep_apart": None if s.milk.sellable else messages.KEEP_APART[lang],
        "meat": messages.meat_line(s, lang, now()),
        "hours_left": (
            round((s.milk.safe_from - now()).total_seconds() / 3600)
            if s.milk.status is Status.WITHHOLD else None
        ),
        "fix_product": product_ids.get(driving.id) if (driving and s.milk.status is Status.WITHHOLD_UNKNOWN) else None,
    }


def farm_board(farm_id, lang):
    st = store()
    farm = st.farm(farm_id)
    schedule = st.schedule(farm_id)
    names = [a["name"] for a in st.animals(farm_id)]
    treatments = st.treatments(farm_id)
    product_ids = {t.id: st.product_for_treatment(t.id) for t in treatments}
    statuses = herd_status(names, treatments, now(), schedule)
    return farm, schedule, names, treatments, [_status_view(s, lang, product_ids) for s in statuses]


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "index.html", ctx(request, farms=store().farms()))


@app.get("/lang/{code}")
def set_lang(code: str, request: Request):
    resp = RedirectResponse(request.headers.get("referer") or "/", status_code=303)
    resp.set_cookie("lang", code if code in T else "sw", max_age=60 * 60 * 24 * 365)
    return resp


@app.post("/farms")
def create_farm(name: str = Form(...), phone: str = Form(""), member_no: str = Form(""),
                milking: str = Form("06:00,17:00")):
    farm_id = store().create_farm(name, phone, member_no, milking)
    return RedirectResponse(f"/farm/{farm_id}", status_code=303)


@app.post("/demo")
def load_demo():
    ids = demo.seed(store())
    return RedirectResponse(f"/farm/{ids[0]}", status_code=303)


# ---------------------------------------------------------------------------
# Farmer
# ---------------------------------------------------------------------------

def render_farm(request, farm_id, logged="", answer=None):
    c = ctx(request)
    farm, schedule, names, treatments, board = farm_board(farm_id, c["lang"])
    sms = []
    if logged:
        wanted = {int(x) for x in logged.split(",") if x.isdigit()}
        for t in treatments:
            if t.id in wanted:
                s = animal_status(t.animal, treatments, now(), schedule)
                sms.append(messages.sms_text(s, t, c["lang"], now()))
    return templates.TemplateResponse(
        request, "farm.html",
        {**c, "farm": farm, "board": board, "schedule": schedule.display(), "sms": sms,
         "history": store().treatment_rows(farm_id)[:8], "answer": answer,
         "demo_note": demo.DEMO_NOTE[c["lang"]] if farm["demo"] else None},
    )


@app.get("/farm/{farm_id}", response_class=HTMLResponse)
def farm_page(request: Request, farm_id: int, logged: str = ""):
    return render_farm(request, farm_id, logged=logged)


@app.post("/farm/{farm_id}/animals")
def add_animal(farm_id: int, name: str = Form(...)):
    if name.strip():
        try:
            store().add_animal(farm_id, name)
        except Exception:
            pass   # duplicate name: the existing cow is kept
    return RedirectResponse(f"/farm/{farm_id}", status_code=303)


@app.post("/farm/{farm_id}/ask", response_class=HTMLResponse)
def ask(request: Request, farm_id: int, text: str = Form(...)):
    c = ctx(request)
    lang = c["lang"]
    st = store()
    schedule = st.schedule(farm_id)
    names = [a["name"] for a in st.animals(farm_id)]
    treatments = st.treatments(farm_id)
    p = parse(text, names, now())

    lines = []
    if p.intent == "log_treatment":
        return RedirectResponse(f"/farm/{farm_id}/treat?text={_q(text)}", status_code=303)
    for name in p.unmatched:
        lines.append({"level": "unknown", "text": messages.UNKNOWN_ANIMAL[lang].format(name=name, herd=", ".join(names))})
    if p.animals:
        for name in p.animals:
            s = animal_status(name, treatments, now(), schedule)
            v = _status_view(s, lang, {})
            lines.append({"level": v["level"], "text": v["milk"] + (" " + v["keep_apart"] if v["keep_apart"] else "")})
    elif not p.unmatched:
        statuses = herd_status(names, treatments, now(), schedule)
        blocked = [s for s in statuses if not s.milk.sellable]
        for s in blocked:
            lines.append({"level": _status_view(s, lang, {})["level"], "text": messages.milk_line(s, lang, now())})
        if not blocked:
            lines.append({"level": "ok", "text": messages.HERD_ALL_CLEAR[lang]})
    answer = {"question": text, "lines": lines, "model_used": p.model_used}
    return render_farm(request, farm_id, answer=answer)


def _q(text):
    from urllib.parse import quote
    return quote(text, safe="")


@app.get("/farm/{farm_id}/treat", response_class=HTMLResponse)
def treat_form(request: Request, farm_id: int, text: str = ""):
    return templates.TemplateResponse(
        request, "treat.html", ctx(request, farm=store().farm(farm_id), text=text)
    )


@app.post("/farm/{farm_id}/treat/read", response_class=HTMLResponse)
async def treat_read(request: Request, farm_id: int, text: str = Form(""), photo: UploadFile = File(None)):
    c = ctx(request)
    st = store()
    names = [a["name"] for a in st.animals(farm_id)]

    image_path, reading = "", None
    if photo is not None and photo.filename:
        data = await photo.read()
        if data:
            config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            fname = f"{uuid.uuid4().hex}{Path(photo.filename).suffix.lower()[:6] or '.jpg'}"
            (config.UPLOAD_DIR / fname).write_bytes(data)
            image_path = fname
            reading = read_label(data)
    if reading is None:
        reading = LabelReading("", [], Withdrawal.unknown(), Withdrawal.unknown(), [], None, source="manual")

    p = parse(text, names, now()) if text.strip() else None
    given = p.given_at.at if p else now()
    form = {
        "product_name": reading.product_name,
        "ingredients": ", ".join(reading.active_ingredients),
        "milk": _w_form(reading.milk),
        "meat": _w_form(reading.meat),
        "animals": p.animals if p else [],
        "given_at": aware(given).strftime("%Y-%m-%dT%H:%M"),
        "time_basis": p.given_at.basis if p else "not given",
        "assumed": p.given_at.assumed if p else True,
        "product_mention": p.product_mention if p else "",
    }
    return templates.TemplateResponse(
        request, "confirm.html",
        {**c, "farm": st.farm(farm_id), "herd": names, "reading": reading, "form": form,
         "unmatched": p.unmatched if p else [], "text": text, "image_path": image_path,
         "original": json.dumps({"milk": form["milk"], "meat": form["meat"]}),
         "model_reply": json.dumps(reading.raw) if reading.raw is not None else "",
         "preview": _preview(form, st.schedule(farm_id), c["lang"]), "error": None},
    )


def _w_form(w):
    return {
        "kind": w.kind.value,
        "value": "" if w.value is None else f"{w.value:g}",
        "unit": w.unit or "days",
        "quote": w.quote,
    }


def _w_from(kind, value, unit, quote):
    kind = Kind(kind)
    if kind is Kind.PERIOD:
        return Withdrawal(kind, float(value), unit, quote)
    return Withdrawal(kind, quote=quote)


def _preview(form, schedule, lang):
    """What the farmer will see after saving, computed by the same engine."""
    try:
        milk = _w_from(form["milk"]["kind"], form["milk"]["value"], form["milk"]["unit"], form["milk"]["quote"])
        meat = _w_from(form["meat"]["kind"], form["meat"]["value"], form["meat"]["unit"], form["meat"]["quote"])
        given = aware(datetime.fromisoformat(form["given_at"]))
    except (ValueError, TypeError):
        return []
    out = []
    for name in form["animals"] or ["…"]:
        unnamed = "dawa hii" if lang == "sw" else "this medicine"
        t = Treatment(name, form["product_name"] or form.get("product_mention") or unnamed, given, milk, meat)
        s = animal_status(name, [t], now(), schedule)
        out.append(_status_view(s, lang, {}))
    return out


@app.post("/farm/{farm_id}/treat/confirm", response_class=HTMLResponse)
def treat_confirm(
    request: Request,
    farm_id: int,
    product_name: str = Form(""),
    ingredients: str = Form(""),
    milk_kind: str = Form("unknown"), milk_value: str = Form(""), milk_unit: str = Form("days"), milk_quote: str = Form(""),
    meat_kind: str = Form("unknown"), meat_value: str = Form(""), meat_unit: str = Form("days"), meat_quote: str = Form(""),
    confirmed_by: str = Form(""),
    animals: list[str] = Form([]),
    new_animals: list[str] = Form([]),
    given_at: str = Form(...),
    time_basis: str = Form(""),
    text: str = Form(""),
    image_path: str = Form(""),
    original: str = Form("{}"),
    model_reply: str = Form(""),
):
    c = ctx(request)
    st = store()
    form = {
        "product_name": product_name, "ingredients": ingredients,
        "milk": {"kind": milk_kind, "value": milk_value, "unit": milk_unit, "quote": milk_quote},
        "meat": {"kind": meat_kind, "value": meat_value, "unit": meat_unit, "quote": meat_quote},
        "animals": animals + new_animals, "given_at": given_at, "time_basis": time_basis,
        "assumed": False, "product_mention": "",
    }
    orig = json.loads(original or "{}")
    edited = any(
        {k: form[w][k] for k in ("kind", "value", "unit")} != {k: (orig.get(w) or {}).get(k) for k in ("kind", "value", "unit")}
        for w in ("milk", "meat")
    )
    manual = edited or not image_path
    periods_given = any(form[w]["kind"] in ("period", "zero") for w in ("milk", "meat"))

    error = None
    if not form["animals"]:
        error = c["t"]["error_animals"]
    elif manual and periods_given and not confirmed_by.strip():
        error = c["t"]["error_confirmed"]
    try:
        milk = _w_from(milk_kind, milk_value, milk_unit, milk_quote if not edited else f"Entered by hand, confirmed by {confirmed_by}")
        meat = _w_from(meat_kind, meat_value, meat_unit, meat_quote if not edited else f"Entered by hand, confirmed by {confirmed_by}")
        given = aware(datetime.fromisoformat(given_at))
        if given > now():
            raise ValueError("future")
    except (ValueError, TypeError) as exc:
        error = error or str(exc)

    if error:
        return templates.TemplateResponse(
            request, "confirm.html",
            {**c, "farm": st.farm(farm_id), "herd": [a["name"] for a in st.animals(farm_id)],
             "reading": LabelReading(product_name, [], Withdrawal.unknown(), Withdrawal.unknown(), [], None),
             "form": form, "unmatched": [], "text": text, "image_path": image_path,
             "original": original, "model_reply": model_reply,
             "preview": _preview(form, st.schedule(farm_id), c["lang"]), "error": error},
            status_code=422,
        )

    for name in new_animals:
        if name.strip() and name not in st.animal_ids(farm_id):
            st.add_animal(farm_id, name)
    ids = st.animal_ids(farm_id)
    product_id = st.save_product(
        product_name, [x.strip() for x in ingredients.split(",") if x.strip()], milk, meat,
        source="manual" if manual else "label_photo",
        confirmed_by=confirmed_by if manual else "",
        image_path=image_path,
        model_reply=json.loads(model_reply) if model_reply else None,
    )
    logged = [
        st.add_treatment(ids[name], product_id, given, text, time_basis)
        for name in dict.fromkeys(animals + new_animals) if name in ids
    ]
    return RedirectResponse(f"/farm/{farm_id}?logged={','.join(map(str, logged))}", status_code=303)


@app.post("/farm/{farm_id}/products/{product_id}/confirm")
def confirm_period(farm_id: int, product_id: int, kind: str = Form(...), value: str = Form(""),
                   unit: str = Form("days"), confirmed_by: str = Form(...)):
    w = _w_from(kind, value, unit, f"Confirmed by {confirmed_by}")
    store().confirm_period(product_id, "milk", w, confirmed_by)
    return RedirectResponse(f"/farm/{farm_id}", status_code=303)


# ---------------------------------------------------------------------------
# Co-op clerk
# ---------------------------------------------------------------------------

def _check(farm_id):
    st = store()
    names = [a["name"] for a in st.animals(farm_id)]
    return collection_check(names, st.treatments(farm_id), now(), st.schedule(farm_id))


@app.get("/coop", response_class=HTMLResponse)
def coop(request: Request, q: str = ""):
    c = ctx(request)
    st = store()
    farms = st.find_farms(q) if q.strip() else st.farms()
    rows = []
    for f in farms:
        check = _check(f["id"])
        rows.append({"farm": f, "decision": check.decision, "exclude": [s.animal for s in check.exclude]})
    to_test = sum(1 for r in rows if r["decision"] == "test")
    return templates.TemplateResponse(
        request, "coop.html",
        {**c, "rows": rows, "q": q, "to_test": to_test, "total": len(rows), "recent": st.checks(10)},
    )


@app.get("/coop/check/{farm_id}", response_class=HTMLResponse)
def coop_check(request: Request, farm_id: int):
    c = ctx(request)
    check = _check(farm_id)
    lang = c["lang"]
    details = [
        {"animal": s.animal, "line": messages.milk_line(s, lang, now())} for s in check.exclude
    ]
    return templates.TemplateResponse(
        request, "check.html",
        {**c, "farm": store().farm(farm_id), "check": check,
         "verdict": messages.collection_line(check, lang, now()), "details": details},
    )


@app.post("/coop/check/{farm_id}")
def coop_log_check(farm_id: int, clerk: str = Form("")):
    store().log_check(farm_id, _check(farm_id), clerk)
    return RedirectResponse("/coop", status_code=303)


# ---------------------------------------------------------------------------
# JSON, for an SMS/WhatsApp front end later
# ---------------------------------------------------------------------------

@app.get("/api/farm/{farm_id}/status")
def api_status(farm_id: int, lang: str = "sw"):
    st = store()
    schedule = st.schedule(farm_id)
    names = [a["name"] for a in st.animals(farm_id)]
    statuses = herd_status(names, st.treatments(farm_id), now(), schedule)
    return JSONResponse([
        {
            "animal": s.animal,
            "milk_status": s.milk.status.value,
            "milk_safe_from": s.milk.safe_from.isoformat() if s.milk.safe_from else None,
            "meat_status": s.meat.status.value,
            "meat_safe_from": s.meat.safe_from.isoformat() if s.meat.safe_from else None,
            "message": messages.milk_line(s, lang if lang in T else "sw", now()),
        }
        for s in statuses
    ])


@app.get("/healthz")
def healthz():
    status = model_status()
    return {"ok": True, "model": status.get("label"), "model_available": status["ok"]}


@app.get("/uploads/{name}")
def upload(name: str):
    from fastapi import HTTPException
    from fastapi.responses import FileResponse
    path = config.UPLOAD_DIR / Path(name).name
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path)
