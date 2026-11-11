#!/usr/bin/env python3
"""Program a Line 6 POD XT from patches.json.

Sends MIDI CC into the XT's edit buffer. Press SAVE on the unit to keep a patch.

Transports:
  default  a MIDI port via mido + python-rtmidi (Linux driver, USB-MIDI cable)
  --usb    raw USB via pyusb + libusb (Windows with WinUSB from Zadig, macOS)

Commands:
  ports                     list MIDI ports and USB devices
  list                      list patches and what each FX param slot means
  models [KIND]             list model names from models.json
  send <patch|all>          load a patch (or cycle through all of them)
  monitor [--save NAME]     print CCs the XT sends; optionally capture a patch
  learn                     record model IDs by turning the XT's select knobs

CC numbers: Linux kernel Line 6 driver (control.h) and arteme/pod-ui.
"""
import argparse
import json
import sys
import time
from pathlib import Path

if getattr(sys, "frozen", False):
    # Packaged app: keep editable data next to the .exe, seeded from the bundle.
    HERE = Path(sys.executable).resolve().parent
    for _name in ("patches.json", "models.json", "library.json", "layout.json"):
        if not (HERE / _name).exists():
            (HERE / _name).write_bytes((Path(sys._MEIPASS) / _name).read_bytes())
else:
    HERE = Path(__file__).resolve().parent
PATCHES = HERE / "patches.json"   # hand-tuned patches
LIBRARY = HERE / "library.json"   # generated artist library (tones.py)
LAYOUT = HERE / "layout.json"     # slot label -> patch key, what the XT should hold
MODELS = HERE / "models.json"

CHANNEL = 0  # XT default MIDI channel 1
MODEL_PAUSE = 0.15  # after a model select the XT reloads defaults
MSG_GAP = 0.005

# Model selects, sent in this order. CC 11 loads the amp's default settings
# (and cab/mic), so it goes first and everything else overrides it.
MODEL_CC = {
    "amp": 11,
    "cab": 71,
    "mic": 70,
    "stomp": 75,
    "mod": 58,
    "delay": 88,
    "reverb": 37,
}

# Block on/off switches. Amp is inverted on the XT: 0 = engaged.
SWITCH_CC = {
    "gate": 22,
    "wah": 43,
    "stomp": 25,
    "comp": 26,
    "mod": 50,
    "delay": 28,
    "reverb": 36,
    "eq": 63,
    "amp": 111,
}
INVERTED_SWITCHES = {"amp"}

# Plain 0-100 percent params.
PARAM_CC = {
    "drive": 13,
    "bass": 14,
    "mid": 15,
    "treble": 16,
    "chan_vol": 17,
    "presence": 21,
    "room": 76,
    "gate_decay": 24,
    "reverb_mix": 18,
    "reverb_decay": 38,
    "reverb_tone": 39,
    "reverb_predelay": 40,
    "stomp_p2": 79,
    "stomp_p3": 80,
    "stomp_p4": 81,
    "stomp_p5": 82,
    "stomp_p6": 83,
    "mod_p2": 52,
    "mod_p3": 53,
    "mod_p4": 54,
    "mod_mix": 56,
    "delay_p2": 33,
    "delay_p3": 35,
    "delay_p4": 85,
    "delay_mix": 34,
    "wah_pos": 4,
    "volume": 7,
}

# Params in real units. 14-bit values go out as MSB then LSB.
#   delay_ms       20..2000 ms    CC 30 / 62
#   mod_speed_hz   0.1..15 Hz     CC 29 / 61
#   gate_db        -96..0 dB      CC 23 (sent as |dB|)
#   comp_thresh_db -63..0 dB      CC 9
#   comp_gain_db   0..16 dB       CC 5
UNIT_PARAMS = {"delay_ms", "mod_speed_hz", "gate_db", "comp_thresh_db", "comp_gain_db"}

