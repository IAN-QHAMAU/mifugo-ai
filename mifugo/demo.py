"""
Demo data for the pitch and for trying the app with no real farm.

Product names are generic and the periods are ILLUSTRATIVE, not taken from
any real product's label. The UI says so wherever demo data is shown.
"""

from datetime import timedelta

from mifugo.clock import now
from mifugo.withdrawal import Kind, Withdrawal

DEMO_NOTE = {
    "sw": "Data ya majaribio: majina ya dawa na muda wa kusubiri ni mifano tu, si kutoka kwenye lebo halisi.",
    "en": "Demo data: product names and withdrawal periods are illustrative, not from real labels.",
}


def seed(store):
    t = now()

    def period(value, unit, quote):
        return Withdrawal(Kind.PERIOD, value, unit, quote)

    def product(name, milk, meat):
        return store.save_product(f"DEMO {name}", [], milk, meat, source="label_photo")

    tube = product("intramammary tube",
                   period(84, "hours", "Milk: 84 hours after last treatment"),
                   period(7, "days", "Meat: 7 days"))
    wormer = product("oral dewormer",
                     period(3, "days", "Milk: 3 days"),
                     period(14, "days", "Meat and offal: 14 days"))
    unread = product("injection (label torn)", Withdrawal.unknown(), Withdrawal.unknown())
    long_acting = product("long-acting injection",
                          period(7, "days", "Milk: 7 days"),
                          period(28, "days", "Meat: 28 days"))

    wanjiku = store.create_farm("Shamba la Wanjiku", "0712000142", "M-0142", demo=True)
    cows = {n: store.add_animal(wanjiku, n) for n in ("Njeri", "Baraka", "Wanjiru", "Chebet")}
    store.add_treatment(cows["Njeri"], tube, t - timedelta(hours=15), "Njeri tube jana jioni", "demo")
    store.add_treatment(cows["Baraka"], wormer, t - timedelta(days=10), "Baraka dawa ya minyoo", "demo")
    store.add_treatment(cows["Wanjiru"], unread, t - timedelta(days=2), "Wanjiru sindano juzi", "demo")

    otieno = store.create_farm("Shamba la Otieno", "0722000207", "M-0207", demo=True)
    for n in ("Akinyi", "Simba"):
        store.add_animal(otieno, n)

    kiprop = store.create_farm("Shamba la Kiprop", "0733000315", "M-0315", milking="05:30,13:00,19:00", demo=True)
    tamu = store.add_animal(kiprop, "Tamu")
    store.add_animal(kiprop, "Lulu")
    store.add_treatment(tamu, long_acting, t - timedelta(days=1), "Tamu sindano jana", "demo")
    return [wanjiku, otieno, kiprop]
