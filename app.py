from flask import Flask, render_template, request, jsonify
import sqlite3
import pandas as pd
import numpy as np
import os
import re
import time
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


# Make sure required folders exist
UPLOAD_FOLDER.mkdir(
    parents=True,
    exist_ok=True
)

DB_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if api_key:
    client = genai.Client(
        api_key=api_key
    )
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

    connection = sqlite3.connect(
        DB_FILE
    )

    return connection


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

    records = df.to_dict(
        orient="records"
    )

    safe_records = []

    for record in records:

        safe_record = {}

        for key, value in record.items():

            safe_record[key] = make_json_safe(
                value
            )

        safe_records.append(
            safe_record
        )

    return safe_records


# ============================================================
# ALLOWED FILE CHECK
# ============================================================

def allowed_file(filename):

    if not filename:
        return False

    extension = filename.rsplit(
        ".",
        1
    )[-1].lower()

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

        cleaned_columns.append(
            column
        )

    df.columns = cleaned_columns

    return df


# ============================================================
# CLEAN DATASET
# ============================================================

def clean_uploaded_data(df):

    df = df.copy()

    # Remove completely empty rows
    df = df.dropna(
        how="all"
    )

    # Remove completely empty columns
    df = df.dropna(
        axis=1,
        how="all"
    )

    # --------------------------------------------------------
    # Strip whitespace from text columns
    # --------------------------------------------------------

    for column in df.select_dtypes(
        include=["object"]
    ).columns:

        df[column] = (
            df[column]
            .astype(str)
            .str.strip()
        )

    # --------------------------------------------------------
    # Numeric columns
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Date column
    # --------------------------------------------------------

    if "Order_Date" in df.columns:

        df["Order_Date"] = pd.to_datetime(
            df["Order_Date"],
            errors="coerce"
        )

        df["Order_Date"] = (
            df["Order_Date"]
            .dt.strftime("%Y-%m-%d")
        )

    # --------------------------------------------------------
    # Remove incomplete business rows
    # --------------------------------------------------------

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

        df = pd.read_csv(
            file
        )

    elif extension == "xlsx":

        df = pd.read_excel(
            file
        )

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

    sql = str(sql).strip()

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
        sql,
        flags=re.IGNORECASE
    )

    # Remove accidental SQL prefix
    if sql.lower().startswith(
        "sql:"
    ):

        sql = sql[4:].strip()

    # Remove accidental surrounding whitespace
    sql = sql.strip()

    return sql


# ============================================================
# SQL VALIDATION
# ============================================================