USB_IDS = {
    0x5044: "POD XT",
    0x5050: "POD XT Pro",
    0x4650: "POD XT Live",
}
LINE6_VID = 0x0E41
EDIT_BUFFER_DUMP_REQ = [0xF0, 0x00, 0x01, 0x0C, 0x03, 0x75, 0xF7]
EDIT_BUFFER_DUMP_HDR = [0xF0, 0x00, 0x01, 0x0C, 0x03, 0x74]
SYSEX_HDR = [0xF0, 0x00, 0x01, 0x0C, 0x03]
XT_MEMBER_ID = 0x02
NAME_LEN = 16
PATCH_SIZE = 160
BACKUPS = HERE / "backups"


def slot_bytes(slot):
    """Patch slot 0-127 as the XT's two 7-bit address bytes (from pod-ui)."""
    v = slot if slot < 64 else slot + 128
    return [v >> 7, v & 0x7F]


def parse_slot(text):
    """'30A' or '117' -> 0-127."""
    t = text.strip().upper()
    if t.isdigit():
        n = int(t)
    elif len(t) >= 2 and t[:-1].isdigit() and t[-1] in "ABCD":
        n = (int(t[:-1]) - 1) * 4 + "ABCD".index(t[-1])
    else:
        sys.exit(f"Bad slot '{text}'. Use e.g. 30A.")
    if not 0 <= n < 128:
        sys.exit(f"Slot '{text}' out of range (1A-32D).")
    return n


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def pct(v):
    return round(clamp(v, 0, 100) * 127 / 100)


def fourteen_bit(value, lo, hi):
    raw = round((clamp(value, lo, hi) - lo) * 16383 / (hi - lo))
    return raw >> 7, raw & 0x7F


def unit_param_ccs(name, value):
    if name == "delay_ms":
        msb, lsb = fourteen_bit(value, 20, 2000)
        return [(30, msb), (62, lsb)]
    if name == "mod_speed_hz":
        msb, lsb = fourteen_bit(value, 0.1, 15)
        return [(29, msb), (61, lsb)]
    if name == "gate_db":
        return [(23, round(-clamp(value, -96, 0)))]
    if name == "comp_thresh_db":
        return [(9, round((clamp(value, -63, 0) + 63) * 127 / 63))]
    if name == "comp_gain_db":
        return [(5, round(clamp(value, 0, 16) * 127 / 16))]
    raise KeyError(name)


# ---------------------------------------------------------------- data files

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def all_patches():
    """Hand-tuned patches plus the generated library; hand-tuned wins on a clash."""
    patches = {}
    if LIBRARY.exists():
        patches.update(load_json(LIBRARY).get("patches", {}))
    patches.update(load_json(PATCHES))
    return patches


def load_layout():
    return load_json(LAYOUT) if LAYOUT.exists() else {}


def save_layout(layout):
    save_json(LAYOUT, {k: layout[k] for k in sorted(layout, key=parse_slot)})


def load_models():
    if not MODELS.exists():
        sys.exit("models.json not found. Run `learn` or restore it.")
    return load_json(MODELS)


def norm(s):
    return "".join(c for c in s.lower() if c.isalnum())


def model_id(models, kind, name):
    if isinstance(name, int):
        return name
    table = models.get(kind, {})
    for label, entry in table.items():
        if norm(label) == norm(name):
            return entry["id"] if isinstance(entry, dict) else entry
    sys.exit(f"Unknown {kind} model '{name}'. Try: python podxt.py models {kind}")


def model_name(models, kind, value):
    for label, entry in models.get(kind, {}).items():
        if (entry["id"] if isinstance(entry, dict) else entry) == value:
            return label
    return f"#{value}"


def slot_meanings(models, kind, name):
    entry = models.get(kind, {}).get(name)
    if isinstance(entry, dict):
        return entry.get("params", {})
    return {}


# ---------------------------------------------------------------- transports

