"""
Layer 1 orchestration.

Flow per turn:
    raw text
      -> Gemma parse (constrained JSON)
      -> Python lexicon backstop unioned in
      -> Python decides what is still missing        [not the model]
      -> Gemma asks ONE follow-up question, max 3 rounds
      -> Python routes to a condition                [not the model]
      -> Python applies safety and herd rules        [not the model]
      -> Gemma rewords the finished verdict in Swahili

The anthrax check runs on EVERY turn, before elicitation. A herder who opens
with "my cow died in the night" gets the stop immediately, not after three
clarifying questions.
"""

import gemma
import router
import safety_rules
import vision
import vision_rules
from lexicon import scan, scan_all
from sw_numbers import parse_number
from schema import FIELD_LABELS_SW, REQUIRED_FIELDS

NUMERIC_FIELDS = ("animals_affected", "herd_size", "duration_days")

MAX_QUESTIONS = 3


class TriageSession:
    def __init__(self, max_questions=MAX_QUESTIONS):
        self.texts = []
        self.history = []          # [{"field", "question", "answer"}]
        self.parsed = None
        self.questions_asked = 0
        self.max_questions = max_questions
        self._pending_question = None
        self._pending_field = None
        self.observation = None      # last vision observation, or None
        self.image_meta = None       # {"body_part": ..., "band": ...}

    # -- public API ---------------------------------------------------------

    def attach_image(self, image, body_part="unspecified"):
        """
        Layer 3 entry point.

        Gemma looks at the photograph and reports observations from a closed
        vocabulary. Python maps those onto the same symptom tokens the text
        pipeline uses, so router.py and safety_rules.py need no knowledge that
        an image was ever involved.

        Returns the observation dict for display. Call submit() afterwards to
        get a verdict, or call it with '' to re-run on the image alone.
        """
        species = (self.parsed or {}).get("species", "unknown")
        obs = vision.observe(image, species=species, body_part=body_part)
        self.observation = obs

        if self.parsed is None:
            from schema import empty_parse
            self.parsed = empty_parse()

        # Fold visual findings into the parse.
        implied = vision_rules.symptoms_from(obs)
        if implied:
            self.parsed["symptoms"] = sorted(
                set(self.parsed.get("symptoms", [])) | implied
            )
        if vision_rules.sets_sudden_death(obs):
            self.parsed["sudden_death"] = True
        if vision_rules.sets_bleeding(obs):
            self.parsed["bleeding_from_orifices"] = True

        # Species-aware anaemia band. Python owns the threshold, not the model.
        band = vision_rules.anaemia_band(obs, self.parsed.get("species"))
        self.image_meta = {
            "body_part_requested": body_part,
            "body_part_visible": obs.get("body_part_visible"),
            "image_quality": obs.get("image_quality"),
            "band": band,
            "regions": obs.get("regions", []),
            "note": obs.get("note", ""),
        }
        return obs

    def submit(self, text):
        """
        Feed the herder's text. Returns either
          {"type": "question", "question_sw": ..., "field": ...}
        or
          {"type": "verdict", ...}
        """
        text = (text or "").strip()
        if not text:
            return self._verdict()

        if self._pending_question:
            self.history.append(
                {
                    "field": self._pending_field,
                    "question": self._pending_question,
                    "answer": text,
                }
            )
            self._pending_question = None
            self._pending_field = None

        self.texts.append(text)
        self.parsed = gemma.parse_description(
            self.texts[0], [(h["question"], h["answer"]) for h in self.history]
        )
        self._merge_lexicon()
        self._merge_vision()
        self._apply_answers()

        # Safety short-circuit. Never delay a zoonotic stop for a follow-up.
        triggered, _ = safety_rules.anthrax_triggered(self.parsed, self.texts)
        if triggered:
            return self._verdict()

        missing = self._missing_fields()
        if missing and self.questions_asked < self.max_questions:
            field = missing[0]
            question = gemma.elicit_question(
                field, FIELD_LABELS_SW[field], self.parsed
            )
            self.questions_asked += 1
            self._pending_question = question
            self._pending_field = field
            return {"type": "question", "question_sw": question, "field": field}

        return self._verdict()

    # -- internals ----------------------------------------------------------

    def _merge_lexicon(self):
        """Union Python's vernacular hits into the model's parse."""
        found = scan_all(self.texts)
        self.parsed["symptoms"] = sorted(
            set(self.parsed.get("symptoms", [])) | found["symptoms"]
        )
        if self.parsed.get("species", "unknown") == "unknown" and found["species"]:
            self.parsed["species"] = found["species"]
        if "sudden_death" in found["symptoms"]:
            self.parsed["sudden_death"] = True
        if "bleeding_from_orifices" in found["symptoms"]:
            self.parsed["bleeding_from_orifices"] = True

    def _merge_vision(self):
        """
        Re-union visual findings after every fresh model parse, because
        parse_description() rebuilds the dict from the text each turn and
        would otherwise silently drop everything the camera saw.
        """
        if not self.observation:
            return
        implied = vision_rules.symptoms_from(self.observation)
        if implied:
            self.parsed["symptoms"] = sorted(
                set(self.parsed.get("symptoms", [])) | implied
            )
        if vision_rules.sets_sudden_death(self.observation):
            self.parsed["sudden_death"] = True
        if vision_rules.sets_bleeding(self.observation):
            self.parsed["bleeding_from_orifices"] = True

    def _apply_answers(self):
        """
        Python asked for a specific field, so Python reads the answer to it.
        Runs after the model parse and only overwrites values still unset, so a
        correct model parse always wins; this is a floor, not a override.
        """
        for turn in self.history:
            field, answer = turn["field"], turn["answer"]
            if field in NUMERIC_FIELDS and self.parsed.get(field) is None:
                value = parse_number(answer)
                if value is not None:
                    self.parsed[field] = value
            elif field == "species" and self.parsed.get("species") in (None, "unknown"):
                found = scan(answer)["species"]
                if found:
                    self.parsed["species"] = found

    def _missing_fields(self):
        """Python owns this, per the architecture rule. The model never sets it."""
        missing = []
        for field in REQUIRED_FIELDS:
            value = self.parsed.get(field)
            if field == "species":
                if value in (None, "unknown"):
                    missing.append(field)
            elif value is None:
                missing.append(field)
        return missing

    def _verdict(self):
        parsed = self.parsed or {}
        condition, ranked = router.route(parsed, self.texts)
        safety = safety_rules.apply(condition, parsed, self.texts)

        verdict = {
            "type": "verdict",
            "parsed": parsed,
            "missing_fields": self._missing_fields() if self.parsed else REQUIRED_FIELDS,
            "condition_id": condition["id"] if condition else None,
            "condition_en": condition["name_en"] if condition else "No confident match",
            "condition_sw": condition["name_sw"] if condition else "Hakuna ulinganifu",
            "confidence_band": ranked[0]["band"] if ranked else "none",
            "matched_signs": ranked[0]["matched_signs"] if ranked else [],
            "alternatives": ranked[1:3],
            "safety": safety,
            "questions_asked": self.questions_asked,
            "mock_mode": gemma.MOCK_MODE,
            "vision": self._vision_block(),
        }
        verdict["explanation_sw"] = self._explain(verdict)
        return verdict

    def _vision_block(self):
        """Display payload for the image panel. Recomputes the band against the
        species we ended up with, which may have arrived after the photo."""
        if not self.observation:
            return None
        species = (self.parsed or {}).get("species", "unknown")
        band = vision_rules.anaemia_band(self.observation, species)
        return {
            "observations": self.observation.get("observations", []),
            "image_quality": self.observation.get("image_quality"),
            "body_part_visible": self.observation.get("body_part_visible"),
            "note": self.observation.get("note", ""),
            "error": self.observation.get("error"),
            "regions": self.observation.get("regions", []),
            "band": band,
            "symptoms_contributed": sorted(
                vision_rules.symptoms_from(self.observation)
            ),
        }

    def _explain(self, verdict):
        """
        Hand Gemma only the finished, Python-authored verdict. Note what is NOT
        sent: the raw zoonotic stop text. That string is displayed verbatim by
        the UI and never round-trips through the model.
        """
        safety = verdict["safety"]
        payload = {
            "_source_text": self.texts[0] if self.texts else "",
            "condition": verdict["condition_en"],
            "confidence": verdict["confidence_band"],
            "signs_observed": verdict["matched_signs"],
            "isolate_this_animal": safety["isolation_required"],
            "do_not_move_to_shared_grazing": safety["do_not_move"],
            "do_not_slaughter_or_sell": safety["do_not_slaughter"],
            "notifiable_disease_in_kenya": safety["notifiable_ke"],
            "what_to_do": safety["advice_en"],
            "who_to_contact": safety["escalation_en"],
            "herd_situation": safety["herd_detail"],
        }
        vblock = verdict.get("vision")
        if vblock and vblock.get("band") and vblock["band"].get("action_en"):
            payload["visual_check_result"] = vblock["band"]["action_en"]
        if safety["herd_instruction_en"]:
            payload["herd_instruction"] = safety["herd_instruction_en"]
        if safety["zoonotic_stop"]:
            # Tell the model a danger warning is being shown separately, so its
            # wording matches the tone, without giving it the text to rewrite.
            payload["danger_warning_shown_separately"] = (
                "A human-health danger warning about handling the carcass is "
                "displayed to the herder above your message. Match its urgency. "
                "Do not restate its instructions in detail."
            )
        return gemma.explain_verdict(payload)


def triage_once(text):
    """Convenience: no elicitation, straight to a verdict. Used by tests."""
    session = TriageSession(max_questions=0)
    return session.submit(text)