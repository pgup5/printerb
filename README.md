# PrinterB

Independent Windows desktop GUI for the USB NIIMBOT B1, using the original project's 50 × 30 mm label layouts and printer protocol. This folder can be copied and run separately; it does not import the parent project. Original source files are unchanged. The copied driver retains its upstream MIT notice.

Requires Python 3.10+ with Tkinter and Windows Chinese fonts (Microsoft JhengHei).

```powershell
cd printerb
python -m pip install -r requirements.txt
python main.py
```

This installation includes its own `.venv` environment with all required packages. Double-click `start.bat` to launch using that environment.

Connect and power on the B1, select its COM port (or automatic detection), select original paper or third-party paper (+1 mm feed), and choose a label type. Enter the relevant fields, preview, then print one label. PNG export does not require a connected printer. Density ranges from 1 to 5. Diagnostics read printer status without printing.

Includes name/ID/birthday, medical-record Code 128 barcode, six-cell name sticker, invoice carrier barcode, collection reason, urine order, multiline text, and growth labels. Birthdays use Gregorian `YYYY/MM/DD` input and ROC output; growth age uses `2y6m` format. Growth percentiles and BMI are entered manually. No connection to the original application's patient database is required or provided; patient entries are kept in memory only.

Run checks from this folder with `python -m unittest discover -s tests`.

All label actions are direct buttons in the main window: 列印姓名生日, 快篩條碼, 姓名貼, 手機條碼, 收集, 開驗尿單, TEXT, and 生長數據. Fill in the visible patient/growth fields and collection reason or custom text, then click an action to print one label. Use the label radio buttons with 預覽 or 儲存 PNG to inspect/export without printing. Settings and diagnostic results stay in the same window; no child label window or data tabs are needed.