class MidoTransport:
    def __init__(self, port=None):
        import mido
        self.mido = mido
        outs = mido.get_output_names()
        ins = mido.get_input_names()
        self.out_name = pick_port(outs, port)
        self.in_name = pick_port(ins, port, required=False)
        self.out = mido.open_output(self.out_name)
        self.inp = None

    def send_cc(self, cc, value):
        self.out.send(self.mido.Message("control_change", channel=CHANNEL,
                                        control=cc, value=value))

    def receive(self):
        """Yield (status, data...) tuples as raw MIDI byte lists."""
        if not self.in_name:
            sys.exit("No POD MIDI input port found.")
        self.inp = self.inp or self.mido.open_input(self.in_name)
        for msg in self.inp:
            yield msg.bytes()

    def close(self):
        self.out.close()
        if self.inp:
            self.inp.close()


def pick_port(names, wanted, required=True):
    if wanted:
        hits = [n for n in names if wanted.lower() in n.lower()]
    else:
        hits = [n for n in names if "pod" in n.lower() or "line 6" in n.lower()]
    if hits:
        return hits[0]
    if required:
        sys.exit(f"No matching MIDI port. Available: {names or 'none'}. "
                 "On Windows without the Line 6 driver, use --usb.")
    return None


def usb_backend():
    try:
        import libusb_package
        return libusb_package.get_libusb1_backend()
    except ImportError:
        return None


def find_usb_devices():
    import usb.core
    return list(usb.core.find(find_all=True, idVendor=LINE6_VID, backend=usb_backend()))


