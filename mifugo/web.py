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
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from mifugo import config, demo, llm, views
from mifugo.clock import now
from mifugo.label_reader import LabelReading, read_label
from mifugo.log_parser import parse
from mifugo.store import Store
from mifugo.ui_text import T
from mifugo.withdrawal import Withdrawal

HERE = Path(__file__).resolve().parent

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
    farm, schedule, names, treatments, board = views.farm_board(store(), farm_id, c["lang"])
    wanted = {int(x) for x in logged.split(",") if x.isdigit()}
    return templates.TemplateResponse(
        request, "farm.html",
        {**c, "farm": farm, "board": board, "schedule": schedule.display(),
         "sms": views.sms_for(store(), farm_id, wanted, c["lang"]) if wanted else [],
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
    result = views.answer(store(), farm_id, text, ctx(request)["lang"])
    if result["intent"] == "log_treatment":
        from urllib.parse import quote
        return RedirectResponse(f"/farm/{farm_id}/treat?text={quote(text, safe='')}", status_code=303)
    return render_farm(request, farm_id, answer=result)


@app.get("/farm/{farm_id}/treat", response_class=HTMLResponse)
def treat_form(request: Request, farm_id: int, text: str = ""):
    return templates.TemplateResponse(
        request, "treat.html", ctx(request, farm=store().farm(farm_id), text=text)
    )


def _confirm_page(request, farm_id, *, reading, form, unmatched, text, image_path,
                  original, model_reply, error=None, status_code=200):
    c = ctx(request)
    st = store()
    return templates.TemplateResponse(
        request, "confirm.html",
        {**c, "farm": st.farm(farm_id), "herd": [a["name"] for a in st.animals(farm_id)],
         "reading": reading, "form": form, "unmatched": unmatched, "text": text,
         "image_path": image_path, "original": original, "model_reply": model_reply,
         "preview": views.preview(form, st.schedule(farm_id), c["lang"]),
         "error": c["t"].get(error, error) if error else None},
        status_code=status_code,
    )


@app.post("/farm/{farm_id}/treat/read", response_class=HTMLResponse)
async def treat_read(request: Request, farm_id: int, text: str = Form(""), photo: UploadFile = File(None)):
    names = [a["name"] for a in store().animals(farm_id)]

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

    parsed = parse(text, names, now()) if text.strip() else None
    form = views.draft(reading, parsed)
    return _confirm_page(
        request, farm_id, reading=reading, form=form,
        unmatched=parsed.unmatched if parsed else [], text=text, image_path=image_path,
        original=json.dumps({"milk": form["milk"], "meat": form["meat"]}),
        model_reply=views.dumps(reading.raw),
    )


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
    form = {
        "product_name": product_name, "ingredients": ingredients,
        "milk": {"kind": milk_kind, "value": milk_value, "unit": milk_unit, "quote": milk_quote},
        "meat": {"kind": meat_kind, "value": meat_value, "unit": meat_unit, "quote": meat_quote},
        "animals": animals, "given_at": given_at, "time_basis": time_basis,
        "assumed": False, "product_mention": "",
    }
    result = views.save_treatment(
        store(), farm_id, form, confirmed_by=confirmed_by, image_path=image_path,
        original=json.loads(original or "{}"),
        model_reply=json.loads(model_reply) if model_reply else None,
        text=text, new_animals=new_animals,
    )
    if result.error:
        form["animals"] = animals + new_animals
        return _confirm_page(
            request, farm_id,
            reading=LabelReading(product_name, [], Withdrawal.unknown(), Withdrawal.unknown(), [], None),
            form=form, unmatched=[], text=text, image_path=image_path, original=original,
            model_reply=model_reply, error=result.error, status_code=422,
        )
    return RedirectResponse(f"/farm/{farm_id}?logged={','.join(map(str, result.logged))}", status_code=303)


@app.post("/farm/{farm_id}/products/{product_id}/confirm")
def confirm_period(farm_id: int, product_id: int, kind: str = Form(...), value: str = Form(""),
                   unit: str = Form("days"), confirmed_by: str = Form(...)):
    views.confirm_period(store(), product_id, kind, value, unit, confirmed_by)
    return RedirectResponse(f"/farm/{farm_id}", status_code=303)


# ---------------------------------------------------------------------------
# Co-op clerk
# ---------------------------------------------------------------------------

@app.get("/coop", response_class=HTMLResponse)
def coop(request: Request, q: str = ""):
    rows = views.coop_rows(store(), q)
    to_test = sum(1 for r in rows if r["decision"] == "test")
    return templates.TemplateResponse(
        request, "coop.html",
        ctx(request, rows=rows, q=q, to_test=to_test, total=len(rows), recent=store().checks(10)),
    )


@app.get("/coop/check/{farm_id}", response_class=HTMLResponse)
def coop_check(request: Request, farm_id: int):
    c = ctx(request)
    check, verdict, details = views.check_details(store(), farm_id, c["lang"])
    return templates.TemplateResponse(
        request, "check.html",
        {**c, "farm": store().farm(farm_id), "check": check, "verdict": verdict, "details": details},
    )


@app.post("/coop/check/{farm_id}")
def coop_log_check(farm_id: int, clerk: str = Form("")):
    store().log_check(farm_id, views.check(store(), farm_id), clerk)
    return RedirectResponse("/coop", status_code=303)


# ---------------------------------------------------------------------------
# JSON, for an SMS/WhatsApp front end later
# ---------------------------------------------------------------------------

@app.get("/api/farm/{farm_id}/status")
def api_status(farm_id: int, lang: str = "sw"):
    return JSONResponse(views.api_status(store(), farm_id, lang if lang in T else "sw"))


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
