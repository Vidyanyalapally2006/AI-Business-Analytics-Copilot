from flask import Flask, render_template, request, jsonify
import sqlite3
import pandas as pd
import numpy as np
import os
import re
from pathlib import Path
from dotenv import load_dotenv
from google import genai

# ============================================================
# APP CONFIGURATION
# ============================================================

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent

DB_FILE = BASE_DIR / "database" / "business_data.db"
UPLOAD_FOLDER = BASE_DIR / "data"

ALLOWED_EXTENSIONS = {
    "csv",
    "xlsx"
}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if api_key:
    client = genai.Client(api_key=api_key)
else:
    client = None


# ============================================================
# REQUIRED BUSINESS COLUMNS
# ============================================================

REQUIRED_COLUMNS = {
    "Order_ID",
    "Order_Date",
    "Customer",
    "Product",
    "Category",
    "Region",
    "Quantity",
    "Sales",
    "Discount",
    "Profit"
}


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():
    return sqlite3.connect(DB_FILE)


# ============================================================
# JSON SAFE VALUE
# ============================================================

def make_json_safe(value):

    if pd.isna(value):
        return None

    if isinstance(value, np.integer):
        return int(value)

    if isinstance(value, np.floating):
        return float(value)

    if isinstance(value, np.bool_):
        return bool(value)

    return value


# ============================================================
# DATAFRAME TO JSON RECORDS
# ============================================================

def dataframe_to_records(df):

    records = df.to_dict(orient="records")

    safe_records = []

    for record in records:

        safe_record = {}

        for key, value in record.items():

            safe_record[key] = make_json_safe(value)

        safe_records.append(safe_record)

    return safe_records


# ============================================================
# ALLOWED FILE CHECK
# ============================================================

def allowed_file(filename):

    if not filename:
        return False

    extension = filename.rsplit(".", 1)[-1].lower()

    return extension in ALLOWED_EXTENSIONS


# ============================================================
# CLEAN COLUMN NAMES
# ============================================================

def clean_column_names(df):

    df = df.copy()

    cleaned_columns = []

    for column in df.columns:

        column = str(column).strip()

        column = re.sub(
            r"\s+",
            "_",
            column
        )

        column = re.sub(
            r"[^A-Za-z0-9_]",
            "",
            column
        )

        cleaned_columns.append(column)

    df.columns = cleaned_columns

    return df


# ============================================================
# CLEAN DATASET
# ============================================================

def clean_uploaded_data(df):

    df = df.copy()

    df = df.dropna(how="all")

    df = df.dropna(
        axis=1,
        how="all"
    )

    # Strip whitespace from text columns
    for column in df.select_dtypes(
        include=["object"]
    ).columns:

        df[column] = (
            df[column]
            .astype(str)
            .str.strip()
        )

    # Numeric columns
    numeric_columns = [
        "Quantity",
        "Sales",
        "Discount",
        "Profit"
    ]

    for column in numeric_columns:

        if column in df.columns:

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce"
            )

    # Date column
    if "Order_Date" in df.columns:

        df["Order_Date"] = pd.to_datetime(
            df["Order_Date"],
            errors="coerce"
        )

        df["Order_Date"] = (
            df["Order_Date"]
            .dt.strftime("%Y-%m-%d")
        )

    # Remove incomplete business rows
    important_columns = [
        "Order_ID",
        "Product",
        "Category",
        "Region",
        "Sales",
        "Profit"
    ]

    existing_important_columns = [
        column
        for column in important_columns
        if column in df.columns
    ]

    if existing_important_columns:

        df = df.dropna(
            subset=existing_important_columns
        )

    return df


# ============================================================
# LOAD UPLOADED FILE
# ============================================================

def load_uploaded_file(file):

    filename = file.filename

    extension = filename.rsplit(
        ".",
        1
    )[-1].lower()

    if extension == "csv":

        df = pd.read_csv(file)

    elif extension == "xlsx":

        df = pd.read_excel(file)

    else:

        raise ValueError(
            "Only CSV and Excel (.xlsx) files are supported."
        )

    return df


# ============================================================
# VALIDATE DATASET
# ============================================================

def validate_dataset(df):

    missing_columns = (
        REQUIRED_COLUMNS
        - set(df.columns)
    )

    if missing_columns:

        missing = sorted(
            list(missing_columns)
        )

        return False, (
            "Missing required columns: "
            + ", ".join(missing)
        )

    if df.empty:

        return False, (
            "The uploaded file does not contain "
            "any usable records."
        )

    return True, None