def validate_sql(sql):

    """
    Validate AI-generated SQL before execution.

    Security goals:
    - SELECT / WITH only
    - sales table only
    - no multiple statements
    - no comments
    - no database modification
    - no SQLite internal tables
    - no dangerous SQLite functions
    - allow legitimate analytical SQL such as:
      GROUP BY, ORDER BY, LIMIT, CASE, ROUND,
      CAST, strftime, subqueries and CTEs.
    """

    if not sql:
        return False

    sql_clean = clean_sql(
        sql
    )

    # --------------------------------------------------------
    # Maximum query length
    # --------------------------------------------------------

    if len(sql_clean) > 5000:
        return False

    # --------------------------------------------------------
    # Remove one trailing semicolon
    # --------------------------------------------------------

    if sql_clean.endswith(";"):

        sql_clean = (
            sql_clean[:-1]
            .strip()
        )

    if not sql_clean:
        return False

    lowered_sql = sql_clean.lower()

    # --------------------------------------------------------
    # Only SELECT / WITH
    # --------------------------------------------------------

    if not (
        lowered_sql.startswith("select")
        or lowered_sql.startswith("with")
    ):
        return False

    # Make sure SELECT/WITH is actually a keyword
    first_keyword_match = re.match(
        r"^\s*(select|with)\b",
        lowered_sql,
        re.IGNORECASE
    )

    if not first_keyword_match:
        return False

    # --------------------------------------------------------
    # Multiple statements
    # --------------------------------------------------------

    if ";" in sql_clean:
        return False

    # --------------------------------------------------------
    # SQL comments
    # --------------------------------------------------------

    if "--" in sql_clean:
        return False

    if "/*" in sql_clean:
        return False

    if "*/" in sql_clean:
        return False

    # --------------------------------------------------------
    # Block dangerous SQL keywords
    # --------------------------------------------------------

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

        pattern = (
            r"\b"
            + re.escape(keyword)
            + r"\b"
        )

        if re.search(
            pattern,
            lowered_sql
        ):
            return False

    # --------------------------------------------------------
    # Block SQLite internal tables
    # --------------------------------------------------------

    blocked_internal_tables = [
        "sqlite_master",
        "sqlite_schema",
        "sqlite_temp_master",
        "sqlite_sequence"
    ]

    for table_name in blocked_internal_tables:

        pattern = (
            r"\b"
            + re.escape(table_name)
            + r"\b"
        )

        if re.search(
            pattern,
            lowered_sql
        ):
            return False

    # --------------------------------------------------------
    # Block dangerous SQLite functions
    # --------------------------------------------------------

    blocked_functions = [
        "load_extension",
        "readfile",
        "writefile"
    ]

    for function_name in blocked_functions:

        pattern = (
            r"\b"
            + re.escape(function_name)
            + r"\s*\("
        )

        if re.search(
            pattern,
            lowered_sql
        ):
            return False

    # --------------------------------------------------------
    # TABLE VALIDATION
    #
    # Only FROM sales and JOIN sales are allowed.
    #
    # Supports:
    # FROM sales
    # FROM "sales"
    # FROM `sales`
    # JOIN sales
    # --------------------------------------------------------

    table_matches = re.findall(
        r"""
        \b(?:FROM|JOIN)
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

        table = (
            match[0]
            or match[1]
        )

        if table.lower() not in allowed_tables:
            return False

    # --------------------------------------------------------
    # The query must reference sales.
    #
    # This also permits CTEs/subqueries that eventually
    # reference the sales table.
    # --------------------------------------------------------

    if not re.search(
        r"\bsales\b",
        lowered_sql
    ):
        return False

    # --------------------------------------------------------
    # Block suspicious database-object access
    # --------------------------------------------------------

    suspicious_patterns = [

        r"\btemp\b",

        r"\btemp\.",

        r"\bmain\.",

        r"\btemp\.",

        r"\battach\b",

        r"\bdetach\b"

    ]

    for pattern in suspicious_patterns:

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

        parameters.append(
            region
        )

    if category:

        conditions.append(
            "Category = ?"
        )

        parameters.append(
            category
        )

    if conditions:

        where_clause = (
            " WHERE "
            + " AND ".join(
                conditions
            )
        )

    else:

        where_clause = ""

    return (
        where_clause,
        parameters
    )


# ============================================================
# GEMINI TRANSIENT ERROR CHECK
# ============================================================

def is_temporary_gemini_error(
    error
):

    error_text = str(
        error
    ).lower()

    temporary_errors = [
        "503",
        "unavailable",
        "high demand",
        "429",
        "resource exhausted",
        "rate limit",
        "too many requests",
        "deadline exceeded",
        "timeout",
        "timed out",
        "temporarily unavailable",
        "service unavailable"
    ]

    return any(
        message in error_text
        for message in temporary_errors
    )


# ============================================================
# GEMINI SAFE GENERATION WITH RETRIES
# ============================================================

def generate_gemini_content(
    prompt,
    max_retries=3
):

    if client is None:

        raise ValueError(
            "Gemini API is not configured."
        )

    last_error = None

    for attempt in range(
        max_retries
    ):

        try:

            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt
            )

            if (
                not response
                or not response.text
            ):

                raise ValueError(
                    "Gemini returned an empty response."
                )

            return response

        except Exception as error:

            last_error = error

            print(
                f"Gemini attempt {attempt + 1} failed:",
                error
            )

            # Retry only temporary service errors
            if not is_temporary_gemini_error(
                error
            ):
                raise

            # No wait after final attempt
            if attempt == max_retries - 1:
                break

            wait_time = 2 ** (
                attempt + 1
            )

            print(
                f"Retrying Gemini in {wait_time} seconds..."
            )

            time.sleep(
                wait_time
            )

    raise last_error


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
        (
            total_profit
            / total_sales
        ) * 100
        if total_sales > 0
        else 0
    )

    average_discount = float(
        df["Discount"].mean() * 100
    )

    region_sales = (
        df.groupby("Region")["Sales"]
        .sum()
        .sort_values(
            ascending=False
        )
    )

    category_sales = (
        df.groupby("Category")["Sales"]
        .sum()
        .sort_values(
            ascending=False
        )
    )

    product_sales = (
        df.groupby("Product")["Sales"]
        .sum()
        .sort_values(
            ascending=False
        )
    )

    product_profit = (
        df.groupby("Product")["Profit"]
        .sum()
        .sort_values(
            ascending=False
        )
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
            float(
                average_order_value
            ),

        "profit_margin":
            float(
                profit_margin
            ),

        "average_discount":
            float(
                average_discount
            ),

        "top_region":
            str(
                region_sales.index[0]
            )
            if not region_sales.empty
            else "-",

        "top_region_sales":
            float(
                region_sales.iloc[0]
            )
            if not region_sales.empty
            else 0,

        "top_category":
            str(
                category_sales.index[0]
            )
            if not category_sales.empty
            else "-",

        "top_category_sales":
            float(
                category_sales.iloc[0]
            )
            if not category_sales.empty
            else 0,

        "top_product":
            str(
                product_sales.index[0]
            )
            if not product_sales.empty
            else "-",

        "top_product_sales":
            float(
                product_sales.iloc[0]
            )
            if not product_sales.empty
            else 0,

        "top_profit_product":
            str(
                product_profit.index[0]
            )
            if not product_profit.empty
            else "-",

        "top_profit_product_value":
            float(
                product_profit.iloc[0]
            )
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

    # --------------------------------------------------------
    # Region
    # --------------------------------------------------------

    region_data = (
        df.groupby("Region")["Sales"]
        .sum()
        .sort_values(
            ascending=False
        )
    )

    # --------------------------------------------------------
    # Category
    # --------------------------------------------------------

    category_data = (
        df.groupby("Category")["Sales"]
        .sum()
        .sort_values(
            ascending=False
        )
    )

    # --------------------------------------------------------
    # Product
    # --------------------------------------------------------

    product_data = (
        df.groupby("Product")["Sales"]
        .sum()
        .sort_values(
            ascending=False
        )
    )

    # --------------------------------------------------------
    # Regional performance
    # --------------------------------------------------------

    performance = (
        df.groupby("Region")
        [["Sales", "Profit"]]
        .sum()
    )

    # --------------------------------------------------------
    # Monthly trend
    # --------------------------------------------------------

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
            f"""
The dashboard is currently filtered to:
Region = '{region}'

You MUST respect this active filter.
"""
        )

    if category:

        filter_instruction += (
            f"""
The dashboard is currently filtered to:
Category = '{category}'

You MUST respect this active filter.
"""
        )

    prompt = f"""
You are the SQL generation engine of an AI Business Analytics application.

Your task is to convert the user's natural-language business question
into ONE safe, valid SQLite query.

DATABASE
========

Table:
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


IMPORTANT SQL RULES
===================

1. Return ONLY the SQL query.
2. Do NOT return explanations.
3. Do NOT return Markdown.
4. Do NOT use ```sql.
5. The query MUST start with SELECT or WITH.
6. Use ONLY the sales table.
7. Never modify data.
8. Never use INSERT.
9. Never use UPDATE.
10. Never use DELETE.
11. Never use DROP.
12. Never use ALTER.
13. Never use CREATE.
14. Never use PRAGMA.
15. Never use ATTACH.
16. Never use DETACH.
17. Never use REPLACE.
18. Never use VACUUM.
19. Never use REINDEX.
20. Never use TRANSACTION.
21. Never use COMMIT.
22. Never use ROLLBACK.
23. Do not use SQL comments.
24. Do not use multiple statements.
25. Use SQLite-compatible syntax.
26. Do not invent columns.
27. Do not invent data.
28. Answer the user's question directly.
29. Use meaningful column aliases.
30. Use GROUP BY when aggregation is required.
31. Use ORDER BY and LIMIT when ranking is required.
32. Use actual Sales and Profit values for financial calculations.
33. Respect active dashboard filters.


BUSINESS QUESTION SUPPORT
=========================

You must correctly handle questions about:

- total sales
- total profit
- sales by region
- sales by category
- sales by product
- profit by product
- highest sales region
- highest profit product
- lowest sales region
- best-selling product
- profit margin
- average order value
- quantity sold
- discounts
- monthly sales
- monthly profit
- sales trends
- monthly trends
- category comparisons
- regional comparisons
- product comparisons
- rankings
- percentages
- business performance


MONTHLY TREND EXAMPLE
=====================

For a question such as:

"Show monthly sales trend"

a valid query can be:

SELECT
    strftime('%Y-%m', Order_Date) AS Month,
    SUM(Sales) AS Total_Sales
FROM sales
GROUP BY strftime('%Y-%m', Order_Date)
ORDER BY Month;


DATE HANDLING
=============

Order_Date contains dates.

For monthly analysis, SQLite strftime() may be used.

Example:

strftime('%Y-%m', Order_Date)


FINANCIAL CALCULATIONS
======================

For profit margin:

(SUM(Profit) * 100.0 / NULLIF(SUM(Sales), 0))

For average order value:

SUM(Sales) * 1.0 / COUNT(DISTINCT Order_ID)


ACTIVE FILTERS
==============

{filter_instruction}


USER QUESTION
=============

{question}
"""

    response = generate_gemini_content(
        prompt,
        max_retries=3
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

    result_text = str(
        results
    )

    prompt = f"""
You are a professional Business Analytics analyst.

The user asked:

{question}

Actual query results:

{result_text}


Create a concise business analysis.

Return exactly these three sections:

SUMMARY:
A short explanation of what the actual data shows.

KEY FINDING:
The most important business finding supported by the actual results.

RECOMMENDATION:
A practical business recommendation based ONLY on the actual results.


IMPORTANT RULES:

- Do not invent numbers.
- Do not invent trends.
- Do not make unsupported claims.
- Use only the actual query results.
- Keep each section concise.
- This is an Indian business analytics application.
- Use Indian Rupee notation (₹) when discussing Sales, Profit,
  Revenue or other monetary values.
- Never use $ for the business data.
"""

    response = generate_gemini_content(
        prompt,
        max_retries=3
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

        # ----------------------------------------------------
        # Generate SQL
        # ----------------------------------------------------

        sql = generate_sql(
            question,
            region,
            category
        )

        sql = clean_sql(
            sql
        )

        print(
            "Generated SQL:",
            repr(sql)
        )

        # ----------------------------------------------------
        # Security validation
        # ----------------------------------------------------

        if not validate_sql(
            sql
        ):

            print(
                "Rejected SQL:",
                repr(sql)
            )

            return jsonify({

                "error":
                    "The AI generated a SQL query that was not accepted by the security validator. Please try the question again."

            }), 400

        # ----------------------------------------------------
        # Execute SQL
        # ----------------------------------------------------

        connection = get_connection()

        try:

            result_df = pd.read_sql_query(
                sql,
                connection
            )

        finally:

            connection.close()

        # ----------------------------------------------------
        # Convert results
        # ----------------------------------------------------

        results = dataframe_to_records(
            result_df
        )

        # ----------------------------------------------------
        # Generate AI insight
        # ----------------------------------------------------

        try:

            insight = generate_business_insight(
                question,
                results
            )

        except Exception as insight_error:

            print(
                "AI insight generation failed:",
                insight_error
            )

            insight = {

                "summary":
                    "The business query was completed successfully. "
                    "AI explanation is temporarily unavailable.",

                "key_finding":
                    "Review the displayed query results for the main business finding.",

                "recommendation":
                    "Use the displayed results to guide the next business decision."

            }

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

        error_text = str(
            error
        ).lower()

        # ----------------------------------------------------
        # Temporary Gemini problems
        # ----------------------------------------------------

        if is_temporary_gemini_error(
            error
        ):

            return jsonify({

                "error":
                    "The AI service is temporarily busy. "
                    "Your data is safe. Please try the question again in a few seconds."

            }), 503

        # ----------------------------------------------------
        # Gemini configuration problems
        # ----------------------------------------------------

        if (
            "api key" in error_text
            or "api_key" in error_text
            or "authentication" in error_text
            or "permission" in error_text
        ):

            return jsonify({

                "error":
                    "The AI service could not be authenticated. "
                    "Please check the Gemini API configuration."

            }), 500

        # ----------------------------------------------------
        # SQL/database problems
        # ----------------------------------------------------

        if (
            "no such table" in error_text
            or "no such column" in error_text
            or "syntax error" in error_text
        ):

            return jsonify({

                "error":
                    "The generated business query could not be executed against the current dataset."

            }), 400

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

        # ----------------------------------------------------
        # Load file
        # ----------------------------------------------------

        df = load_uploaded_file(
            file
        )

        # ----------------------------------------------------
        # Clean column names
        # ----------------------------------------------------

        df = clean_column_names(
            df
        )

        # ----------------------------------------------------
        # Validate structure
        # ----------------------------------------------------

        valid, error_message = (
            validate_dataset(
                df
            )
        )

        if not valid:

            return jsonify({

                "success": False,

                "error":
                    error_message

            }), 400

        # ----------------------------------------------------
        # Clean data
        # ----------------------------------------------------

        df = clean_uploaded_data(
            df
        )

        # ----------------------------------------------------
        # Validate usable records
        # ----------------------------------------------------

        if df.empty:

            return jsonify({

                "success": False,

                "error":
                    "No usable records remained after cleaning."

            }), 400

        # ----------------------------------------------------
        # Save uploaded file
        # ----------------------------------------------------

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
                app.config[
                    "UPLOAD_FOLDER"
                ]
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

        # ----------------------------------------------------
        # Replace SQLite table
        # ----------------------------------------------------

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
                int(
                    len(df)
                ),

            "columns":
                list(
                    df.columns
                )

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