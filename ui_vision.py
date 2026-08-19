"""
Streamlit rendering for the image path.

This file renders. It decides nothing. Every band, action string and threshold
comes from vision_rules.py.

The annotated overlay exists for one reason: a herder — and a judge — should be
able to see *where* the model was looking before trusting what it says. A
verdict with no visible basis is a black box. Boxes are drawn from normalised
0-1000 coordinates as CSS percentages so they hold their position on any
screen width, which is the whole trick.
"""

import base64
import io

import streamlit as st

import vision_rules

BODY_PART_LABELS = {
    "sw": {
        "eyelid_conjunctiva": "Kope la chini (mbuzi/kondoo)",
        "comb_wattle": "Upanga na ndevu (kuku)",
        "mouth_or_gums": "Mdomo au ufizi",
        "teat_or_udder": "Matiti au kiwele",
        "foot_or_hoof": "Mguu au kwato",
        "skin": "Ngozi",
        "droppings": "Kinyesi",
        "whole_animal": "Mnyama mzima",
        "carcass": "Mzoga",
    },
    "en": {
        "eyelid_conjunctiva": "Lower eyelid (goat/sheep)",
        "comb_wattle": "Comb and wattle (poultry)",
        "mouth_or_gums": "Mouth or gums",
        "teat_or_udder": "Teats or udder",
        "foot_or_hoof": "Foot or hoof",
        "skin": "Skin",
        "droppings": "Droppings",
        "whole_animal": "Whole animal",
        "carcass": "Carcass",
    },
}

BAND_STYLE = {
    "healthy": ("#1b5e20", "#e8f5e9"),
    "borderline": ("#e65100", "#fff3e0"),
    "pale": ("#e65100", "#fff3e0"),
    "anaemic": ("#b71c1c", "#ffebee"),
    "severely_anaemic": ("#7f0000", "#ffcdd2"),
    "cyanotic": ("#7f0000", "#ffcdd2"),
}

BAND_LABEL = {
    "sw": {
        "healthy": "Rangi ya kawaida",
        "borderline": "Kati na kati",
        "pale": "Imepauka",
        "anaemic": "Upungufu wa damu",
        "severely_anaemic": "Upungufu mkubwa wa damu",
        "cyanotic": "Ukosefu wa hewa — dharura",
    },
    "en": {
        "healthy": "Normal colour",
        "borderline": "Borderline",
        "pale": "Pale",
        "anaemic": "Anaemic",
        "severely_anaemic": "Severely anaemic",
        "cyanotic": "Oxygen deficit — emergency",
    },
}


def _b64(image_bytes):
    return base64.b64encode(image_bytes).decode("ascii")


def render_uploader(lang="sw"):
    """
    Draws the capture guidance + uploader. Returns (file, body_part) or
    (None, body_part).
    """
    sw = lang == "sw"
    labels = BODY_PART_LABELS[lang]
    keys = list(labels.keys())

    body_part = st.selectbox(
        "Unapiga picha ya nini?" if sw else "What are you photographing?",
        keys,
        format_func=lambda k: labels[k],
        key="mifugo_body_part",
    )

    guide = vision_rules.CAPTURE_GUIDE.get(body_part)
    if guide:
        st.caption(guide[1 if sw else 0] if isinstance(guide, tuple) else guide)

    file = st.file_uploader(
        "Pakia picha" if sw else "Upload a photo",
        type=["jpg", "jpeg", "png", "webp"],
        key="mifugo_image",
    )
    return file, body_part


def render_result(image_bytes, vblock, lang="sw"):
    """Draws the photo with overlay boxes, then the Python-decided band."""
    if not vblock:
        return
    sw = lang == "sw"

    if vblock.get("error") == "model_unavailable":
        st.warning(vision_rules.MODEL_UNAVAILABLE[0 if sw else 1])
        if image_bytes:
            st.image(image_bytes, use_container_width=True)
        return

    quality = vblock.get("image_quality")
    if quality in ("unusable", "poor"):
        msg = vision_rules.QUALITY_RETRY.get(quality)
        if msg:
            (st.error if quality == "unusable" else st.warning)(msg[1 if sw else 0])
        if quality == "unusable":
            if image_bytes:
                st.image(image_bytes, use_container_width=True)
            return

    if image_bytes:
        _render_overlay(image_bytes, vblock.get("regions") or [])

    obs = vblock.get("observations") or []
    if obs:
        st.caption(
            ("Kilichoonekana: " if sw else "Observed: ")
            + ", ".join(o.replace("_", " ") for o in obs)
        )

    band = vblock.get("band")
    if not band:
        return

    if not band.get("species_supported"):
        note = band.get("note_sw" if sw else "note_en")
        if note:
            st.info(note)
        return

    label = BAND_LABEL[lang].get(band["band"], band["band"])
    fg, bg = BAND_STYLE.get(band["band"], ("#333", "#f5f5f5"))
    action = band.get("action_sw" if sw else "action_en") or ""

    st.markdown(
        f"""
        <div style="background:{bg};border-left:6px solid {fg};
                    padding:14px 16px;border-radius:8px;margin:10px 0;">
          <div style="color:{fg};font-weight:700;font-size:1.05rem;
                      letter-spacing:.02em;">{label}</div>
          <div style="color:#222;margin-top:6px;line-height:1.45;">{action}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.caption(
        (
            "Kipimo hiki ni cha mwongozo, si nambari kamili. Rangi ya utando "
            "hupimwa kwa mbuzi na kondoo pekee, na hata wataalamu waliofunzwa "
            "hukosea mara kwa mara."
            if sw
            else "This is a guidance band, not a precise score. Membrane colour "
            "scoring is validated for sheep and goats only, and even trained "
            "human scorers show meaningful error rates."
        )
    )


def _render_overlay(image_bytes, regions):
    """0-1000 normalised boxes -> CSS percentages, so they hold on any width."""
    if not regions:
        st.image(image_bytes, use_container_width=True)
        return

    b64 = _b64(image_bytes if isinstance(image_bytes, bytes) else image_bytes.getvalue())

    boxes = []
    for r in regions:
        x0, y0, x1, y1 = r["box"]
        boxes.append(
            f"""<div style="position:absolute;
                 left:{x0/10:.2f}%;top:{y0/10:.2f}%;
                 width:{(x1-x0)/10:.2f}%;height:{(y1-y0)/10:.2f}%;
                 border:3px solid #ffb300;border-radius:4px;
                 box-shadow:0 0 0 2px rgba(0,0,0,.35);">
               <span style="position:absolute;top:-1.55rem;left:-3px;
                     background:#ffb300;color:#1a1a1a;font-size:.72rem;
                     font-weight:700;padding:2px 7px;border-radius:3px;
                     white-space:nowrap;">{r['label']}</span>
             </div>"""
        )

    st.markdown(
        f"""<div style="position:relative;width:100%;line-height:0;
                 border-radius:10px;overflow:hidden;">
              <img src="data:image/jpeg;base64,{b64}" style="width:100%;display:block;"/>
              {''.join(boxes)}
            </div>""",
        unsafe_allow_html=True,
    )