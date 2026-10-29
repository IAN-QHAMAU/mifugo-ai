"""
Mifugo visual system — "Field Record".

Design thesis
-------------
A triage verdict is not a chat message. It is a document a herder is issued and
acts on, the way a veterinary field card or a livestock movement permit is. So
the interface borrows from that world: manila-kraft stock, official-form
typography, hairline field rules, and rubber-stamp status marks with a record
number and timestamp.

The signature is a deliberate rupture. Everything is calm officialdom until the
zoonotic stop fires, at which point the document metaphor is abandoned entirely
for a full-bleed hazard placard. That is not decoration — it encodes the
asymmetric cost the whole system is tuned around. A wrong condition costs a
phone call. A missed carcass warning can cost a person. The interface should
not treat those two states as visually comparable.

This file renders. It decides nothing.
"""

# --- tokens ----------------------------------------------------------------
# Manila kraft rather than the warmer cream that generic templates reach for;
# stamp red rather than terracotta. Both chosen against the subject's own
# artifacts — county office stamps, dip-tank cards, carbon-copy receipts.

PAPER      = "#E9E1D1"
PAPER_2    = "#DFD5C1"
RULE       = "#BCAF97"
INK        = "#1F241F"   # warm green-black, sits with the forest
INK_SOFT   = "#6B6154"
STAMP      = "#A32718"
FOREST     = "#14452F"   # jungle green — structure, safe states
STAMP_GRN  = "#14452F"
CAUTION    = "#A66A05"
ALARM_BG   = "#4E0806"
ALARM_FG   = "#FFD9D2"
ALARM_EDGE = "#FF6B5A"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root {{
  --paper:{PAPER}; --paper2:{PAPER_2}; --rule:{RULE};
  --ink:{INK}; --inksoft:{INK_SOFT};
  --stamp:{STAMP}; --stampgrn:{STAMP_GRN}; --forest:{FOREST}; --caution:{CAUTION};
  --alarmbg:{ALARM_BG}; --alarmfg:{ALARM_FG}; --alarmedge:{ALARM_EDGE};
  --display:'Barlow Condensed',system-ui,sans-serif;
  --body:'IBM Plex Sans',system-ui,sans-serif;
  --mono:'IBM Plex Mono',ui-monospace,monospace;
}}

/* ---- ground -------------------------------------------------------- */
.stApp {{ background:var(--paper); }}
.stApp, .stApp p, .stApp li, .stApp label {{
  font-family:var(--body); color:var(--ink);
}}
/* Streamlit draws icons as ligature text in a Material Symbols face. Any
   blanket font-family on span/div turns them into literal words like
   "arrow_right" and "upload". Protect them explicitly. */
.stApp [data-testid="stIconMaterial"],
.stApp span[class*="material-symbols"],
.stApp i[class*="material-symbols"],
.stApp [data-testid="stExpanderToggleIcon"],
.stApp [data-testid="stFileUploaderIcon"] {{
  font-family:'Material Symbols Rounded','Material Symbols Outlined',
              'Material Icons' !important;
  text-transform:none !important; letter-spacing:normal !important;
}}
.block-container {{ padding-top:1.4rem; padding-bottom:3rem; max-width:520px; }}
#MainMenu, footer, header {{ visibility:hidden; }}

/* ---- masthead ------------------------------------------------------ */
.mf-mast {{
  display:flex; align-items:baseline; justify-content:space-between;
  border-bottom:2.5px solid var(--forest); padding-bottom:.35rem; margin-bottom:.2rem;
}}
.mf-mast h1 {{
  color:var(--forest);
  font-family:var(--display); font-weight:700; font-size:2.5rem;
  letter-spacing:.02em; line-height:1; margin:0; text-transform:uppercase;
}}
.mf-mast .org {{
  font-family:var(--mono); font-size:.62rem; letter-spacing:.16em;
  text-transform:uppercase; color:var(--inksoft); text-align:right; line-height:1.5;
}}
.mf-tag {{
  font-family:var(--body); font-size:1.02rem; line-height:1.45;
  color:var(--inksoft); margin:.55rem 0 1.4rem 0; max-width:34ch;
}}

