"""
Observations -> symptom tokens, and colour -> anaemia band.

Pure Python. No model call. This is the file that decides what a photograph
*means*, which is precisely why the model is not allowed anywhere near it.

Two mappings live here:

  1. OBSERVATION_TO_SYMPTOM — folds a visual finding into the same closed
     symptom vocabulary the text pipeline uses, so router.py needs no changes
     at all to accept image evidence.

  2. Anaemia banding — mucous membrane colour to an action threshold, for
     small ruminants (FAMACHA-style eyelid scoring) and for poultry (comb
     pallor and cyanosis).

Licence: the FAMACHA(c) colour chart is copyrighted and is not reproduced.
Mifugo maps a plain-language colour description to a band in code. Published
field evaluation of the chart on smallholder goats in Kenya (Ejlertsen et al.,
2006) reported false-negative rates of 0.7-1.6% and false-positive rates of
9.7-21.4% among trained human scorers. A phone camera under field lighting is
not better than a trained human eye, so Mifugo reports a band and an action,
never a precise score, and says so in the interface.
"""

# ---------------------------------------------------------------------------
# 1. Visual finding -> canonical symptom token
# ---------------------------------------------------------------------------

OBSERVATION_TO_SYMPTOM = {
    # Ruminant membrane pallor
    "conjunctiva_pink_white": ["pale_conjunctiva"],
    "conjunctiva_white": ["pale_conjunctiva"],
    # Poultry membrane pallor / cyanosis
    "comb_pale": ["pale_comb"],
    "comb_blue_purple": ["cyanotic_comb", "difficulty_breathing"],
    "comb_shrunken": ["pale_comb"],
    # Lesions
    "mouth_lesions_visible": ["mouth_lesions"],
    "foot_lesions_visible": ["foot_lesions"],
    "skin_lesions_visible": ["skin_lesions"],
    "skin_lesions_black_scab": ["skin_lesions"],
    "teat_lesions_visible": ["teat_lesions"],
    # Discharge
    "nasal_discharge_visible": ["nasal_discharge"],
    "ocular_discharge_visible": ["ocular_discharge"],
    "frothy_salivation_visible": ["salivation"],
    # Swelling
    "swollen_jaw_underside": ["bottle_jaw"],
    "swollen_lymph_node_visible": ["swollen_lymph_nodes"],
    "swollen_head_or_face": ["swollen_head"],
    "distended_left_flank": ["distended_left_flank"],
    "abdomen_distended": ["rapid_bloating"],
    # Droppings
    "diarrhoea_visible": ["diarrhoea"],
    "bloody_diarrhoea_visible": ["bloody_diarrhoea"],
    "green_white_droppings": ["green_white_droppings", "diarrhoea"],
    # Posture and condition
    "animal_recumbent": ["recumbent"],
    "visible_emaciation": ["weight_loss"],
    "ruffled_feathers": ["ruffled_feathers"],
    "twisted_neck_posture": ["twisted_neck"],
    # Carcass — routes straight into the zoonotic path
    "carcass_bloated": ["rapid_bloating", "sudden_death"],
    "blood_from_orifices_visible": ["bleeding_from_orifices"],
}


LESION_SITE = {
    "mouth_lesions_visible": "mouth",
    "foot_lesions_visible": "feet",
    "teat_lesions_visible": "teats",
    "skin_lesions_visible": "skin",
    "skin_lesions_black_scab": "skin",
    "swollen_head_or_face": "head",
}


def lesion_sites(observation):
    """
    Which anatomical sites carry lesions. This is the diagnostically loaded
    output of the vision layer: for FMD the weight is not that lesions exist
    but that they appear in the mouth AND on the feet or teats at once.
    Python combines this with the text; the model only reports location.
    """
    return sorted(
        {LESION_SITE[o] for o in observation.get("observations", []) if o in LESION_SITE}
    )


def symptoms_from(observation):
    """Returns a set of canonical symptom tokens implied by the observations."""
    found = set()
    for obs in observation.get("observations", []):
        found.update(OBSERVATION_TO_SYMPTOM.get(obs, []))
    return found


def sets_sudden_death(observation):
    obs = set(observation.get("observations", []))
    return "carcass_bloated" in obs or observation.get("body_part_visible") == "carcass"


def sets_bleeding(observation):
    return "blood_from_orifices_visible" in observation.get("observations", [])


# ---------------------------------------------------------------------------
# 2. Anaemia banding
# ---------------------------------------------------------------------------

RUMINANT_SPECIES = {"goat", "sheep"}
POULTRY_SPECIES = {"chicken", "poultry", "duck", "turkey"}