class UsbTransport:
    """Raw MIDI bytes over the XT's interrupt endpoints (alt setting 5).

    Endpoint layout from the Linux line6 driver and pod-ui: OUT 0x03, IN 0x84,
    no USB-MIDI framing. Inbound status bytes sometimes arrive with low nibble
    2 (0xB2/0xC2/0xF2) and get corrected to channel 0.
    """
    EP_OUT = 0x03
    EP_IN = 0x84

    def __init__(self):
        import usb.core
        import usb.util
        self.usb = usb
        devs = [d for d in find_usb_devices() if d.idProduct in USB_IDS]
        if not devs:
            sys.exit("No POD XT on USB. Check the cable and that Zadig installed WinUSB "
                     "on the PODxt device.")
        self.dev = devs[0]
        alt_setting = 1 if self.dev.idProduct == 0x4650 else 5
        try:
            self.dev.set_configuration()
        except usb.core.USBError:
            pass  # already configured
        cfg = self.dev.get_active_configuration()
        intf = None
        for i in cfg:
            if i.bAlternateSetting == alt_setting and any(
                    e.bEndpointAddress == self.EP_OUT for e in i):
                intf = i
                break
        if intf is None:
            sys.exit(f"Couldn't find interface with alt setting {alt_setting} "
                     "and endpoint 0x03.")
        self.iface = intf.bInterfaceNumber
        try:
            if self.dev.is_kernel_driver_active(self.iface):
                self.dev.detach_kernel_driver(self.iface)
        except (NotImplementedError, usb.core.USBError):
            pass  # not supported on Windows
        usb.util.claim_interface(self.dev, self.iface)
        self.dev.set_interface_altsetting(interface=self.iface,
                                          alternate_setting=alt_setting)
        self.buf = bytearray()

    def write(self, data):
        self.dev.write(self.EP_OUT, bytes(data), timeout=1000)

    def send_cc(self, cc, value):
        self.write([0xB0 | CHANNEL, cc & 0x7F, value & 0x7F])

    def edit_buffer(self):
        """Request an edit buffer dump. Returns (id, data) where data is the
        160 patch bytes (name at 0, CC n stored at 32 + n), or None.
        The first request after opening the device often goes unanswered, so retry."""
        for _ in range(3):
            self._drain(0.2)
            self.write(EDIT_BUFFER_DUMP_REQ)
            raw = self._drain(1.0)
            for i in range(len(raw) - 2):
                if raw[i:i + 2] == [0x03, 0x74]:
                    end = raw.index(0xF7, i) if 0xF7 in raw[i:] else len(raw)
                    return raw[i + 2], raw[i + 3:end]
        return None

    def read_slot(self, slot):
        """Read stored patch 0-127 (1A-32D). Returns 160 data bytes or None."""
        self._drain(0.1)
        self.write(SYSEX_HDR + [0x73, *slot_bytes(slot), 0x00, 0x00, 0xF7])
        raw = self._drain(0.8)
        for i in range(len(raw) - 2):
            if raw[i:i + 2] == [0x03, 0x74]:
                end = raw.index(0xF7, i) if 0xF7 in raw[i:] else len(raw)
                data = raw[i + 3:end]
                return data if len(data) == PATCH_SIZE else None
        return None

    def write_slot(self, slot, data):
        """Store 160 data bytes into patch slot 0-127. Returns True on success ack."""
        self._drain(0.1)
        self.write(SYSEX_HDR + [0x71, XT_MEMBER_ID, *slot_bytes(slot)] + list(data) + [0xF7])
        time.sleep(0.1)
        self.write(SYSEX_HDR + [0x72, 0xF7])
        raw = self._drain(2.0)
        for i in range(len(raw) - 1):
            if raw[i] == 0x03 and raw[i + 1] in (0x50, 0x51):
                return raw[i + 1] == 0x50
        return False

    def write_edit_buffer(self, dump_id, data):
        self.write(EDIT_BUFFER_DUMP_HDR + [dump_id] + list(data) + [0xF7])

    def set_name(self, name):
        """Rename the edit buffer: read it, replace the 16-byte name, write it back."""
        dump = self.edit_buffer()
        if not dump:
            print("   name: no edit buffer dump received, name unchanged")
            return
        dump_id, data = dump
        label = name.encode("ascii", "replace")[:NAME_LEN].ljust(NAME_LEN, b" ")
        data[:NAME_LEN] = list(label)
        self.write_edit_buffer(dump_id, data)
        time.sleep(MODEL_PAUSE)

    def _drain(self, secs):
        out = []
        end = time.time() + secs
        while time.time() < end:
            try:
                out.extend(self.dev.read(self.EP_IN, 64, timeout=200))
            except self.usb.core.USBTimeoutError:
                pass
        return out

    def receive(self):
        while True:
            try:
                chunk = self.dev.read(self.EP_IN, 64, timeout=500)
            except self.usb.core.USBTimeoutError:
                continue
            self.buf.extend(chunk)
            yield from self._split()

    def _split(self):
        while self.buf:
            if self.buf[0] in (0xB2, 0xC2, 0xF2):
                self.buf[0] &= 0xF0
            status = self.buf[0]
            if status == 0xF0:
                end = self.buf.find(0xF7)
                if end < 0:
                    return
                msg, self.buf = self.buf[:end + 1], self.buf[end + 1:]
            elif status & 0xF0 in (0xC0, 0xD0):
                if len(self.buf) < 2:
                    return
                msg, self.buf = self.buf[:2], self.buf[2:]
            elif status & 0x80:
                if len(self.buf) < 3:
                    return
                msg, self.buf = self.buf[:3], self.buf[3:]
            else:
                self.buf.pop(0)  # stray data byte
                continue
            yield list(msg)

    def close(self):
        self.usb.util.release_interface(self.dev, self.iface)
        self.usb.util.dispose_resources(self.dev)


def open_transport(args):
    return UsbTransport() if args.usb else MidoTransport(args.port)


# ---------------------------------------------------------------- patch -> CCs

