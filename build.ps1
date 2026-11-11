# Builds dist\PODXT.exe, a single-file desktop app.
# The data files are bundled and copied next to the .exe on first run.
python -m pip install -r requirements.txt pyinstaller
python tones.py
python -m PyInstaller --noconfirm --onefile --windowed --name PODXT `
    --collect-all libusb_package `
    --add-data "patches.json;." --add-data "models.json;." `
    --add-data "library.json;." --add-data "layout.json;." `
    podxt_gui.py