# Colour description -> (band label, action key). Bands, not scores.
CONJUNCTIVA_BANDS = {
    "conjunctiva_deep_red": ("healthy", "no_action"),
    "conjunctiva_red_pink": ("healthy", "no_action"),
    "conjunctiva_pink": ("borderline", "monitor"),
    "conjunctiva_pink_white": ("anaemic", "treat_now"),
    "conjunctiva_white": ("severely_anaemic", "treat_now_urgent"),
}

COMB_BANDS = {
    "comb_bright_red": ("healthy", "no_action"),
    "comb_pale": ("pale", "poultry_review"),
    "comb_shrunken": ("pale", "poultry_review"),
    "comb_blue_purple": ("cyanotic", "poultry_urgent"),
}

ACTION_TEXT = {
    "no_action": (
        "Membrane colour looks healthy. This sign alone does not call for "
        "treatment. Check the rest of the flock the same way.",
        "Rangi ya utando inaonekana ya kawaida. Dalili hii pekee haihitaji "
        "matibabu. Kagua kundi lote kwa njia hiyo hiyo.",
    ),
    "monitor": (
        "Borderline. Do not treat on this sign alone. Check this animal again in "
        "5 to 7 days, and check every other animal in the flock now.",
        "Kati na kati. Usitibu kwa dalili hii pekee. Mkague tena baada ya "
        "siku 5 hadi 7, na ukague kila mnyama mwingine sasa.",
    ),
    "treat_now": (
        "Pale membrane consistent with anaemia. Separate this animal, give clean "
        "water and shade, and take it to an agrovet or veterinarian for "
        "treatment. Check every other animal in the flock the same way.",
        "Utando uliopauka unaonyesha upungufu wa damu. Mtenge mnyama huyu, mpe "
        "maji safi na kivuli, na umpeleke kwa agrovet au daktari wa mifugo kwa "
        "matibabu. Kagua kila mnyama mwingine kwa njia hiyo hiyo.",
    ),
    "treat_now_urgent": (
        "Very pale membrane. Severe anaemia is likely and animals at this stage "
        "can die. Separate the animal, do not move it far, and get veterinary "
        "help today.",
        "Utando umepauka sana. Huenda ni upungufu mkubwa wa damu na wanyama "
        "katika hali hii wanaweza kufa. Mtenge, usimsafirishe mbali, na utafute "
        "msaada wa daktari wa mifugo leo.",
    ),
    "poultry_review": (
        "Pale comb in poultry has several causes. Separate this bird, check the "
        "droppings and the feed, keep clean water available, and take the bird "
        "to an agrovet or veterinarian.",
        "Upanga uliopauka kwa kuku unaweza kusababishwa na mambo mengi. Mtenge "
        "ndege huyu, kagua kinyesi na chakula, mpe maji safi, na umpeleke kwa "
        "agrovet au daktari wa mifugo.",
    ),
    "poultry_urgent": (
        "Blue or purple comb means the bird is not getting enough oxygen. This "
        "is an emergency measured in hours. Separate the bird and get help now.",
        "Upanga wa buluu au zambarau unamaanisha ndege hapati hewa ya kutosha. "
        "Hii ni dharura ya masaa. Mtenge ndege na utafute msaada sasa.",
    ),
}

# What we will and will not assess visually, by species.
UNSUPPORTED_SPECIES_NOTE = {
    "cattle": (
        "Eyelid colour scoring is validated for sheep and goats, not cattle. "
        "Mifugo will not give an anaemia band for cattle. The photograph is "
        "still used for lesions, swelling and discharge.",
        "Upimaji wa rangi ya kope umethibitishwa kwa kondoo na mbuzi, si "
        "ng'ombe. Mifugo haitatoa kipimo cha upungufu wa damu kwa ng'ombe. "
        "Picha bado inatumika kwa vidonda, uvimbe na majimaji.",
    ),
    "camel": (
        "Eyelid colour scoring is not validated for camels. Mifugo will not "
        "give an anaemia band. The photograph is still used for other signs.",
        "Upimaji wa rangi ya kope haujathibitishwa kwa ngamia. Mifugo "
        "haitatoa kipimo cha upungufu wa damu. Picha bado inatumika kwa "
        "dalili nyingine.",
    ),
}


