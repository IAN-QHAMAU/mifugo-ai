"""
How well does Mifugo read farmers' messages?

    python -m eval.run_log_eval                    # whatever MIFUGO_BACKEND is set to
    MIFUGO_BACKEND=none python -m eval.run_log_eval  # word lists only, no model

Reported in order of what matters:
  1. Early dose times: the parsed time is EARLIER than the careful reading.
     This ends a withdrawal too soon. Target: 0.
  2. Intent accuracy.
  3. Animal accuracy (exact set).
  4. Dose time exact.
Running with MIFUGO_BACKEND=none shows the floor the deterministic matchers
guarantee when the model is down. Running with a model shows what Gemma adds.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from mifugo import llm
from mifugo.clock import aware
from mifugo.log_parser import parse

HERE = Path(__file__).resolve().parent


def main(path=HERE / "utterances.json"):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    now = aware(datetime.fromisoformat(data["now"]))
    herd = data["herd"]
    rows, early, intent_ok, animals_ok, time_ok, timed = [], 0, 0, 0, 0, 0

    for case in data["cases"]:
        p = parse(case["text"], herd, now)
        i_ok = p.intent == case["intent"]
        a_ok = sorted(p.animals) == sorted(case["animals"])
        t_mark = ""
        if case.get("given_at"):
            timed += 1
            expected = aware(datetime.fromisoformat(case["given_at"]))
            got = p.given_at.at.replace(second=0, microsecond=0)
            if got == expected:
                time_ok += 1
                t_mark = "ok"
            elif got < expected:
                early += 1
                t_mark = f"EARLY {got:%d %H:%M} < {expected:%d %H:%M}"
            else:
                t_mark = f"later {got:%d %H:%M} > {expected:%d %H:%M}"
        intent_ok += i_ok
        animals_ok += a_ok
        rows.append((case["text"], p.intent if not i_ok else "ok", "ok" if a_ok else str(p.animals), t_mark))

    n = len(data["cases"])
    print(f"\nMifugo message reading  ·  {n} messages  ·  backend: {llm.backend().describe()}")
    print("=" * 72)
    print(f"1. Early dose times     {early}/{timed}   TARGET 0")
    print(f"2. Intent               {intent_ok}/{n}")
    print(f"3. Animals              {animals_ok}/{n}")
    print(f"4. Dose time exact      {time_ok}/{timed}")
    print("=" * 72)
    for text, i, a, t in rows:
        if i != "ok" or a != "ok" or (t and t != "ok"):
            print(f"  {text[:44]:44}  intent={i}  animals={a}  {t}")
    return 1 if early else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
