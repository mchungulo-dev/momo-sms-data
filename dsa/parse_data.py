"""
Task 1: Data Parsing
Parses modified_sms_v2.xml (SMS Backup & Restore export of MoMo messages)
into a list of clean JSON transaction objects.

Each <sms> element only carries raw attributes (address, date, body, ...).
The actual transaction details (type, amount, sender/receiver, fee,
balance, transaction id) are embedded as free text inside `body`, so this
parser extracts them with regex rules built from the real message formats
found in the dataset (deposits, transfers, payments, withdrawals, airtime
purchases, and receipts).
"""

import xml.etree.ElementTree as ET
import json
import re
import os


def clean_amount(raw):
    """'1,000' -> 1000.0"""
    if raw is None:
        return None
    return float(raw.replace(",", ""))


# Each rule: (transaction_type, compiled regex, field-mapping function)
# Order matters — more specific patterns are checked first.
RULES = [
    (
        "deposit",
        re.compile(
            r"A bank deposit of (?P<amount>[\d,]+) RWF has been added .* "
            r"at (?P<timestamp>[\d-]+ [\d:]+)\. Your NEW BALANCE :(?P<balance>[\d,]+) RWF"
        ),
    ),
    (
        "received",
        re.compile(
            r"You have received (?P<amount>[\d,]+) RWF from (?P<sender>[^(]+)\(\*+(?P<sender_id>\d+)\) "
            r"on your mobile money account at (?P<timestamp>[\d-]+ [\d:]+)\..*"
            r"Your new balance:(?P<balance>[\d,]+) RWF\. Financial Transaction Id: (?P<transaction_id>\d+)"
        ),
    ),
    (
        "payment",
        re.compile(
            r"TxId: (?P<transaction_id>\d+)\. Your payment of (?P<amount>[\d,]+) RWF to (?P<receiver>[^\d]+?) "
            r"\d+ has been completed at (?P<timestamp>[\d-]+ [\d:]+)\. "
            r"Your new balance: (?P<balance>[\d,]+) RWF\. Fee was (?P<fee>[\d,]+) RWF"
        ),
    ),
    (
        "transfer",
        re.compile(
            r"(?P<amount>[\d,]+) RWF transferred to (?P<receiver>[^(]+)\((?P<receiver_id>\d+)\) "
            r"from (?P<sender_id>\d+) at (?P<timestamp>[\d-]+ [\d:]+) \. "
            r"Fee was: (?P<fee>[\d,]+) RWF\. New balance: (?P<balance>[\d,]+) RWF"
        ),
    ),
    (
        "airtime_or_bundle_payment",
        re.compile(
            r"TxId:(?P<transaction_id>\d+)\*S\*Your payment of (?P<amount>[\d,]+) RWF to (?P<receiver>[^\n]+?) "
            r"(?:with token[^\.]*)?has been completed at (?P<timestamp>[\d-]+ [\d:]+)\. "
            r"Fee was (?P<fee>[\d,]+) RWF\. Your new balance: (?P<balance>[\d,]+) RWF"
        ),
    ),
    (
        "merchant_payment",
        re.compile(
            r"A transaction of (?P<amount>[\d,]+) RWF by (?P<receiver>[^\n]+?) on your MOMO account was "
            r"successfully completed at (?P<timestamp>[\d-]+ [\d:]+)\..*"
            r"Your new balance:(?P<balance>[\d,]+) RWF\. Fee was (?P<fee>[\d,]+) RWF\. "
            r"Financial Transaction Id: (?P<transaction_id>\d+)"
        ),
    ),
    (
        "withdrawal",
        re.compile(
            r"You (?P<sender>[^(]+)\(\*+(?P<sender_id>\d+)\) have via agent: Agent (?P<agent>[^(]+)"
            r"\((?P<agent_id>\d+)\), withdrawn (?P<amount>[\d,]+) RWF from your mobile money account: "
            r"(?P<account>\d+) at (?P<timestamp>[\d-]+ [\d:]+) .*"
            r"Your new balance: (?P<balance>[\d,]+) RWF\. Fee paid: (?P<fee>[\d,]+) RWF"
        ),
    ),
    (
        "bundle_purchase",
        re.compile(
            r"Umaze kugura .*igura (?P<amount>[\d,]+) RWF"
        ),
    ),
    (
        "otp",
        re.compile(
            r"your MTN MoMo application one-time password is :(?P<otp>\d+)"
        ),
    ),
    (
        "reversal",
        re.compile(
            r"Your transaction to (?P<receiver>[^(]+)\((?P<receiver_id>\d+)\) with (?P<amount>[\d,]+) RWF "
            r"has been reversed at (?P<timestamp>[\d-]+ [\d:]+)"
        ),
    ),
    (
        "failed_transaction",
        re.compile(
            r"the transaction with amount (?P<amount>[\d,]+) RWF for (?P<receiver>[^\n]+?) with message: "
            r"\S+ failed at (?P<timestamp>[\d-]+ [\d:]+)"
        ),
    ),
]


def classify(body):
    """Try each rule in order; return (type, extracted_fields) or ('other', {})."""
    for txn_type, pattern in RULES:
        match = pattern.search(body)
        if match:
            fields = match.groupdict()
            for money_field in ("amount", "fee", "balance"):
                if money_field in fields:
                    fields[money_field] = clean_amount(fields[money_field])
            for name_field in ("sender", "receiver", "agent"):
                if name_field in fields and fields[name_field]:
                    fields[name_field] = fields[name_field].strip()
            return txn_type, fields
    return "other", {}


def parse_sms_xml(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    transactions = []
    for i, sms in enumerate(root.findall("sms"), start=1):
        body = sms.get("body", "")
        txn_type, fields = classify(body)

        record = {
            "id": i,
            "type": txn_type,
            "timestamp": sms.get("readable_date"),
            "raw_sms_body": body,
        }
        record.update(fields)
        transactions.append(record)

    return transactions


def save_as_json(transactions, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(transactions, f, indent=2)


if __name__ == "__main__":
    input_path = "modified_sms_v2.xml"
    output_path = os.path.join("data", "transactions.json")

    transactions = parse_sms_xml(input_path)
    save_as_json(transactions, output_path)

    # Coverage report so you can see how well the parsing worked
    from collections import Counter
    counts = Counter(t["type"] for t in transactions)
    print(f"Parsed {len(transactions)} records total.\n")
    print("Breakdown by type:")
    for txn_type, count in counts.most_common():
        print(f"  {txn_type:30s} {count}")

    other = [t for t in transactions if t["type"] == "other"]
    if other:
        print(f"\n{len(other)} unmatched records, examples:")
        for t in other[:5]:
            print(" -", t["raw_sms_body"][:120])
