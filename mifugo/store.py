"""
SQLite persistence. Plain sqlite3, one file, nothing to install.

A product row holds what was read off one box; treatments point at it. When a
person later confirms a period that was unreadable, they update the product,
and every treatment that used it is recomputed. Nothing is cached: verdicts
are always computed fresh by withdrawal.py from these rows.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

from mifugo import config
from mifugo.clock import MilkingSchedule, aware, now
from mifugo.withdrawal import Kind, Treatment, Withdrawal

SCHEMA = """
CREATE TABLE IF NOT EXISTS farms (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT DEFAULT '',
    member_no TEXT DEFAULT '',
    milking TEXT NOT NULL DEFAULT '06:00,17:00',
    demo INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS animals (
    id INTEGER PRIMARY KEY,
    farm_id INTEGER NOT NULL REFERENCES farms(id),
    name TEXT NOT NULL,
    tag TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE (farm_id, name)
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    ingredients TEXT DEFAULT '[]',
    milk_kind TEXT NOT NULL, milk_value REAL, milk_unit TEXT, milk_quote TEXT DEFAULT '',
    meat_kind TEXT NOT NULL, meat_value REAL, meat_unit TEXT, meat_quote TEXT DEFAULT '',
    source TEXT NOT NULL,              -- label_photo | manual
    confirmed_by TEXT DEFAULT '',      -- who supplied a manually entered period
    image_path TEXT DEFAULT '',
    model_reply TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS treatments (
    id INTEGER PRIMARY KEY,
    animal_id INTEGER NOT NULL REFERENCES animals(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    given_at TEXT NOT NULL,
    reported TEXT DEFAULT '',          -- the farmer's own words
    time_basis TEXT DEFAULT '',        -- how the time was worked out
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY,
    farm_id INTEGER NOT NULL REFERENCES farms(id),
    checked_at TEXT NOT NULL,
    milking_at TEXT NOT NULL,
    decision TEXT NOT NULL,
    excluded TEXT DEFAULT '[]',
    clerk TEXT DEFAULT ''
);
"""


def _iso(dt):
    return aware(dt).isoformat(timespec="minutes")


def _dt(text):
    return aware(datetime.fromisoformat(text))


@contextmanager
def connect(path=None):
    path = path or config.DB_PATH
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


class Store:
    def __init__(self, path=None):
        self.path = path or config.DB_PATH
        with connect(self.path) as c:
            c.executescript(SCHEMA)

    def _c(self):
        return connect(self.path)

    # -- farms and animals ---------------------------------------------------

    def create_farm(self, name, phone="", member_no="", milking="06:00,17:00", demo=False):
        MilkingSchedule.parse(milking)   # reject a bad schedule before it is stored
        with self._c() as c:
            cur = c.execute(
                "INSERT INTO farms (name, phone, member_no, milking, demo, created_at) VALUES (?,?,?,?,?,?)",
                (name.strip(), phone.strip(), member_no.strip(), milking, int(demo), _iso(now())),
            )
            return cur.lastrowid

    def farms(self):
        with self._c() as c:
            return [dict(r) for r in c.execute("SELECT * FROM farms ORDER BY name")]

    def farm(self, farm_id):
        with self._c() as c:
            row = c.execute("SELECT * FROM farms WHERE id=?", (farm_id,)).fetchone()
            return dict(row) if row else None

    def find_farms(self, query):
        q = f"%{query.strip()}%"
        with self._c() as c:
            rows = c.execute(
                "SELECT * FROM farms WHERE member_no LIKE ? OR phone LIKE ? OR name LIKE ? ORDER BY name",
                (q, q, q),
            )
            return [dict(r) for r in rows]

    def schedule(self, farm_id):
        return MilkingSchedule.parse(self.farm(farm_id)["milking"])

    def add_animal(self, farm_id, name, tag=""):
        with self._c() as c:
            cur = c.execute(
                "INSERT INTO animals (farm_id, name, tag, created_at) VALUES (?,?,?,?)",
                (farm_id, name.strip(), tag.strip(), _iso(now())),
            )
            return cur.lastrowid

    def animals(self, farm_id):
        with self._c() as c:
            rows = c.execute("SELECT * FROM animals WHERE farm_id=? ORDER BY name", (farm_id,))
            return [dict(r) for r in rows]

    def animal_ids(self, farm_id):
        return {a["name"]: a["id"] for a in self.animals(farm_id)}

    # -- products --------------------------------------------------------------

    def save_product(self, name, ingredients, milk, meat, source, confirmed_by="",
                     image_path="", model_reply=None):
        with self._c() as c:
            cur = c.execute(
                """INSERT INTO products (name, ingredients, milk_kind, milk_value, milk_unit, milk_quote,
                   meat_kind, meat_value, meat_unit, meat_quote, source, confirmed_by, image_path,
                   model_reply, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    name or "Dawa bila jina", json.dumps(ingredients or []),
                    milk.kind.value, milk.value, milk.unit, milk.quote,
                    meat.kind.value, meat.value, meat.unit, meat.quote,
                    source, confirmed_by, image_path,
                    json.dumps(model_reply) if model_reply is not None else "",
                    _iso(now()),
                ),
            )
            return cur.lastrowid

    def product(self, product_id):
        with self._c() as c:
            row = c.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
            return dict(row) if row else None

    def confirm_period(self, product_id, which, withdrawal, confirmed_by):
        """A person supplies the period that could not be read. `which` is milk|meat."""
        if which not in ("milk", "meat"):
            raise ValueError(which)
        if not confirmed_by.strip():
            raise ValueError("a manually entered period must say who confirmed it")
        with self._c() as c:
            c.execute(
                f"UPDATE products SET {which}_kind=?, {which}_value=?, {which}_unit=?, "
                f"{which}_quote=?, confirmed_by=? WHERE id=?",
                (withdrawal.kind.value, withdrawal.value, withdrawal.unit,
                 withdrawal.quote, confirmed_by.strip(), product_id),
            )

    # -- treatments ------------------------------------------------------------

    def add_treatment(self, animal_id, product_id, given_at, reported="", time_basis=""):
        if aware(given_at) > now() + timedelta(minutes=5):
            raise ValueError("a treatment cannot be logged in the future")
        with self._c() as c:
            cur = c.execute(
                "INSERT INTO treatments (animal_id, product_id, given_at, reported, time_basis, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (animal_id, product_id, _iso(given_at), reported, time_basis, _iso(now())),
            )
            return cur.lastrowid

    def treatments(self, farm_id):
        """All treatments on a farm, as engine objects."""
        with self._c() as c:
            rows = c.execute(
                """SELECT t.id, t.given_at, a.name AS animal, p.* , p.id AS product_id
                   FROM treatments t JOIN animals a ON a.id=t.animal_id
                   JOIN products p ON p.id=t.product_id
                   WHERE a.farm_id=? ORDER BY t.given_at""",
                (farm_id,),
            ).fetchall()
        out = []
        for r in rows:
            out.append(
                Treatment(
                    animal=r["animal"],
                    product=r["name"],
                    given_at=_dt(r["given_at"]),
                    milk=_withdrawal(r, "milk"),
                    meat=_withdrawal(r, "meat"),
                    id=r["id"],
                )
            )
        return out

    def treatment_rows(self, farm_id):
        """Treatments with their product details, newest first, for display."""
        with self._c() as c:
            rows = c.execute(
                """SELECT t.*, a.name AS animal, p.name AS product, p.source, p.confirmed_by,
                   p.milk_kind, p.milk_quote, p.meat_kind, p.meat_quote
                   FROM treatments t JOIN animals a ON a.id=t.animal_id
                   JOIN products p ON p.id=t.product_id
                   WHERE a.farm_id=? ORDER BY t.given_at DESC""",
                (farm_id,),
            )
            return [dict(r) for r in rows]

    def product_for_treatment(self, treatment_id):
        with self._c() as c:
            row = c.execute("SELECT product_id FROM treatments WHERE id=?", (treatment_id,)).fetchone()
            return row["product_id"] if row else None

    # -- co-op checks ----------------------------------------------------------

    def log_check(self, farm_id, check, clerk=""):
        with self._c() as c:
            c.execute(
                "INSERT INTO checks (farm_id, checked_at, milking_at, decision, excluded, clerk) "
                "VALUES (?,?,?,?,?,?)",
                (farm_id, _iso(now()), _iso(check.milking_at), check.decision,
                 json.dumps([s.animal for s in check.exclude]), clerk),
            )

    def checks(self, limit=50):
        with self._c() as c:
            rows = c.execute(
                """SELECT k.*, f.name AS farm FROM checks k JOIN farms f ON f.id=k.farm_id
                   ORDER BY k.checked_at DESC LIMIT ?""",
                (limit,),
            )
            return [dict(r) for r in rows]


def _withdrawal(row, which):
    kind = Kind(row[f"{which}_kind"])
    if kind is Kind.PERIOD:
        return Withdrawal(kind, row[f"{which}_value"], row[f"{which}_unit"], row[f"{which}_quote"] or "")
    return Withdrawal(kind, quote=row[f"{which}_quote"] or "")
