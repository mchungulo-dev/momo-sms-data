# MoMo SMS Data Processing and Analytics System, Team 1

## Team members

- China Viola
- Esther Harusi Konde
- Memory Chungulo
- Yves Isite

## Project Description

This project processes MoMo (Mobile Money) SMS data provided in XML format.
The system extracts, cleans, categorizes, and stores the transaction data in
a relational database, and provides a frontend dashboard for analyzing and
visualizing the data.

## Links

- Architecture Diagram: https://miro.com/app/board/uXjVHpg8KfI=/?share_link_id=992757985832
- Scrum Board: https://alustudent-team-lszz7o93.atlassian.net/jira/software/projects/LMS/summary?atlOrigin=eyJpIjoiN2U4YzY0ZWRmZDY5NDBlMDlhNDZlZTYzZWMxMTc5YWEiLCJwIjoiaiJ9

## Setup

Setup instructions will be added as the project is developed.

## Project Structure

```text
momo-sms-data-processing/
│
├── README.md
├── .env.example
├── requirements.txt
├── index.html
│
├── web/
│   ├── styles.css
│   ├── chart_handler.js
│   └── assets/
│
├── data/
│   ├── raw/
│   │   └── momo.xml
│   ├── processed/
│   │   └── dashboard.json
│   ├── db.sqlite3
│   └── logs/
│       ├── etl.log
│       └── dead_letter/
│
├── etl/
│   ├── __init__.py
│   ├── config.py
│   ├── parse_xml.py
│   ├── clean_normalize.py
│   ├── categorize.py
│   ├── load_db.py
│   └── run.py
│
├── api/            # optional bonus
│   ├── __init__.py
│   ├── app.py
│   ├── db.py
│   └── schemas.py
│
├── scripts/
│   ├── run_etl.sh
│   ├── export_json.sh
│   └── serve_frontend.sh
│
└── tests/
    ├── test_parse_xml.py
    ├── test_clean_normalize.py
    └── test_categorize.py
```
