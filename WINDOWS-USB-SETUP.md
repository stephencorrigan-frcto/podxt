# Windows 11 USB setup

The POD XT's USB isn't class-compliant, and the old Line 6 driver is often blocked on Windows 11. This app talks to the XT through the generic **WinUSB** driver instead. You install it once.

## From the app (easiest)

1. Plug the XT into USB and switch it on.
2. Open `PODXT.exe`. If the XT has no WinUSB driver, a banner appears at the top.
3. Click **Install USB driver**. The app:
   - downloads Zadig 2.9 from the official libwdi release on GitHub,
   - checks it is digitally signed by Akeo Consulting (Zadig's author), and refuses to run it otherwise,
   - sets Zadig to list all devices with WinUSB selected,
   - opens it. Windows asks for admin approval.
4. In Zadig, pick **PODxt** from the list. The USB ID must read **0E41 5044**.
5. Check the box to the right of the green arrow says **WinUSB**, then click **Install Driver** (or **Replace Driver**).
6. Wait for "successful". The app checks every few seconds and the banner disappears once the XT is ready. If it doesn't, unplug and replug the XT.

From the command line, `python podxt.py install-driver` does steps 3 onwards, and `python podxt.py setup` checks the current state.

## By hand

1. Download Zadig from [zadig.akeo.ie](https://zadig.akeo.ie/) and run it.
2. **Options > List All Devices**.
3. Pick **PODxt** (USB ID 0E41 5044), target **WinUSB**, click **Install Driver**.

## Good to know

- Leave Windows **Memory Integrity** on. WinUSB doesn't need it off.
- WinUSB replaces Line 6 USB audio. Listen through the XT's headphone or line outputs.
- To go back to the Line 6 driver, open Device Manager, find PODxt, and roll back or uninstall the driver.
- A USB-MIDI cable into the XT's 5-pin MIDI In/Out also works, with no driver at all: drop `--usb` on the command line.