def patch_messages(models, patch):
    """Return a list of (cc, value, pause_after) for a patch."""
    msgs = []
    for kind, cc in MODEL_CC.items():
        if kind in patch.get("models", {}):
            msgs.append((cc, model_id(models, kind, patch["models"][kind]), MODEL_PAUSE))
    for block, on in patch.get("on", {}).items():
        if block not in SWITCH_CC:
            sys.exit(f"Unknown switch '{block}'. Known: {', '.join(SWITCH_CC)}")
        value = 127 if on else 0
        if block in INVERTED_SWITCHES:
            value = 127 - value
        msgs.append((SWITCH_CC[block], value, 0))
    for name, value in patch.get("params", {}).items():
        if name in PARAM_CC:
            msgs.append((PARAM_CC[name], pct(value), 0))
        elif name in UNIT_PARAMS:
            msgs.extend((cc, v, 0) for cc, v in unit_param_ccs(name, value))
        else:
            sys.exit(f"Unknown param '{name}'.")
    return msgs


def send_patch(transport, models, name, patch, verify=False):
    print(f"-> {name}: {patch.get('description', '')}")
    msgs = patch_messages(models, patch)
    for cc, value, pause in msgs:
        transport.send_cc(cc, value)
        time.sleep(pause or MSG_GAP)
    if hasattr(transport, "set_name"):
        transport.set_name(patch_label(name, patch))
    if verify:
        verify_patch(transport, msgs)


def patch_label(key, patch):
    return patch.get("name") or key.replace("_", " ").title()


def verify_patch(transport, msgs):
    dump = transport.edit_buffer()
    if not dump:
        print("   verify: no edit buffer dump received")
        return
    data = dump[1]
    name = bytes(b for b in data[:NAME_LEN] if b).decode("ascii", "replace").strip()
    wrong = []
    for cc, value, _ in msgs:
        addr = 32 + (12 if cc == 11 else cc)
        if addr < len(data) and data[addr] != value:
            wrong.append(f"CC {cc} sent {value} got {data[addr]}")
    print(f"   verify: edit buffer (channel '{name}') "
          + ("matches all CCs" if not wrong else "MISMATCH: " + "; ".join(wrong)))


# ---------------------------------------------------------------- commands

def cmd_ports(args):
    try:
        import mido
        print("MIDI out:", mido.get_output_names() or "none")
        print("MIDI in: ", mido.get_input_names() or "none")
    except ImportError:
        print("mido not installed (pip install mido python-rtmidi)")
    try:
        devs = find_usb_devices()
        if not devs:
            print("USB: no Line 6 devices")
        for d in devs:
            print(f"USB: {USB_IDS.get(d.idProduct, 'Line 6 device')} "
                  f"{d.idVendor:04x}:{d.idProduct:04x} bus {d.bus} addr {d.address}")
    except ImportError:
        print("pyusb not installed (pip install pyusb libusb-package)")
    except Exception as e:  # no backend, no access
        print(f"USB: {e}")


def cmd_list(args):
    models = load_models()
    for name, p in all_patches().items():
        m = p.get("models", {})
        on = [b for b, v in p.get("on", {}).items() if v]
        print(f"{name}: {p.get('description', '')}")
        print(f"    {', '.join(f'{k}={v}' for k, v in m.items())}")
        print(f"    on: {', '.join(on) or 'nothing'}")
        for kind in ("stomp", "mod", "delay"):
            if kind in m:
                slots = slot_meanings(models, kind, m[kind])
                if slots:
                    print(f"    {kind} slots: "
                          + ", ".join(f"{k}={v}" for k, v in slots.items()))


def cmd_models(args):
    models = load_models()
    kinds = [args.kind] if args.kind else [k for k in MODEL_CC if k in models]
    for kind in kinds:
        print(f"[{kind}]")
        for label, entry in models.get(kind, {}).items():
            if isinstance(entry, dict):
                slots = ", ".join(f"{k}={v}" for k, v in entry.get("params", {}).items())
                print(f"  {entry['id']:3d}  {label}" + (f"   ({slots})" if slots else ""))
            else:
                print(f"  {entry:3d}  {label}")