# ============================================================
# STORE DATAFRAME IN SQLITE
# ============================================================

def save_dataframe_to_database(df):

    connection = get_connection()

    try:

        df.to_sql(
            "sales",
            connection,
            if_exists="replace",
            index=False
        )

    finally:

        connection.close()


# ============================================================
# SQL CLEANING
# ============================================================

def clean_sql(sql):

    if not sql:
        return ""

    sql = sql.strip()

    # Remove Markdown code fences
    sql = re.sub(
        r"^```(?:sql)?\s*",
        "",
        sql,
        flags=re.IGNORECASE
    )

    sql = re.sub(
        r"\s*```$",
        "",
        sql
    )

    # Remove accidental explanatory prefix
    if sql.lower().startswith("sql:"):

        sql = sql[4:].strip()

    # Keep only the SQL portion if Gemini
    # accidentally adds text after it
    sql = sql.strip()

    return sql


# ============================================================
# SQL VALIDATION
# ============================================================

def validate_sql(sql):

    if not sql:
        return False

    sql_clean = clean_sql(sql)

    # Maximum query length
    if len(sql_clean) > 5000:
        return False

    # Remove one trailing semicolon
    if sql_clean.endswith(";"):

        sql_clean = sql_clean[:-1].strip()

    lowered_sql = sql_clean.lower()

    # Only SELECT / WITH queries are allowed
    if not (
        lowered_sql.startswith("select ")
        or lowered_sql.startswith("with ")
    ):
        return False

    # Prevent multiple statements
    if ";" in sql_clean:
        return False

    # Block SQL comments
    if "--" in sql_clean:
        return False

    if "/*" in sql_clean:
        return False

    if "*/" in sql_clean:
        return False

    # Dangerous operations
    dangerous_keywords = [
        "insert",
        "update",
        "delete",
        "drop",
        "alter",
        "create",
        "pragma",
        "attach",
        "detach",
        "replace",
        "vacuum",
        "reindex",
        "transaction",
        "commit",
        "rollback"
    ]

    for keyword in dangerous_keywords:

        pattern = r"\b" + re.escape(keyword) + r"\b"

        if re.search(
            pattern,
            lowered_sql
        ):
            return False

    # ========================================================
    # TABLE VALIDATION
    # ========================================================

    # Find tables after FROM and JOIN
    table_matches = re.findall(
        r"""
        \b
        (?:FROM|JOIN)
        \s+
        (?:
            ["`]
            ([A-Za-z_][A-Za-z0-9_]*)
            ["`]
            |
            ([A-Za-z_][A-Za-z0-9_]*)
        )
        """,
        sql_clean,
        re.IGNORECASE | re.VERBOSE
    )

    allowed_tables = {
        "sales"
    }

    for match in table_matches:

        table = match[0] or match[1]

        if table.lower() not in allowed_tables:

            return False

    # Query must reference sales
    if not re.search(
        r"\bsales\b",
        lowered_sql
    ):
        return False

    # ========================================================
    # BLOCK SQLITE INTERNAL ACCESS
    # ========================================================

    blocked_patterns = [

        r"\bload_extension\s*\(",

        r"\breadfile\s*\(",

        r"\bwritefile\s*\(",

        r"\bsqlite_master\b",

        r"\bsqlite_schema\b",

        r"\bsqlite_temp_master\b"

    ]

    for pattern in blocked_patterns:

        if re.search(
            pattern,
            lowered_sql
        ):
            return False

    return True


# ============================================================
# BUILD FILTER CONDITIONS
# ============================================================

def build_filter_conditions(
    region=None,
    category=None
):

    conditions = []
    parameters = []

    if region:

        conditions.append(
            "Region = ?"
        )

        parameters.append(region)

    if category:

        conditions.append(
            "Category = ?"
        )

        parameters.append(category)

    if conditions:

        where_clause = (
            " WHERE "
            + " AND ".join(conditions)
        )

    else:

        where_clause = ""

    return where_clause, parameters


# ============================================================
# KPI API
# ============================================================