/* ---- the card: a tear-off field record ----------------------------- */
.mf-rec {{
  background:#F2EBDD; border:1px solid var(--rule); border-radius:3px;
  box-shadow:0 1px 0 rgba(42,37,30,.10), 0 6px 18px -12px rgba(42,37,30,.35);
  margin:0 0 1.1rem 0; overflow:hidden;
}}
/* perforated top edge — the card was torn from a book */
.mf-rec::before {{
  content:''; display:block; height:7px;
  background:radial-gradient(circle at 5px 0, transparent 4px, var(--rule) 4px 4.7px, transparent 4.8px) 0 0/10px 7px repeat-x;
  opacity:.75;
}}
.mf-rec-hd {{
  display:flex; justify-content:space-between; align-items:center;
  font-family:var(--mono); font-size:.63rem; letter-spacing:.11em;
  text-transform:uppercase; color:var(--inksoft);
  padding:.5rem .95rem; border-bottom:1px solid var(--rule); background:var(--paper2);
}}
.mf-rec-bd {{ padding:1rem .95rem 1.1rem .95rem; }}

.mf-band {{
  font-family:var(--mono); font-size:.62rem; letter-spacing:.15em;
  text-transform:uppercase; color:var(--inksoft); margin-bottom:.25rem;
}}
.mf-cond {{
  font-family:var(--display); font-weight:700; font-size:2.15rem;
  line-height:1.02; letter-spacing:.005em; text-transform:uppercase;
}}
.mf-cond-alt {{
  font-family:var(--body); font-size:.94rem; color:var(--inksoft); margin-top:.2rem;
}}

/* ---- rubber stamps: the signature element -------------------------- */
.mf-stamps {{ display:flex; flex-wrap:wrap; gap:.45rem; margin-top:.95rem; }}
.mf-stamp {{
  font-family:var(--display); font-weight:600; font-size:.86rem;
  letter-spacing:.11em; text-transform:uppercase;
  padding:.3rem .6rem; border:2px double currentColor; border-radius:2px;
  opacity:.92;
}}
.mf-stamp.red {{ color:var(--stamp); transform:rotate(-1.4deg); }}
.mf-stamp.amb {{ color:var(--caution); transform:rotate(.9deg); }}
.mf-stamp.grn {{ color:var(--stampgrn); transform:rotate(-.5deg); }}

