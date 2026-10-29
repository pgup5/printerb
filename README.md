# PrinterB

Desktop GUI for the USB NIIMBOT B1 on Linux Mint and Windows, using the original project's 50 × 30 mm label layouts and printer protocol. This folder runs independently. The copied driver retains its upstream MIT notice.

Requires Python 3.10+ and Tkinter.

## Linux Mint setup

Run these commands from this project folder:

```bash
sudo apt update
sudo apt install python3-venv python3-tk fonts-noto-cjk fonts-arphic-ukai
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
./start.sh
```

Create a fresh Linux `.venv`; an environment copied from Windows cannot be reused. The launcher works from any current directory and uses this project's environment. Launch from a terminal to see startup errors.

Noto Sans CJK TC supplies Traditional Chinese text in the interface and labels. The five-cell name sticker prefers AR PL UKai when installed, otherwise it uses Noto. Font metrics differ from Windows, so preview labels before printing.

For USB serial access, add your account to `dialout` once:

```bash
sudo usermod -aG dialout "$USER"
```

Log out of your desktop session and log back in for group membership to take effect. Connect and power on the B1, then click 重新偵測. Linux ports usually look like `/dev/ttyUSB0` or `/dev/ttyACM0`; select the printer's port if automatic detection is ambiguous. No CUPS printer queue is needed: PrinterB sends the protocol directly over USB serial. Run the application as your normal user.

If opening a port fails, check its permissions with `ls -l /dev/ttyUSB0` (substitute your actual port), your groups with `id -nG`, and whether another application is using the device. Preview and PNG export work without USB access.

## Windows setup

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

Microsoft JhengHei and Kai fonts remain supported. Double-click `start.bat` after creating the Windows environment.

Connect and power on the B1, select its serial port (or automatic detection), select original paper or third-party paper (+1 mm feed), and choose a label type. Enter the relevant fields, preview, then print one label. PNG export does not require a connected printer. Density ranges from 1 to 5. Diagnostics read printer status without printing.

The GUI includes name/ID/birthday, five-cell name sticker, invoice carrier barcode, and multiline text labels. Birthdays use Gregorian `YYYY/MM/DD` for both input and output. No connection to the original application's patient database is required or provided; patient entries are kept in memory only.

Run checks from this folder with `.venv/bin/python -m unittest discover -s tests` on Linux (use `.venv\Scripts\python` on Windows). GUI tests require a desktop display; on a headless Linux machine install `xvfb` and run `xvfb-run -a .venv/bin/python -m unittest discover -s tests`.

The main window contains printer settings, patient inputs, custom text, preview/export, printing, and diagnostics. Use 標籤種類 to select 列印姓名生日, 姓名貼, 手機條碼, or TEXT. 預覽, 儲存 PNG, and 列印一張 use the selected layout. Settings and diagnostic results stay in the same window.

The interface uses a compact two-column workspace with grouped settings and a highlighted print action. Smaller windows can scroll vertically so controls remain accessible.

Custom TEXT labels offer 黑體 and 標楷體 font choices. On Linux, the Kai option uses bundled AR PL UKai; its license and attribution are in `printerb_core/fonts/`. Windows uses 標楷體 when installed.
