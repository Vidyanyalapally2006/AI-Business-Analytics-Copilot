import sqlite3
import pandas as pd
from pathlib import Path


# Project folders
BASE_DIR = Path(__file__).resolve().parent.parent
CSV_FILE = BASE_DIR / "data" / "sales_data.csv"
DB_FILE = BASE_DIR / "database" / "business_data.db"


# Read CSV
df = pd.read_csv(CSV_FILE)

# Connect to SQLite
connection = sqlite3.connect(DB_FILE)

# Store data in SQLite
df.to_sql("sales", connection, if_exists="replace", index=False)

# Close connection
connection.close()

print("Database created successfully!")
print(f"Database location: {DB_FILE}")
print(f"Records inserted: {len(df)}")