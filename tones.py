#!/usr/bin/env python3
"""Expand one-line artist tone profiles into four XT patches each -> library.json.

Profile line (profiles/*.txt, '#' starts a comment):

    Artist | genre | amp | gain 0-10 | tags | source

amp is a key from AMPS below, gain is the rhythm gain, tags are space-separated
words from TAGS, source is you / spotify / curated. Each artist becomes:

    Cln  clean version of the sound
    Rhy  main rhythm tone
    Ld   lead: more gain, boost, delay
    Sig  signature: every tagged effect at once

Artists that already have hand-tuned patches in patches.json are skipped here.
Run: python tones.py
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROFILES = HERE / "profiles"
LIBRARY = HERE / "library.json"
PATCHES = HERE / "patches.json"
MODELS = json.loads((HERE / "models.json").read_text(encoding="utf-8"))

# key: (amp, cab, mic, family) where family picks the clean partner and gate
AMPS = {
    "twin":       ("Double Verb", "2x12 Blackface", "67 Condenser", "clean"),
    "deluxe":     ("Blackface Lux", "1x12 Blackface", "57 Off Axis", "clean"),
    "twotone":    ("Two-Tone", "2x12 Blackface", "57 Off Axis", "clean"),
    "tweed":      ("Tweed B-Man", "4x10 Tweed", "57 Off Axis", "vintage"),
    "smalltweed": ("Small Tweed", "1x12 Tweed", "57 On Axis", "vintage"),
    "tinytweed":  ("Tiny Tweed", "1x8 Tweed", "57 Off Axis", "vintage"),
    "ac30":       ("Class A-30 TB", "2x12 Class A", "57 Off Axis", "vintage"),
    "ac15":       ("Class A-15", "1x12 Class A", "57 Off Axis", "vintage"),
    "plexi":      ("Plexi 45", "4x12 Green 25's", "57 Off Axis", "vintage"),
    "plexilead":  ("Plexi Lead 100", "4x12 Green 25's", "57 On Axis", "vintage"),
    "variac":     ("Plexi Variac", "4x12 Green 25's", "57 On Axis", "vintage"),
    "jcm800":     ("Brit J-800", "4x12 Green 25's", "57 On Axis", "rock"),
    "jmp":        ("Brit JM Pre", "4x12 Green 25's", "57 On Axis", "rock"),
    "hiwatt":     ("Hiway 100", "4x12 Line 6", "57 Off Axis", "vintage"),
    "matchless":  ("Match D-30", "2x12 Match", "57 Off Axis", "vintage"),
    "matchchief": ("Match Chief", "2x12 Match", "57 Off Axis", "vintage"),
    "supro":      ("Super O", "1x6 Super O", "57 On Axis", "vintage"),
    "gibtone":    ("CC-Gibtone Expo", "1x10 Gibtone", "57 Off Axis", "vintage"),
    "jazz":       ("Jazz Clean", "2x12 Jazz", "67 Condenser", "clean"),
    "l6clean":    ("Line 6 Clean", "4x12 Line 6", "67 Condenser", "clean"),
    "zen":        ("Zen Master", "2x12 Line 6", "57 Off Axis", "vintage"),
    "mesa":       ("Cali Crunch", "4x12 Brit V30's", "57 On Axis", "rock"),
    "soldano":    ("Solo 100", "4x12 Brit V30's", "57 On Axis", "high"),
    "recto":      ("Treadplate Dual", "4x12 Treadplate", "57 On Axis", "high"),
    "diamond":    ("MS-Diamondplate", "4x12 Treadplate", "57 On Axis", "high"),
    "bomber":     ("MS-Bomber Uber", "4x12 Treadplate", "57 On Axis", "high"),
    "jcm2000":    ("MS-Brit J-2000", "4x12 Brit V30's", "57 On Axis", "high"),
    "criminal":   ("MS-Criminal", "4x12 Brit V30's", "57 On Axis", "high"),
    "deity":      ("MS-Deity Lead", "4x12 Brit V30's", "57 On Axis", "high"),
    "insane":     ("Line 6 Insane", "4x12 Line 6", "57 On Axis", "high"),
    "mood":       ("Line 6 Mood", "4x12 Line 6", "57 Off Axis", "rock"),
    "chemx":      ("Line 6 Chemical X", "4x12 Line 6", "57 On Axis", "high"),
    "acoustic":   ("Line 6 Acoustic 2", "No Cab", "67 Condenser", "acoustic"),
}

CLEAN_PARTNER = {"high": "l6clean", "rock": "twin", "acoustic": "acoustic"}

STOMPS = {   # tag: (model, p2 drive, p3 gain/level, p4 tone)
    "fuzz": ("Fuzz Pi", 70, 55, 45),
    "facefuzz": ("Facial Fuzz", 70, 55, 55),
    "octfuzz": ("Octave Fuzz", 65, 55, 50),
    "od": ("Screamer", 25, 70, 55),
    "dist": ("Classic Dist", 55, 55, 50),
}
MODS = {     # tag: (model, Hz, depth, mix)
    "chorus": ("Analog Chorus", 0.8, 45, 40),
    "flanger": ("Jet Flanger", 0.25, 50, 45),
    "phaser": ("Phaser", 0.5, 45, 50),
    "vibe": ("U-Vibe", 1.8, 55, 50),
    "trem": ("Opto Trem", 4.5, 50, 55),
    "rotary": ("Rotary Drum + Horn", 1.2, 50, 55),
}
DELAYS = {   # tag: (model, ms, feedback, mix)
    "delay": ("Analog Delay", 420, 25, 18),
    "slap": ("Tube Echo", 110, 10, 20),
    "dotted": ("Digital Delay", 375, 35, 30),
    "tape": ("Tube Echo", 450, 35, 25),
    "ambient": ("Analog Delay w/ Mod", 550, 45, 32),
    "reverse": ("Reverse", 500, 30, 30),
}
REVERBS = {"spring": "Lux Spring", "plate": "Vintage Plate", "room": "Small Room",
           "hall": "Large Hall", "cavern": "Cavernous"}
OTHER = {"bright", "dark", "scoop", "mids", "comp", "wah", "lofi", "dry", "tight"}
TAGS = set(STOMPS) | set(MODS) | set(DELAYS) | set(REVERBS) | OTHER

SUFFIX = [("cln", "Cln", "clean"), ("rhy", "Rhy", "rhythm"), ("ld", "Ld", "lead"), ("sig", "Sig", "signature")]


def ascii_only(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", ascii_only(s).lower()).strip("_")


def alias(artist):
    a = re.sub(r"^The ", "", ascii_only(artist))
    a = a.replace(" and ", " & ")
    return a if len(a) <= 11 else a[:11].rstrip()


def clamp(v):
    return max(0, min(100, round(v)))


def eq_for(tags, gain):
    b, m, t, p = 50, 55, 55, 50
    if "bright" in tags:
        t, p = t + 10, p + 8
    if "dark" in tags:
        t, p, b = t - 12, p - 10, b + 5
    if "scoop" in tags:
        m, b, t = m - 18, b + 8, t + 5
    if "mids" in tags:
        m = m + 12
    if "tight" in tags or gain >= 8:
        b = b - 5
    return [clamp(x) for x in (b, m, t, p)]


def build(amp_key, drive, tags, *, stomp=None, mod=None, delay=None, reverb=None,
          vol=62, gate=False, comp=False, wah=False, mid_bump=0):
    amp, cab, mic, _ = AMPS[amp_key]
    b, m, t, p = eq_for(tags, drive / 10)
    if "lofi" in tags and amp_key != "acoustic":
        mic = "57 Off Axis"
    patch = {
        "models": {"amp": amp, "cab": cab, "mic": mic},
        "on": {"amp": True, "gate": gate, "comp": comp, "wah": wah, "stomp": bool(stomp),
               "mod": bool(mod), "delay": bool(delay), "reverb": bool(reverb), "eq": False},
        "params": {"drive": clamp(drive), "bass": b, "mid": clamp(m + mid_bump), "treble": t,
                   "presence": p, "chan_vol": vol},
    }
    pr = patch["params"]
    if stomp:
        model, d, g, tone = STOMPS[stomp]
        patch["models"]["stomp"] = model
        pr.update({"stomp_p2": d, "stomp_p3": g, "stomp_p4": tone})
    if mod:
        model, hz, depth, mix = MODS[mod]
        patch["models"]["mod"] = model
        pr.update({"mod_speed_hz": hz, "mod_p2": depth, "mod_mix": mix})
    if delay:
        model, ms, fb, mix = DELAYS[delay]
        patch["models"]["delay"] = model
        pr.update({"delay_ms": ms, "delay_p2": fb, "delay_mix": mix})
    if reverb:
        name, mix, decay = reverb
        patch["models"]["reverb"] = name
        pr.update({"reverb_mix": mix, "reverb_decay": decay})
    if gate:
        pr.update({"gate_db": -50 if drive > 70 else -58, "gate_decay": 20})
    if comp:
        pr.update({"comp_thresh_db": -22, "comp_gain_db": 4})
    return patch


def first(tags, table):
    return next((t for t in tags if t in table), None)


def expand(artist, genre, amp_key, gain, tags):
    family = AMPS[amp_key][3]
    rev_tag = first(tags, REVERBS)
    rev_name = REVERBS[rev_tag] if rev_tag else ("Lux Spring" if family == "clean" else "Small Room")
    dry = "dry" in tags
    stomp = first(tags, STOMPS)
    mod = first(tags, MODS)
    delay = first(tags, DELAYS)
    comp = "comp" in tags
    rhythm_drive = 10 + gain * 7
    high = gain >= 7

    clean_key = CLEAN_PARTNER.get(family, amp_key)
    clean_mod = mod if mod in ("chorus", "vibe", "trem", "phaser", "rotary", "flanger") else None
    out = []
    out.append(build(clean_key, min(25, rhythm_drive) if family != "acoustic" else 20, tags,
                     mod=clean_mod, delay=delay if delay in ("dotted", "ambient", "tape", "delay") else None,
                     reverb=(rev_name, 20, 45), vol=70, comp=comp or family == "acoustic"))
    out.append(build(amp_key, rhythm_drive, tags,
                     stomp=stomp if stomp != "od" or high else None,
                     delay="slap" if "slap" in tags else None,
                     reverb=None if dry else (rev_name, 12, 30),
                     vol=56 if high else 60, gate=high, comp=comp and not high))
    out.append(build(amp_key, rhythm_drive + 15, tags,
                     stomp=stomp or ("od" if family != "acoustic" else None),
                     delay=delay if delay in ("dotted", "tape", "ambient") else "delay",
                     reverb=(rev_name, 15, 40), vol=56 if high else 58, gate=high, mid_bump=8,
                     wah="wah" in tags))
    out.append(build(amp_key, rhythm_drive, tags, stomp=stomp, mod=mod, delay=delay,
                     reverb=(rev_name, 25 if not dry else 8, 55 if "ambient" in tags else 40),
                     vol=56 if high else 60, gate=high, comp=comp, wah="wah" in tags))

    patches = {}
    amp_name = AMPS[amp_key][0]
    for (sfx, short, label), patch in zip(SUFFIX, out):
        fx = [m for m in (patch["models"].get("stomp"), patch["models"].get("mod"),
                          patch["models"].get("delay")) if m]
        patch["artist"] = artist
        patch["genre"] = genre
        patch["name"] = f"{alias(artist)} {short}"
        patch["description"] = f"{artist}: {label}. {patch['models']['amp']}" + (
            f" + {', '.join(fx)}" if fx else "")
        patches[f"{slug(artist)}_{sfx}"] = patch
    return patches


def parse(line, where):
    parts = [p.strip() for p in line.split("|")]
    if len(parts) != 6:
        sys.exit(f"{where}: expected 6 fields: {line}")
    artist, genre, amp, gain, tags, source = parts
    if amp not in AMPS:
        sys.exit(f"{where}: unknown amp '{amp}'")
    tags = tags.split()
    bad = [t for t in tags if t not in TAGS]
    if bad:
        sys.exit(f"{where}: unknown tags {bad}")
    return {"artist": artist, "genre": genre, "amp": amp, "gain": int(gain),
            "tags": tags, "source": source}


def main():
    for key, (amp, cab, mic, _) in AMPS.items():
        assert amp in MODELS["amp"], f"amp model '{amp}'"
        assert cab in MODELS["cab"], f"cab '{cab}'"
    hand = json.loads(PATCHES.read_text(encoding="utf-8"))
    hand_artists = {p.get("artist") for p in hand.values()}
    artists, patches, seen = [], {}, set()
    for f in sorted(PROFILES.glob("*.txt")):
        for n, raw in enumerate(f.read_text(encoding="utf-8-sig").splitlines(), 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            prof = parse(line, f"{f.name}:{n}")
            if prof["artist"].lower() in seen:
                continue
            seen.add(prof["artist"].lower())
            artists.append(prof)
            if prof["artist"] in hand_artists:
                continue
            patches.update(expand(prof["artist"], prof["genre"], prof["amp"], prof["gain"], prof["tags"]))
    for name in hand_artists - {a["artist"] for a in artists}:
        artists.append({"artist": name, "genre": "", "source": "hand"})
    for p in patches.values():
        assert len(p["name"]) <= 16, p["name"]
    LIBRARY.write_text(json.dumps({"artists": artists, "patches": patches}, indent=1) + "\n",
                       encoding="utf-8")
    print(f"{len(artists)} artists, {len(patches)} generated patches -> library.json "
          f"({len(hand)} hand-tuned in patches.json)")


if __name__ == "__main__":
    main()
