"""In-memory transaction store used by the API."""

import json
import threading

FIELDS = {"type", "timestamp", "amount", "sender", "receiver", "fee", "balance", "transaction_id", "raw_sms_body"}


class DataError(Exception):
    pass


class TransactionNotFound(DataError):
    pass


class ValidationError(DataError):
    pass


def _validate(body, required):
    unknown = set(body) - FIELDS
    if unknown:
        raise ValidationError(f"Unknown fields: {', '.join(sorted(unknown))}")
    if required and ("type" not in body or "amount" not in body):
        raise ValidationError("'type' and 'amount' are required")
    if not body:
        raise ValidationError("Provide at least one field to update")
    amount = body.get("amount", 0)
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0:
        raise ValidationError("'amount' must be a non-negative number")
    return dict(body)


class TransactionStore:
    def __init__(self, json_path=None):
        self._lock = threading.Lock()
        # id -> transaction, so finding one by id is a dictionary lookup
        self._transactions = {}
        if json_path:
            with open(json_path, encoding="utf-8") as f:
                for transaction in json.load(f):
                    self._transactions[transaction["id"]] = transaction
        self._next_id = max(self._transactions, default=0) + 1

    def list_transactions(self):
        return list(self._transactions.values())

    def get_transaction(self, transaction_id):
        if transaction_id not in self._transactions:
            raise TransactionNotFound(f"Transaction {transaction_id} not found")
        return self._transactions[transaction_id]

   