def cmd_send(args):
    models = load_models()
    patches = all_patches()
    names = list(load_layout().values()) if args.patch == "all" else [args.patch]
    for n in names:
        if n not in patches:
            sys.exit(f"No patch '{n}'. Have: {', '.join(patches)}")
    t = open_transport(args)
    try:
        for i, n in enumerate(names):
            send_patch(t, models, n, patches[n], verify=args.usb)
            if len(names) > 1 and i < len(names) - 1:
                time.sleep(args.gap)
    finally:
        t.close()
    print("Done. Press SAVE on the XT to keep it.")


def reverse_maps():
    params = {cc: n for n, cc in PARAM_CC.items()}
    models = {cc: k for k, cc in MODEL_CC.items()}
    models[12] = "amp"  # amp select without defaults
    switches = {cc: n for n, cc in SWITCH_CC.items()}
    return params, models, switches


def decode_edit_buffer(models, data):
    """Turn 160 edit buffer bytes into a patches.json entry."""
    def at(cc):
        return data[32 + cc]

    patch = {"name": bytes(b for b in data[:NAME_LEN] if b).decode("ascii", "replace").strip(),
             "models": {}, "on": {}, "params": {}}
    for kind, cc in MODEL_CC.items():
        patch["models"][kind] = model_name(models, kind, at(12 if cc == 11 else cc))
    for block, cc in SWITCH_CC.items():
        on = at(cc) >= 64
        patch["on"][block] = (not on) if block in INVERTED_SWITCHES else on
    for name, cc in PARAM_CC.items():
        patch["params"][name] = round(at(cc) * 100 / 127)
    p = patch["params"]
    p["delay_ms"] = round(20 + ((at(30) << 7) | at(62)) * 1980 / 16383)
    p["mod_speed_hz"] = round(0.1 + ((at(29) << 7) | at(61)) * 14.9 / 16383, 2)
    p["gate_db"] = -at(23)
    p["comp_thresh_db"] = round(at(9) * 63 / 127 - 63, 1)
    p["comp_gain_db"] = round(at(5) * 16 / 127, 1)
    return patch


def cmd_dump(args):
    if not args.usb:
        sys.exit("dump needs --usb")
    models = load_models()
    t = UsbTransport()
    try:
        dump = t.edit_buffer()
    finally:
        t.close()
    if not dump:
        sys.exit("No edit buffer dump received.")
    patch = decode_edit_buffer(models, dump[1])
    print(json.dumps(patch, indent=2))
    for kind in ("stomp", "mod", "delay"):
        slots = slot_meanings(models, kind, patch["models"][kind])
        if slots:
            print(f"{kind} slots: " + ", ".join(f"{k}={v}" for k, v in slots.items()))
    if args.save:
        patches = load_json(PATCHES)
        patches[args.save] = {"description": f"dumped from XT ({patch['name']})", **patch}
        save_json(PATCHES, patches)
        print(f"Saved '{args.save}' to patches.json.")


def slot_name(data):
    return bytes(b for b in data[:NAME_LEN] if b).decode("ascii", "replace").strip()


def cmd_backup(args):
    """Read every stored patch into backups/slots-<time>.json."""
    if not args.usb:
        sys.exit("backup needs --usb")
    t = UsbTransport()
    slots = {}
    try:
        for n in range(128):
            data = t.read_slot(n)
            if data is None:
                data = t.read_slot(n)  # one retry
            label = channel_label(n)
            if data is None:
                print(f"  {label:>4}  (no reply)")
                continue
            slots[label] = data
            print(f"  {label:>4}  {slot_name(data)}")
    finally:
        t.close()
    BACKUPS.mkdir(exist_ok=True)
    path = BACKUPS / f"slots-{time.strftime('%Y%m%d-%H%M%S')}.json"
    save_json(path, slots)
    print(f"Backed up {len(slots)} slots to {path.name}")


