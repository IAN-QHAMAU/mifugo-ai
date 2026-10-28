"""
Mifugo on Streamlit, for hosting on Streamlit Community Cloud.

    streamlit run app.py

Same engine, same sentences, same save rules as the FastAPI app
(python -m mifugo): both are thin skins over mifugo/views.py. This file
renders and stores session state; it decides nothing.

On Streamlit Cloud, put MIFUGO_GEMMA_API_KEY in the app's secrets to let
Gemma read labels. Without a key the app runs in manual-entry mode: the
farmer types the period from the box and the Swahili word lists read the
message.
"""

import html
import os
import uuid
from datetime import datetime, time

import streamlit as st


def _secrets_to_env():
    """Copy MIFUGO_* secrets into the environment before mifugo.config reads it."""
    try:
        for key, value in st.secrets.items():
            if key.startswith("MIFUGO_") and isinstance(value, (str, int, float)):
                os.environ.setdefault(key, str(value))
    except Exception:
        pass   # no secrets file: a local run


_secrets_to_env()
if "MIFUGO_BACKEND" not in os.environ and os.environ.get("MIFUGO_GEMMA_API_KEY"):
    os.environ["MIFUGO_BACKEND"] = "gemma_api"

from mifugo import config, demo, llm, views  # noqa: E402  (config reads the environment)
from mifugo.clock import NAIROBI, now  # noqa: E402
from mifugo.label_reader import LabelReading, read_label  # noqa: E402
from mifugo.log_parser import parse  # noqa: E402
from mifugo.store import Store  # noqa: E402
from mifugo.ui_text import T  # noqa: E402
from mifugo.withdrawal import Withdrawal  # noqa: E402

st.set_page_config(page_title="Mifugo", page_icon="\U0001f404", layout="centered")

