import zipfile
import os
from pathlib import Path

zips = [
    'TextWidget_1.0.0.zip',
    'SystemMonitor_1.0.0.zip',
    'RSSWidget_1.0.0.zip',
    'ClockWidget_1.0.0.zip',
    'PagesExtension_1.0.0.zip',
    'BulgarianLanguagePack_1.0.0.zip'
]

for zip_name in zips:
    if os.path.exists(zip_name):
        extract_dir = f"temp_{zip_name.replace('.zip', '')}"
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(zip_name, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        print(f"Extracted {zip_name} to {extract_dir}")
    else:
        print(f"{zip_name} not found")