def store_slots(t, models, patches, pairs):
    """Write [(slot label, patch key), ...] to the XT. Each slot is read and kept in
    one backup file first, and nothing is written to a slot that couldn't be backed up.
    Returns the labels that failed."""
    backup, failed = {}, []
    BACKUPS.mkdir(exist_ok=True)
    bak = BACKUPS / f"commit-{time.strftime('%Y%m%d-%H%M%S')}.json"
    for i, (label, key) in enumerate(pairs, 1):
        slot = parse_slot(label)
        patch = patches[key]
        print(f"[{i}/{len(pairs)}] {label} <- {patch.get('artist', '')}: {patch.get('name', key)}")
        old = t.read_slot(slot) or t.read_slot(slot) or t.read_slot(slot)
        if old is None:
            print(f"   couldn't read {label} to back it up, skipped")
            failed.append(label)
            continue
        backup[label] = old
        save_json(bak, backup)
        print(f"   was '{slot_name(old)}'")
        send_patch(t, models, key, patch, verify=True)
        dump = t.edit_buffer()
        if not dump or len(dump[1]) != PATCH_SIZE or not t.write_slot(slot, dump[1]):
            print("   FAILED to store")
            failed.append(label)
            continue
        check = t.read_slot(slot) or t.read_slot(slot)
        if check == dump[1]:
            print(f"   stored '{slot_name(dump[1])}', read back matches")
        else:
            print("   READ BACK DIFFERS")
            failed.append(label)
    if backup:
        print(f"Previous contents backed up to {bak.name}")
    return failed


def cmd_store(args):
    """Send a patch, then write the edit buffer into a slot (after backing it up)."""
    if not args.usb:
        sys.exit("store needs --usb")
    patches = all_patches()
    if args.patch not in patches:
        sys.exit(f"No patch '{args.patch}'.")
    label = channel_label(parse_slot(args.slot))
    t = UsbTransport()
    try:
        failed = store_slots(t, load_models(), patches, [(label, args.patch)])
    finally:
        t.close()
    if failed:
        sys.exit(f"Store to {label} failed.")


def cmd_store_library(args):
    """Write every slot in layout.json to the XT."""
    if not args.usb:
        sys.exit("store-library needs --usb")
    commit_layout(load_layout())


def commit_layout(pairs):
    """Store {label: key} or [(label, key)] pairs; used by the CLI and the app."""
    pairs = sorted(pairs.items() if isinstance(pairs, dict) else pairs,
                   key=lambda kv: parse_slot(kv[0]))
    patches = all_patches()
    missing = [k for _, k in pairs if k not in patches]
    if missing:
        sys.exit(f"Unknown patches in layout: {', '.join(missing)}")
    t = UsbTransport()
    try:
        failed = store_slots(t, load_models(), patches, pairs)
    finally:
        t.close()
    print(f"Done: {len(pairs) - len(failed)} stored" + (f", failed: {', '.join(failed)}" if failed else ""))
    return failed


def read_slot_names():
    """Read the name stored in every slot: {label: name}."""
    t = UsbTransport()
    names = {}
    try:
        for n in range(128):
            data = t.read_slot(n) or t.read_slot(n)
            names[channel_label(n)] = slot_name(data) if data else None
    finally:
        t.close()
    return names


def cmd_restore(args):
    """Write a slot back from a backup file."""
    if not args.usb:
        sys.exit("restore needs --usb")
    backup = load_json(BACKUPS / args.file)
    label = channel_label(parse_slot(args.slot))
    if label not in backup:
        sys.exit(f"{label} not in {args.file}.")
    t = UsbTransport()
    try:
        ok = t.write_slot(parse_slot(args.slot), backup[label])
    finally:
        t.close()
    print(f"Restored {label} ('{slot_name(backup[label])}')" if ok else "XT did not confirm the restore.")


def channel_label(program):
    """XT program number 0-127 as its front-panel name, e.g. 74 -> 19C."""
    return f"{program // 4 + 1}{'ABCD'[program % 4]}"


