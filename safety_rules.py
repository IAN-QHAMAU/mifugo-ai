"""
Every safety instruction in Mifugo lives in this file, as a literal string or a
literal threshold. Nothing here is generated, templated by, or passed through
the model. Gemma may reword the explanation of a verdict downstream; it can
never author, edit, suppress or trigger one of these.

Grounding: Kenya Directorate of Veterinary Services guidance on anthrax
management and carcass disposal, and the WOAH Terrestrial Animal Health Code
chapter on anthrax (Bacillus anthracis).
"""

from lexicon import scan_all

# ---------------------------------------------------------------------------
# The zoonotic stop. Verbatim. Do not reformat, do not translate at runtime,
# do not pass through the model.
# ---------------------------------------------------------------------------

ANTHRAX_STOP = """\u26a0\ufe0f HATARI \u2014 USIFUNGUE MZOGA HUU

Do NOT open, skin, slaughter, eat, or sell this animal.
Do NOT let others handle the carcass.
Bury it deep, where it lies, with lime if available.
Notify the county veterinary officer immediately.

Sudden death with bleeding that does not clot may be anthrax,
which kills people who handle or eat infected meat."""

ANTHRAX_STOP_SW = """\u26a0\ufe0f HATARI \u2014 USIFUNGUE MZOGA HUU

USIFUNGUE, usichune, usichinje, usile, wala usiuze mnyama huyu.
Usiruhusu mtu yeyote kugusa mzoga huu.
Uzike mahali ulipo, shimo refu, na chokaa kama unayo.
Mjulishe ofisa wa mifugo wa kaunti mara moja.

Kifo cha ghafla pamoja na damu isiyoganda huenda ni kimeta,
ambayo huua watu wanaogusa au kula nyama iliyoathirika."""

ZOONOTIC_STOPS = {"anthrax_suspected": (ANTHRAX_STOP, ANTHRAX_STOP_SW)}


# ---------------------------------------------------------------------------
# Trigger. Two independent paths, OR'd. The model's booleans are one input,
# not the gate.
# ---------------------------------------------------------------------------

def anthrax_triggered(parsed, texts):
    """
    Returns (triggered: bool, reasons: list[str]).

    Path A: the model set sudden_death or bleeding_from_orifices.
    Path B: Python found the vernacular directly in the raw text.

    Path B exists because a parse failure must not be able to silence a
    zoonotic warning. If either path fires, the stop fires.
    """
    reasons = []

    if parsed.get("sudden_death"):
        reasons.append("model_flag:sudden_death")
    if parsed.get("bleeding_from_orifices"):
        reasons.append("model_flag:bleeding_from_orifices")
    if "sudden_death" in parsed.get("symptoms", []):
        reasons.append("model_symptom:sudden_death")
    if "bleeding_from_orifices" in parsed.get("symptoms", []):
        reasons.append("model_symptom:bleeding_from_orifices")

    found = scan_all(texts)
    if "sudden_death" in found["symptoms"]:
        reasons.append("keyword:sudden_death")
    if "bleeding_from_orifices" in found["symptoms"]:
        reasons.append("keyword:bleeding_from_orifices")
    if "anthrax_suspected" in found["condition_hints"]:
        reasons.append("keyword:named_anthrax")

    # Carcass handling language alone is not a diagnosis, but combined with a
    # death it means someone is about to touch or eat the animal.
    if found["carcass_context"] and any(r.endswith("sudden_death") for r in reasons):
        reasons.append("keyword:carcass_handling_intent")

    return bool(reasons), reasons


# ---------------------------------------------------------------------------
# Herd spread arithmetic. Layer 2 thresholds, wired in early because the
# fields are already parsed in Layer 1.
# ---------------------------------------------------------------------------

HERD_OUTBREAK = "outbreak"
HERD_SUSPECTED_CONTAGIOUS = "suspected_contagious"
HERD_INDIVIDUAL = "individual"
HERD_UNKNOWN = "unknown"

