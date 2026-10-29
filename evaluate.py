"""
Evaluation harness.

    python evaluate.py            # against the live model
    MIFUGO_MOCK=1 python evaluate.py

Why these metrics and not accuracy
----------------------------------
Top-1 diagnosis accuracy is the wrong headline number for a triage tool. A
system that names the wrong condition but still sends the herder to a vet has
failed gracefully. A system that names the right condition but says "monitor at
home" has failed dangerously. Those two outcomes score identically on accuracy
and could not be more different in the field.

So the headline metrics are, in order of importance:

  1. ZOONOTIC RECALL   - of the cases where a human-health stop must fire, how
                         many fired? Target: 100%. Anything less is a defect,
                         not a tuning parameter.
  2. ESCALATION RECALL - of the cases that must reach a vet or county officer,
                         how many did? A false positive here costs a herder a
                         phone call. A false negative can cost the herd.
  3. ABSTAIN PRECISION - of the out-of-scope cases, how many correctly refused
                         to guess?
  4. Condition accuracy - reported last, on purpose. It is the least important
                         of the four.

The deliberate recall bias is stated in the writeup as a design decision, not
discovered here. This file measures whether the bias actually holds.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gemma
from triage import TriageSession

VIGNETTES = json.loads(
    (Path(__file__).resolve().parent / "vignettes.json").read_text(encoding="utf-8")
)


def run_one(v):
    session = TriageSession(max_questions=0)
    result = session.submit(v["text"])
    safety = result["safety"]

    got_stop = bool(safety["zoonotic_stop"])
    got_abstain = bool(safety["abstained"])
    # Escalated = anything other than "no clear match, no urgency". A must-escalate
    # case is satisfied by a named must-escalate condition OR by the zoonotic stop
    # OR by an outbreak-level herd instruction.
    got_escalation = (
        got_stop
        or safety.get("must_escalate", False)
        or safety.get("herd_status") == "outbreak"
    )

    return {
        "id": v["id"],
        "text": v["text"],
        "expected_condition": v.get("expect_condition"),
        "got_condition": result["condition_id"],
        "band": result["confidence_band"],
        "expect_stop": v.get("expect_zoonotic_stop", False),
        "got_stop": got_stop,
        "must_escalate": v.get("must_escalate", False),
        "got_escalation": got_escalation,
        "expect_abstain": v.get("expect_abstain", False),
        "got_abstain": got_abstain,
    }


def main():
    rows = [run_one(v) for v in VIGNETTES["vignettes"]]

    stop_needed = [r for r in rows if r["expect_stop"]]
    stop_hit = [r for r in stop_needed if r["got_stop"]]
    stop_false = [r for r in rows if r["got_stop"] and not r["expect_stop"]]

    esc_needed = [r for r in rows if r["must_escalate"]]
    esc_hit = [r for r in esc_needed if r["got_escalation"]]

    abs_needed = [r for r in rows if r["expect_abstain"]]
    abs_hit = [r for r in abs_needed if r["got_abstain"]]

    cond_checked = [r for r in rows if r["expected_condition"]]
    cond_hit = [r for r in cond_checked if r["got_condition"] == r["expected_condition"]]

    print(f"\nMifugo evaluation  ·  {len(rows)} vignettes  ·  "
          f"{'MOCK' if gemma.MOCK_MODE else gemma.MODEL}")
    print("=" * 62)
    print(f"1. Zoonotic recall     {len(stop_hit)}/{len(stop_needed)}"
          f"   ({_pct(stop_hit, stop_needed)})   TARGET 100%")
    print(f"   False stops         {len(stop_false)}"
          "   (acceptable: advice is safe regardless of cause)")
    print(f"2. Escalation recall   {len(esc_hit)}/{len(esc_needed)}"
          f"   ({_pct(esc_hit, esc_needed)})")
    print(f"3. Abstain precision   {len(abs_hit)}/{len(abs_needed)}"
          f"   ({_pct(abs_hit, abs_needed)})")
    print(f"4. Condition accuracy  {len(cond_hit)}/{len(cond_checked)}"
          f"   ({_pct(cond_hit, cond_checked)})   least important")
    print("=" * 62)

    misses = [r for r in rows if (r["expect_stop"] and not r["got_stop"])
              or (r["must_escalate"] and not r["got_escalation"])
              or (r["expect_abstain"] and not r["got_abstain"])]
    if misses:
        print("\nSAFETY-RELEVANT MISSES\n" + "-" * 62)
        for r in misses:
            flags = []
            if r["expect_stop"] and not r["got_stop"]:
                flags.append("MISSED ZOONOTIC STOP")
            if r["must_escalate"] and not r["got_escalation"]:
                flags.append("did not escalate")
            if r["expect_abstain"] and not r["got_abstain"]:
                flags.append(f"guessed {r['got_condition']} instead of abstaining")
            print(f"  {r['id']}  {'; '.join(flags)}")
            print(f"       {r['text'][:70]}")
    else:
        print("\nNo safety-relevant misses.")

    print("\nPER-VIGNETTE\n" + "-" * 62)
    for r in rows:
        mark = "ok " if r["got_condition"] == r["expected_condition"] else "   "
        stop = " STOP" if r["got_stop"] else ""
        esc = " esc" if r["got_escalation"] else ""
        print(f"  {r['id']} {mark} {str(r['got_condition']):24s}"
              f" {r['band']:9s}{stop}{esc}")

    if misses:
        sys.exit(1)


def _pct(hit, total):
    return f"{(100.0 * len(hit) / len(total)):.0f}%" if total else "n/a"


if __name__ == "__main__":
    if os.environ.get("MIFUGO_MOCK") == "1":
        gemma.MOCK_MODE = True
    main()