import os
import glob
import re
import requests
import json

def download_file(url, save_path):
    response = requests.get(url)
    response.raise_for_status()

    with open(save_path, 'wb') as f:
        f.write(response.content)
    print(f"Downloaded: {save_path}")

def quarter_to_number(quarter_str):
    """Convert '1Q', '2Q', etc. to a number for easier comparison"""
    return int(quarter_str.replace("Q", ""))

def find_latest_psgc_file(raw_folder):
    pattern = os.path.join(raw_folder, "PSGC-*-Publication-Datafile.xlsx")
    matching_files = glob.glob(pattern)

    if not matching_files:
        return None, None, None

    psgc_files = []
    for file in matching_files:
        basename = os.path.basename(file)
        match = re.search(r"PSGC-(\dQ)-(\d{4})-Publication-Datafile\.xlsx", basename)
        if match:
            quarter = match.group(1)
            year = int(match.group(2))
            psgc_files.append((file, year, quarter))

    if not psgc_files:
        return None, None, None

    # Sort first by year descending, then by quarter descending
    psgc_files.sort(key=lambda x: (x[1], quarter_to_number(x[2])), reverse=True)
    latest_file, latest_year, latest_quarter = psgc_files[0]

    return os.path.basename(latest_file), latest_quarter, latest_year

def save_metadata(metadata_folder, filename, quarter, year):
    os.makedirs(metadata_folder, exist_ok=True)
    metadata = {
        "filename": filename,
        "year": year,
        "quarter": quarter
    }
    metadata_path = os.path.join(metadata_folder, "latest_psgc.json")
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=4)
    print(f"Metadata saved: {metadata_path}")

def main():
    raw_folder = os.path.join(os.getcwd(), "data", "raw")
    metadata_folder = os.path.join(os.getcwd(), "data", "metadata")
    os.makedirs(raw_folder, exist_ok=True)

    # 1. Find latest PSGC Excel file
    latest_psgc_file, quarter, year = find_latest_psgc_file(raw_folder)

    if latest_psgc_file:
        print(f"Found latest PSGC file: {latest_psgc_file} (Year: {year}, Quarter: {quarter})")
        save_metadata(metadata_folder, latest_psgc_file, quarter, year)
    else:
        print("Warning: No valid PSGC Excel file found in ./data/raw/.")

    # 2. Download P-Codes TSV file
    p_codes_url = "https://github.com/govvin/PHL-PSGC-P-Codes/raw/refs/heads/master/philippines_psgc_p-codes.tsv"
    p_codes_filename = "philippines_psgc_p-codes.tsv"
    p_codes_path = os.path.join(raw_folder, p_codes_filename)

    if not os.path.exists(p_codes_path):
        print(f"Downloading {p_codes_filename}...")
        download_file(p_codes_url, p_codes_path)
    else:
        print(f"Found existing file: {p_codes_filename}")

if __name__ == "__main__":
    main()
