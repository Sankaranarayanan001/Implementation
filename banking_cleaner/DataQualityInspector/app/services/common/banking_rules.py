"""Canonical banking fields, aliases and validation rules."""
from __future__ import annotations

import re

DESCRIPTIONS = {
    "account_number": "bank account number",
    "customer_id": "customer identifier / CIF",
    "customer_name": "customer full name",
    "transaction_id": "unique transaction reference",
    "transaction_date": "date of transaction",
    "transaction_amount": "amount of a transaction",
    "transaction_type": "credit/debit/transfer etc.",
    "currency": "ISO currency code",
    "balance": "account balance",
    "branch_code": "branch identifier",
    "ifsc_code": "Indian IFSC code",
    "email": "customer email",
    "phone": "customer phone number",
    "pan_number": "Indian PAN number",
    "age": "customer age in years",
    "date_of_birth": "customer date of birth",
    "gender": "customer gender",
    "kyc_status": "KYC verification status",
    "loan_amount": "sanctioned/outstanding loan amount",
    "interest_rate": "interest rate in percent",
    "credit_score": "credit score (300-900)",
    "tenure_months": "loan/deposit tenure in months",
    "account_status": "account status",
}
CANONICAL = list(DESCRIPTIONS)

ALIASES = {
    "account_number": ["account_no", "acct_no", "account_num", "acc_no", "a_c_no", "account_id", "acct_number", "acc_number"],
    "customer_id": ["cust_id", "customer_no", "cif", "cif_no", "client_id", "customerid"],
    "customer_name": ["cust_name", "name", "customer", "account_holder", "holder_name", "full_name"],
    "transaction_id": ["txn_id", "trans_id", "transaction_ref", "txn_ref", "reference_no", "txn_no", "utr"],
    "transaction_date": ["txn_date", "trans_date", "date", "transaction_dt", "posting_date", "value_date"],
    "transaction_amount": ["txn_amount", "amount", "amt", "trans_amount", "txn_amt", "transaction_amt"],
    "transaction_type": ["txn_type", "trans_type", "dr_cr", "debit_credit", "type"],
    "currency": ["ccy", "curr", "currency_code"],
    "balance": ["closing_balance", "available_balance", "acct_balance", "bal", "current_balance"],
    "branch_code": ["branch", "branch_id", "branch_no", "sol_id"],
    "ifsc_code": ["ifsc", "ifs_code", "bank_ifsc"],
    "email": ["email_id", "e_mail", "mail", "email_address"],
    "phone": ["mobile", "mobile_no", "phone_no", "contact_no", "telephone", "phone_number", "mobile_number"],
    "pan_number": ["pan", "pan_no", "pan_card"],
    "age": ["customer_age", "age_years"],
    "date_of_birth": ["dob", "birth_date", "date_birth", "birthdate"],
    "gender": ["sex"],
    "kyc_status": ["kyc", "kyc_flag", "kyc_verified"],
    "loan_amount": ["loan_amt", "principal", "sanctioned_amount", "loan_principal", "outstanding_amount"],
    "interest_rate": ["roi", "rate_of_interest", "int_rate", "interest", "interest_pct"],
    "credit_score": ["cibil", "cibil_score", "credit_rating", "fico"],
    "tenure_months": ["tenure", "loan_tenure", "term_months", "tenor", "duration_months"],
    "account_status": ["acct_status", "status", "account_state"],
    
}
# Fixed output formats. Change here and everything follows.
# key = banking field or normalised column name -> (prefix, number of digits)
ID_FORMATS = {
    "customer_id": ("CUST", 6),
    # "transaction_id": ("TXN", 8),   # add more like this if you want
}

def _id_rx(key):
    prefix, width = ID_FORMATS[key]
    return rf"{prefix}\d{{{width}}}"


# kind: text | numeric | date | category
RULES = {
    "account_number": dict(kind="text", required=True, regex=r"\d{9,18}"),
    "customer_name": dict(kind="text"),
    "transaction_id": dict(kind="text", required=True, unique=True),
    "transaction_date": dict(kind="date", required=True, no_future=True),
    "transaction_amount": dict(kind="numeric", required=True, min=0),
    "transaction_type": dict(kind="category", allowed=[
        "credit", "debit", "cr", "dr", "deposit", "withdrawal", "transfer", "payment", "refund", "fee",
        "neft", "rtgs", "imps", "upi", "atm", "pos", "cheque", "emi", "interest"]),
    "currency": dict(kind="category", regex=r"[A-Z]{3}"),
    "balance": dict(kind="numeric"),
    "branch_code": dict(kind="text"),
    "ifsc_code": dict(kind="text", regex=r"[A-Z]{4}0[A-Z0-9]{6}", upper=True),
    "pan_number": dict(kind="text", regex=r"[A-Z]{5}[0-9]{4}[A-Z]", upper=True),
    "age": dict(kind="numeric", min=18, max=100),
    "date_of_birth": dict(kind="date", no_future=True),
    "gender": dict(kind="category", allowed=["male", "female", "other", "m", "f", "o", "transgender"]),
    "kyc_status": dict(kind="category", allowed=[
        "verified", "pending", "rejected", "expired", "complete", "incomplete", "yes", "no", "y", "n"]),
    "loan_amount": dict(kind="numeric", min=0),
    "interest_rate": dict(kind="numeric", min=0, max=100),
    "credit_score": dict(kind="numeric", min=300, max=900),
    "tenure_months": dict(kind="numeric", min=1, max=600),
    "account_status": dict(kind="category", allowed=[
        "active", "inactive", "dormant", "closed", "frozen", "suspended", "open","pending"]),
    "customer_id": dict(kind="text", required=True, regex=r"CUST-\d{4}", sentinels=["CUST-0000"]),    "customer_id": dict(kind="text", required=True, regex=_id_rx("customer_id")),
    "email": dict(kind="text", regex=r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}"),
    "phone": dict(kind="text", regex=r"[6-9]\d{9}",
                  sentinels=["0000000000", "1234567890", "9999999999", "1111111111", "12345"]),    
}

UNKNOWN_FIELDS = {"customer_id", "customer_name", "gender", "email", "phone",
                  "kyc_status", "account_status", "branch_code"}

# (earlier_field, later_field, operator) -> earlier <op> later must hold
CROSS_RULES = [("date_of_birth", "transaction_date", "<=")]


def norm_name(c) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(c).lower()).strip("_")


def anchored(rx: str) -> str:
    return rf"^(?:{rx})$"

GENERIC_RANGES = [
    (r"(^|_)age($|_)", 18, 100),
    (r"credit_?score|cibil", 300, 900),
    (r"interest_?rate|rate_of_interest|(^|_)roi($|_)", 0, 40),
    (r"loan_?term|tenure|tenor", 1, 480),
    (r"debt_?to_?income|(^|_)dti($|_)", 0, 1),
    (r"late_?payments?|existing_?loan|loan_?count|number_of|(^|_)num_", 0, None),
    (r"amount|income|salary|debt|installment|(^|_)emi($|_)|principal", 0, None),
]


def generic_range(col):
    n = norm_name(col)
    for pat, mn, mx in GENERIC_RANGES:
        if re.search(pat, n):
            return {"min": mn, "max": mx}
    return None


_DATE_NAME = re.compile(r"(^|_)(date|dob)($|_)|birth|_dt$")


def id_format_for(col, canon=None):
    for key in (canon, norm_name(col)):
        if key in ID_FORMATS:
            return ID_FORMATS[key]
    return None


def is_date_name(col) -> bool:
    return bool(_DATE_NAME.search(norm_name(col)))