def cmd_monitor(args):
    models = load_models() if MODELS.exists() else {}
    params, model_ccs, switches = reverse_maps()
    captured = {"models": {}, "on": {}, "params": {}}
    t = open_transport(args)
    print("Listening. Turn knobs on the XT. Ctrl+C to stop.")
    try:
        for msg in t.receive():
            if msg[0] & 0xF0 == 0xC0 and len(msg) >= 2:
                print(f"  channel change -> {channel_label(msg[1])} "
                      "(edit buffer replaced)")
                continue
            if msg[0] & 0xF0 != 0xB0 or len(msg) < 3:
                print("  raw:", " ".join(f"{b:02x}" for b in msg[:24]),
                      "..." if len(msg) > 24 else "")
                continue
            cc, val = msg[1], msg[2]
            if cc in model_ccs:
                kind = model_ccs[cc]
                label = model_name(models, kind, val)
                captured["models"][kind] = label
                print(f"  CC {cc:3d} = {val:3d}  {kind} model: {label}")
            elif cc in switches:
                block = switches[cc]
                on = val >= 64
                if block in INVERTED_SWITCHES:
                    on = not on
                captured["on"][block] = on
                print(f"  CC {cc:3d} = {val:3d}  {block} {'on' if on else 'off'}")
            elif cc in params:
                p = round(val * 100 / 127)
                captured["params"][params[cc]] = p
                print(f"  CC {cc:3d} = {val:3d}  {params[cc]} {p}%")
            else:
                print(f"  CC {cc:3d} = {val:3d}  (unmapped)")
    except KeyboardInterrupt:
        pass
    finally:
        t.close()
    if args.save:
        patches = load_json(PATCHES)
        patches[args.save] = {"description": "captured with monitor", **captured}
        save_json(PATCHES, patches)
        print(f"Saved '{args.save}' to patches.json.")


def cmd_learn(args):
    models = load_json(MODELS) if MODELS.exists() else {}
    _, model_ccs, _ = reverse_maps()
    t = open_transport(args)
    print("Turn a model select knob on the XT. After each change, type the name on "
          "screen (blank to skip). Ctrl+C to finish.")
    try:
        for msg in t.receive():
            if msg[0] & 0xF0 != 0xB0 or len(msg) < 3 or msg[1] not in model_ccs:
                continue
            kind, val = model_ccs[msg[1]], msg[2]
            label = input(f"{kind} id {val} ({model_name(models, kind, val)}): ").strip()
            if label:
                table = models.setdefault(kind, {})
                if kind in ("stomp", "mod", "delay"):
                    table[label] = {"id": val, "params": table.get(label, {}).get("params", {})}
                else:
                    table[label] = val
    except KeyboardInterrupt:
        pass
    finally:
        t.close()
    save_json(MODELS, models)
    print("Saved models.json.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--usb", action="store_true", help="talk to the XT over raw USB")
    ap.add_argument("--port", help="MIDI port name substring (default: anything with POD)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ports").set_defaults(fn=cmd_ports)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    m = sub.add_parser("models")
    m.add_argument("kind", nargs="?", choices=list(MODEL_CC))
    m.set_defaults(fn=cmd_models)
    s = sub.add_parser("send")
    s.add_argument("patch")
    s.add_argument("--gap", type=float, default=5.0, help="seconds between patches for 'all'")
    s.set_defaults(fn=cmd_send)
    mon = sub.add_parser("monitor")
    mon.add_argument("--save", metavar="NAME")
    mon.set_defaults(fn=cmd_monitor)
    sub.add_parser("learn").set_defaults(fn=cmd_learn)
    d = sub.add_parser("dump")
    d.add_argument("--save", metavar="NAME")
    d.set_defaults(fn=cmd_dump)
    sub.add_parser("backup").set_defaults(fn=cmd_backup)
    st = sub.add_parser("store")
    st.add_argument("patch")
    st.add_argument("slot", help="e.g. 30A")
    st.set_defaults(fn=cmd_store)
    sub.add_parser("store-library").set_defaults(fn=cmd_store_library)
    rs = sub.add_parser("restore")
    rs.add_argument("file", help="file in backups/")
    rs.add_argument("slot", help="e.g. 30A")
    rs.set_defaults(fn=cmd_restore)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
