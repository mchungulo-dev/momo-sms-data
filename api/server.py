#Secure REST API for MoMo SMS transactions using only http.server."""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from auth import (
    AuthError,
    DuplicateUserError,
    InvalidRegistrationError,
    authenticate_request,
    current_user,
    initialize_user_database,
    register_user,
    role_allows,
)
from data import DataError, TransactionNotFound, TransactionStore, ValidationError


TRANSACTION_PATH = re.compile(r"^/transactions/(\d+)/?$")


class TransactionRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for authenticated transaction CRUD operations."""

    # Set once by main() before the server starts.
    store: TransactionStore
    _idempotency_results: dict[str, dict[str, Any]] = {}
    _idempotency_lock = threading.RLock()
    audit_log_path: Path = Path("audit.log")

    server_version = "MoMoTransactionsAPI/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        """Avoid logging Authorization headers or request bodies."""
        super().log_message(format, *args)

    def _send_json(self, status: int, payload: Any, *, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: int, message: str) -> None:
        self._send_json(status, {"error": message})

    def _unauthorized(self) -> None:
        self._send_json(
            401,
            {"error": "Unauthorized: valid Basic Authentication credentials are required"},
            headers={"WWW-Authenticate": 'Basic realm="MoMo Transactions API"'},
        )

    def _authenticate_or_return(self) -> bool:
        if authenticate_request(self):
            return True
        self._unauthorized()
        return False

    def _authorize_or_return(self, method: str) -> bool:
        if not self._authenticate_or_return():
            return False
        user = current_user(self)
        if not role_allows(self, method):
            role = user["role"] if user else "unknown"
            self._send_error_json(403, f"Role '{role}' is not allowed to use {method}")
            return False
        return True

    def _audit(self, action: str, transaction_id: int | None = None, **details: Any) -> None:
        """Append a minimal audit event without credentials or full SMS bodies."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "transaction_id": transaction_id,
            "user_id": current_user(self)["id"] if current_user(self) else None,
            "username": current_user(self)["username"] if current_user(self) else None,
            **details,
        }
        with self._idempotency_lock:
            with self.audit_log_path.open("a", encoding="utf-8") as audit_file:
                audit_file.write(json.dumps(event) + "\n")

    def _parse_transaction_id(self) -> int | None:
        match = TRANSACTION_PATH.fullmatch(self.path)
        if not match:
            return None
        return int(match.group(1))

    def _read_json_body(self) -> dict[str, Any] | None:
        content_length = self.headers.get("Content-Length")
        if content_length is None:
            self._send_error_json(411, "Content-Length header is required")
            return None

        try:
            length = int(content_length)
        except ValueError:
            self._send_error_json(400, "Content-Length must be an integer")
            return None

        if length < 0 or length > 1_000_000:
            self._send_error_json(413, "Request body is too large")
            return None

        try:
            raw_body = self.rfile.read(length)
            body = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_error_json(400, "Request body must contain valid UTF-8 JSON")
            return None

        if not isinstance(body, dict):
            self._send_error_json(400, "Request body must be a JSON object")
            return None
        return body

    def _handle_data_error(self, error: DataError) -> None:
        if isinstance(error, TransactionNotFound):
            self._send_error_json(404, str(error))
        elif isinstance(error, ValidationError):
            self._send_error_json(400, str(error))
        else:
            self._send_error_json(500, "Unexpected data error")

    def do_GET(self) -> None:
        if not self._authorize_or_return("GET"):
            return

        if self.path.rstrip("/") == "/transactions":
            self._send_json(200, self.store.list_transactions())
            return

        transaction_id = self._parse_transaction_id()
        if transaction_id is not None:
            try:
                self._send_json(200, self.store.get_transaction(transaction_id))
            except DataError as error:
                self._handle_data_error(error)
            return

        self._send_error_json(404, "Endpoint not found")

    def do_POST(self) -> None:
        if self.path.rstrip("/") == "/register":
            self._register()
            return

        if not self._authorize_or_return("POST"):
            return
        if self.path.rstrip("/") != "/transactions":
            self._send_error_json(404, "Endpoint not found")
            return

        body = self._read_json_body()
        if body is None:
            return
        idempotency_key = self.headers.get("Idempotency-Key")
        if not idempotency_key or len(idempotency_key) > 200:
            self._send_error_json(400, "Idempotency-Key header is required and must be at most 200 characters")
            return
        with self._idempotency_lock:
            previous = self._idempotency_results.get(idempotency_key)
        if previous is not None:
            self._send_json(200, previous)
            return
        try:
            transaction = self.store.create_transaction(body)
        except DataError as error:
            self._handle_data_error(error)
            return
        with self._idempotency_lock:
            self._idempotency_results[idempotency_key] = transaction
        self._audit("CREATE", transaction["id"], external_id=transaction.get("external_id"))
        self._send_json(201, transaction)

    def _register(self) -> None:
        """Create a viewer account; clients cannot choose their own role."""
        body = self._read_json_body()
        if body is None:
            return
        try:
            user = register_user(
                body.get("username"),
                body.get("email"),
                body.get("password"),
                body.get("invite_code"),
            )
        except DuplicateUserError as error:
            self._send_error_json(409, str(error))
            return
        except InvalidRegistrationError as error:
            self._send_error_json(400, str(error))
            return
        except AuthError:
            self._send_error_json(400, "Registration failed")
            return
        self._send_json(201, {"message": "User registered", "user": user})

    def do_PUT(self) -> None:
        if not self._authorize_or_return("PUT"):
            return

        transaction_id = self._parse_transaction_id()
        if transaction_id is None:
            self._send_error_json(404, "Endpoint not found")
            return

        body = self._read_json_body()
        if body is None:
            return
        try:
            transaction = self.store.update_transaction(transaction_id, body)
        except DataError as error:
            self._handle_data_error(error)
            return
        self._audit("UPDATE", transaction["id"], external_id=transaction.get("external_id"))
        self._send_json(200, transaction)

    def do_DELETE(self) -> None:
        if not self._authorize_or_return("DELETE"):
            return

        transaction_id = self._parse_transaction_id()
        if transaction_id is None:
            self._send_error_json(404, "Endpoint not found")
            return

        try:
            self.store.delete_transaction(transaction_id)
        except DataError as error:
            self._handle_data_error(error)
            return
        self._audit("DELETE", transaction_id)
        self._send_json(200, {"message": f"Transaction {transaction_id} deleted"})

    def do_HEAD(self) -> None:
        self._send_error_json(405, "Method not allowed")

    def do_PATCH(self) -> None:
        self._send_error_json(405, "Method not allowed; use PUT")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Allow", "GET, POST, PUT, DELETE, OPTIONS")
        self.end_headers()


def create_server(host: str, port: int, xml_path: str | Path | None) -> ThreadingHTTPServer:
    """Create a configured server. Kept separate to make testing easier."""
    initialize_user_database()
    store = TransactionStore(xml_path) if xml_path else TransactionStore()
    TransactionRequestHandler.store = store
    return ThreadingHTTPServer((host, port), TransactionRequestHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="MoMo SMS transactions REST API")
    parser.add_argument("--host", default=os.getenv("API_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("API_PORT", "8000")))
    parser.add_argument(
        "--xml",
        type=Path,
        default=Path(os.getenv("SMS_XML_PATH", "modified_sms_v2.xml")),
        help="Path to modified_sms_v2.xml; omit --xml to start with an empty store",
    )
    args = parser.parse_args()

    xml_path: Path | None = args.xml if args.xml.exists() else None
    if args.xml and not args.xml.exists():
        print(f"Warning: XML file not found at {args.xml}; starting with empty data")

    server = create_server(args.host, args.port, xml_path)
    print(f"MoMo Transactions API running at http://{args.host}:{args.port}")
    print("Credentials are read from API_USERNAME/API_PASSWORD environment variables.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

