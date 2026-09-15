# MoMo SMS Data Processing and Analytics System, Team 1

## Team members

- China Viola
- Esther Harusi Konde
- Memory Chungulo
- Yves Isite

## Project Description

This project processes MoMo (Mobile Money) SMS data provided in XML format. The system extracts, cleans, categorizes, and stores the transaction data in a relational database, and provides a frontend dashboard for analyzing and visualizing the data.

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
├── database/
│   └── database_setup.sql
│
└── tests/
    ├── test_parse_xml.py
    ├── test_clean_normalize.py
    └── test_categorize.py
```

## Database Design

### Entity Relationship Diagram

![ERD](./Momo%20SMS%20App%20ERD.png)

The schema is built around five tables: `users`, `transactions`, `transaction_categories`, `transaction_has_categories`, and `system_logs`.

### Design rationale

We built this database around `transactions` because that's where everything begins, every MoMo SMS message turns into a transaction record.

For sender and receiver, we kept things simple by adding two foreign keys directly on the `transactions` table: one for who sent the money, one for who received it. That mirrors how it actually works, one sender, one receiver, every time. Rather than creating a separate table just to track who's involved in a transaction, we linked directly to `users`. A single user can appear across many transactions, sometimes sending, sometimes receiving.

For the many-to-many relationship, we chose `transactions` and `transaction_categories`. A transaction can carry more than one category (a merchant payment that's also part of a promotion, for example), and a single category can apply to many transactions. To support this, we created a junction table, `transaction_has_categories`, using a composite key of `transaction_id` and `category_id`, so the same category can't be tagged onto the same transaction twice. We also added a `created_at` field so we can tell exactly when a category was applied.

`transaction_categories` stays as its own table because we expect new categories to be added over time. We didn't want to keep modifying the `transactions` table structure every time a new category comes up.

Finally, `system_logs` connects back to both `users` and `transactions`. That way, whenever something succeeds, fails, or ends up in the dead-letter queue, we can trace exactly who was involved and which transaction it was tied to. That traceability matters when you're dealing with money, you need to be able to explain what went wrong and when.

### Data Dictionary

| Table | Column | Type | Nullable | Key | Description |
|---|---|---|---|---|---|
| users | user_id | int | NO | PRI | Unique identifier for a user (sender/receiver) |
| users | full_name | varchar(100) | NO | | Full name of the user |
| users | phone_number | varchar(15) | NO | UNI | MoMo-registered phone number |
| users | user_type | enum('CUSTOMER','AGENT','MERCHANT') | NO | | Role of the user in the MoMo network |
| users | created_at | datetime | NO | | Record creation timestamp |
| transactions | transaction_id | bigint | NO | PRI | Unique identifier for a transaction |
| transactions | sender_id | int | YES | MUL | FK to users; NULL when the SMS has no identifiable sender (e.g. deposit) |
| transactions | receiver_id | int | YES | MUL | FK to users; NULL when the SMS has no identifiable receiver (e.g. withdrawal) |
| transactions | amount | decimal(12,2) | NO | | Transaction amount in local currency |
| transactions | fee | decimal(8,2) | NO | | Transaction fee charged |
| transactions | created_at | datetime | NO | MUL | Timestamp the transaction occurred, parsed from the SMS |
| transactions | raw_sms_body | text | YES | | Original SMS text this record was parsed from |
| transaction_categories | category_id | int | NO | PRI | Unique identifier for a transaction category |
| transaction_categories | category_name | varchar(50) | NO | UNI | e.g. Transfer, Airtime, Bill Payment, Withdrawal |
| transaction_categories | description | varchar(255) | YES | | Human-readable explanation of the category |
| transaction_has_categories | transaction_id | bigint | NO | PRI | FK to transactions |
| transaction_has_categories | category_id | int | NO | PRI | FK to transaction_categories |
| transaction_has_categories | created_at | datetime | NO | | When this category tag was applied |
| system_logs | log_id | int | NO | PRI | Unique identifier for a log entry |
| system_logs | user_id | int | YES | MUL | FK to users; NULL when no user could be identified |
| system_logs | transaction_id | bigint | YES | MUL | FK to transactions; NULL for dead-letter entries with no created transaction |
| system_logs | log_level | enum('INFO','WARNING','ERROR') | NO | | Severity of the log entry |
| system_logs | action_performed | varchar(100) | NO | | e.g. PARSE, CLEAN, CATEGORIZE, LOAD |
| system_logs | status | enum('SUCCESS','FAILED','SKIPPED') | NO | MUL | Outcome of the ETL step |
| system_logs | error_message | text | YES | | Error detail when status is FAILED |
| system_logs | created_at | datetime | NO | | When the log entry was recorded |

### Constraints and integrity rules

To keep the data accurate and protect against bad or duplicate entries, we added the following at the database level:

| Rule | Enforced by | What it catches |
|---|---|---|
| Duplicate phone numbers | `UNIQUE` on `users.phone_number` | Two users registered with the same phone number |
| Malformed phone numbers | `CHECK chk_phone_format` | Phone numbers that don't match a valid format (e.g. `abc123`) |
| Invalid user roles | `ENUM` on `users.user_type` | Any role outside `CUSTOMER`, `AGENT`, `MERCHANT` |
| Negative transaction amounts | `CHECK chk_amount_positive` | Transactions with a negative amount |
| Negative fees | `CHECK chk_fee_non_negative` | Transactions with a negative fee |
| Unknown sender/receiver | `FOREIGN KEY` on `sender_id` / `receiver_id` | A transaction referencing a `user_id` that doesn't exist |
| Duplicate category tag | Composite `PRIMARY KEY` on `transaction_has_categories` | The same category applied twice to the same transaction |

These were tested directly against the database, for example, attempting to insert a transaction with a negative amount fails with `Check constraint 'chk_amount_positive' is violated`, and referencing a non-existent `sender_id` fails with a foreign key constraint error rather than silently corrupting the data.

### Sample queries

**Read: joining transactions with sender and receiver names**

```sql
SELECT t.transaction_id, u1.full_name AS sender, u2.full_name AS receiver, t.amount
FROM transactions t
LEFT JOIN users u1 ON t.sender_id = u1.user_id
LEFT JOIN users u2 ON t.receiver_id = u2.user_id;
```

**Create**

```sql
INSERT INTO users (full_name, phone_number, user_type)
VALUES ('Test User', '+250781457023', 'CUSTOMER');
```

**Update**

```sql
UPDATE transactions SET fee = 200.00 WHERE transaction_id = 1;
```

**Delete**

```sql
DELETE FROM system_logs WHERE log_id = 6;
```

The full set of table definitions, seed data, and these queries live in `database/database_setup.sql`.

## Status

This project is in active development as part of ALU coursework.