def anaemia_band(observation, species):
    """
    Returns a dict or None. None means no colour assessment was made — either
    nothing relevant was visible, or the species is not supported for it.

    {
      "band": "anaemic",
      "action_key": "treat_now",
      "action_en": "...",
      "action_sw": "...",
      "basis": "conjunctiva_pink_white",
      "method": "eyelid_membrane" | "comb_wattle",
      "species_supported": True,
      "note_en": None
    }
    """
    obs = observation.get("observations", [])
    species = (species or "unknown").lower()

    conj = next((o for o in obs if o in CONJUNCTIVA_BANDS), None)
    comb = next((o for o in obs if o in COMB_BANDS), None)

    if conj:
        if species in RUMINANT_SPECIES:
            band, action = CONJUNCTIVA_BANDS[conj]
            return _band_block(band, action, conj, "eyelid_membrane", True, None)
        note = UNSUPPORTED_SPECIES_NOTE.get(species)
        if note:
            return _band_block(None, None, conj, "eyelid_membrane", False, note)
        return None

    if comb:
        if species in POULTRY_SPECIES:
            band, action = COMB_BANDS[comb]
            return _band_block(band, action, comb, "comb_wattle", True, None)
        return None

    return None


def _band_block(band, action_key, basis, method, supported, note):
    en, sw = ACTION_TEXT.get(action_key, ("", "")) if action_key else ("", "")
    return {
        "band": band,
        "action_key": action_key,
        "action_en": en or None,
        "action_sw": sw or None,
        "basis": basis,
        "method": method,
        "species_supported": supported,
        "note_en": note[0] if note else None,
        "note_sw": note[1] if note else None,
    }


# ---------------------------------------------------------------------------
# 3. Guidance shown before the shutter is pressed
# ---------------------------------------------------------------------------

CAPTURE_GUIDE = {
    "eyelid_conjunctiva": (
        "Pull the lower eyelid down gently. Fill the frame with the eye. "
        "Use natural daylight, not shade, not a flash.",
        "Vuta kope la chini taratibu. Jaza fremu na jicho. Tumia mwanga wa "
        "jua, si kivuli, wala si mweko wa kamera.",
    ),
    "comb_wattle": (
        "Photograph the comb and wattle from the side, in daylight. Hold the "
        "bird still and fill the frame with the head.",
        "Piga picha ya upanga na ndevu kutoka upande, kwa mwanga wa jua. "
        "Mshike ndege bila kutikisika na ujaze fremu na kichwa.",
    ),
    "mouth_or_gums": (
        "Open the mouth and photograph the gums and tongue in daylight.",
        "Fungua mdomo na upige picha ya ufizi na ulimi kwa mwanga wa jua.",
    ),
    "foot_or_hoof": (
        "Clean off loose mud first. Photograph between the claws.",
        "Ondoa matope kwanza. Piga picha katikati ya kwato.",
    ),
    "skin": (
        "Photograph the affected patch close up, in daylight, with some "
        "healthy skin visible beside it for comparison.",
        "Piga picha ya sehemu iliyoathirika kwa karibu, kwa mwanga wa jua, "
        "na ngozi nzuri ionekane kando kwa kulinganisha.",
    ),
    "teat_or_udder": (
        "Photograph the teats and udder from below or behind, in daylight. "
        "Wipe off mud first so sores are visible.",
        "Piga picha ya matiti na kiwele kutoka chini au nyuma, kwa mwanga wa "
        "jua. Ondoa matope kwanza ili vidonda vionekane.",
    ),
    "droppings": (
        "Photograph fresh droppings from directly above.",
        "Piga picha ya kinyesi kipya kutoka juu moja kwa moja.",
    ),
    "whole_animal": (
        "Stand back and photograph the whole animal from the side.",
        "Simama nyuma na upige picha ya mnyama mzima kutoka upande.",
    ),
    "carcass": (
        "Do not touch or move the carcass. Photograph from a distance.",
        "Usiguse wala usisogeze mzoga. Piga picha kutoka mbali.",
    ),
}

MODEL_UNAVAILABLE = (
    "The model is not running, so the photo was not analysed. Start Ollama, or "
    "switch on MOCK_MODE in the sidebar to see how this works without a model. "
    "Nothing is wrong with your photograph.",
    "Modeli haifanyi kazi, kwa hivyo picha haikuchambuliwa. Washa Ollama, au "
    "washa MOCK_MODE kwenye upande. Picha yako haina tatizo.",
)

QUALITY_RETRY = {
    "unusable": (
        "The photograph is not clear enough to read. Move into daylight, hold "
        "the phone steady, and fill the frame with the part you want checked.",
        "Picha haionekani vizuri. Nenda kwenye mwanga wa jua, shika simu bila "
        "kutetemeka, na ujaze fremu na sehemu unayotaka kukaguliwa.",
    ),
    "poor": (
        "The photograph is marginal. The reading below may be wrong. Retake it "
        "in better light if you can.",
        "Picha si nzuri sana. Jibu hapa chini linaweza kuwa si sahihi. Piga "
        "tena kwa mwanga bora ikiwezekana.",
    ),
}