@app.route(
    "/api/kpis",
    methods=["GET"]
)
def get_kpis():

    region = request.args.get(
        "region"
    )

    category = request.args.get(
        "category"
    )

    where_clause, parameters = (
        build_filter_conditions(
            region,
            category
        )
    )

    connection = get_connection()

    try:

        df = pd.read_sql_query(
            "SELECT * FROM sales"
            + where_clause,
            connection,
            params=parameters
        )

    finally:

        connection.close()

    if df.empty:

        return jsonify({

            "total_sales": 0,
            "total_profit": 0,
            "total_orders": 0,
            "total_quantity": 0,
            "average_order_value": 0,
            "profit_margin": 0,
            "average_discount": 0,
            "top_region": "-",
            "top_region_sales": 0,
            "top_category": "-",
            "top_category_sales": 0,
            "top_product": "-",
            "top_product_sales": 0,
            "top_profit_product": "-",
            "top_profit_product_value": 0

        })

    total_sales = float(
        df["Sales"].sum()
    )

    total_profit = float(
        df["Profit"].sum()
    )

    total_orders = int(
        len(df)
    )

    total_quantity = int(
        df["Quantity"].sum()
    )

    average_order_value = (
        total_sales / total_orders
        if total_orders > 0
        else 0
    )

    profit_margin = (
        (total_profit / total_sales) * 100
        if total_sales > 0
        else 0
    )

    average_discount = float(
        df["Discount"].mean() * 100
    )

    region_sales = (
        df.groupby("Region")["Sales"]
        .sum()
        .sort_values(ascending=False)
    )

    category_sales = (
        df.groupby("Category")["Sales"]
        .sum()
        .sort_values(ascending=False)
    )

    product_sales = (
        df.groupby("Product")["Sales"]
        .sum()
        .sort_values(ascending=False)
    )

    product_profit = (
        df.groupby("Product")["Profit"]
        .sum()
        .sort_values(ascending=False)
    )

    return jsonify({

        "total_sales":
            float(total_sales),

        "total_profit":
            float(total_profit),

        "total_orders":
            int(total_orders),

        "total_quantity":
            int(total_quantity),

        "average_order_value":
            float(average_order_value),

        "profit_margin":
            float(profit_margin),

        "average_discount":
            float(average_discount),

        "top_region":
            str(region_sales.index[0])
            if not region_sales.empty
            else "-",

        "top_region_sales":
            float(region_sales.iloc[0])
            if not region_sales.empty
            else 0,

        "top_category":
            str(category_sales.index[0])
            if not category_sales.empty
            else "-",

        "top_category_sales":
            float(category_sales.iloc[0])
            if not category_sales.empty
            else 0,

        "top_product":
            str(product_sales.index[0])
            if not product_sales.empty
            else "-",

        "top_product_sales":
            float(product_sales.iloc[0])
            if not product_sales.empty
            else 0,

        "top_profit_product":
            str(product_profit.index[0])
            if not product_profit.empty
            else "-",

        "top_profit_product_value":
            float(product_profit.iloc[0])
            if not product_profit.empty
            else 0

    })


# ============================================================
# DASHBOARD API
# ============================================================

@app.route(
    "/api/dashboard",
    methods=["GET"]
)
def dashboard():

    region = request.args.get(
        "region"
    )

    category = request.args.get(
        "category"
    )

    where_clause, parameters = (
        build_filter_conditions(
            region,
            category
        )
    )

    connection = get_connection()

    try:

        df = pd.read_sql_query(
            "SELECT * FROM sales"
            + where_clause,
            connection,
            params=parameters
        )

    finally:

        connection.close()

    if df.empty:

        return jsonify({

            "region": {
                "labels": [],
                "values": []
            },

            "category": {
                "labels": [],
                "values": []
            },

            "product": {
                "labels": [],
                "values": []
            },

            "region_performance": {
                "labels": [],
                "sales": [],
                "profit": []
            },

            "monthly": {
                "labels": [],
                "values": []
            }

        })

    region_data = (
        df.groupby("Region")["Sales"]
        .sum()
        .sort_values(ascending=False)
    )

    category_data = (
        df.groupby("Category")["Sales"]
        .sum()
        .sort_values(ascending=False)
    )

    product_data = (
        df.groupby("Product")["Sales"]
        .sum()
        .sort_values(ascending=False)
    )

    performance = (
        df.groupby("Region")
        [["Sales", "Profit"]]
        .sum()
    )

    df["Order_Date"] = pd.to_datetime(
        df["Order_Date"],
        errors="coerce"
    )

    monthly_data = (
        df.dropna(
            subset=["Order_Date"]
        )
        .assign(
            Month=lambda x:
                x["Order_Date"]
                .dt.to_period("M")
                .astype(str)
        )
        .groupby("Month")["Sales"]
        .sum()
        .sort_index()
    )

    return jsonify({

        "region": {

            "labels":
                region_data.index.tolist(),

            "values":
                [
                    float(value)
                    for value
                    in region_data.values
                ]

        },

        "category": {

            "labels":
                category_data.index.tolist(),

            "values":
                [
                    float(value)
                    for value
                    in category_data.values
                ]

        },

        "product": {

            "labels":
                product_data.index.tolist(),

            "values":
                [
                    float(value)
                    for value
                    in product_data.values
                ]

        },

        "region_performance": {

            "labels":
                performance.index.tolist(),

            "sales":
                [
                    float(value)
                    for value
                    in performance["Sales"]
                ],

            "profit":
                [
                    float(value)
                    for value
                    in performance["Profit"]
                ]

        },

        "monthly": {

            "labels":
                monthly_data.index.tolist(),

            "values":
                [
                    float(value)
                    for value
                    in monthly_data.values
                ]

        }

    })