/* ---- field rows ---------------------------------------------------- */
.mf-sec {{
  font-family:var(--mono); font-size:.63rem; letter-spacing:.15em;
  text-transform:uppercase; color:var(--inksoft);
  border-bottom:1px solid var(--rule); padding-bottom:.25rem;
  margin:1.5rem 0 .7rem 0;
}}
.mf-step {{ display:flex; gap:.7rem; margin-bottom:.55rem; align-items:flex-start; }}
.mf-step .n {{
  flex:0 0 1.35rem; font-family:var(--mono); font-size:.78rem; font-weight:600;
  color:var(--forest); padding-top:.16rem;
}}
.mf-step .t {{ font-size:1rem; line-height:1.52; }}
.mf-who {{
  border-left:3px solid var(--stampgrn); padding:.15rem 0 .15rem .8rem;
  font-size:1rem; line-height:1.5;
}}
.mf-note {{
  background:var(--paper2); border:1px solid var(--rule); border-radius:3px;
  padding:.7rem .85rem; font-size:.9rem; line-height:1.55; color:var(--ink);
  margin-top:.6rem;
}}
.mf-grid {{
  display:grid; grid-template-columns:1fr 1fr; gap:0;
  border:1px solid var(--rule); border-radius:3px; margin-top:1rem; overflow:hidden;
}}
.mf-cell {{ padding:.6rem .8rem; border-right:1px solid var(--rule); background:#F2EBDD; }}
.mf-cell:last-child {{ border-right:none; }}
.mf-cell .k {{
  font-family:var(--mono); font-size:.58rem; letter-spacing:.13em;
  text-transform:uppercase; color:var(--inksoft); margin-bottom:.18rem;
}}
.mf-cell .v {{ font-size:.9rem; line-height:1.42; }}

/* ---- the rupture: hazard placard ----------------------------------- */
.mf-alarm {{
  background:var(--alarmbg); color:var(--alarmfg);
  border-radius:3px; margin:0 0 1.2rem 0; overflow:hidden;
  animation:mf-in .22s ease-out;
}}
@keyframes mf-in {{ from {{ opacity:0; transform:translateY(-3px); }} to {{ opacity:1; }} }}
@media (prefers-reduced-motion:reduce) {{ .mf-alarm {{ animation:none; }} }}
.mf-alarm .rule {{
  height:9px;
  background:repeating-linear-gradient(-45deg,var(--alarmedge) 0 9px,var(--alarmbg) 9px 18px);
}}
.mf-alarm .in {{ padding:1.15rem 1.1rem 1.3rem 1.1rem; }}
.mf-alarm .t {{
  font-family:var(--mono); font-size:.64rem; letter-spacing:.19em;
  text-transform:uppercase; color:var(--alarmedge); margin-bottom:.6rem;
}}
.mf-alarm .h {{
  font-family:var(--display); font-weight:700; font-size:1.72rem; line-height:1.08;
  text-transform:uppercase; margin-bottom:.7rem; color:#fff;
}}
.mf-alarm .b {{ font-size:1rem; line-height:1.62; white-space:pre-wrap; }}

[data-testid="stFileUploaderDropzone"] {{
  background:#F2EBDD; border:1px dashed var(--rule); border-radius:3px;
}}
[data-testid="stFileUploaderDropzone"] button {{
  font-family:var(--display); font-weight:600; letter-spacing:.06em;
  text-transform:uppercase; font-size:.8rem;
}}
[data-testid="stSelectbox"] div[data-baseweb="select"] > div {{
  background:#F2EBDD; border-color:var(--rule); border-radius:3px;
}}

[data-testid="stTabs"] [data-baseweb="tab-list"] {{
  gap:.4rem; border-bottom:1px solid var(--rule); background:transparent;
}}
[data-testid="stTabs"] [data-baseweb="tab"] {{
  font-family:var(--display); font-weight:600; font-size:1rem;
  letter-spacing:.05em; text-transform:uppercase; color:var(--inksoft);
  background:transparent; border-radius:0; padding:.5rem .95rem;
}}
[data-testid="stTabs"] [aria-selected="true"] {{
  color:var(--forest); border-bottom:2.5px solid var(--forest);
}}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] {{ background:transparent; }}

/* ---- empty state --------------------------------------------------- */
.mf-empty {{ margin:.2rem 0 1rem 0; }}
.mf-empty .lead {{
  font-family:var(--body); font-size:1rem; line-height:1.6;
  color:var(--ink); margin-bottom:1.15rem;
}}
.mf-try {{
  background:#F2EBDD; border:1px solid var(--rule); border-left:3px solid var(--stampgrn);
  border-radius:3px; padding:.7rem .85rem; margin-bottom:.55rem;
}}
.mf-try .q {{
  font-family:var(--body); font-size:.97rem; line-height:1.45; color:var(--ink);
}}
.mf-try .w {{
  font-family:var(--mono); font-size:.58rem; letter-spacing:.13em;
  text-transform:uppercase; color:var(--inksoft); margin-top:.3rem;
}}
.mf-hint {{
  font-family:var(--body); font-size:.88rem; line-height:1.55;
  color:var(--inksoft); margin-top:1.1rem; padding-top:.75rem;
  border-top:1px solid var(--rule);
}}

/* ---- provenance footer -------------------------------------------- */
.mf-prov {{
  font-family:var(--mono); font-size:.6rem; letter-spacing:.09em;
  text-transform:uppercase; color:var(--inksoft); line-height:1.7;
  border-top:1px solid var(--rule); padding-top:.55rem; margin-top:1.6rem;
}}

/* ---- streamlit chrome --------------------------------------------- */
[data-testid="stSidebar"] {{ background:#DFD5C1; border-right:1px solid var(--rule); }}
[data-testid="stSidebar"] * {{ font-family:var(--body); }}
.stButton button {{
  font-family:var(--display); font-weight:600; letter-spacing:.06em;
  text-transform:uppercase; font-size:.86rem; min-height:42px;
  background:transparent; color:var(--forest);
  border:1.5px solid var(--forest); border-radius:2px;
}}
.stButton button:hover {{ background:var(--forest); color:var(--paper); border-color:var(--forest); }}
[data-testid="stFileUploaderDropzone"] {{
  background:var(--paper2); border:1px dashed var(--rule); border-radius:3px;
}}
[data-testid="stFileUploaderDropzone"] small {{ color:var(--inksoft); }}
[data-testid="stChatInput"] textarea {{ font-family:var(--body); font-size:1rem; }}
[data-testid="stChatInput"] {{ border-color:var(--rule); }}
.stChatMessage {{ background:transparent; }}
[data-testid="stExpander"] details {{
  border:1px solid var(--rule); border-radius:3px; background:#F2EBDD;
}}
/* Scope to the label only. Styling `summary` itself overrides Streamlit's
   Material Symbols icon font and the ligature renders as literal text. */
[data-testid="stExpander"] summary p {{
  font-family:var(--body); font-weight:500; font-size:.92rem;
  letter-spacing:0; text-transform:none;
}}
</style>
"""


# --- builders --------------------------------------------------------------

def masthead(tagline, status):
    return (
        '<div class="mf-mast"><h1>Mifugo</h1>'
        f'<div class="org">Triage ya mifugo<br>{status}</div></div>'
        f'<div class="mf-tag">{tagline}</div>'
    )


def alarm(label, head, body):
    return (
        '<div class="mf-alarm"><div class="rule"></div><div class="in">'
        f'<div class="t">{label}</div><div class="h">{head}</div>'
        f'<div class="b">{body}</div></div></div>'
    )


def record(ref, stamped, band_label, condition, alt, stamps_html):
    return (
        '<div class="mf-rec">'
        f'<div class="mf-rec-hd"><span>{ref}</span><span>{stamped}</span></div>'
        f'<div class="mf-rec-bd"><div class="mf-band">{band_label}</div>'
        f'<div class="mf-cond">{condition}</div>'
        f'<div class="mf-cond-alt">{alt}</div>'
        f'<div class="mf-stamps">{stamps_html}</div></div></div>'
    )


def stamp(text, kind="red"):
    return f'<span class="mf-stamp {kind}">{text}</span>'


def section(label):
    return f'<div class="mf-sec">{label}</div>'


def step(n, text):
    return f'<div class="mf-step"><div class="n">{n:02d}</div><div class="t">{text}</div></div>'


def who(text):
    return f'<div class="mf-who">{text}</div>'


def note(text):
    return f'<div class="mf-note">{text}</div>'


def grid(pairs):
    cells = "".join(
        f'<div class="mf-cell"><div class="k">{k}</div><div class="v">{v}</div></div>'
        for k, v in pairs
    )
    return f'<div class="mf-grid">{cells}</div>'


def empty_state(lead, examples, hint):
    """
    Shown before the first query. Names what the person can do and gives them
    real sentences to copy, in the register they would actually use. An empty
    screen is an invitation to act, not a blank.
    """
    rows = "".join(
        f'<div class="mf-try"><div class="q">{q}</div><div class="w">{w}</div></div>'
        for q, w in examples
    )
    return (
        f'<div class="mf-empty"><div class="lead">{lead}</div>{rows}'
        f'<div class="mf-hint">{hint}</div></div>'
    )


def provenance(lines):
    return '<div class="mf-prov">' + "<br>".join(lines) + "</div>"