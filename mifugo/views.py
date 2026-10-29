"""
What both front ends show, computed once.

The FastAPI app (web.py) and the Streamlit app (app.py) are two skins over
the same functions here, so a verdict, an answer or a save rule cannot
drift between them. Nothing here renders HTML; nothing here decides a
verdict either. That is withdrawal.py and messages.py.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime

from mifugo import messages
from mifugo.clock import aware, now
from mifugo.log_parser import parse
from mifugo.withdrawal import (
    Kind,
    Status,
    Treatment,
    Withdrawal,
    animal_status,
    collection_check,
    herd_status,
)

LEVEL = {Status.CLEAR: "ok", Status.WITHHOLD: "stop", Status.WITHHOLD_UNKNOWN: "unknown"}


def status_view(s, lang, product_ids=None):
    """One cow's card: level, the milk sentence, the meat sentence."""
    driving = s.milk.driving
    product_ids = product_ids or {}
    return {
        "animal": s.animal,
        "level": LEVEL[s.milk.status],
        "milk": messages.milk_line(s, lang, now()),
        "keep_apart": None if s.milk.sellable else messages.KEEP_APART[lang],
        "meat": messages.meat_line(s, lang, now()),
        "hours_left": (
            round((s.milk.safe_from - now()).total_seconds() / 3600)
            if s.milk.status is Status.WITHHOLD else None
        ),
        "fix_product": (
            product_ids.get(driving.id)
            if driving and s.milk.status is Status.WITHHOLD_UNKNOWN else None
        ),
    }


def farm_board(store, farm_id, lang):
    farm = store.farm(farm_id)
    schedule = store.schedule(farm_id)
    names = [a["name"] for a in store.animals(farm_id)]
    treatments = store.treatments(farm_id)
    product_ids = {t.id: store.product_for_treatment(t.id) for t in treatments}
    statuses = herd_status(names, treatments, now(), schedule)
    return farm, schedule, names, treatments, [status_view(s, lang, product_ids) for s in statuses]


def sms_for(store, farm_id, treatment_ids, lang):
    """SMS previews for treatments that were just logged."""
    schedule = store.schedule(farm_id)
    treatments = store.treatments(farm_id)
    out = []
    for t in treatments:
        if t.id in treatment_ids:
            s = animal_status(t.animal, treatments, now(), schedule)
            out.append(messages.sms_text(s, t, lang, now()))
    return out


def answer(store, farm_id, text, lang):
    """
    A farmer's question -> {intent, question, lines, model_used}.
    intent == "log_treatment" means the message was a treatment report, and
    the caller should send the farmer to the logging screen instead.
    """
    schedule = store.schedule(farm_id)
    names = [a["name"] for a in store.animals(farm_id)]
    treatments = store.treatments(farm_id)
    p = parse(text, names, now())

    lines = []
    if p.intent != "log_treatment":
        for name in p.unmatched:
            lines.append({"level": "unknown",
                          "text": messages.UNKNOWN_ANIMAL[lang].format(name=name, herd=", ".join(names))})
        if p.animals:
            for name in p.animals:
                v = status_view(animal_status(name, treatments, now(), schedule), lang)
                lines.append({"level": v["level"],
                              "text": v["milk"] + (" " + v["keep_apart"] if v["keep_apart"] else "")})
        elif not p.unmatched:
            blocked = [s for s in herd_status(names, treatments, now(), schedule) if not s.milk.sellable]
            for s in blocked:
                lines.append({"level": LEVEL[s.milk.status], "text": messages.milk_line(s, lang, now())})
            if not blocked:
                lines.append({"level": "ok", "text": messages.HERD_ALL_CLEAR[lang]})
    return {"intent": p.intent, "question": text, "lines": lines, "model_used": p.model_used}


# ---------------------------------------------------------------------------
# Logging a treatment
# ---------------------------------------------------------------------------

def withdrawal_to_form(w):
    return {
        "kind": w.kind.value,
        "value": "" if w.value is None else f"{w.value:g}",
        "unit": w.unit or "days",
        "quote": w.quote,
    }


def withdrawal_from_form(kind, value, unit, quote):
    kind = Kind(kind)
    if kind is Kind.PERIOD:
        return Withdrawal(kind, float(value), unit, quote)
    return Withdrawal(kind, quote=quote)


def draft(reading, parsed):
    """A label reading and a parsed message -> the editable treatment form."""
    given = parsed.given_at.at if parsed else now()
    return {
        "product_name": reading.product_name,
        "ingredients": ", ".join(reading.active_ingredients),
        "milk": withdrawal_to_form(reading.milk),
        "meat": withdrawal_to_form(reading.meat),
        "animals": parsed.animals if parsed else [],
        "given_at": aware(given).strftime("%Y-%m-%dT%H:%M"),
        "time_basis": parsed.given_at.basis if parsed else "not given",
        "assumed": parsed.given_at.assumed if parsed else True,
        "product_mention": parsed.product_mention if parsed else "",
    }


