"""
Mifugo — Streamlit front end.

    streamlit run app.py

Design decisions worth knowing:

* Swahili is the default language, not a translation toggle bolted on. The
  person this is built for does not read English clinical terms.
* The layout is constrained to phone width. A herder holds a phone, and a demo
  that looks like a phone is honest about who uses it.
* The danger state is deliberately loud and takes the whole width. It is the
  one thing that must be unmissable at arm's length in daylight.
* Advice renders as numbered steps because "what do I do right now" is the
  actual question being asked.
* This file renders. It decides nothing. Every string with safety meaning comes
  from safety_rules.py or conditions.json.
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

import gemma
import ui_theme
import ui_vision
from triage import TriageSession

st.set_page_config(page_title="Mifugo", page_icon="\U0001f410", layout="centered",
                   initial_sidebar_state="expanded")

T = {
    "sw": {
        "tab_text": "Eleza",
        "tab_photo": "Picha",
        "empty_lead": "Andika chini kwa maneno yako mwenyewe, au ongeza picha. Jaribu mojawapo ya haya:",
        "ex1": "Ng\u2019ombe inatoa mate, haitaki kula, ina vidonda mdomoni.",
        "ex1w": "Ugonjwa unaoambukiza",
        "ex2": "Kuku wanakufa wengi, kinyesi cha kijani, shingo zimepinda.",
        "ex2w": "Kideri",
        "ex3": "Mbuzi ni dhaifu, kope la chini ni jeupe.",
        "ex3w": "Unaweza kuongeza picha ya jicho",
        "empty_hint": "Mifugo hutoa ushauri wa hatua, si dawa wala kipimo. Ikiwa haijui, itakwambia.",
        "ref": "Kumbukumbu",
        "stamped": "Imetolewa",
        "status_on": "Bila intaneti",
        "visual": "Ukaguzi wa picha",
        "report": "Kuhusu kuripoti",
        "abstain": "Haijatambuliwa",
        "prov1": "Gemma: lugha na picha pekee",
        "prov2": "Python: vipimo, kanuni, na maamuzi yote",
        "tagline": "Eleza hali ya mnyama wako kwa Kiswahili au Sheng. Utapata ushauri wa haraka \u2014 bila intaneti.",
        "prompt": "Eleza hali ya mnyama wako",
        "placeholder": "ng'ombe inatoa mate, haitaki kula\u2026",
        "thinking": "Inachambua\u2026",
        "danger_title": "HATARI KWA BINADAMU",
        "steps": "Fanya haya sasa",
        "who": "Mwone nani",
        "herd": "Hali ya kundi",
        "signs": "Dalili zilizoonekana",
        "confidence": "uhakika",
        "also": "Pia ilizingatiwa",
        "explain": "Maelezo",
        "new": "Anza upya",
        "demos": "Mifano ya majaribio",
        "lang": "Lugha",
        "how": "Nani aliamua nini",
        "gemma_did": "Gemma ilifanya lugha pekee",
        "python_did": "Python iliamua kila kitu kingine",
        "isolate": "MTENGE",
        "nomove": "USIPELEKE MALISHO YA PAMOJA",
        "noslaughter": "USICHINJE WALA USIUZE",
        "notifiable": "LAZIMA URIPOTI (KE)",
        "noisolate": "Hakuna haja ya kutenga",
    },
    "en": {
        "tab_text": "Describe",
        "tab_photo": "Photo",
        "empty_lead": "Type below in your own words, or add a photo. Try one of these:",
        "ex1": "Ng\u2019ombe inatoa mate, haitaki kula, ina vidonda mdomoni.",
        "ex1w": "Contagious disease",
        "ex2": "Kuku wanakufa wengi, kinyesi cha kijani, shingo zimepinda.",
        "ex2w": "Newcastle disease",
        "ex3": "Mbuzi ni dhaifu, kope la chini ni jeupe.",
        "ex3w": "You can add an eye photo",
        "empty_hint": "Mifugo gives action steps, never a drug or a dose. When it cannot tell, it says so.",
        "ref": "Record",
        "stamped": "Issued",
        "status_on": "Offline capable",
        "visual": "Visual check",
        "report": "About reporting",
        "abstain": "Not identified",
        "prov1": "Gemma: language and images only",
        "prov2": "Python: every threshold, rule and verdict",
        "tagline": "Describe your animal in Swahili or Sheng and get triage advice in seconds \u2014 with no internet.",
        "prompt": "Describe your animal's condition",
        "placeholder": "ng'ombe inatoa mate, haitaki kula\u2026",
        "thinking": "Analysing\u2026",
        "danger_title": "DANGER TO PEOPLE",
        "steps": "Do this now",
        "who": "Who to contact",
        "herd": "Herd situation",
        "signs": "Signs observed",
        "confidence": "confidence",
        "also": "Also considered",
        "explain": "Explanation",
        "new": "Start over",
        "demos": "Demo cases",
        "lang": "Language",
        "how": "Who decided what",
        "gemma_did": "Gemma did language only",
        "python_did": "Python decided everything else",
        "isolate": "ISOLATE",
        "nomove": "NO SHARED GRAZING",
        "noslaughter": "DO NOT SLAUGHTER OR SELL",
        "notifiable": "MUST REPORT (KE)",
        "noisolate": "No isolation needed",
    },
}

st.markdown(ui_theme.CSS, unsafe_allow_html=True)


DEMOS = [
    ("1", "Homa ya midomo na miguu", "Foot and mouth",
     "ng'ombe inatoa mate, haitaki kula, ina vidonda mdomoni, siku mbili sasa"),
    ("2", "Kifo cha ghafla", "Sudden death",
     "ng'ombe wangu wawili wamekufa ghafla usiku, damu inatoka puani na "
     "haigandi, nina ng'ombe kumi na nne"),
    ("3", "Upungufu wa damu", "Anaemia",
     "mbuzi wangu watatu wamedhoofika, macho ni meupe, taya limevimba, siku "
     "nane sasa, nina mbuzi ishirini"),
]


def reset():
    st.session_state.session = TriageSession()
    st.session_state.messages = []
    st.session_state.verdict = None
    st.session_state.elapsed = None
    st.session_state.image_bytes = None
    st.session_state.observation = None


for key, default in (("session", None), ("messages", []), ("verdict", None),
                     ("elapsed", None), ("lang", "sw")):
    if key not in st.session_state:
        st.session_state[key] = default
if st.session_state.session is None:
    reset()


def steps_from(text):
    if not text:
        return []
    parts = [p.strip() for p in text.replace("\n", " ").split(". ")]
    return [p if p.endswith(".") else p + "." for p in parts if len(p) > 2]


with st.sidebar:
    st.markdown("### Mifugo")
    st.session_state.lang = st.radio(
        T[st.session_state.lang]["lang"], ["sw", "en"],
        format_func=lambda x: "Kiswahili" if x == "sw" else "English",
        horizontal=True,
        index=0 if st.session_state.lang == "sw" else 1,
    )
    L = T[st.session_state.lang]

    mock = st.toggle("MOCK_MODE", value=gemma.MOCK_MODE)
    gemma.MOCK_MODE = mock

    MODELS = ["gemma4:e4b", "gemma4:e2b", "gemma3:4b", "gemma3:1b", "gemma3:270m"]
    gemma.MODEL = st.selectbox(
        "Model", MODELS,
        index=MODELS.index(gemma.MODEL) if gemma.MODEL in MODELS else 0,
        disabled=mock,
    )

    if mock:
        st.info("MOCK_MODE \u2014 no model calls")
    elif gemma.is_available():
        st.success("Ollama reachable")
    else:
        st.error(f"Ollama unreachable\n\n`{gemma.OLLAMA_URL}`")

    st.divider()
    st.markdown(f"**{L['demos']}**")
    for num, sw_label, en_label, text in DEMOS:
        label = f"{num}. {sw_label if st.session_state.lang == 'sw' else en_label}"
        if st.button(label, use_container_width=True, key=f"d{num}"):
            reset()
            st.session_state.pending = text
            st.rerun()

    if st.button(L["new"], use_container_width=True):
        reset()
        st.rerun()

L = T[st.session_state.lang]
sw_mode = st.session_state.lang == "sw"

st.markdown(
    ui_theme.masthead(
        L["tagline"],
        L["status_on"] if not gemma.MOCK_MODE else "MOCK",
    ),
    unsafe_allow_html=True,
)


def render(v):
    s = v["safety"]
    ts = time.localtime()
    ref = f"MFG-{time.strftime('%d%m', ts)}-{time.strftime('%H%M', ts)}"

    # The rupture. When a person could die, the document metaphor is abandoned.
    if s["zoonotic_stop"]:
        primary = s["zoonotic_stop_sw"] if sw_mode else s["zoonotic_stop"]
        head, _, rest = primary.partition("\n\n")
        st.markdown(
            ui_theme.alarm(L["danger_title"], head.strip(), rest.strip()),
            unsafe_allow_html=True,
        )

    stamps = ""
    if s["isolation_required"]:
        stamps += ui_theme.stamp(L["isolate"], "red")
    if s["do_not_move"]:
        stamps += ui_theme.stamp(L["nomove"], "red")
    if s["do_not_slaughter"]:
        stamps += ui_theme.stamp(L["noslaughter"], "red")
    if s["notifiable_ke"]:
        stamps += ui_theme.stamp(L["notifiable"], "amb")
    if not stamps:
        stamps = ui_theme.stamp(L["noisolate"], "grn")

    if s["abstained"]:
        title = L["abstain"]
        alt = v["condition_en"]
    else:
        title = v["condition_sw"] if sw_mode else v["condition_en"]
        alt = v["condition_en"] if sw_mode else v["condition_sw"]

    st.markdown(
        ui_theme.record(
            f"{L['ref']} {ref}",
            f"{L['stamped']} {time.strftime('%H:%M', ts)}",
            f"{v['confidence_band']} {L['confidence']}",
            title, alt, stamps,
        ),
        unsafe_allow_html=True,
    )

    if s["herd_instruction_en"]:
        st.markdown(
            ui_theme.alarm(
                L["herd"],
                (s["herd_instruction_sw"] if sw_mode else s["herd_instruction_en"]).split(".")[0],
                s["herd_instruction_sw"] if sw_mode else s["herd_instruction_en"],
            ),
            unsafe_allow_html=True,
        )

    advice = s["advice_sw"] if (sw_mode and s["advice_sw"]) else s["advice_en"]
    st.markdown(ui_theme.section(L["steps"]), unsafe_allow_html=True)
    for i, txt in enumerate(steps_from(advice), 1):
        st.markdown(ui_theme.step(i, txt), unsafe_allow_html=True)

    st.markdown(ui_theme.section(L["who"]), unsafe_allow_html=True)
    st.markdown(
        ui_theme.who(s["escalation_sw"] if sw_mode else s["escalation_en"]),
        unsafe_allow_html=True,
    )

    if s.get("reporting_explainer_en"):
        st.markdown(ui_theme.section(L["report"]), unsafe_allow_html=True)
        st.markdown(
            ui_theme.note(
                s["reporting_explainer_sw"] if sw_mode else s["reporting_explainer_en"]
            ),
            unsafe_allow_html=True,
        )

    signs = ", ".join(x.replace("_", " ") for x in v["matched_signs"]) or "\u2014"
    st.markdown(
        ui_theme.grid([(L["herd"], s["herd_detail"]), (L["signs"], signs)]),
        unsafe_allow_html=True,
    )

    st.markdown(
        ui_theme.provenance([L["prov1"], L["prov2"]]),
        unsafe_allow_html=True,
    )


if st.session_state.get("image_bytes") and st.session_state.get("verdict"):
    ui_vision.render_result(
        st.session_state.image_bytes,
        st.session_state.verdict.get("vision"),
        lang=st.session_state.lang,
    )

if st.session_state.verdict:
    render(st.session_state.verdict)


def handle(text):
    st.session_state.messages.append(("user", text))
    start = time.time()
    with st.spinner(L["thinking"]):
        result = st.session_state.session.submit(text)
    st.session_state.elapsed = time.time() - start
    if result["type"] == "question":
        st.session_state.messages.append(("assistant", result["question_sw"]))
    else:
        st.session_state.verdict = result


pending = st.session_state.pop("pending", None)
if pending:
    handle(pending)
    st.rerun()

tab_text, tab_photo = st.tabs([L["tab_text"], L["tab_photo"]])

with tab_text:
    if not st.session_state.verdict and not st.session_state.messages:
        st.markdown(
            ui_theme.empty_state(
                L["empty_lead"],
                [(L["ex1"], L["ex1w"]), (L["ex2"], L["ex2w"]), (L["ex3"], L["ex3w"])],
                L["empty_hint"],
            ),
            unsafe_allow_html=True,
        )
    for role, text in st.session_state.messages:
        with st.chat_message(role):
            st.write(text)

with tab_photo:
    up, body_part = ui_vision.render_uploader(st.session_state.lang)
    if up is not None:
        st.image(up, use_container_width=True)
        if st.button(
            "Chambua picha" if sw_mode else "Analyse photo",
            use_container_width=True,
        ):
            raw = up.getvalue()
            st.session_state.image_bytes = raw
            start = time.time()
            with st.spinner("Inaangalia picha\u2026" if sw_mode else "Reading the photo\u2026"):
                st.session_state.session.attach_image(raw, body_part=body_part)
                result = st.session_state.session.submit("")
            st.session_state.elapsed = time.time() - start
            st.session_state.verdict = result
            st.rerun()

typed = st.chat_input(L["placeholder"])
if typed:
    if st.session_state.verdict:
        reset()
    handle(typed)
    st.rerun()