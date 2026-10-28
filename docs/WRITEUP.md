# Mifugo: can I sell this cow's milk today?

*Draft writeup for the next submission. Keep it under 1,500 words; this
draft is about 900. Replace every [bracket] with a real number before
submitting.*

## The problem

A Kenyan dairy farmer treats a cow for mastitis. The box says, in small
English print, "Milk: 84 hours." Two days later a relative does the morning
milking. The treated cow's milk goes into the shared can. The co-op's
residue test rejects the whole can, or nobody tests it and the residues are
drunk.

This is common. In one study, 63% of small-scale dairy farmers did not
observe withdrawal periods, and milk from Kenyan smallholders has shown
residues above the legal limits (Springer, 2026). In one Kenyan study area,
more than 5,000 litres of milk a month were rejected for residues before
farmers were trained (ScienceDirect, 2024). In another study, 42.7% of the
antibiotics dispensed without a prescription were handed over by agrovet
attendants (Frontiers in Veterinary Science, 2025).

The information needed to get this right already exists. It is printed on
the box. It just never reaches the moment of milking, or the person doing it.

## What Mifugo does

1. **Photograph the box.** Gemma reads the withdrawal statements: milk and
   meat, in hours, days or milkings, including "nil" and "not for use in
   lactating animals".
2. **Say who and when, in your own words.** "Nimemdunga Njeri sindano jana
   jioni." Gemma extracts the cow and the time; Swahili word lists read them
   too, as a backstop.
3. **Get an exact answer.** "USIUZE maziwa ya Njeri. Yanaweza kuuzwa kuanzia
   ukamuaji wa Jumamosi, saa 11 jioni (17:00)." The farmer gets the same as
   an SMS (previewed in the prototype).
4. **Ask any time.** "Naweza kuuza maziwa ya Njeri leo?"
5. **At the co-op.** The collection clerk looks up the farmer and sees
   **POKEA** (accept) or **PIMA CHOMBO HIKI** (test this delivery), with the
   cows whose milk must not be in it. Test strips go where the risk is.

## Gemma reads, Python guarantees

Gemma is essential here: it reads small print on a creased box and
code-switched Swahili. Without it, a farmer must find and type the period,
which is the step that fails today.

Python decides what to believe and what to say:

- **The evidence rule.** Gemma must quote the printed words. Python accepts
  a period only if the number is the first number after the word *milk*,
  the unit is printed with it, and, on multi-species labels, it comes from
  the cattle line. A model that swaps the milk and meat numbers, or reads
  the sheep period, is refused.
- **Never a default.** An unread period means "do not sell" until a person
  enters one and names who confirmed it.
- **Latest plausible time.** "Jana jioni" is 20:59, not 16:00. Every guess
  can only push the end later.
- **Real milkings.** The answer is a milking on the farm's own schedule,
  not "about three days".

Every verdict sentence is a literal in Python. Gemma never writes one.

## Offline

With Ollama and Gemma 4 E4B on a laptop or a co-op field box, everything
runs without internet. The public demo uses hosted Gemma; the safety logic
is identical.

## Evaluation

| What | Result |
|---|---|
| Real label photos ([N] products, photographed at [agrovet]) | dangerous [0] · refused [n] · correct [n] |
| Farmer messages ([N] real messages) | early dose times [0] · intent [n/N] · cows [n/N] |
| Unit and web tests | 104 pass |

"Dangerous" means a saleable date earlier than the truth. It is the only
number that has to be zero.

## What we have not proven

- **Honesty.** A farmer loses milk income by logging a treatment. Logging may
  only happen when the farmer already intends to withhold. The co-op side,
  targeted testing, is designed to work even when logging is incomplete,
  because it gets better as more treatments are logged and costs nothing
  when they are not.
- **Who pays.** We believe co-ops pay to cut rejected milk and test-strip
  spend. We have [not yet / N] conversations with co-op managers to support it.
- **Label coverage.** Some products print withdrawal periods only on the
  leaflet inside. Those will be refused until someone types them in.

## Next

1. Fill `eval/labels/real/` with 50 photographed products. Report DANGEROUS.
2. Five co-op managers: how many litres were rejected last month, and what did
   test strips cost?
3. Capture at the point of sale: the agrovet photographs the box once, and
   the treatment reaches the farmer's record without the farmer typing.

---

## Three-minute demo script

1. **(20 s) The moment.** Hold up a real medicine box. Point at the
   withdrawal line. "This is the most important sentence on the box, and
   nobody reads it at milking time."
2. **(40 s) Log it.** On a phone: photograph the box. Type "Nimemdunga Njeri
   sindano jana jioni." Show Gemma's quoted words and Python's check. Save.
   The card turns red with the exact milking. Show the SMS preview.
3. **(20 s) The guard.** Change the milk number on the confirm screen. It
   now demands who confirmed it. Show a label with no withdrawal statement:
   "do not sell until confirmed", not a guess.
4. **(20 s) Ask.** "Naweza kuuza maziwa ya Njeri leo?" The answer is the same
   literal, in Swahili.
5. **(30 s) The co-op.** Switch to the clerk view. Two of three deliveries
   are flagged, with the cows named. "Strips go where the risk is."
6. **(20 s) Offline.** Turn on airplane mode. Log another treatment. It works.
7. **(30 s) Numbers.** Dangerous misreads on real photos: [0]. What we have
   not proven yet, said plainly.
