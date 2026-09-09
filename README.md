\# AI Business Analytics Copilot



An AI-powered business analytics web application that transforms business data into actionable insights using Python, SQL, interactive visualizations, and Generative AI.



\---



\## 📌 Project Overview



AI Business Analytics Copilot allows users to upload business datasets, explore important business KPIs, analyze trends through interactive visualizations, and ask business questions using natural language.



Instead of manually searching through dashboards, users can simply ask questions such as:



\- Which region generated the highest sales?

\- Which product generated the highest profit?

\- Which category generated the highest sales?

\- Which region has the best profit margin?

\- Show the monthly sales trend.



The system converts the natural-language question into SQL, retrieves the relevant data, creates a visualization, and generates business-focused insights and recommendations.



\---



\## 🎯 Problem Statement



Business users often need technical knowledge of SQL and data analytics to extract meaningful insights from business datasets.



Traditional dashboards require users to manually explore multiple charts and filters.



This project aims to simplify business analysis by allowing users to interact with their data using natural language while keeping the underlying SQL and analytical process visible.



\---



\## 💡 Solution



The AI Business Analytics Copilot combines traditional data analytics with Generative AI.



The application:



1\. Accepts business datasets through CSV or Excel upload.

2\. Cleans and validates the dataset using Pandas.

3\. Stores the data in a SQLite database.

4\. Calculates business KPIs.

5\. Allows users to ask questions in natural language.

6\. Uses Gemini AI to generate SQL.

7\. Validates the generated SQL before execution.

8\. Executes the query against the business database.

9\. Displays the query results.

10\. Generates an automatic visualization.

11\. Produces business-focused insights and recommendations.



\---



\## ✨ Key Features



\### 📊 Interactive Business Dashboard



The dashboard provides important business metrics including:



\- Total Sales

\- Total Profit

\- Total Orders

\- Quantity Sold

\- Average Order Value

\- Profit Margin

\- Average Discount

\- Top Region

\- Top Category

\- Top Product

\- Top Profit Product



\### 📈 Interactive Visualizations



The application provides interactive Plotly charts for:



\- Sales by Region

\- Sales by Category

\- Sales by Product

\- Regional Sales \& Profit

\- Monthly Sales Trend

\- AI-generated query visualizations



\### 🤖 AI Business Copilot



Users can ask business questions using natural language.



Example:



> Which region generated the highest sales?



The Copilot generates SQL, retrieves the relevant data, creates a visualization, and generates business insights.



\### 📁 CSV / Excel Upload



Users can upload:



\- CSV files

\- Excel `.xlsx` files



The application validates and cleans uploaded datasets before storing them in the database.



\### 🔐 SQL Security Validation



AI-generated SQL is validated before execution.



The validation layer:



\- Allows analytical SELECT queries

\- Restricts database access to the intended business table

\- Blocks database modification operations

\- Blocks multiple SQL statements

\- Blocks SQL comments

\- Blocks potentially dangerous SQLite operations

\- Rejects invalid SQL queries



\### 💡 Business Insights



The AI generates three business-focused outputs:



\- Summary

\- Key Finding

\- Recommendation



These insights are generated from the retrieved query results.



\---



\## 🏗️ System Architecture



```text

&#x20;                        User

&#x20;                          │

&#x20;                          ▼

&#x20;                 Business Question

&#x20;                          │

&#x20;                          ▼

&#x20;                      Gemini AI

&#x20;                          │

&#x20;                          ▼

&#x20;                    SQL Generation

&#x20;                          │

&#x20;                          ▼

&#x20;                   SQL Validation

&#x20;                          │

&#x20;                          ▼

&#x20;                   SQLite Database

&#x20;                          │

&#x20;                          ▼

&#x20;                     SQL Results

&#x20;                          │

&#x20;                 ┌────────┴────────┐

&#x20;                 ▼                 ▼

&#x20;            Plotly Chart      AI Analysis

&#x20;                 │                 │

&#x20;                 └────────┬────────┘

&#x20;                          ▼

&#x20;                Business Recommendation



CSV / Excel Upload

&#x20;       ↓

Data Validation

&#x20;       ↓

Data Cleaning with Pandas

&#x20;       ↓

SQLite Database

&#x20;       ↓

Dashboard KPIs \& Charts

&#x20;       ↓

Natural Language Question

&#x20;       ↓

Gemini AI

&#x20;       ↓

SQL Query

&#x20;       ↓

SQL Security Validation

&#x20;       ↓

Query Execution

&#x20;       ↓

Query Results

&#x20;       ↓

Automatic Visualization

&#x20;       ↓

Business Insights

&#x20;       ↓

Recommendation   







| Technology    | Purpose                              |

| ------------- | ------------------------------------ |

| Python        | Backend and data processing          |

| Flask         | Web application backend              |

| Pandas        | Data cleaning and analysis           |

| NumPy         | Numerical operations                 |

| SQLite        | Local business database              |

| SQL           | Business data querying               |

| Plotly        | Interactive data visualization       |

| HTML          | Frontend structure                   |

| CSS           | Frontend styling                     |

| JavaScript    | Frontend interaction                 |

| Gemini AI     | SQL generation and business insights |

| python-dotenv | Environment variable management      |

| openpyxl      | Excel file processing                |







📂 Project Structure



AI-Business-Analytics-Copilot/

│

├── .env

├── .gitignore

├── app.py

├── README.md

│

├── data/

│   └── sales\_data.csv

│

├── database/

│   ├── setup\_database.py

│   ├── test\_database.py

│   └── business\_data.db

│

├── static/

│

├── templates/

│   └── index.html

│

├── test\_gemini.py

│

└── venv/



📋 Dataset



The included sample dataset contains business sales transactions

Dataset Columns

Order\_ID

Order\_Date

Customer

Product

Category

Region

Quantity

Sales

Discount

Profit



📊 Sample Business Results

| Metric              |      Result |

| ------------------- | ----------: |

| Total Sales         |  ₹12,55,000 |

| Total Profit        |   ₹1,97,000 |

| Total Orders        |          16 |

| Quantity Sold       |          65 |

| Average Order Value |  ₹78,437.50 |

| Top Region          |       South |

| Top Category        | Electronics |

| Top Product         |      Laptop |

| Top Profit Product  |      Laptop |

🔒 Security



The application includes an SQL validation layer before executing AI-generated queries.



The validation process checks that:



The query is an analytical query.

Only permitted database tables are accessed.

Data modification operations are blocked.

Multiple SQL statements are blocked.

SQL comments are blocked.

Potentially dangerous SQLite operations are blocked.

Invalid SQL queries are rejected.



The current implementation provides application-level SQL validation. Additional parser-level SQL controls and database permissions could be added for production environments.



🔑 Environment Variables



The Gemini API key is stored using an environment variable.



Create a .env file in the project root:



GEMINI\_API\_KEY=your\_api\_key\_here

Important



Never upload the .env file to GitHub.



The project includes .env in .gitignore to help prevent accidental exposure of API credentials.

