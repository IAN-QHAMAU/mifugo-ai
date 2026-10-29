# Mifugo

**Offline livestock triage for Kenyan smallholders.** Describe a sick animal in Swahili or Sheng, or photograph the part you are worried about, and get a condition, an isolation instruction, a herd judgement, and an escalation threshold with no internet connection.

Gemma 4 E4B, served locally. Nine conditions across cattle, goats, sheep and poultry.

---

## Quickstart

```bash
pip install -r requirements.txt
ollama pull gemma4:e4b        # E2B also works, faster, slightly weaker vision
streamlit run app.py
```

No model available? Everything is exercisable without one:

```bash
MIFUGO_MOCK=1 streamlit run app.py
```

## The architecture rule

**Gemma understands language and images. Python owns every threshold, rule and verdict.**

This is division of labour by suitability, not distrust. No rules engine parses code-switched Sheng; no language model should decide whether a carcass is safe to open.

| Job | Owner | File |
|---|---|---|
| Messy Swahili/Sheng to structured facts | Gemma | `gemma.py` |
| One follow-up question when facts are missing | Gemma | `gemma.py` |
| Describing what is visible in a photograph | Gemma | `vision.py` |
| Rewording a finished verdict in warm Swahili | Gemma | `gemma.py` |
| Vernacular keyword backstop | Python | `lexicon.py` |
| Symptoms + lesion sites to candidate condition | Python | `router.py` |
| Colour description to anaemia band | Python | `vision_rules.py` |
| Isolation, movement, slaughter, reporting rules | Python | `safety_rules.py` |
| The zoonotic danger stop | Python, verbatim | `safety_rules.py` |

Three consequences, each deliberate:

1. **The model cannot silence a warning.** The anthrax trigger has two independent paths OR'd together - Gemma's extracted booleans, and a pure-Python scan of the raw text. If the model fails entirely, the keyword path still fires.
2. **The model cannot author a safety instruction.** Every such string is a literal in `safety_rules.py`. Gemma is told a warning is being displayed and asked to match its urgency; it is never handed the text to rewrite.
3. **The model cannot emit an unknown token.** Both the text parse and the vision observation are constrained to closed enums enforced during decoding.

## No drug names, on purpose

No advice string in this repository names a drug, a drug class, or a dose. Antimicrobial and anthelmintic misuse in Kenyan livestock keeping is a real problem, and milk and meat withdrawal periods cannot be reasoned about without knowing what the animal was already given. Output is restricted to action classes: isolate, separate, water, bed, do not move, do not slaughter, report, transport, seek help.

## Evaluation

```bash
MIFUGO_MOCK=1 python evaluate.py     # or without MOCK against the live model
```

Top-1 accuracy is the wrong metric for triage. A system that names the wrong condition but escalates has failed gracefully; one that names the right condition and says "monitor at home" has failed dangerously. So the headline metrics are, in order:

1. **Zoonotic recall** - of cases where a human-health stop must fire, how many fired. Target 100%; anything less is a defect.
2. **Escalation recall** - of cases that must reach a vet or county officer, how many did.
3. **Abstain precision** - of out-of-scope cases, how many refused to guess.
4. Condition accuracy - reported last, on purpose.

Current: **3/3 · 9/9 · 3/3 · 9/11**, one false stop (documented and retained).

## Demo script

1. `ng'ombe inatoa mate, haitaki kula, ina vidonda mdomoni` - one clarifying question, then FMD with isolation and movement instructions.
2. `kuku wangu wanakufa wengi, kinyesi cha kijani, shingo zimepinda` - Newcastle (kideri), notifiable, movement stopped, reporting explained.
3. **Photo** - open the camera panel, choose *Lower eyelid (goat/sheep)*, upload, analyse. Overlay boxes on the membrane, band card: **Anaemic, separate, water, take to an agrovet.**
4. **The guard** - same photo, tell it the animal is a cow. Mifugo refuses to give a band and says why. Fifteen seconds that show the system knows the limits of its own method.
5. **The abstain case** - `ng'ombe wangu ana wasiwasi kidogo, sijui shida ni nini` "I cannot tell from this," plus safe interim advice and what to watch for.
6. `ng'ombe amekufa ghafla usiku, damu inatoka puani` - full-width red stop.
7. **Turn off the network. Re-run step 1.** It still works.

Step 7 is the Track 3 proof. Show the airplane-mode toggle on screen *before* typing.

## Files

```
app.py              Streamlit UI. Renders; decides nothing.
ui_vision.py        Camera panel, annotated overlay, band card.
triage.py           Orchestration. Parse, elicit, route, safety, explain.
gemma.py            The only file that talks to the model. Three language jobs.
vision.py           Gemma job D: image to constrained observations.
vision_schema.py    Closed observation vocabulary + JSON schema.
vision_rules.py     DETERMINISTIC. Observation to symptoms; colour to band.
router.py           DETERMINISTIC. Symptoms + lesion sites to condition.
safety_rules.py     DETERMINISTIC. Every safety literal lives here.
lexicon.py/.json    Vernacular keyword backstop. The model-failure safety net.
schema.py           Canonical symptom vocabulary and parse schema.
conditions.json     Nine conditions. Hand-written, sourced, no drug names.
vignettes.json      15 cases with known outcomes.
evaluate.py         Recall-first evaluation harness.
sw_numbers.py       Swahili numeral parsing.
```

## Known limits

Validated on Swahili and code-switched Sheng **not** on Somali, Turkana, Borana or Maa, which are the languages of the pure pastoralist counties where livestock is the largest share of household wealth. That is the primary generalisation requirement and we do not claim it.

Nine conditions only; anything else abstains. Camel disease absent by design. Eyelid colour banding is validated for sheep and goats only and reports a band, not a score published field data shows 9.7 to 21.4% false positives among trained human scorers. The FAMACHA chart is copyrighted and is not reproduced here. The condition table is hand-written from published guidance and has not been validated against field outcomes.

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `MIFUGO_MOCK` | `0` | `1` runs the whole app with no model |
| `MIFUGO_MODEL` | `gemma4:e4b` | Ollama model tag |
| `MIFUGO_OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama endpoint |
| `MIFUGO_NUM_CTX` | `8192` | Context window (Ollama defaults far lower) |
