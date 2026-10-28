# Real label photos

This folder is the test that matters, and it is empty until someone fills it.

## How to build it (one afternoon at an agrovet)

1. Ask an agrovet owner if you may photograph the outside of medicine boxes,
   tubes and bottles on the shelf. Do not buy anything; do not open anything.
2. Photograph 30 to 50 different products used on dairy cattle: mastitis
   tubes, antibiotic injections, dewormers, acaricides, dry-cow tubes.
   Take the photo the way a farmer would: phone in hand, shop lighting, the
   panel that carries the withdrawal statement in view.
3. For each photo `name.jpg`, write `name.json`:

```json
{
  "image": "name.jpg",
  "milk": {"kind": "period", "value": 72, "unit": "hours"},
  "meat": {"kind": "period", "value": 14, "unit": "days"},
  "several_species": false,
  "printed": "copy the withdrawal text exactly as printed"
}
```

`kind` is one of `period`, `zero`, `not_for_lactating`, `unknown`. Use
`unknown` when the photo genuinely does not show a withdrawal statement.
Have a second person check every JSON file against its photo.

4. Run it:

```bash
python -m eval.run_label_eval eval/labels/real
```

The number that decides whether Mifugo can be used is **DANGEROUS**. It must
be zero. A non-zero count is a defect to fix before any farmer sees the app.

Do not commit photos that show a shop's prices or anyone's face.