# ============================================================
# GEMINI SQL GENERATION
# ============================================================

def generate_sql(
    question,
    region=None,
    category=None
):

    if client is None:

        raise ValueError(
            "Gemini API is not configured."
        )

    filter_instruction = ""

    if region:

        filter_instruction += (
            f"\nThe dashboard is currently filtered "
            f"to Region = '{region}'. "
            f"Respect this filter."
        )

    if category:

        filter_instruction += (
            f"\nThe dashboard is currently filtered "
            f"to Category = '{category}'. "
            f"Respect this filter."
        )

    prompt = f"""
You are an expert business data analyst.

Generate ONE SQLite SQL query to answer the user's business question.

Database table:
sales

Columns:
Order_ID
Order_Date
Customer
Product
Category
Region
Quantity
Sales
Discount
Profit

Rules:

1. Return ONLY the SQL query.
2. The query must be SELECT or WITH.
3. Use ONLY the sales table.
4. Never modify the database.
5. Never use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE,
   PRAGMA, ATTACH, DETACH, REPLACE, VACUUM, REINDEX,
   TRANSACTION, COMMIT, or ROLLBACK.
6. Do not use SQL comments.
7. Do not use multiple SQL statements.
8. Use SQLite-compatible syntax.
9. Answer the business question directly.
10. Use clear column aliases.
11. If aggregation is needed, use GROUP BY.
12. If ranking is needed, use ORDER BY and LIMIT.
13. If percentages or margins are requested, calculate them
    from actual Sales and Profit values.
14. Do not invent columns.
15. Do not invent data.
16. Respect active dashboard filters.
17. Do not wrap the SQL in Markdown code fences.

{filter_instruction}

User question:
{question}
"""

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt
    )

    return clean_sql(
        response.text
    )


# ============================================================
# AI BUSINESS INSIGHT
# ============================================================

def generate_business_insight(
    question,
    results
):

    if client is None:

        return {

            "summary":
                "AI insight generation is unavailable.",

            "key_finding":
                "The query results are available for analysis.",

            "recommendation":
                "Review the displayed results and identify the most important business trend."

        }

    result_text = str(results)

    prompt = f"""
You are a professional business analyst.

The user asked:
{question}

Actual query results:
{result_text}

Create a concise business analysis.

Return exactly three sections:

SUMMARY:
A short explanation of what the data shows.

KEY FINDING:
The most important business finding supported by the actual results.

RECOMMENDATION:
A practical business recommendation based ONLY on the actual results.

Rules:
- Do not invent numbers.
- Do not invent trends.
- Do not make unsupported claims.
- Use actual data from the results.
- Keep each section concise.
"""

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt
    )

    text = response.text.strip()

    summary = ""
    key_finding = ""
    recommendation = ""

    summary_match = re.search(
        r"SUMMARY:\s*(.*?)(?=KEY FINDING:|$)",
        text,
        re.IGNORECASE | re.DOTALL
    )

    finding_match = re.search(
        r"KEY FINDING:\s*(.*?)(?=RECOMMENDATION:|$)",
        text,
        re.IGNORECASE | re.DOTALL
    )

    recommendation_match = re.search(
        r"RECOMMENDATION:\s*(.*)$",
        text,
        re.IGNORECASE | re.DOTALL
    )

    if summary_match:

        summary = (
            summary_match
            .group(1)
            .strip()
        )

    if finding_match:

        key_finding = (
            finding_match
            .group(1)
            .strip()
        )

    if recommendation_match:

        recommendation = (
            recommendation_match
            .group(1)
            .strip()
        )

    return {

        "summary":
            summary
            or "No summary generated.",

        "key_finding":
            key_finding
            or "No key finding generated.",

        "recommendation":
            recommendation
            or "No recommendation generated."

    }