CSS = """
<style>
.cow { border: 1px solid #d9d3c4; border-left: 8px solid #1e7a3c; border-radius: 12px;
       padding: 0.6rem 0.9rem; margin: 0.5rem 0; background: #fff; }
.cow.stop { border-left-color: #b3261e; background: #fbe7e5; }
.cow.unknown { border-left-color: #8a5a00; border-left-style: dashed; background: #fff1d6; }
.cow .name { font-weight: 800; font-size: 1.1rem; display: flex; justify-content: space-between; }
.cow .milk { font-weight: 700; margin: 0.3rem 0; }
.cow .meat { font-size: 0.85rem; color: #5c645e; }
.verdict.ok { color: #1e7a3c; font-weight: 700; }
.verdict.stop { color: #b3261e; font-weight: 700; }
.verdict.unknown { color: #8a5a00; font-weight: 700; }
.banner { font-weight: 800; padding: 0.8rem 1rem; border-radius: 12px; }
.banner.ok { background: #e5f3e8; color: #1e7a3c; border: 2px solid #1e7a3c; }
.banner.stop { background: #fbe7e5; color: #b3261e; border: 2px solid #b3261e; }
blockquote.quote { margin: 0.2rem 0 0.6rem; padding: 0.3rem 0.6rem; border-left: 4px solid #1f3a2e;
                   background: #f1efe8; font-family: monospace; font-size: 0.85rem; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


@st.cache_resource
def get_store():
    s = Store()
    if not s.farms() and os.environ.get("MIFUGO_AUTO_DEMO", "1") == "1":
        demo.seed(s)
    return s


@st.cache_data(ttl=30)
def model_label():
    b = llm.backend()
    return b.describe(), b.available()


def esc(text):
    return html.escape(text or "")


store = get_store()
ss = st.session_state
ss.setdefault("lang", "sw")
ss.setdefault("view", "board")

# ---------------------------------------------------------------------------
# Sidebar: language, role, farm
# ---------------------------------------------------------------------------

with st.sidebar:
    ss.lang = st.radio("Lugha / Language", ["sw", "en"], format_func=str.upper, horizontal=True,
                       index=["sw", "en"].index(ss.lang))
t = T[ss.lang]
lang = ss.lang

with st.sidebar:
    role = st.radio(t["role"], ["farmer", "clerk"], format_func=lambda r: t[r])
    label, up = model_label()
    st.caption(("\U0001f7e2 " if up else "\U0001f534 ") + label)
    if not store.farms() and st.button(t["demo"]):
        demo.seed(store)
        st.rerun()
    with st.expander(t["new_farm"]):
        with st.form("new_farm", clear_on_submit=True):
            name = st.text_input(t["name"])
            phone = st.text_input(t["phone"])
            member = st.text_input(t["member"])
            milking = st.text_input(t["milking"], "06:00,17:00")
            if st.form_submit_button(t["create"]) and name.strip():
                try:
                    ss.farm_id = store.create_farm(name, phone, member, milking)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

st.title("Mifugo")
st.caption(t["tagline"])


# ---------------------------------------------------------------------------
# Farmer
# ---------------------------------------------------------------------------

def cow_card(b):
    clock = f"<span>{b['hours_left']} h</span>" if b["hours_left"] is not None else ""
    keep = f"<div>{esc(b['keep_apart'])}</div>" if b["keep_apart"] else ""
    st.markdown(
        f'<div class="cow {b["level"]}"><div class="name"><span>{esc(b["animal"])}</span>{clock}</div>'
        f'<div class="milk">{esc(b["milk"])}</div>{keep}'
        f'<div class="meat"><b>{esc(t["meat"])}:</b> {esc(b["meat"])}</div></div>',
        unsafe_allow_html=True,
    )
    if b["fix_product"]:
        with st.expander(t["confirm_period"]):
            with st.form(f"fix_{b['animal']}"):
                kind = st.selectbox(t["kind_period"], ["period", "zero"],
                                    format_func=lambda k: t["kind_" + k], key=f"fk_{b['animal']}")
                value = st.text_input(t["value"], key=f"fv_{b['animal']}")
                unit = st.selectbox(" ", ["days", "hours", "milkings"],
                                    format_func=lambda u: t["unit_" + u], key=f"fu_{b['animal']}")
                who = st.text_input(t["confirmed_by"], key=f"fw_{b['animal']}")
                if st.form_submit_button(t["save"]):
                    if not who.strip():
                        st.error(t["error_confirmed"])
                    else:
                        try:
                            views.confirm_period(store, b["fix_product"], kind, value, unit, who)
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))


def board_view(farm_id):
    farm, schedule, names, treatments, board = views.farm_board(store, farm_id, lang)
    st.caption(f"{farm['member_no']} · {t['milking']}: {schedule.display()}")
    if farm["demo"]:
        st.info(demo.DEMO_NOTE[lang])
    for message in ss.pop("sms", []):
        st.success(f"**{t['sms']}**\n\n{message}\n\n_{t['sms_note']}_")
    st.subheader(t["herd"])
    for b in board:
        cow_card(b)
    with st.expander(t["add_cow"]):
        with st.form("add_cow", clear_on_submit=True):
            cow = st.text_input(t["name"])
            if st.form_submit_button(t["add"]) and cow.strip():
                if cow.strip() not in names:
                    store.add_animal(farm_id, cow)
                st.rerun()
    history = store.treatment_rows(farm_id)[:8]
    if history:
        st.subheader(t["history"])
        for h in history:
            line = f"**{h['animal']}** · {h['product']} · {h['given_at'].replace('T', ' ')[:16]}"
            if h["reported"]:
                line += f"  \n_“{h['reported']}”_"
            if h["source"] == "manual" and h["confirmed_by"]:
                line += f"  \n✓ {h['confirmed_by']}"
            st.markdown(line)


def ask_view(farm_id):
    with st.form("ask"):
        text = st.text_input(t["ask"], placeholder=t["ask_ph"])
        asked = st.form_submit_button(t["ask_btn"])
    if asked and text.strip():
        result = views.answer(store, farm_id, text, lang)
        if result["intent"] == "log_treatment":
            ss.log_text = text
            ss.view = "log"
            ss.notice = t["looks_like_log"]
            st.rerun()
        st.markdown(f"_“{esc(text)}”_", unsafe_allow_html=True)
        for line in result["lines"]:
            st.markdown(f'<p class="verdict {line["level"]}">{esc(line["text"])}</p>', unsafe_allow_html=True)


def withdrawal_inputs(prefix, w, units, kinds):
    kind = st.selectbox(t["milk_w"] if prefix == "milk" else t["meat_w"], kinds,
                        index=kinds.index(w["kind"]) if w["kind"] in kinds else kinds.index("unknown"),
                        format_func=lambda k: t["kind_" + {"not_for_lactating": "nfl"}.get(k, k)],
                        key=f"{prefix}_kind")
    cols = st.columns(2)
    value = cols[0].text_input(t["value"], w["value"], key=f"{prefix}_value")
    unit = cols[1].selectbox(" ", units, index=units.index(w["unit"]) if w["unit"] in units else 0,
                             format_func=lambda u: t["unit_" + u], key=f"{prefix}_unit")
    if w["quote"]:
        st.markdown(f'<blockquote class="quote">{esc(w["quote"])}</blockquote>', unsafe_allow_html=True)
    return {"kind": kind, "value": value, "unit": unit, "quote": w["quote"]}


def log_view(farm_id):
    names = [a["name"] for a in store.animals(farm_id)]
    if "notice" in ss:
        st.info(ss.pop("notice"))

    if "draft" not in ss:
        with st.form("read"):
            photo = st.file_uploader(t["photo"], type=["jpg", "jpeg", "png", "webp"], help=t["photo_hint"])
            text = st.text_area(t["words"], ss.pop("log_text", ""), placeholder=t["words_ph"])
            go = st.form_submit_button(t["read"], type="primary")
        if not model_label()[1]:
            st.caption(t["no_model"])
        if go:
            image_path, reading = "", None
            if photo is not None:
                data = photo.getvalue()
                config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
                image_path = f"{uuid.uuid4().hex}.jpg"
                (config.UPLOAD_DIR / image_path).write_bytes(data)
                with st.spinner("Gemma…"):
                    reading = read_label(data)
            if reading is None:
                reading = LabelReading("", [], Withdrawal.unknown(), Withdrawal.unknown(), [], None,
                                       source="manual")
            parsed = parse(text, names, now()) if text.strip() else None
            form = views.draft(reading, parsed)
            ss.draft = {
                "form": form, "issues": reading.issues, "read_ok": reading.raw is not None and not reading.issues,
                "image_path": image_path, "model_reply": reading.raw,
                "unmatched": parsed.unmatched if parsed else [], "text": text,
                "original": {"milk": dict(form["milk"]), "meat": dict(form["meat"])},
            }
            st.rerun()
        return

    d = ss.draft
    form = d["form"]
    st.subheader(t["confirm_title"])
    if d["image_path"]:
        st.image(str(config.UPLOAD_DIR / d["image_path"]))
        st.markdown(f"**{t['gemma_read']}**")
        if d["issues"]:
            st.warning(f"**{t['issues']}:**\n\n" + "\n".join(f"- {i}" for i in d["issues"]))
        elif d["read_ok"]:
            st.success(f"{t['python_checked']}: {t['checks_ok']}")

    product = st.text_input(t["product"], form["product_name"] or form["product_mention"])
    milk = withdrawal_inputs("milk", form["milk"], ["hours", "days", "milkings"],
                             ["period", "zero", "not_for_lactating", "unknown"])
    meat = withdrawal_inputs("meat", form["meat"], ["days", "hours"], ["period", "zero", "unknown"])
    confirmed_by = st.text_input(t["confirmed_by"], help=t["confirmed_by_hint"])

    animals = st.multiselect(t["animals"], names, default=[a for a in form["animals"] if a in names])
    new_animals = []
    if d["unmatched"]:
        st.caption(f"{t['not_in_herd']}: {', '.join(d['unmatched'])}")
        new_animals = st.multiselect(t["add_as_new"], d["unmatched"])

    given = datetime.fromisoformat(form["given_at"])
    cols = st.columns(2)
    day = cols[0].date_input(t["date"], given.date(), max_value=now().date())
    clock = cols[1].time_input(t["time"], time(given.hour, given.minute), step=60)
    if form["assumed"]:
        st.caption(t["time_assumed"])

    current = {
        **form, "product_name": product, "milk": milk, "meat": meat, "animals": animals + new_animals,
        "given_at": datetime.combine(day, clock, tzinfo=NAIROBI).strftime("%Y-%m-%dT%H:%M"),
    }
    preview = views.preview(current, store.schedule(farm_id), lang)
    if preview:
        st.markdown(f"**{t['preview']}**")
        for p in preview:
            st.markdown(f'<p class="verdict {p["level"]}">{esc(p["milk"])}</p>'
                        f'<p class="meat">{esc(p["meat"])}</p>', unsafe_allow_html=True)

    cols = st.columns(2)
    if cols[0].button(t["save"], type="primary"):
        current["animals"] = animals
        result = views.save_treatment(
            store, farm_id, current, confirmed_by=confirmed_by, image_path=d["image_path"],
            original=d["original"], model_reply=d["model_reply"], text=d["text"], new_animals=new_animals,
        )
        if result.error:
            st.error(t.get(result.error, result.error))
        else:
            ss.sms = views.sms_for(store, farm_id, set(result.logged), lang)
            del ss.draft
            ss.view = "board"
            st.rerun()
    if cols[1].button(t["cancel"]):
        del ss.draft
        st.rerun()


def farmer():
    farms = store.farms()
    if not farms:
        st.info(t["demo"])
        return
    ids = [f["id"] for f in farms]
    if ss.get("farm_id") not in ids:
        ss.farm_id = min(ids)   # the first farm registered on this device
    by_id = {f["id"]: f["name"] for f in farms}
    ss.farm_id = st.selectbox(t["farm"], ids, index=ids.index(ss.farm_id), format_func=by_id.get)

    views_ = {"board": t["herd"], "log": t["log"], "ask": t["ask"]}
    ss.view = st.radio(" ", list(views_), format_func=views_.get, horizontal=True,
                       index=list(views_).index(ss.view), label_visibility="collapsed")
    {"board": board_view, "log": log_view, "ask": ask_view}[ss.view](ss.farm_id)


# ---------------------------------------------------------------------------
# Co-op clerk
# ---------------------------------------------------------------------------

def clerk():
    st.header(t["coop_title"])
    query = st.text_input(t["search"])
    rows = views.coop_rows(store, query)
    to_test = sum(1 for r in rows if r["decision"] == "test")
    st.metric(t["to_test"], f"{to_test} {t['of']} {len(rows)}")
    for r in rows:
        f = r["farm"]
        flag = "\U0001f534" if r["decision"] == "test" else "\U0001f7e2"
        with st.expander(f"{flag} {f['name']}  ·  {f['member_no']}"):
            check, verdict, details = views.check_details(store, f["id"], lang)
            level = "stop" if check.decision == "test" else "ok"
            st.markdown(f'<div class="banner {level}">{esc(verdict)}</div>', unsafe_allow_html=True)
            for item in details:
                st.markdown(f"**{item['animal']}**: {item['line']}")
            with st.form(f"check_{f['id']}"):
                who = st.text_input(t["name"], key=f"clerk_{f['id']}")
                if st.form_submit_button(t["log_check"]):
                    store.log_check(f["id"], views.check(store, f["id"]), who)
                    st.rerun()
    recent = store.checks(10)
    if recent:
        st.subheader(t["recent_checks"])
        for k in recent:
            st.markdown(f"{k['checked_at'].replace('T', ' ')[:16]} · {k['farm']} · "
                        f"**{k['decision']}**" + (f" · {k['clerk']}" if k["clerk"] else ""))


if role == "farmer":
    farmer()
else:
    clerk()
st.divider()
st.caption(t["footer"])
