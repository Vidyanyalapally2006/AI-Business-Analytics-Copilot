import sqlite3
import pandas as pd
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DB_FILE = BASE_DIR / "database" / "business_data.db"


connection = sqlite3.connect(DB_FILE)

query = "SELECT * FROM sales LIMIT 5"

df = pd.read_sql_query(query, connection)

connection.close()

print("\nFirst 5 records from the database:\n")
print(df.to_string(index=False))