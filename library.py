#!/usr/bin/env python3
"""Build the 128-slot library into patches.json.

Banks 1-20: top Spotify artists, four patches each.
Banks 21-22: the starter patches plus three utility platforms.
Banks 23-32: players with great tone outside that listening.

Each patch gets a "slot" (1A-32D). `python podxt.py --usb store-library` writes them all.
Run: python library.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PATCHES = HERE / "patches.json"
MODELS = json.loads((HERE / "models.json").read_text(encoding="utf-8"))

# ------------------------------------------------------------ building blocks

def fuzz(model, drive, gain=55, tone=50):
    return model, {"stomp_p2": drive, "stomp_p3": gain, "stomp_p4": tone}


def scomp(model="Red Comp", sustain=50, level=55):
    return model, {"stomp_p2": sustain, "stomp_p3": level}


def tube_drive(drive, treble=55, gain=60, bass=50):
    return "FX-Tube Drive", {"stomp_p2": drive, "stomp_p3": treble, "stomp_p4": gain, "stomp_p5": bass}


def mod(model, hz, depth=50, mix=50, p3=None, p4=None):
    p = {"mod_speed_hz": hz, "mod_p2": depth, "mod_mix": mix}
    if p3 is not None:
        p["mod_p3"] = p3
    if p4 is not None:
        p["mod_p4"] = p4
    return model, p


def dly(model, ms, fb=25, mix=20, p3=None, p4=None):
    p = {"delay_ms": ms, "delay_p2": fb, "delay_mix": mix}
    if p3 is not None:
        p["delay_p3"] = p3
    if p4 is not None:
        p["delay_p4"] = p4
    return model, p


def rev(model="Small Room", mix=15, decay=30):
    return model, mix, decay


LIB = []


def P(name, desc, amp, cab, mic, drive, eq, vol=65,
      stomp=None, md=None, delay=None, reverb=rev(), gate=None, comp=None, wah=False):
    """eq = (bass, mid, treble, presence)."""
    b, m, t, pr = eq
    patch = {
        "name": name,
        "description": desc,
        "models": {"amp": amp, "cab": cab, "mic": mic},
        "on": {"amp": True, "gate": bool(gate), "comp": bool(comp), "wah": wah,
               "stomp": bool(stomp), "mod": bool(md), "delay": bool(delay),
               "reverb": bool(reverb), "eq": False},
        "params": {"drive": drive, "bass": b, "mid": m, "treble": t,
                   "presence": pr, "chan_vol": vol},
    }
    p = patch["params"]
    if stomp:
        patch["models"]["stomp"] = stomp[0]
        p.update(stomp[1])
    if md:
        patch["models"]["mod"] = md[0]
        p.update(md[1])
    if delay:
        patch["models"]["delay"] = delay[0]
        p.update(delay[1])
    if reverb:
        patch["models"]["reverb"] = reverb[0]
        p["reverb_mix"], p["reverb_decay"] = reverb[1], reverb[2]
    if gate:
        p["gate_db"], p["gate_decay"] = gate
    if comp:
        p["comp_thresh_db"], p["comp_gain_db"] = comp
    LIB.append((key_for(name), patch))


def keep(key):
    """Reuse a hand-tuned patch from the existing patches.json."""
    patch = {k: v for k, v in EXISTING[key].items() if k != "slot"}
    patch.setdefault("name", key.replace("_", " ").title())
    patch["on"] = {"wah": False, "eq": False, **patch["on"]}
    LIB.append((key, patch))


def key_for(name):
    return "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")


EXISTING = json.loads(PATCHES.read_text(encoding="utf-8"))

# Cleans sit around chan vol 70, crunch 62, high gain 55 so levels roughly match.

# ------------------------------------------------------------ 1 Smashing Pumpkins
P("SP Cherub Rock", "Big Muff wall into a cranked Marshall", "Plexi 45", "4x12 Green 25's", "57 Off Axis",
  45, (60, 45, 55, 50), 58, stomp=fuzz("Fuzz Pi", 75, 55, 45), gate=(-55, 30))
P("SP 1979", "Clean jangle, chorus shimmer, short delay", "Double Verb", "2x12 Blackface", "67 Condenser",
  25, (45, 55, 62, 50), 70, md=mod("Analog Chorus", 0.8, 40, 35), delay=dly("Digital Delay", 280, 20, 15),
  reverb=rev("Medium Hall", 18, 40))
P("SP Zero", "Tight fuzz drive with the gate clamped", "Brit J-800", "4x12 Brit V30's", "57 On Axis",
  55, (65, 40, 55, 55), 55, stomp=fuzz("Fuzz Pi", 85, 50, 40), gate=(-45, 15))
P("SP Mayonaise", "Soft fuzz bloom with chorus", "Plexi 45", "4x12 Green 25's", "421 Dynamic",
  35, (55, 55, 50, 45), 60, stomp=fuzz("Fuzz Pi", 55, 55, 40), md=mod("Analog Chorus", 0.5, 45, 35),
  reverb=rev("Large Hall", 20, 50))

# ------------------------------------------------------------ 2 Placebo
P("Pure Morning", "Droning fuzz riff, dry and mid-forward", "Brit J-800", "4x12 Brit V30's", "57 Off Axis",
  35, (55, 60, 55, 50), 60, stomp=fuzz("Facial Fuzz", 70, 55, 50))
P("Every You Every", "Bright Marshall crunch, punchy", "Brit J-800", "4x12 Green 25's", "57 On Axis",
  55, (50, 60, 62, 55), 60, gate=(-60, 25))
P("Placebo Special", "Overdriven chorus, glassy top", "Class A-30 TB", "2x12 Class A", "57 Off Axis",
  45, (45, 55, 60, 55), 62, md=mod("Analog Chorus", 1.0, 50, 40))
P("Nancy Boy", "Screamer-pushed Marshall for leads", "Brit J-800", "4x12 Brit V30's", "57 On Axis",
  50, (50, 65, 60, 55), 58, stomp=fuzz("Screamer", 30, 70, 55), delay=dly("Analog Delay", 320, 15, 12))

# ------------------------------------------------------------ 3 Arctic Monkeys
P("AM Do I Wanna", "Fuzzy, woolly riff tone, slow-burn", "Hiway 100", "4x12 Green 20's", "57 Off Axis",
  30, (60, 55, 45, 40), 60, stomp=fuzz("Fuzz Pi", 70, 55, 35), reverb=rev("Small Room", 10, 25))
P("AM R U Mine", "Spitty fuzz into a Plexi", "Plexi Lead 100", "4x12 Green 25's", "57 On Axis",
  40, (55, 60, 60, 55), 58, stomp=fuzz("Facial Fuzz", 75, 55, 55), gate=(-60, 25))
P("AM 505", "Clean with slow tremolo and spring", "Double Verb", "2x12 Blackface", "67 Condenser",
  20, (50, 50, 55, 45), 70, md=mod("Opto Trem", 3.5, 50, 60), reverb=rev("Lux Spring", 25, 45))
P("AM Brianstorm", "Fast bright crunch, AC30 bite", "Class A-30 TB", "2x12 Class A", "57 On Axis",
  60, (45, 60, 65, 60), 58, gate=(-55, 20))

# ------------------------------------------------------------ 4 The Strokes
P("Strokes LastNite", "Hot Rod style edge-of-breakup, bright and thin", "Blackface Lux", "2x12 Blackface", "57 On Axis",
  45, (40, 60, 65, 60), 62, stomp=fuzz("Screamer", 20, 60, 60), reverb=rev("Small Room", 6, 20))
P("Strokes Reptilia", "Driving crunch rhythm, dry", "Blackface Lux", "2x12 Blackface", "57 On Axis",
  55, (45, 60, 60, 55), 60, stomp=fuzz("Screamer", 30, 65, 55), reverb=None)
P("Strokes Someday", "Cleaner jangle with a touch of hair", "Two-Tone", "2x12 Blackface", "57 Off Axis",
  35, (45, 55, 60, 55), 64, reverb=rev("Small Room", 10, 25))
P("Strokes Lead", "Boosted lead for those wiry solos", "Blackface Lux", "2x12 Blackface", "57 On Axis",
  60, (40, 65, 60, 55), 60, stomp=fuzz("Screamer", 45, 70, 55), delay=dly("Analog Delay", 300, 15, 10))

# ------------------------------------------------------------ 5 Stereophonics
P("Stereo Dakota", "Chiming crunch with dotted delay", "Class A-30 TB", "2x12 Class A", "57 Off Axis",
  45, (50, 55, 60, 55), 60, delay=dly("Digital Delay", 340, 30, 20), reverb=rev("Medium Hall", 15, 40))
P("Stereo Nice Day", "Acoustic-style strum", "Line 6 Acoustic 2", "No Cab", "67 Condenser",
  20, (45, 50, 55, 50), 70, comp=(-20, 3), reverb=rev("Small Room", 15, 30))
P("Stereo Bartender", "Bluesy Brit crunch", "Brit JM Pre", "4x12 Green 25's", "57 Off Axis",
  50, (55, 55, 55, 50), 60)
P("Stereo Lead", "Warm sustaining lead", "Brit JM Pre", "4x12 Green 25's", "57 On Axis",
  65, (55, 60, 55, 50), 58, stomp=fuzz("Screamer", 35, 65, 50), delay=dly("Analog Delay", 380, 20, 15))

# ------------------------------------------------------------ 6 Muse
P("Muse PlugInBaby", "Fuzz Factory style squeal into Marshall", "Brit J-800", "4x12 Brit V30's", "57 On Axis",
  60, (55, 50, 60, 60), 55, stomp=fuzz("Facial Fuzz", 90, 50, 60), gate=(-45, 20))
P("Muse Hysteria", "Tight high gain, huge low end", "Treadplate Dual", "4x12 Treadplate", "57 Off Axis",
  60, (65, 45, 55, 55), 55, gate=(-45, 20))
P("Muse Knights", "Saturated lead with delay tails", "Line 6 Insane", "4x12 Brit V30's", "57 On Axis",
  55, (55, 55, 55, 50), 55, delay=dly("Digital Delay", 420, 30, 18), gate=(-50, 20))
P("Muse Clean Arp", "Glassy clean for arpeggios", "Double Verb", "2x12 Blackface", "67 Condenser",
  20, (45, 50, 60, 50), 70, delay=dly("Ping Pong", 360, 30, 22), reverb=rev("Large Hall", 22, 55))

# ------------------------------------------------------------ 7 Radiohead
P("RH Paranoid", "Fuzz lead and crunchy Brit grind", "Brit J-800", "4x12 Green 25's", "57 Off Axis",
  50, (50, 55, 60, 55), 58, stomp=fuzz("Classic Dist", 45, 55, 55))
P("RH Creep Crunch", "The dead-note kerrang", "Blackface Lux", "4x12 Green 25's", "57 On Axis",
  45, (55, 50, 60, 55), 56, stomp=fuzz("Classic Dist", 75, 55, 50), gate=(-50, 15))
P("RH Weird Fishes", "Clean arps with tight delay", "Double Verb", "2x12 Blackface", "67 Condenser",
  18, (45, 55, 58, 45), 70, delay=dly("Digital Delay", 230, 30, 25), reverb=rev("Medium Hall", 20, 45))
P("RH Street Spirt", "Warm clean arpeggio, deep room", "Blackface Lux", "1x12 Blackface", "67 Condenser",
  22, (50, 50, 55, 45), 70, reverb=rev("Large Hall", 25, 55))

# ------------------------------------------------------------ 8 Rage Against The Machine
P("RATM Bombtrack", "JCM800 with mids forward, tight", "Brit J-800", "4x12 Green 25's", "57 On Axis",
  60, (55, 70, 55, 50), 56, gate=(-50, 20))
P("RATM Killing", "Drop D crunch, low and tight", "Brit J-800", "4x12 Brit V30's", "57 On Axis",
  65, (60, 65, 55, 50), 55, gate=(-45, 15))
P("RATM Bulls Wah", "Wah parked for the scratch solo", "Brit J-800", "4x12 Green 25's", "57 On Axis",
  60, (55, 65, 55, 50), 56, wah=True, gate=(-50, 15))
P("RATM Morello Ld", "Boosted lead with slap delay", "Brit J-800", "4x12 Green 25's", "57 On Axis",
  65, (55, 70, 55, 50), 56, stomp=fuzz("Screamer", 25, 70, 50), delay=dly("Digital Delay", 120, 10, 15))

# ------------------------------------------------------------ 9 Future Islands
P("FI Tall Grass", "Soft chorused clean", "Jazz Clean", "2x12 Jazz", "67 Condenser",
  20, (50, 50, 55, 45), 70, md=mod("Analog Chorus", 0.7, 55, 45), reverb=rev("Medium Hall", 20, 45))
P("FI Seasons", "Bright clean with chorus and echo", "Double Verb", "2x12 Blackface", "67 Condenser",
  22, (45, 50, 62, 50), 70, md=mod("Sine Chorus", 0.9, 45, 40), delay=dly("Digital Delay", 330, 25, 18),
  reverb=rev("Large Hall", 20, 50))
P("FI Bassline", "Round, dark clean for low melodies", "Jazz Clean", "2x12 Jazz", "421 Dynamic",
  25, (60, 50, 40, 35), 70, comp=(-22, 4), reverb=rev("Small Room", 10, 25))
P("FI Dreamwash", "Slow chorus, long hall", "Jazz Clean", "2x12 Jazz", "67 Condenser",
  15, (50, 45, 55, 45), 68, md=mod("Analog Chorus", 0.3, 70, 50), delay=dly("Analog Delay", 500, 35, 25),
  reverb=rev("Cavernous", 30, 70))

# ------------------------------------------------------------ 10 Fontaines D.C.
keep("fontaines_dc")
P("FDC Starburster", "Snarling AC30 fuzz", "Class A-30 TB", "2x12 Class A", "57 On Axis",
  55, (50, 60, 65, 60), 56, stomp=fuzz("Fuzz Pi", 70, 55, 55), gate=(-55, 20))
P("FDC Better Land", "Punchy post-punk crunch, dry", "Class A-30 TB", "2x12 Class A", "57 On Axis",
  50, (45, 60, 65, 60), 60, reverb=rev("Small Room", 8, 20))
P("FDC Drone", "Flanged drone into a big hall", "Class A-30 TB", "2x12 Class A", "57 Off Axis",
  40, (50, 55, 60, 55), 60, md=mod("Jet Flanger", 0.2, 50, 45, p3=40, p4=50), reverb=rev("Large Hall", 25, 60))

# ------------------------------------------------------------ 11 Oasis
P("Oasis Supersonc", "Wall of Marshall crunch", "Brit J-800", "4x12 Green 25's", "57 Off Axis",
  60, (55, 60, 55, 50), 56, stomp=fuzz("Screamer", 25, 65, 50), reverb=rev("Medium Hall", 12, 35))
P("Oasis Wonderwal", "Strummed acoustic", "Line 6 Acoustic 2", "No Cab", "67 Condenser",
  20, (50, 50, 55, 50), 70, comp=(-20, 3), reverb=rev("Small Room", 15, 30))
P("Oasis LiveForev", "Singing lead with delay", "Brit J-800", "4x12 Green 25's", "57 On Axis",
  65, (55, 60, 55, 50), 56, stomp=fuzz("Screamer", 30, 65, 50), delay=dly("Analog Delay", 420, 25, 18))
P("Oasis Champagne", "Phased crunch, wide hall", "Brit J-800", "4x12 Green 25's", "57 Off Axis",
  55, (55, 55, 55, 50), 58, md=mod("Phaser", 0.4, 40, 50), reverb=rev("Large Hall", 18, 50))

# ------------------------------------------------------------ 12 More Manics, one per era
# From Bradfield's documented rig: Les Paul Custom / Tele Thinline into a Marshall
# JCM900 (Brit J-800 is the closest XT model), TS-808/TS9DX (Screamer), Boss FZ-2 (Fuzz Pi).
P("Manics YouLoveUs", "Generation Terrorists glam: FZ-2 fuzz into Marshall", "Brit J-800", "4x12 Brit V30's", "57 Off Axis",
  45, (55, 60, 60, 55), 56, stomp=fuzz("Fuzz Pi", 60, 55, 55), gate=(-55, 20))
P("Manics Faster", "Holy Bible: dry, mid-heavy Marshall, Screamer tightening", "Brit J-800", "4x12 Green 25's", "57 On Axis",
  60, (50, 70, 58, 55), 56, stomp=fuzz("Screamer", 15, 75, 55), gate=(-55, 20), reverb=None)
P("Manics Australia", "Everything Must Go anthem crunch", "Brit J-800", "4x12 Green 25's", "57 Off Axis",
  55, (55, 60, 58, 55), 58, stomp=fuzz("Screamer", 25, 65, 50), reverb=rev("Medium Hall", 15, 40))
P("Manics Autumnsng", "Send Away the Tigers: Les Paul, JCM900, TS9DX", "Brit J-800", "4x12 Green 25's", "57 On Axis",
  62, (55, 62, 58, 55), 56, stomp=fuzz("Screamer", 30, 70, 55), delay=dly("Analog Delay", 380, 20, 12),
  reverb=rev("Medium Hall", 12, 35))

# ------------------------------------------------------------ 13 The Verve
P("Verve BitterSwt", "Bright clean strum", "Double Verb", "2x12 Blackface", "67 Condenser",
  25, (45, 55, 60, 50), 70, reverb=rev("Medium Hall", 18, 40))
P("Verve Lucky Man", "Light crunch with delay", "Class A-30 TB", "2x12 Class A", "57 Off Axis",
  40, (50, 55, 58, 50), 62, delay=dly("Tube Echo", 380, 25, 18, 30, 30), reverb=rev("Medium Hall", 15, 40))
P("Verve McCabe", "Nick McCabe wash: flange, echo, hall", "Class A-30 TB", "2x12 Class A", "57 Off Axis",
  40, (50, 50, 55, 50), 60, md=mod("Line 6 Flanger", 0.15, 60, 45), delay=dly("Tube Echo", 600, 45, 35, 40, 35),
  reverb=rev("Cavernous", 30, 70))
P("Verve Sonnet", "Acoustic-ish strum with chamber", "Line 6 Acoustic 2", "No Cab", "67 Condenser",
  20, (50, 50, 55, 50), 70, reverb=rev("Rich Chamber", 18, 40))

# ------------------------------------------------------------ 14 Arcade Fire
P("AF Wake Up", "Big chorus-of-guitars crunch", "Class A-30 TB", "2x12 Class A", "57 Off Axis",
  50, (50, 55, 60, 55), 60, reverb=rev("Large Hall", 22, 55))
P("AF Rebellion", "Bright rhythmic crunch", "Blackface Lux", "2x12 Blackface", "57 On Axis",
  45, (45, 60, 60, 55), 62, reverb=rev("Medium Hall", 15, 40))
P("AF Ready Start", "Fuzzy driving rhythm", "Plexi 45", "4x12 Green 25's", "57 Off Axis",
  40, (55, 55, 55, 50), 60, stomp=fuzz("Facial Fuzz", 55, 55, 50))
P("AF Jangle", "Clean jangle, short room", "Two-Tone", "2x12 Blackface", "67 Condenser",
  25, (45, 55, 62, 55), 68, reverb=rev("Small Room", 15, 30))

# ------------------------------------------------------------ 15 Beck
P("Beck Loser", "Lo-fi tiny-amp grit", "Tiny Tweed", "1x8 Tweed", "57 Off Axis",
  55, (50, 60, 50, 45), 62, delay=dly("FX-Low Rez", 120, 10, 15))
P("Beck Devils Hr", "Fuzzy, swaggering riff", "Small Tweed", "1x12 Tweed", "57 On Axis",
  50, (55, 60, 55, 50), 58, stomp=fuzz("Fuzz Pi", 60, 55, 50))
P("Beck Sea Change", "Warm clean, slow trem, plate", "Blackface Lux", "1x12 Blackface", "67 Condenser",
  20, (50, 50, 52, 45), 70, md=mod("Opto Trem", 2.5, 40, 35), reverb=rev("Vintage Plate", 25, 50))
P("Beck Odelay", "Crunchy tweed with slapback", "Tweed B-Man", "4x10 Tweed", "57 Off Axis",
  45, (50, 55, 55, 50), 62, delay=dly("Tube Echo", 110, 10, 20, 30, 40))

# ------------------------------------------------------------ 16 Marilyn Manson
P("Manson Beautful", "Industrial high gain, gated", "Treadplate Dual", "4x12 Treadplate", "57 On Axis",
  65, (65, 40, 60, 55), 55, gate=(-40, 15))
P("Manson DopeShow", "Glam fuzz grind", "Brit J-800", "4x12 Brit V30's", "57 Off Axis",
  45, (60, 50, 55, 50), 56, stomp=fuzz("Fuzz Pi", 70, 55, 45), gate=(-50, 20))
P("Manson SweetDrm", "Creepy clean with phaser", "Line 6 Clean", "4x12 Line 6", "67 Condenser",
  15, (50, 45, 55, 45), 68, md=mod("Phaser", 0.5, 50, 45), reverb=rev("Dark Hall", 20, 50))
P("Manson Heavy", "Modern high gain wall (Metal Shop)", "MS-Bomber Uber", "4x12 Treadplate", "57 On Axis",
  55, (60, 45, 55, 55), 55, gate=(-40, 15))

# ------------------------------------------------------------ 17 The Killers
P("Killers Brghtsd", "Bright drive, dotted-eighth delay", "Class A-30 TB", "2x12 Class A", "57 Off Axis",
  45, (45, 55, 62, 55), 60, delay=dly("Digital Delay", 410, 30, 22), reverb=rev("Medium Hall", 15, 40))
P("Killers WhenYou", "Chorused clean pop", "Double Verb", "2x12 Blackface", "67 Condenser",
  22, (45, 55, 60, 50), 70, md=mod("Analog Chorus", 0.9, 45, 40), reverb=rev("Medium Hall", 18, 40))
P("Killers Human", "Clean arpeggio with ping pong", "Double Verb", "2x12 Blackface", "67 Condenser",
  20, (45, 50, 60, 50), 70, delay=dly("Ping Pong", 340, 30, 22), reverb=rev("Large Hall", 20, 50))
P("Killers Lead", "Driven lead with delay", "Brit J-800", "4x12 Green 25's", "57 On Axis",
  55, (50, 60, 60, 55), 58, stomp=fuzz("Screamer", 30, 65, 55), delay=dly("Digital Delay", 400, 25, 18))

# ------------------------------------------------------------ 18 Manic Street Preachers
P("Manics Design", "Les Paul into Plexi, anthemic", "Plexi 45", "4x12 Green 25's", "57 Off Axis",
  55, (55, 55, 58, 55), 58, reverb=rev("Medium Hall", 15, 40))
P("Manics Motorcyc", "Tele riff: Shredmaster-style Marshall grit, CH-1 chorus, delay", "Brit J-800", "4x12 Green 25's", "57 On Axis",
  55, (50, 60, 62, 55), 58, md=mod("Sine Chorus", 0.9, 40, 35), delay=dly("Analog Delay", 450, 30, 20))
P("Manics Bradfld", "Boosted Bradfield lead", "Plexi Lead 100", "4x12 Green 25's", "57 On Axis",
  60, (55, 65, 58, 55), 56, stomp=fuzz("Screamer", 35, 70, 55), delay=dly("Analog Delay", 380, 20, 15))
P("Manics Tolerate", "Clean with echo, wide room", "Double Verb", "2x12 Blackface", "67 Condenser",
  25, (45, 55, 58, 50), 70, delay=dly("Digital Delay", 360, 30, 20), reverb=rev("Large Hall", 18, 45))

# ------------------------------------------------------------ 19 Blur
P("Blur Song 2", "Fuzz explosion", "Hiway 100", "4x12 Green 20's", "57 On Axis",
  55, (60, 55, 55, 55), 55, stomp=fuzz("Fuzz Pi", 85, 55, 50), gate=(-50, 20))
P("Blur Coffee TV", "Coxon wiry crunch", "Class A-30 TB", "2x12 Class A", "57 On Axis",
  50, (45, 60, 62, 60), 60, reverb=rev("Small Room", 10, 25))
P("Blur Beetlebum", "Woozy octave fuzz", "Class A-30 TB", "2x12 Class A", "57 Off Axis",
  40, (55, 55, 55, 50), 58, stomp=fuzz("Octave Fuzz", 60, 50, 45), reverb=rev("Medium Hall", 15, 40))
P("Blur Tender", "Clean, warm, gospel-ish", "Blackface Lux", "1x12 Blackface", "67 Condenser",
  20, (50, 50, 55, 45), 70, reverb=rev("Rich Chamber", 20, 45))

# ------------------------------------------------------------ 20 Still Corners
P("SC The Trip", "Dreamy clean, chorus and long delay", "Double Verb", "2x12 Blackface", "67 Condenser",
  18, (45, 50, 58, 45), 68, md=mod("Analog Chorus", 0.5, 55, 45), delay=dly("Analog Delay", 520, 40, 28),
  reverb=rev("Large Hall", 30, 65))
P("SC Strange Plsr", "Twangy trem with spring", "Blackface Lux", "1x12 Blackface", "67 Condenser",
  22, (45, 50, 60, 50), 70, md=mod("Bias Trem", 5.0, 50, 50), reverb=rev("King Spring", 30, 55))
P("SC Slow Tape", "Warbly tape echo", "Double Verb", "2x12 Blackface", "67 Condenser",
  18, (45, 50, 55, 45), 68, delay=dly("FX-Tape Echo", 450, 35, 30), reverb=rev("Large Hall", 25, 60))
P("SC Shimmer", "Vibrato clean in a cavern", "Jazz Clean", "2x12 Jazz", "67 Condenser",
  15, (45, 50, 58, 45), 68, md=mod("U-Vibe", 1.5, 50, 45), reverb=rev("Cavernous", 35, 75))

# ------------------------------------------------------------ 21-22 handoff + platforms
keep("mayer_clean")
keep("mayer_gravity")
keep("deftones_heavy")
keep("deftones_clean")
keep("the_xx")
P("Clean Platform", "Neutral clean for pedals and tweaking", "Double Verb", "2x12 Blackface", "67 Condenser",
  25, (50, 50, 55, 50), 70, reverb=rev("Small Room", 12, 30))
P("Crunch Platform", "Neutral Marshall crunch", "Plexi 45", "4x12 Green 25's", "57 Off Axis",
  50, (55, 55, 55, 50), 60)
P("Lead Platform", "Smooth lead, delay and hall", "Brit J-800", "4x12 Green 25's", "57 On Axis",
  65, (55, 60, 55, 50), 56, stomp=fuzz("Screamer", 30, 65, 50), delay=dly("Analog Delay", 420, 25, 18),
  reverb=rev("Medium Hall", 15, 40))

# ------------------------------------------------------------ 23 Johnny Marr (The Smiths)
P("Marr How Soon", "The tremolo: deep bias trem on a clean", "Double Verb", "2x12 Blackface", "57 Off Axis",
  25, (50, 55, 58, 50), 68, md=mod("Bias Trem", 6.5, 70, 70), reverb=rev("Medium Hall", 18, 45))
P("Marr Charming", "Chorused jangle, layered", "Double Verb", "2x12 Blackface", "67 Condenser",
  22, (45, 55, 62, 55), 70, md=mod("Analog Chorus", 1.0, 40, 35), reverb=rev("Small Room", 15, 30))
P("Marr Bigmouth", "Bright compressed crunch", "Class A-30 TB", "2x12 Class A", "57 Off Axis",
  40, (45, 60, 62, 55), 62, comp=(-20, 4))
P("Marr Panic", "Jangly clean with compression", "Two-Tone", "2x12 Blackface", "67 Condenser",
  28, (45, 55, 62, 55), 68, comp=(-22, 4), reverb=rev("Small Room", 12, 25))

# ------------------------------------------------------------ 24 Shoegaze
P("MBV Only Shallw", "Fuzz wall with reverse smear", "Plexi 45", "4x12 Green 25's", "57 Off Axis",
  45, (55, 50, 55, 50), 58, stomp=fuzz("Fuzz Pi", 80, 55, 50), delay=dly("Reverse", 500, 30, 30),
  reverb=rev("Cavernous", 30, 70))
P("Slowdive Alison", "Chorus wash, huge reverb", "Double Verb", "2x12 Blackface", "67 Condenser",
  20, (45, 50, 55, 45), 66, md=mod("Analog Chorus", 0.5, 65, 50), delay=dly("Analog Delay w/ Mod", 600, 45, 35, 30, 40),
  reverb=rev("Cavernous", 40, 80))
P("Ride Vapour", "Jangle with echo trails", "Class A-30 TB", "2x12 Class A", "67 Condenser",
  30, (45, 55, 62, 55), 64, md=mod("Analog Chorus", 0.8, 40, 35), delay=dly("Digital Delay", 420, 40, 28),
  reverb=rev("Large Hall", 25, 60))
P("MBV Soon", "Glide fuzz with flange", "Plexi 45", "4x12 Green 25's", "57 Off Axis",
  40, (55, 50, 55, 50), 58, stomp=fuzz("Fuzz Pi", 65, 55, 50), md=mod("Line 6 Flanger", 0.2, 50, 40),
  reverb=rev("Large Hall", 25, 60))

# ------------------------------------------------------------ 25 The Edge (U2)
P("Edge Streets", "Dotted-eighth delay over AC30 chime", "Class A-30 TB", "2x12 Class A", "57 Off Axis",
  35, (40, 55, 65, 60), 62, delay=dly("Digital Delay", 375, 35, 35), reverb=rev("Large Hall", 15, 45))
P("Edge WithOrWith", "Infinite-sustain style ambient pad", "Class A-30 TB", "2x12 Class A", "67 Condenser",
  30, (45, 50, 60, 50), 60, stomp=("Auto Swell", {"stomp_p2": 60, "stomp_p3": 60}),
  delay=dly("Analog Delay w/ Mod", 500, 50, 35, 25, 35), reverb=rev("Cavernous", 35, 75))
P("Edge Sunday", "Edgy crunch with delay", "Class A-30 TB", "2x12 Class A", "57 On Axis",
  55, (45, 60, 62, 60), 58, delay=dly("Digital Delay", 340, 25, 20))
P("Edge Pride", "Chimey drive with 8th delay", "Class A-30 TB", "2x12 Class A", "57 Off Axis",
  45, (40, 55, 65, 60), 60, delay=dly("Digital Delay", 270, 35, 30), reverb=rev("Large Hall", 15, 45))

# ------------------------------------------------------------ 26 David Gilmour
P("Gilmour Numb", "Muff into Hiwatt, delay and hall", "Hiway 100", "4x12 Line 6", "57 Off Axis",
  35, (50, 55, 55, 50), 58, stomp=fuzz("Fuzz Pi", 60, 55, 45), delay=dly("Digital Delay", 440, 30, 22),
  reverb=rev("Large Hall", 22, 55))
P("Gilmour Shine", "Clean with chorus and delay", "Hiway 100", "4x12 Line 6", "67 Condenser",
  20, (45, 50, 60, 50), 66, md=mod("Analog Chorus", 0.6, 50, 40), delay=dly("Digital Delay", 480, 30, 22),
  reverb=rev("Large Hall", 20, 50))
P("Gilmour Time", "Singing lead, compressed", "Hiway 100", "4x12 Line 6", "57 On Axis",
  40, (50, 60, 55, 50), 58, stomp=fuzz("Screamer", 50, 65, 50), comp=(-25, 4),
  delay=dly("Digital Delay", 430, 30, 22), reverb=rev("Large Hall", 18, 50))
P("Gilmour Leslie", "Rotary clean", "Hiway 100", "4x12 Line 6", "67 Condenser",
  25, (50, 50, 55, 50), 64, md=mod("Rotary Drum + Horn", 1.2, 50, 55), reverb=rev("Medium Hall", 15, 40))

# ------------------------------------------------------------ 27 Jack White
P("White SevenNat", "Octave-up fuzz riff", "Small Tweed", "1x12 Tweed", "57 On Axis",
  50, (55, 60, 55, 50), 56, stomp=fuzz("Octave Fuzz", 75, 55, 55))
P("White Ball Bisc", "Raw fuzz, ragged", "Tweed B-Man", "4x10 Tweed", "57 On Axis",
  55, (55, 60, 60, 55), 56, stomp=fuzz("Facial Fuzz", 70, 55, 55))
P("White Clean", "Dry, honky clean", "Small Tweed", "1x12 Tweed", "57 Off Axis",
  30, (50, 60, 55, 50), 64, reverb=None)
P("White Icky", "Fuzz lead with slap", "Small Tweed", "1x12 Tweed", "57 On Axis",
  55, (50, 60, 60, 55), 56, stomp=fuzz("Fuzz Pi", 80, 55, 60), delay=dly("Tube Echo", 100, 10, 15, 20, 40))

# ------------------------------------------------------------ 28 Queens of the Stone Age
P("QOTSA No One", "Mid-heavy, tight, dry", "Brit JM Pre", "4x12 Green 25's", "57 On Axis",
  60, (40, 70, 55, 50), 56, gate=(-50, 15), reverb=None)
P("QOTSA GoWithFlw", "Driving fuzzy rhythm", "Plexi 45", "4x12 Green 25's", "57 On Axis",
  55, (45, 65, 55, 50), 56, stomp=fuzz("Classic Dist", 40, 55, 50), gate=(-50, 15))
P("QOTSA Little Ss", "Bouncy crunch with mids", "Brit JM Pre", "4x12 Green 25's", "57 On Axis",
  50, (45, 65, 58, 50), 58)
P("QOTSA MakeItWit", "Warm clean groove", "Blackface Lux", "1x12 Blackface", "57 Off Axis",
  25, (50, 55, 55, 45), 68, reverb=rev("Small Room", 15, 30))

# ------------------------------------------------------------ 29 Post-punk greats
P("Verlaine Marque", "Television: thin, bright, edge of breakup", "Two-Tone", "2x12 Blackface", "57 On Axis",
  40, (40, 60, 65, 60), 62, reverb=rev("Small Room", 12, 25))
P("Interpol Untitl", "Clean with a long echo", "Double Verb", "2x12 Blackface", "57 Off Axis",
  25, (45, 55, 60, 50), 68, delay=dly("Digital Delay", 450, 35, 25), reverb=rev("Large Hall", 20, 50))
P("Interpol Evil", "Mid-dirty driving rhythm", "Class A-30 TB", "2x12 Class A", "57 On Axis",
  45, (45, 60, 60, 55), 60, reverb=rev("Small Room", 10, 25))
P("Cure Pictures", "Robert Smith chorus and flange", "Jazz Clean", "2x12 Jazz", "67 Condenser",
  20, (45, 50, 60, 50), 68, md=mod("Jet Flanger", 0.3, 50, 45, p3=40, p4=40), delay=dly("Digital Delay", 380, 30, 20),
  reverb=rev("Large Hall", 22, 55))

# ------------------------------------------------------------ 30 Groove and desert
P("Khruangbin", "Mid-scooped clean, drenched spring", "Double Verb", "2x12 Blackface", "67 Condenser",
  25, (55, 40, 55, 45), 68, reverb=rev("King Spring", 35, 55))
P("Mdou Moctar", "Fuzzy desert lead", "Class A-30 TB", "2x12 Class A", "57 On Axis",
  50, (45, 60, 62, 55), 58, stomp=fuzz("Screamer", 55, 60, 55), delay=dly("Analog Delay", 300, 20, 15))
P("Knopfler Sultan", "Clean Strat bite, compressed", "Blackface Lux", "1x12 Blackface", "57 Off Axis",
  30, (45, 60, 60, 55), 66, comp=(-22, 4), reverb=rev("Medium Hall", 15, 35))
P("Nile Rodgers", "Bright compressed funk chop", "Jazz Clean", "2x12 Jazz", "57 On Axis",
  20, (40, 55, 65, 60), 66, stomp=scomp("Red Comp", 55, 60), reverb=rev("Small Room", 8, 20))

# ------------------------------------------------------------ 31 Jimi Hendrix
P("Hendrix LittleW", "Uni-Vibe over a low-gain Plexi", "Plexi 45", "4x12 Green 25's", "57 Off Axis",
  30, (50, 55, 58, 50), 64, md=mod("U-Vibe", 1.8, 60, 55), reverb=rev("Medium Hall", 15, 40))
P("Hendrix Voodoo", "Octavia fuzz with wah", "Plexi Lead 100", "4x12 Green 25's", "57 On Axis",
  50, (50, 60, 58, 55), 56, stomp=fuzz("Octave Fuzz", 70, 55, 55), wah=True)
P("Hendrix Purple", "Fuzz Face into Marshall", "Plexi Lead 100", "4x12 Green 25's", "57 On Axis",
  45, (55, 60, 58, 55), 56, stomp=fuzz("Facial Fuzz", 70, 55, 55))
P("Hendrix Hey Joe", "Warm crunch, room", "Plexi 45", "4x12 Green 25's", "57 Off Axis",
  50, (55, 55, 55, 50), 60, reverb=rev("Small Room", 15, 30))

# ------------------------------------------------------------ 32 Noise and post-rock
P("Mascis Feel", "Dinosaur Jr: Muff maxed into a Plexi", "Plexi Lead 100", "4x12 Green 25's", "57 Off Axis",
  50, (60, 55, 55, 50), 55, stomp=fuzz("Fuzz Pi", 95, 55, 50), gate=(-55, 20))
P("SonicYouth Riot", "Teen Age Riot crunch", "Blackface Lux", "2x12 Blackface", "57 On Axis",
  50, (45, 60, 62, 55), 60, reverb=rev("Small Room", 12, 25))
P("Mogwai Swell", "Clean that blooms into tape echo", "Double Verb", "2x12 Blackface", "67 Condenser",
  25, (45, 50, 55, 45), 66, delay=dly("Tube Echo", 520, 45, 30, 30, 35), reverb=rev("Cavernous", 30, 70))
P("EITS Crescendo", "Tremolo-picked clean with delay", "Double Verb", "2x12 Blackface", "67 Condenser",
  22, (45, 50, 60, 50), 68, delay=dly("Digital Delay", 400, 40, 30), reverb=rev("Large Hall", 30, 65))

# ------------------------------------------------------------ extras (no slot yet)
# More Manics from Bradfield's documented rig: Les Paul Custom / Tele Thinline into
# Marshall JCM900 (Brit J-800 is the closest XT model), TS-808/TS9DX (Screamer),
# Boss FZ-2 (Fuzz Pi), RAT (Classic Dist), CS-3 (comp block), CH-1 (Sine Chorus),
# Fender Twin with a Fryer Treble Boost (Double Verb + FX-Boost + EQ).

P("Manics EMG Title", "Gretsch-ish bright crunch, comp, echo and hall", "Brit J-800", "4x12 Green 25's", "57 Off Axis",
  40, (45, 55, 65, 60), 60, comp=(-24, 4), delay=dly("Analog Delay", 400, 25, 18), reverb=rev("Large Hall", 18, 45))
P("Manics TwinBoost", "Fender Twin hit with a Fryer-style treble boost", "Double Verb", "2x12 Blackface", "57 Off Axis",
  45, (40, 55, 62, 55), 60, stomp=("FX-Boost + EQ", {"stomp_p2": 70, "stomp_p3": 40, "stomp_p4": 75, "stomp_p5": 55, "stomp_p6": 60}),
  reverb=rev("Small Room", 12, 25))
P("Manics Crystal", "CS-3 compressed clean, a touch of CH-1", "Double Verb", "2x12 Blackface", "67 Condenser",
  25, (45, 55, 62, 55), 68, comp=(-28, 5), md=mod("Sine Chorus", 0.8, 30, 25), reverb=rev("Medium Hall", 15, 35))
P("Manics RAT Riff", "RAT distortion into a cleaner Marshall", "Brit J-800", "4x12 Brit V30's", "57 On Axis",
  35, (55, 60, 55, 55), 58, stomp=fuzz("Classic Dist", 55, 55, 50), gate=(-55, 20))

# ------------------------------------------------------------ assemble

def slot_label(i):
    return f"{i // 4 + 1}{'ABCD'[i % 4]}"


def check(patch):
    assert len(patch["name"]) <= 16, patch["name"]
    for kind, model in patch["models"].items():
        table = MODELS[kind]
        assert any(label.lower() == model.lower() for label in table), f"{patch['name']}: {kind} '{model}'"


ARTIST_PREFIX = [  # patch name prefix -> artist, longest match wins
    ("SP ", "The Smashing Pumpkins"), ("Pure Morning", "Placebo"), ("Every You Every", "Placebo"),
    ("Placebo", "Placebo"), ("Nancy Boy", "Placebo"), ("AM ", "Arctic Monkeys"),
    ("Strokes", "The Strokes"), ("Stereo", "Stereophonics"), ("Muse", "Muse"), ("RH ", "Radiohead"),
    ("RATM", "Rage Against The Machine"), ("FI ", "Future Islands"), ("Fontaines", "Fontaines D.C."),
    ("FDC", "Fontaines D.C."), ("Oasis", "Oasis"), ("Manics", "Manic Street Preachers"),
    ("Verve", "The Verve"), ("AF ", "Arcade Fire"), ("Beck", "Beck"), ("Manson", "Marilyn Manson"),
    ("Killers", "The Killers"), ("Blur", "Blur"), ("SC ", "Still Corners"), ("Mayer", "John Mayer"),
    ("Deftones", "Deftones"), ("The xx", "The xx"), ("Clean Platform", "Utility"),
    ("Crunch Platform", "Utility"), ("Lead Platform", "Utility"), ("Marr", "The Smiths"),
    ("MBV", "My Bloody Valentine"), ("Slowdive", "Slowdive"), ("Ride", "Ride"), ("Edge", "U2"),
    ("Gilmour", "Pink Floyd"), ("White", "The White Stripes"), ("QOTSA", "Queens of the Stone Age"),
    ("Verlaine", "Television"), ("Interpol", "Interpol"), ("Cure", "The Cure"),
    ("Khruangbin", "Khruangbin"), ("Mdou", "Mdou Moctar"), ("Knopfler", "Dire Straits"),
    ("Nile Rodgers", "Chic"), ("Hendrix", "Jimi Hendrix"), ("Mascis", "Dinosaur Jr."),
    ("SonicYouth", "Sonic Youth"), ("Mogwai", "Mogwai"), ("EITS", "Explosions in the Sky"),
]


def artist_of(name):
    hits = [(len(p), a) for p, a in ARTIST_PREFIX if name.startswith(p)]
    assert hits, f"no artist for {name}"
    return max(hits)[1]


assert len(LIB) >= 128, len(LIB)
out, layout = {}, {}
for i, (key, patch) in enumerate(LIB):
    check(patch)
    assert key not in out, f"duplicate key {key}"
    artist = artist_of(patch["name"])
    desc = patch["description"]
    if not desc.startswith(artist + ":"):
        desc = f"{artist}: {desc}"
    out[key] = {"artist": artist, **{k: v for k, v in patch.items() if k != "slot"}, "description": desc}
    if i < 128:
        layout[slot_label(i)] = key
PATCHES.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
LAYOUT = HERE / "layout.json"
if not LAYOUT.exists():
    LAYOUT.write_text(json.dumps(layout, indent=1) + "\n", encoding="utf-8")
print(f"Wrote {len(out)} hand-tuned patches to patches.json")
