"""
Interactive Layer 1 demo.

    python cli.py                          # live, needs Ollama
    MIFUGO_MOCK=1 python cli.py            # no model at all
    python cli.py "ng'ombe inatoa mate..."  # one-shot

Set MIFUGO_MODEL=gemma4:e2b if E4B latency is bad on your laptop.
"""

import sys

import gemma
from triage import TriageSession

RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
OFF = "\033[0m"

RULE = "\u2500" * 62


def render(verdict):
    safety = verdict["safety"]
    print()

    if safety["zoonotic_stop"]:
        print(RED + BOLD + "\u2588" * 62 + OFF)
        print(RED + BOLD + safety["zoonotic_stop"] + OFF)
        print()
        print(RED + safety["zoonotic_stop_sw"] + OFF)
        print(RED + BOLD + "\u2588" * 62 + OFF)
        print(DIM + "trigger: " + ", ".join(safety["zoonotic_trigger_reasons"]) + OFF)
        print()

    print(RULE)
    print(BOLD + f"  {verdict['condition_en']}" + OFF)
    print(f"  {verdict['condition_sw']}")
    print(f"  confidence: {verdict['confidence_band']}")
    if verdict["matched_signs"]:
        print(f"  signs matched: {', '.join(verdict['matched_signs'])}")
    print(RULE)

    flags = []
    if safety["isolation_required"]:
        flags.append("ISOLATE")
    if safety["do_not_move"]:
        flags.append("DO NOT MOVE TO SHARED GRAZING")
    if safety["do_not_slaughter"]:
        flags.append("DO NOT SLAUGHTER OR SELL")
    if safety["notifiable_ke"]:
        flags.append("NOTIFIABLE DISEASE (KE)")
    if flags:
        print("  " + "\n  ".join(flags))
        print(RULE)

    print(f"  Herd: {safety['herd_status']} \u2014 {safety['herd_detail']}")
    if safety["herd_instruction_en"]:
        print(BOLD + "  " + safety["herd_instruction_en"] + OFF)
    print(RULE)
    print("  " + safety["advice_en"])
    print("  " + safety["escalation_en"])
    print(RULE)

    if verdict["explanation_sw"]:
        print(BOLD + "  Kwa Kiswahili:" + OFF)
        print("  " + verdict["explanation_sw"].replace("\n", "\n  "))
        print(RULE)

    if verdict["alternatives"]:
        alts = ", ".join(f"{a['name_en']} ({a['band']})" for a in verdict["alternatives"])
        print(DIM + f"  also considered: {alts}" + OFF)
    if verdict["mock_mode"]:
        print(DIM + "  [MOCK_MODE \u2014 no model calls]" + OFF)
    print()


def main():
    if not gemma.MOCK_MODE and not gemma.is_available():
        print(
            f"Ollama not reachable at {gemma.OLLAMA_URL}.\n"
            "Start it, or run with MIFUGO_MOCK=1.",
            file=sys.stderr,
        )
        sys.exit(1)

    session = TriageSession()

    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
    else:
        print("Eleza hali ya mnyama wako (Kiswahili au Sheng):")
        text = input("> ")

    while True:
        result = session.submit(text)
        if result["type"] == "verdict":
            render(result)
            return
        print(f"\n  ? {result['question_sw']}")
        text = input("> ")


if __name__ == "__main__":
    main()
