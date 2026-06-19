# Meridian Bank — Product Requirements Document

## Overview

Meridian Bank is a digital-first retail banking platform offering savings accounts,
domestic money transfers, and real-time fraud alerting. This PRD defines the five
core functional requirements that the CoGMEM-QA agent swarm will verify.

---

## Actors

| ID | Name | Role |
|----|------|------|
| actor-customer | Customer | account_holder |
| actor-compliance | Compliance Officer | compliance_officer |

---

## Requirements

### REQ-001 · Account Opening (req-account-opening)
- **Priority:** P0
- **Regulatory control:** AML-KYC
- **Functionality:** Account Opening Flow (func-account-opening)
- **Component:** AccountController (comp-account-opening)

**Acceptance Criteria**

| ID | Statement | Actor |
|----|-----------|-------|
| ac-ao-1 | Customer can register a new savings account by providing personal details (name, DOB, address, national ID). | account_holder |
| ac-ao-2 | System rejects duplicate account registrations where the same national ID is already on file and returns a clear error message. | account_holder |

---

### REQ-002 · KYC Verification (req-kyc)
- **Priority:** P0
- **Regulatory control:** KYC-AML-2023
- **Functionality:** KYC Verification (func-kyc)
- **Component:** KYCController (comp-kyc)

**Acceptance Criteria**

| ID | Statement | Actor |
|----|-----------|-------|
| ac-kyc-1 | System verifies customer identity against a government-issued ID within 60 seconds and updates account status to VERIFIED. | compliance_officer |
| ac-kyc-2 | Account is immediately frozen and a compliance alert is raised when identity cannot be verified after two attempts. | compliance_officer |

---

### REQ-003 · Money Transfer (req-money-transfer)
- **Priority:** P0
- **Regulatory control:** _(none)_
- **Functionality:** Money Transfer (func-money-transfer)
- **Component:** TransferController (comp-money-transfer)

**Acceptance Criteria**

| ID | Statement | Actor |
|----|-----------|-------|
| ac-mt-1 | Customer can initiate a domestic transfer to any valid sort-code/account-number pair, confirmed by 4-digit PIN. | account_holder |
| ac-mt-2 | Transfer is rejected with error code INSUFFICIENT_FUNDS when the sender's available balance is less than the transfer amount plus fee. | account_holder |

---

### REQ-004 · Transaction History (req-transaction-history)
- **Priority:** P1
- **Regulatory control:** _(none)_
- **Functionality:** Transaction History (func-transaction-history)
- **Component:** TransactionHistoryController (comp-transaction-history)

**Acceptance Criteria**

| ID | Statement | Actor |
|----|-----------|-------|
| ac-th-1 | Customer can view a paginated list (20 per page) of all transactions for the last 90 days, ordered newest first. | account_holder |
| ac-th-2 | Customer can export the current transaction view to a CSV file containing date, description, amount, and running balance. | account_holder |

---

### REQ-005 · Fraud Alerting (req-fraud-alerting)
- **Priority:** P1
- **Regulatory control:** PSD2-SCA
- **Functionality:** Fraud Detection & Alerting (func-fraud-alerting)
- **Component:** FraudDetectionEngine (comp-fraud-alerting)

**Acceptance Criteria**

| ID | Statement | Actor |
|----|-----------|-------|
| ac-fa-1 | System automatically flags any single transaction above £10,000 for manual compliance review within 5 seconds of posting. | compliance_officer |
| ac-fa-2 | Customer receives an SMS alert within 30 seconds for any transaction the fraud engine classifies as suspicious. | account_holder |

---

## Out of Scope

- Multi-currency accounts and FX conversion
- Joint accounts or business accounts
- Loan and credit products
- Mobile app (web-only for evaluation purposes)