def preview(form, schedule, lang):
    """What the farmer will see after saving, computed by the same engine."""
    try:
        milk = withdrawal_from_form(**{k: form["milk"][k] for k in ("kind", "value", "unit", "quote")})
        meat = withdrawal_from_form(**{k: form["meat"][k] for k in ("kind", "value", "unit", "quote")})
        given = aware(datetime.fromisoformat(form["given_at"]))
    except (ValueError, TypeError, KeyError):
        return []
    unnamed = "dawa hii" if lang == "sw" else "this medicine"
    product = form.get("product_name") or form.get("product_mention") or unnamed
    out = []
    for name in form["animals"] or ["…"]:
        t = Treatment(name, product, given, milk, meat)
        out.append(status_view(animal_status(name, [t], now(), schedule), lang))
    return out


@dataclass
class SaveResult:
    logged: list = field(default_factory=list)   # treatment ids
    error: str = None                            # "error_animals" | "error_confirmed" | message


def save_treatment(store, farm_id, form, *, confirmed_by="", image_path="", original=None,
                   model_reply=None, text="", new_animals=()):
    """
    Validate and store a confirmed treatment form.

    A period typed or changed by hand, or entered without a photo, is saved
    only with the name of whoever confirmed it. A dose time in the future is
    refused. Returns the new treatment ids, or an error key.
    """
    original = original or {}
    keys = ("kind", "value", "unit")
    edited = any(
        {k: form[w][k] for k in keys} != {k: (original.get(w) or {}).get(k) for k in keys}
        for w in ("milk", "meat")
    )
    manual = edited or not image_path
    periods_given = any(form[w]["kind"] in ("period", "zero") for w in ("milk", "meat"))
    animals = list(dict.fromkeys(list(form["animals"]) + [n for n in new_animals if n.strip()]))

    if not animals:
        return SaveResult(error="error_animals")
    if manual and periods_given and not confirmed_by.strip():
        return SaveResult(error="error_confirmed")
    hand = f"Entered by hand, confirmed by {confirmed_by}"
    try:
        milk = withdrawal_from_form(form["milk"]["kind"], form["milk"]["value"], form["milk"]["unit"],
                                    hand if edited else form["milk"]["quote"])
        meat = withdrawal_from_form(form["meat"]["kind"], form["meat"]["value"], form["meat"]["unit"],
                                    hand if edited else form["meat"]["quote"])
        given = aware(datetime.fromisoformat(form["given_at"]))
        if given > now():
            raise ValueError("future")
    except (ValueError, TypeError) as exc:
        return SaveResult(error=str(exc))

    for name in new_animals:
        if name.strip() and name not in store.animal_ids(farm_id):
            store.add_animal(farm_id, name)
    ids = store.animal_ids(farm_id)
    ingredients = [x.strip() for x in (form.get("ingredients") or "").split(",") if x.strip()]
    product_id = store.save_product(
        form.get("product_name") or form.get("product_mention") or "",
        ingredients, milk, meat,
        source="manual" if manual else "label_photo",
        confirmed_by=confirmed_by if manual else "",
        image_path=image_path,
        model_reply=model_reply,
    )
    logged = [
        store.add_treatment(ids[name], product_id, given, text, form.get("time_basis", ""))
        for name in animals if name in ids
    ]
    return SaveResult(logged=logged)


def confirm_period(store, product_id, kind, value, unit, confirmed_by):
    w = withdrawal_from_form(kind, value, unit, f"Confirmed by {confirmed_by}")
    store.confirm_period(product_id, "milk", w, confirmed_by)


# ---------------------------------------------------------------------------
# Co-op
# ---------------------------------------------------------------------------

def check(store, farm_id):
    names = [a["name"] for a in store.animals(farm_id)]
    return collection_check(names, store.treatments(farm_id), now(), store.schedule(farm_id))


def coop_rows(store, query=""):
    farms = store.find_farms(query) if query.strip() else store.farms()
    rows = []
    for f in farms:
        c = check(store, f["id"])
        rows.append({"farm": f, "decision": c.decision, "exclude": [s.animal for s in c.exclude]})
    return rows


def check_details(store, farm_id, lang):
    c = check(store, farm_id)
    return c, messages.collection_line(c, lang, now()), [
        {"animal": s.animal, "line": messages.milk_line(s, lang, now())} for s in c.exclude
    ]


def api_status(store, farm_id, lang):
    schedule = store.schedule(farm_id)
    names = [a["name"] for a in store.animals(farm_id)]
    return [
        {
            "animal": s.animal,
            "milk_status": s.milk.status.value,
            "milk_safe_from": s.milk.safe_from.isoformat() if s.milk.safe_from else None,
            "meat_status": s.meat.status.value,
            "meat_safe_from": s.meat.safe_from.isoformat() if s.meat.safe_from else None,
            "message": messages.milk_line(s, lang, now()),
        }
        for s in herd_status(names, store.treatments(farm_id), now(), schedule)
    ]


def dumps(obj):
    return json.dumps(obj) if obj is not None else ""