OUTBREAK_INSTRUCTION_EN = (
    "OUTBREAK. Isolate all affected animals now. Do not move any animal to "
    "shared grazing or shared water. Do not sell or slaughter any animal from "
    "this herd. Notify the county veterinary officer today."
)
OUTBREAK_INSTRUCTION_SW = (
    "MLIPUKO. Tenga wanyama wote walioathirika sasa. Usipeleke mnyama yeyote "
    "kwenye malisho au maji ya pamoja. Usiuze wala usichinje mnyama yeyote "
    "kutoka kundi hili. Mjulishe ofisa wa mifugo wa kaunti leo."
)


def herd_status(animals_affected, herd_size, duration_days):
    """
    1 animal, >5 days, no spread            -> individual treatment, monitor
    >=2 animals within 48h                  -> suspected contagious outbreak
    >=3 animals OR >10% of herd within 72h  -> OUTBREAK
    """
    if animals_affected is None:
        return HERD_UNKNOWN, "Number of affected animals not known."

    proportion = None
    if herd_size and herd_size > 0:
        proportion = animals_affected / herd_size

    within_72h = duration_days is not None and duration_days <= 3
    within_48h = duration_days is not None and duration_days <= 2

    if within_72h and (animals_affected >= 3 or (proportion is not None and proportion > 0.10)):
        detail = f"{animals_affected} animals"
        if proportion is not None:
            detail += f" ({proportion:.0%} of the herd)"
        return HERD_OUTBREAK, f"{detail} affected within 72 hours."

    if animals_affected >= 2 and within_48h:
        return HERD_SUSPECTED_CONTAGIOUS, (
            f"{animals_affected} animals affected within 48 hours."
        )

    if animals_affected == 1 and duration_days is not None and duration_days > 5:
        return HERD_INDIVIDUAL, (
            f"One animal only, {duration_days} days, no spread reported."
        )

    if animals_affected >= 2:
        return HERD_SUSPECTED_CONTAGIOUS, f"{animals_affected} animals affected."

    return HERD_INDIVIDUAL, "One animal affected."


# ---------------------------------------------------------------------------
# Escalation copy. Fixed strings keyed off conditions.json.
# ---------------------------------------------------------------------------

ESCALATION_TEXT = {
    "county_vet_immediate": (
        "Notify the county veterinary officer immediately, today.",
        "Mjulishe ofisa wa mifugo wa kaunti mara moja, leo.",
    ),
    "county_vet_within_24h": (
        "Report to the county veterinary officer within 24 hours.",
        "Ripoti kwa ofisa wa mifugo wa kaunti ndani ya saa 24.",
    ),
    "vet_within_24h": (
        "See a veterinarian within 24 hours. Treatment is time-critical.",
        "Mwone daktari wa mifugo ndani ya saa 24. Matibabu yanahitajika haraka.",
    ),
    "vet_or_agrovet_within_days": (
        "See a veterinarian or agrovet within the next few days.",
        "Mwone daktari wa mifugo au agrovet katika siku chache zijazo.",
    ),
    "emergency_hours": (
        "This is an emergency. Get help within hours, not days.",
        "Hii ni dharura. Tafuta msaada ndani ya masaa, si siku.",
    ),
    "no_match": (
        "Mifugo does not recognise this pattern. Contact a veterinarian or your "
        "county livestock extension officer for an assessment.",
        "Mifugo haitambui dalili hizi. Wasiliana na daktari wa mifugo au ofisa "
        "wa ugani wa mifugo wa kaunti yako kwa uchunguzi.",
    ),
}

NO_MATCH_ADVICE_EN = (
    "Mifugo covers six conditions and this description does not match any of "
    "them clearly. It will not guess. Separate the affected animal from the "
    "rest of the herd as a precaution, keep it eating and drinking if it will, "
    "and get a veterinary opinion."
)
NO_MATCH_ADVICE_SW = (
    "Mifugo inashughulikia magonjwa sita, na maelezo haya hayalingani na "
    "lolote kati yao waziwazi. Haitakisii. Tenga mnyama aliyeathirika na "
    "wengine kwa tahadhari, mpe chakula na maji akipenda, na utafute maoni ya "
    "daktari wa mifugo."
)


# ---------------------------------------------------------------------------
# Reporting. A notifiable disease carries a legal duty to inform county
# veterinary authorities. Herders often read "report" as "accuse" or "expect
# your animals to be destroyed", so the copy says what reporting actually is.
# ---------------------------------------------------------------------------

