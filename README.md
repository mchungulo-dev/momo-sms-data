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

Requirements: Python 3.10+ and a running MySQL server (users for Basic Auth are stored there).

1. Create the database and an app user (once):

   ```bash
   mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS momo;
   CREATE USER IF NOT EXISTS 'momo_app'@'%' IDENTIFIED BY 'MomoApp#2026';
   GRANT ALL PRIVILEGES ON momo.* TO 'momo_app'@'%';"
   ```

2. Install dependencies and start the API:

   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   export MOMO_DB_PASSWORD='MomoApp#2026' ADMIN_INVITE_CODE='team1-invite'
   python api/server.py
   ```

   The server loads the parsed `dsa/data/transactions.json` into memory and listens on `http://127.0.0.1:8000`. Data resets on restart.

3. Create an admin account (only admins can POST, PUT and DELETE):

   ```bash
   curl -X POST http://127.0.0.1:8000/register -H "Content-Type: application/json" \
     -d '{"username":"team1admin","email":"team1admin@example.com","password":"Team1#Secure2026","invite_code":"team1-invite"}'
   ```

   Without the `invite_code` the account is a `viewer` (GET only). Passwords need 12+ characters with upper and lower case letters, a number and a symbol.

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
├── api/
│   ├── server.py       # REST API (http.server)
│   ├── auth.py         # Basic Auth + users in MySQL
│   └── data.py         # in-memory transaction store
│
├── dsa/
│   ├── modified_sms_v2.xml
│   ├── parse_data.py   # XML -> JSON
│   ├── search_compare.py
│   └── data/transactions.json
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

## API Documentation

Base URL: `http://127.0.0.1:8000`. Every `/transactions` request needs Basic Auth (`curl -u username:password`). Bodies are JSON.

| Method | Endpoint | Description | Role |
|---|---|---|---|
| POST | `/register` | Create a user (no auth) | none |
| GET | `/transactions` | List all transactions | viewer, operator, admin |
| GET | `/transactions/{id}` | Get one transaction | viewer, operator, admin |
| POST | `/transactions` | Add a transaction | operator, admin |
| PUT | `/transactions/{id}` | Update fields of a transaction | operator, admin |
| DELETE | `/transactions/{id}` | Delete a transaction | admin |

Transaction fields: `type`, `amount` (required on POST), and optionally `timestamp`, `sender`, `receiver`, `fee`, `balance`, `transaction_id`, `raw_sms_body`. The `id` is assigned by the server.

**GET /transactions/1**

```bash
curl -u 'team1admin:Team1#Secure2026' http://127.0.0.1:8000/transactions/1
```

```json
{"id": 1, "type": "received", "timestamp": "2024-05-10 16:30:51", "amount": 2000.0, "sender": "Jane Smith", "sender_id": "013", "balance": 2000.0, "transaction_id": "76662021700", "raw_sms_body": "You have received 2000 RWF from Jane Smith ..."}
```

**POST /transactions** (requires an `Idempotency-Key` header; sending the same key again returns the first result instead of a duplicate)

```bash
curl -u 'team1admin:Team1#Secure2026' -X POST http://127.0.0.1:8000/transactions \
  -H "Content-Type: application/json" -H "Idempotency-Key: team1-post-1" \
  -d '{"type":"payment","amount":7777,"receiver":"Team1 Test","timestamp":"2026-09-29 10:00:00"}'
```

```json
{"type": "payment", "amount": 7777, "receiver": "Team1 Test", "timestamp": "2026-09-29 10:00:00", "id": 1692}
```

**PUT /transactions/1692**

```bash
curl -u 'team1admin:Team1#Secure2026' -X PUT http://127.0.0.1:8000/transactions/1692 \
  -H "Content-Type: application/json" -d '{"amount":8888,"fee":100}'
```

```json
{"type": "payment", "amount": 8888, "receiver": "Team1 Test", "timestamp": "2026-09-29 10:00:00", "id": 1692, "fee": 100}
```

**DELETE /transactions/1692**

```bash
curl -u 'team1admin:Team1#Secure2026' -X DELETE http://127.0.0.1:8000/transactions/1692
```

```json
{"message": "Transaction 1692 deleted"}
```

### Error codes

| Code | When |
|---|---|
| 400 | Invalid JSON, unknown field, missing `type`/`amount`, negative amount, missing `Idempotency-Key` |
| 401 | Missing or wrong credentials (also after 5 failed attempts in 60 s from the same IP) |
| 403 | Your role can't use this method (e.g. a viewer sending DELETE) |
| 404 | Transaction or endpoint not found |
| 405 | Unsupported method (HEAD, PATCH) |
| 409 | Username or email already registered |
| 411 / 413 | Missing `Content-Length` / body larger than 1 MB |

Errors look like `{"error": "Transaction 1692 not found"}`.

## Data Structures & Algorithms

`dsa/search_compare.py` finds 20 random transactions by `id` two ways, 1000 times each:

- **Linear search**: loop through the list until the id matches.
- **Dictionary lookup**: build `{id: transaction}` once, then `index[id]`.

Run it:

```bash
python3 dsa/search_compare.py
```

Our result (1691 records):

| Method | Time per search |
|---|---|
| Linear search | ~15.4 µs |
| Dictionary lookup | ~0.04 µs (~357x faster) |

**Why the dictionary is faster:** linear search checks records one by one, so its time grows with the list size (O(n)). A dictionary hashes the id to jump straight to its slot, so it takes about the same time no matter how many records there are (O(1) on average). The API uses a dictionary for this reason.

**Other options:** keep the records sorted by id and use binary search (O(log n), no extra memory for a hash table), or use a balanced binary search tree / database B-tree index, which also supports fast range queries such as "all transactions between two dates".

## Testing & Validation (screenshots)

Start the server and register `team1admin` as in [Setup](#setup), then run each command in a second terminal and take one screenshot per step. `-i` shows the status code.

1. **Successful GET with auth** → `200 OK`

   ```bash
   curl -i -u 'team1admin:Team1#Secure2026' http://127.0.0.1:8000/transactions/1
   ```

2. **Wrong credentials** → `401 Unauthorized`

   ```bash
   curl -i -u 'team1admin:WrongPass#1' http://127.0.0.1:8000/transactions
   ```

3. **Successful POST** → `201 Created`, note the returned `id` (1692 on a fresh start)

   ```bash
   curl -i -u 'team1admin:Team1#Secure2026' -X POST http://127.0.0.1:8000/transactions \
     -H "Content-Type: application/json" -H "Idempotency-Key: team1-post-1" \
     -d '{"type":"payment","amount":7777,"receiver":"Team1 Test","timestamp":"2026-09-29 10:00:00"}'
   ```

4. **Successful PUT** → `200 OK` with the new amount

   ```bash
   curl -i -u 'team1admin:Team1#Secure2026' -X PUT http://127.0.0.1:8000/transactions/1692 \
     -H "Content-Type: application/json" -d '{"amount":8888,"fee":100}'
   ```

5. **Successful DELETE** → `200 OK`, then the same GET returns `404`

   ```bash
   curl -i -u 'team1admin:Team1#Secure2026' -X DELETE http://127.0.0.1:8000/transactions/1692
   curl -i -u 'team1admin:Team1#Secure2026' http://127.0.0.1:8000/transactions/1692
   ```

6. **DSA comparison**: screenshot the output of `python3 dsa/search_compare.py`.

Save them in `screenshots/`. Tip: 5 wrong logins within 60 s block your IP for a minute, so run step 2 only once.

## Status

This project is in active development as part of ALU coursework.