# POD XT patch loader

Describe a tone, edit `patches.json`, push it into the XT's edit buffer, press SAVE on the unit to keep it.

## Desktop app

Download `PODXT.exe` from the Releases page (Windows), or build it yourself:

```
powershell -ExecutionPolicy Bypass -File build.ps1
```

On first run the app writes `patches.json` and `models.json` next to itself. Pick a patch, then:

- **Audition** (or double-click): loads it into the XT's edit buffer.
- **Store to slot**: backs up the slot, then writes the patch there.
- **Back up all slots**: saves all 128 stored patches to `backups/`.
- **Capture XT sound**: saves whatever is on the XT as a new patch.
- **Store whole library**: writes every patch that has a slot.

The app talks to the XT over USB, so it needs WinUSB on the PODxt (see Setup).

## Setup

```
pip install mido python-rtmidi pyusb libusb-package
```

How the XT connects:

- **Linux**: the kernel `snd_usb_line6` driver gives a MIDI port. Use the default transport.
- **Windows 11**: Zadig, then WinUSB on the `PODxt` device (USB ID `0E41 5044`). Use `--usb`. This drops Line 6 USB audio. Leave Memory Integrity on.
- **macOS**: no driver needed. Use `--usb`.
- **Any OS**: a USB-MIDI cable into the XT's 5-pin MIDI In/Out. Use the default transport.

## Commands

```
python podxt.py ports                    # MIDI ports and Line 6 USB devices
python podxt.py list                     # patches, plus what each FX slot means
python podxt.py models [amp|cab|mic|stomp|mod|delay|reverb]
python podxt.py --usb send mayer_clean
python podxt.py --usb send all --gap 8
python podxt.py --usb backup                      # all 128 slots -> backups/slots-<time>.json
python podxt.py --usb store mayer_clean 1A        # backs up 1A, then writes the patch there
python podxt.py --usb restore <backup file> 1A    # put a slot back from a backup
python podxt.py --usb dump [--save NAME]  # read the XT's current sound as a patch
python podxt.py --usb monitor [--save NAME]
python podxt.py --usb learn              # only if models.json is wrong
```

Drop `--usb` when using a MIDI port. `--port NAME` picks a specific one.

## The 128-slot library

`library.py` generates all 128 patches into `patches.json`, each with a `"slot"`. `python podxt.py --usb store-library` writes them to the XT (run `backup` first). Edit a patch in `library.py`, rerun it, then `store <key> <slot>` for just that one.

| Banks | Contents |
|---|---|
| 1-20 | Top Spotify artists, four patches each: Smashing Pumpkins, Placebo, Arctic Monkeys, The Strokes, Stereophonics, Muse, Radiohead, RATM, Future Islands, Fontaines D.C., Oasis, more Manics (bank 12: one per era), The Verve, Arcade Fire, Beck, Marilyn Manson, The Killers, Manics, Blur, Still Corners |
| 21-22 | Mayer Clean, Mayer Gravity, Deftones Heavy, Deftones Clean, The xx, Clean / Crunch / Lead platforms |
| 23-32 | Discoveries: Johnny Marr, shoegaze (MBV, Slowdive, Ride), The Edge, Gilmour, Jack White, QOTSA, post-punk (Television, Interpol, The Cure), Khruangbin / Mdou Moctar / Knopfler / Nile Rodgers, Hendrix, Dinosaur Jr / Sonic Youth / Mogwai / Explosions in the Sky |

Four more Manics patches are in `patches.json` without a slot (EMG Title, TwinBoost, Crystal, RAT Riff). Audition them from the app, or `store` one over a slot you don't use.

## Licence