REPORTING_EXPLAINER_EN = (
    "This is a reportable disease in Kenya. Reporting means telling the county "
    "veterinary officer what you have seen so they can check nearby herds and "
    "advise you. It is not an accusation and it is not a fine. Officers can "
    "confirm the disease, advise on protecting the animals that are still "
    "healthy, and warn neighbours before it reaches them."
)
REPORTING_EXPLAINER_SW = (
    "Huu ni ugonjwa unaotakiwa kuripotiwa Kenya. Kuripoti maana yake ni "
    "kumwambia ofisa wa mifugo wa kaunti ulichokiona ili aweze kukagua makundi "
    "ya jirani na kukushauri. Si tuhuma, na si faini. Ofisa anaweza kuthibitisha "
    "ugonjwa, kukushauri kuhusu kulinda wanyama walio salama, na kuwatahadharisha "
    "majirani kabla ugonjwa uwafikie."
)


def apply(condition, parsed, texts):
    """
    Build the safety block for a verdict. `condition` is a dict from
    conditions.json, or None for the no-match path.

    Returns a dict. Every string in it is a literal from this module or from
    conditions.json. None of it came from the model.
    """
    triggered, reasons = anthrax_triggered(parsed, texts)

    status, detail = herd_status(
        parsed.get("animals_affected"),
        parsed.get("herd_size"),
        parsed.get("duration_days"),
    )

    block = {
        "zoonotic_stop": None,
        "zoonotic_stop_sw": None,
        "zoonotic_trigger_reasons": reasons,
        "isolation_required": False,
        "do_not_move": False,
        "do_not_slaughter": False,
        "notifiable_ke": False,
        "escalation_en": ESCALATION_TEXT["no_match"][0],
        "escalation_sw": ESCALATION_TEXT["no_match"][1],
        "herd_status": status,
        "herd_detail": detail,
        "herd_instruction_en": None,
        "herd_instruction_sw": None,
        "advice_en": NO_MATCH_ADVICE_EN,
        "advice_sw": NO_MATCH_ADVICE_SW,
        "reporting_explainer_en": None,
        "reporting_explainer_sw": None,
        "abstained": condition is None,
        "must_escalate": bool(condition and condition.get("must_escalate")),
    }

    if condition:
        block["isolation_required"] = condition["isolation_required"]
        block["do_not_move"] = condition["do_not_move"]
        block["do_not_slaughter"] = condition["do_not_slaughter"]
        block["notifiable_ke"] = condition["notifiable_ke"]
        block["advice_en"] = condition["advice_en"]
        block["advice_sw"] = None  # Gemma rewords advice_en downstream.
        esc = ESCALATION_TEXT.get(condition["escalation"])
        if esc:
            block["escalation_en"], block["escalation_sw"] = esc

    if block["notifiable_ke"]:
        block["reporting_explainer_en"] = REPORTING_EXPLAINER_EN
        block["reporting_explainer_sw"] = REPORTING_EXPLAINER_SW

    if status == HERD_OUTBREAK:
        block["herd_instruction_en"] = OUTBREAK_INSTRUCTION_EN
        block["herd_instruction_sw"] = OUTBREAK_INSTRUCTION_SW
        block["isolation_required"] = True
        block["do_not_move"] = True

    # The stop overrides everything, including a higher-scoring non-anthrax
    # condition. A false positive here costs one buried carcass. A false
    # negative can cost a life.
    if triggered:
        block["zoonotic_stop"], block["zoonotic_stop_sw"] = ZOONOTIC_STOPS[
            "anthrax_suspected"
        ]
        block["isolation_required"] = True
        block["do_not_move"] = True
        block["do_not_slaughter"] = True
        block["notifiable_ke"] = True
        block["escalation_en"], block["escalation_sw"] = ESCALATION_TEXT[
            "county_vet_immediate"
        ]
        block["must_escalate"] = True
        block["reporting_explainer_en"] = REPORTING_EXPLAINER_EN
        block["reporting_explainer_sw"] = REPORTING_EXPLAINER_SW

    return block