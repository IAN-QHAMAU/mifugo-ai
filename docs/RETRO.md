# Why version 1 did not win, and what changed

Version 1 (still on `main`) was an offline livestock-triage app: describe a
sick animal in Swahili or Sheng, or photograph it, and get a likely
condition, an isolation instruction and an escalation threshold. It was
entered in **Build with Gemma: Comeback Sprint (GDG UoN)**, July 2026,
Track 3. Fourteen submissions. It did not place. The track winners
included Mshauri (SME records to insights), Jirani Alerts (SMS reports to
verified community alerts) and Mkulima Gemma (an offline AI farming
adviser).

We do not have the judges' scores. What follows is our reading of the
published rubric against what we built.

## The rubric

| Criterion | Weight |
|---|---|
| Gemma Integration: *"Is the model core to the solution?"* | 30% |
| Innovation & Impact | 30% |
| Functionality: *"Does the demo work?"* | 20% |
| Writeup | 20% |

## What went wrong

1. **We told the judges Gemma was not core.** The README said "Python owns
   every threshold, rule and verdict." The UI showed "Gemma did language
   only / Python decided everything else." A mock mode ran the entire app
   with zero model calls. Keeping the model away from safety decisions was
   good engineering, but on a rubric that gives 30% to "is the model core?",
   we argued against ourselves.

2. **A rare problem with a thin answer.** A farmer meets a sick-animal
   emergency occasionally. For most cases the app's answer was "isolate it,
   don't move it, call the vet", which the farmer would do anyway by phoning
   the agrovet. It deliberately gave no treatment advice, covered nine
   conditions, and remembered nothing between sessions. Mkulima Gemma, in
   the same space, kept a farm log and gave advice that remembered it.

3. **The person it was for could not run it.** Streamlit plus Ollama plus
   Gemma 4 E4B on a laptop. A herder has a cheap phone. "Offline" meant a
   laptop without internet. The rules required a public live demo; without a
   hosted model, the only public version was the mock.

4. **The numbers proved less than they appeared to.** Zoonotic recall 3/3,
   escalation recall 9/9 and so on were produced in mock mode, where the
   pre-written model responses were keyed to the same phrases as the 15 test
   cases we wrote. That tests our rules against our own answers, not Gemma
   against real farmer language.

## What we kept

- Swahili/Sheng understanding through a closed JSON schema.
- A deterministic backstop that still works when the model fails.
- Safety sentences as literals that the model never authors.
- The refusal to name drugs or doses.
- Recall-first evaluation, now aimed at the failure that matters: a date
  that is too early.

## What changed

The README of the fork already named the better problem: advice about
milk withdrawal "depends on knowing exactly what the animal has already been
given — information an app cannot verify." A photo of the medicine box *is*
that information.

| | Version 1: triage | Version 2: withdrawal |
|---|---|---|
| Question | What is wrong with my animal? | Can I sell this cow's milk today? |
| How often | Occasional emergency | Every milking during every treatment |
| Answer | Usually "isolate and call a vet" | An exact milking: "from Saturday's 17:00 milking" |
| Gemma's role | Optional: the app ran without it | Essential: reads the label and the farmer's words |
| Python's role | Everything | Checks Gemma's evidence; owns every date and verdict |
| Memory | None | Per-cow treatment record |
| Who pays | Unclear | Dairy co-ops (rejected milk, test-strip spend) |
| Evaluation | 15 self-written cases, mock mode | Real label photos (to collect); "dangerous" must be 0 |

The safety architecture did not get weaker. It moved from "the model is not
needed" to "the model is needed, and here is how Python refuses to believe
it without evidence".