GPLv3 (see `LICENSE`). The PODxt model tables and USB protocol details come from [arteme/pod-ui](https://github.com/arteme/pod-ui), which is GPLv3.

## patches.json

```json
"name": {
  "description": "...",
  "models": {"amp": "Double Verb", "cab": "2x12 Blackface", "mic": "67 Condenser",
             "stomp": "Screamer", "mod": "Analog Chorus", "delay": "Digital Delay", "reverb": "Lux Spring"},
  "on": {"amp": true, "gate": false, "comp": true, "stomp": false, "mod": false, "delay": true, "reverb": true},
  "params": {"drive": 30, "delay_ms": 380, "mod_speed_hz": 0.6}
}
```

Optional `"name"` (16 characters max) sets the patch name shown on the XT. Without it the key is used, e.g. `mayer_clean` becomes "Mayer Clean". Naming works over `--usb` only.

Model names match `models.json` (case and punctuation ignored). Switches: `amp gate wah stomp comp mod delay reverb eq`.

Percent params (0 to 100): `drive bass mid treble presence chan_vol room gate_decay reverb_mix reverb_decay reverb_tone reverb_predelay stomp_p2..stomp_p6 mod_p2..mod_p4 mod_mix delay_p2..delay_p4 delay_mix wah_pos volume`.

Real-unit params:

| name | range | CC |
|---|---|---|
| `delay_ms` | 20 to 2000 ms | 30 / 62 (14-bit) |
| `mod_speed_hz` | 0.1 to 15 Hz | 29 / 61 (14-bit) |
| `gate_db` | -96 to 0 dB | 23 |
| `comp_thresh_db` | -63 to 0 dB | 9 |
| `comp_gain_db` | 0 to 16 dB | 5 |

The FX slots mean different things per model. `python podxt.py list` shows them for each patch, e.g. Screamer: `stomp_p2=Drive, stomp_p3=Gain, stomp_p4=Tone`; Digital Delay: `delay_p2=Feedback, delay_p3=Bass, delay_p4=Treble`.

## How a patch is sent

1. Amp model on CC 11 (loads that amp's defaults), then a 150 ms pause.
2. Cab, mic, stomp, mod, delay and reverb models, 150 ms after each.
3. Block switches. Amp (CC 111) is inverted: 0 means engaged.
4. Params.
5. Over `--usb`: the edit buffer is read back, the name swapped in, and the buffer written back via SysEx (`F0 00 01 0C 03 74 <id> <160 bytes> F7`). Then it's read again and every CC checked.

## Sources

- CC numbers: Linux kernel Line 6 driver and arteme/pod-ui.
- `models.json`: generated from pod-ui's `mod-xt/src/config.rs` (GPLv3). Model IDs and slot names are data, not copied code.
- USB: interface alt setting 5, interrupt OUT 0x03, IN 0x84 (XT Live: alt setting 1). Raw MIDI bytes, no framing.

## Verified on hardware (POD XT, Windows 11, WinUSB)

- USB transport: sends, edit buffer dump/write, naming.
- Front panel CCs: drive, bass, mid, treble, chan vol, presence, reverb mix, amp model.
- Amp, cab, mic, reverb and stomp model IDs (Double Verb, 2x12 Blackface, 67 Condenser, Lux Spring, Facial Fuzz, Screamer).
- Stomp slots on Screamer: p2 Drive, p3 Gain, p4 Tone.
- Delay on Digital Delay: `delay_ms` (250 ms read 250 ms), p2 Feedback, p4 Treble.
- Mod on Analog Chorus: `mod_speed_hz` (2.0 Hz), p2 Depth, p4 Treble.
- Comp threshold and gain round-trip.
- Installed packs: Metal Shop, Collector's Classics, FX Junkie (not Bass Expansion).

The XT does not send model changes as CCs when you turn SELECT, so `monitor` can't see them. Use `dump`. The on-unit scroll order differs from the model IDs.

## Not yet verified

- Slot names on other stomp/mod/delay models (taken from pod-ui, same mechanism).
- Patches have not been judged by ear yet.

## Tone notes

- If it sounds fizzy, try a darker mic (421 or 67) before cutting treble.
- Deftones heavy: tuning matters as much as the patch.
- Set Output Mode on the XT to Studio/Direct for headphones or a DAW.
- Metal Shop (MS-), Collector's Classics (CC-) and FX Junkie (FX-) models need the paid model packs. The boot screen shows which are installed.
