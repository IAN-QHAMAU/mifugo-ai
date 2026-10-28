# Mifugo

**Can I sell this cow's milk today?**

A Kenyan dairy farmer treats a cow for mastitis. The withdrawal period, how
long her milk must stay out of the can, is printed on the box in small
English type. Two days later someone else does the milking, the treated cow's
milk goes into the shared can, and the co-op's residue test rejects all of it.
Or nobody tests it, and the residues reach the people who drink it.

Mifugo closes that gap. Photograph the medicine box, say in Swahili or Sheng
which cow and when ("nimemdunga Njeri sindano jana jioni"), and Mifugo tells
the farmer exactly which milking her milk can be sold from. At the collection
point, the co-op clerk sees which deliveries carry that risk and tests those
cans first, instead of guessing.

> This branch is a rebuild. Version 1 was a general livestock-triage app. Why
> it was replaced is in [docs/RETRO.md](docs/RETRO.md).

---

## Why this problem

| Finding | Source |
|---|---|
| 63% of small-scale dairy farmers studied did not observe withdrawal periods; milk from Kenyan smallholders has shown residues above the maximum limits | [Springer, 2026](https://link.springer.com/article/10.1186/s42269-026-01393-z) |
| In one Kenyan study area, 5,182.75 litres of milk a month were rejected for antibiotic residues before farmers were trained | [ScienceDirect, 2024](https://www.sciencedirect.com/science/article/pii/S2352771424001691) |
| Of antibiotics dispensed without a prescription in one study, 42.7% were dispensed by agrovet attendants | [Frontiers in Veterinary Science, 2025](https://www.frontiersin.org/journals/veterinary-science/articles/10.3389/fvets.2025.1707434/full) |

What is **not** yet known, and must be tested before anyone builds a company on
this: whether farmers will log treatments honestly when logging costs them
milk sales, and whether co-ops will pay for targeted testing. See
[docs/WRITEUP.md](docs/WRITEUP.md#what-we-have-not-proven).

## How it works

```
photo of the box ──► Gemma reads the label ──► Python checks the evidence ─┐
                                                                           ├─► withdrawal engine ──► "USIUZE maziwa ya Njeri.
"Njeri, sindano, jana jioni" ──► Gemma reads the words ─┐                  │    (pure Python)         Yanaweza kuuzwa kuanzia
                       Swahili word lists read them too ┴─► latest time ───┘                          ukamuaji wa Jumamosi..."
```

**Gemma reads. Python guarantees.**

| Job | Who | File |
|---|---|---|
| Read the withdrawal statements off a photo of the packaging | Gemma (vision) | `mifugo/label_reader.py` |
| Check that the printed words actually support the number read | Python | `mifugo/label_reader.py` |
| Understand a Swahili / Sheng / English message: intent, cows, time | Gemma | `mifugo/log_parser.py` |
| Read cow names and time phrases directly, as a backstop | Python | `mifugo/log_parser.py`, `mifugo/timewords.py` |
| Turn "jana jioni" into a timestamp | Python | `mifugo/timewords.py` |
| Compute the first saleable milking, per cow, across all treatments | Python | `mifugo/withdrawal.py` |
| Every sentence that tells someone to sell or not sell | Python literals | `mifugo/messages.py` |

Gemma is what makes the product possible: without it, the farmer has to find
and type a period from small print, which is exactly the step that fails
today. Python is what makes it safe to rely on.

### The rules that keep it safe

1. **The evidence rule.** Gemma must copy the exact printed words of each
   withdrawal statement. Python accepts a period only if the number is the
   first number printed after the word *milk* (or *meat*), the unit is printed
   with it, the value is plausible, and, where several species are listed, the
   number comes from the cattle line. A model that swaps the milk and meat
   numbers, or reports the sheep period, is refused.
2. **Never a default.** If the period was not read, or the label says *not for
   lactating animals*, the verdict is DO NOT SELL with no end date until a
   person enters a period and says who confirmed it.
3. **Latest plausible time.** "Jana jioni" means 20:59 yesterday, not 16:00.
   No time at all means now. When Gemma and the word lists disagree, the later
   time wins. Every guess can only push the end date later.
4. **Real milkings.** A period in hours or days ends at the first scheduled
   milking at or after it. A period printed in *milkings* is counted in the
   farm's own milkings.
5. **Last dose, worst case.** Each dose is its own treatment; a cow's status is
   the latest end across all of them, and one unconfirmed treatment blocks sale.

Mifugo never recommends a medicine or a dose. It only reads what was already given.

---

## Run it

```bash
pip install -r requirements.txt
ollama pull gemma4:e4b          # Gemma on this machine; no internet needed after this
python -m mifugo                # http://127.0.0.1:8000
```

Open it on a phone on the same Wi-Fi with `MIFUGO_HOST=0.0.0.0 python -m mifugo`.
On the home page, **Load demo farms** creates three farms with treatments in
every state. Demo product names and periods are illustrative, and the app says so.

| Variable | Default | Purpose |
|---|---|---|
| `MIFUGO_BACKEND` | `ollama` | `ollama` (offline), `gemma_api` (hosted Gemma), `none` (no model: the farmer types the period) |
| `MIFUGO_MODEL` | `gemma4:e4b` | Ollama model tag |
| `MIFUGO_OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama endpoint |
| `MIFUGO_GEMMA_API_KEY` | | Google AI Studio key, for `gemma_api` |
| `MIFUGO_GEMMA_MODEL` | `gemma-4-26b-a4b-it` | Hosted Gemma model id; check the current id in AI Studio |
| `MIFUGO_DB` | `data/mifugo.db` | SQLite file |
| `MIFUGO_UPLOADS` | `data/uploads` | Where label photos are kept |

For a public live demo, run with `MIFUGO_BACKEND=gemma_api` on any small host.
The safety logic is identical with either backend.

---

## Evidence, honestly

```bash
pytest                                              # 104 tests
MIFUGO_BACKEND=none python -m eval.run_log_eval     # message reading, word lists only
python -m eval.run_log_eval                         # the same with Gemma
python -m eval.run_label_eval eval/labels/real      # the test that matters (photos needed)
python -m eval.make_synthetic_labels                # regenerate the synthetic smoke-test labels
```

| What | Result | What it does and does not show |
|---|---|---|
| Unit and web tests | 104 pass | The engine, the evidence rule, time parsing and both user flows behave as specified. Includes: a correct reading of every synthetic label is accepted, and swapped or wrong-species numbers are refused. |
| Message reading, no model | 0 early times; 30/30 intent, cows and time | **A regression check, not evidence.** The 30 messages were written by the team while building the word lists. Real farmers' messages will be messier. |
| Message reading, with Gemma | not yet run | Ollama was not reachable from the environment this rebuild was written in. Run it on a laptop. |
| Label reading, real photos | not yet run | `eval/labels/real/` is empty. Filling it is the first job; see its README. **DANGEROUS must be 0.** |
| Label reading, synthetic | refused 10, correct 2, dangerous 0 with no model | Smoke test only. Flat rendered text is much easier than a creased box. |

## What is simulated or missing

- **SMS is a preview.** The message a farmer would receive is shown, not sent.
  Sending needs an SMS gateway account (for example Africa's Talking).
- **No accounts.** Anyone with the link can see every farm. Fine for a demo,
  not for real farm data.
- **Offline means the laptop or a co-op field box,** not the farmer's phone.
  Running Gemma on the phone itself would need an Android build.
- **The Swahili sentences were written by a non-native speaker.** They are all
  in `mifugo/messages.py`, to be reviewed by Swahili speakers who keep cows.
- **Not validated with farmers, agrovets or a co-op.** See
  [docs/WRITEUP.md](docs/WRITEUP.md#what-we-have-not-proven).

## Files

```
mifugo/withdrawal.py     DETERMINISTIC. Treatments -> first saleable milking; co-op check.
mifugo/timewords.py      DETERMINISTIC. Swahili/Sheng/English time phrases -> latest plausible time.
mifugo/label_reader.py   Gemma vision job + the evidence rule.
mifugo/log_parser.py     Gemma language job + name/intent/time backstops.
mifugo/messages.py       Every safety sentence, as literals, in Swahili and English.
mifugo/llm.py            The only file that talks to a model (Ollama, Gemma API, none).
mifugo/clock.py          Nairobi time, milking schedules, Swahili clock ("saa 11 jioni").
mifugo/store.py          SQLite.
mifugo/web.py            FastAPI app: farmer and co-op clerk views.
mifugo/demo.py           Demo farms (illustrative data).
eval/                    Message and label evaluations; synthetic label generator.
tests/                   pytest.
docs/RETRO.md            Why version 1 did not win, and what changed.
docs/WRITEUP.md          Draft hackathon writeup, demo script, and open questions.
```
