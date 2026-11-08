# Builds dist\PODXT.exe, a single-file desktop app.
# patches.json and models.json are bundled and copied next to the .exe on first run.
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --name PODXT `
    --collect-all libusb_package `
    --add-data "patches.json;." --add-data "models.json;." `
    podxt_gui.py
