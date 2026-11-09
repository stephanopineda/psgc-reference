import os
import json
import pandas as pd

def load_metadata():
    metadata_path = os.path.join(os.getcwd(), "data/metadata/latest_psgc.json")
    with open(metadata_path, "r") as f:
        metadata = json.load(f)
    return metadata

def main():
    raw_folder = os.path.join(os.getcwd(), "data/raw")

    # 1. Load metadata
    metadata = load_metadata()
    latest_psgc_file = metadata['filename']

    # 2. Load Excel
    psgc_path = os.path.join(raw_folder, latest_psgc_file)
    df_psgc = pd.read_excel(psgc_path)

    # 3. Load TSV
    tsv_path = os.path.join(raw_folder, "philippines_psgc_p-codes.tsv")
    df_tsv = pd.read_csv(tsv_path, sep="\t", dtype=str)  # force string type for PSGC codes

    # 4. Columns to check
    psgc_columns = [
        "GC2014", "GC2013", "GC2011", "GC2010", "GC2009",
        "GC2008", "GC2007", "GC2006", "GC2005", "GC2004",
        "GC2003", "GC2002", "GC2001c", "GC1995c", "GC1990x"
    ]

    # 5. Check for nulls in each PSGC column
    null_summary = df_tsv[psgc_columns].isnull().sum()
    print("\n[Null values per PSGC column]:")
    print(null_summary)

    # 6. Check changes between years and print the changes
    print("\n[Changes between PSGC columns]:")
    for i in range(len(psgc_columns)-1):
        col_newer = psgc_columns[i]
        col_older = psgc_columns[i+1]
        
        # Find where values are different, excluding null matches
        changed = (df_tsv[col_newer] != df_tsv[col_older]) & ~(df_tsv[col_newer].isnull() & df_tsv[col_older].isnull())
        
        # Print the changes
        print(f"\nChanges between {col_newer} and {col_older}:")
        print(df_tsv[changed][[col_newer, col_older]])

if __name__ == "__main__":
    main()