# ============================================================
# AI ANALYZE API
# ============================================================

@app.route(
    "/api/analyze",
    methods=["POST"]
)
def analyze():

    data = request.get_json(
        silent=True
    ) or {}

    question = (
        data.get("question")
        or ""
    ).strip()

    region = data.get(
        "region"
    )

    category = data.get(
        "category"
    )

    if not question:

        return jsonify({

            "error":
                "Please enter a business question."

        }), 400

    try:

        # Generate SQL
        sql = generate_sql(
            question,
            region,
            category
        )

        sql = clean_sql(
            sql
        )

        # Security validation
        if not validate_sql(sql):

            print(
                "Rejected SQL:",
                repr(sql)
            )

            return jsonify({

                "error":
                    "The generated SQL query failed security validation."

            }), 400

        # Execute SQL
        connection = get_connection()

        try:

            result_df = pd.read_sql_query(
                sql,
                connection
            )

        finally:

            connection.close()

        # Convert results
        results = dataframe_to_records(
            result_df
        )

        # Generate insight
        insight = generate_business_insight(
            question,
            results
        )

        return jsonify({

            "question":
                question,

            "region":
                region,

            "category":
                category,

            "sql":
                sql,

            "results":
                results,

            "insight":
                insight

        })

    except Exception as error:

        print(
            "Analysis error:",
            error
        )

        return jsonify({

            "error":
                str(error)

        }), 500


# ============================================================
# FILE UPLOAD API
# ============================================================

@app.route(
    "/api/upload",
    methods=["POST"]
)
def upload_file():

    if "file" not in request.files:

        return jsonify({

            "success": False,

            "error":
                "No file was uploaded."

        }), 400

    file = request.files["file"]

    if not file.filename:

        return jsonify({

            "success": False,

            "error":
                "Please select a file."

        }), 400

    if not allowed_file(
        file.filename
    ):

        return jsonify({

            "success": False,

            "error":
                "Only CSV and Excel (.xlsx) files are supported."

        }), 400

    try:

        # Load file
        df = load_uploaded_file(
            file
        )

        # Clean column names
        df = clean_column_names(
            df
        )

        # Validate structure
        valid, error_message = (
            validate_dataset(df)
        )

        if not valid:

            return jsonify({

                "success": False,

                "error":
                    error_message

            }), 400

        # Clean data
        df = clean_uploaded_data(
            df
        )

        # Validate usable records
        if df.empty:

            return jsonify({

                "success": False,

                "error":
                    "No usable records remained after cleaning."

            }), 400

        # Save uploaded file
        extension = file.filename.rsplit(
            ".",
            1
        )[-1].lower()

        saved_filename = (
            "uploaded_sales_data."
            + extension
        )

        saved_path = (
            Path(
                app.config["UPLOAD_FOLDER"]
            )
            / saved_filename
        )

        file.seek(0)

        with open(
            saved_path,
            "wb"
        ) as output_file:

            output_file.write(
                file.read()
            )

        # Replace SQLite table
        save_dataframe_to_database(
            df
        )

        return jsonify({

            "success": True,

            "message":
                "Dataset uploaded successfully.",

            "filename":
                file.filename,

            "records":
                int(len(df)),

            "columns":
                list(df.columns)

        })

    except Exception as error:

        print(
            "Upload error:",
            error
        )

        return jsonify({

            "success": False,

            "error":
                "Unable to process the uploaded file: "
                + str(error)

        }), 500


# ============================================================
# HOME PAGE
# ============================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# ============================================================
# FILE SIZE ERROR
# ============================================================

@app.errorhandler(413)
def file_too_large(error):

    return jsonify({

        "success": False,

        "error":
            "File is too large. Maximum size is 10 MB."

    }), 413


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )