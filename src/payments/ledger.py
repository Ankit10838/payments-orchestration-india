class Ledger:
    """Append-only double-entry ledger. Entries are never updated or deleted."""

    def __init__(self):
        self.entries = []

    def post(self, txn_id, lines):
        """lines: list of (account, debit, credit). Total debits must equal total credits."""
        debit = sum(l[1] for l in lines)
        credit = sum(l[2] for l in lines)
        if debit != credit:
            raise ValueError(f"Unbalanced transaction {txn_id}: debit {debit} != credit {credit}")
        for account, d, c in lines:
            self.entries.append({"txn_id": txn_id, "account": account, "debit": d, "credit": c})

    def balance(self, account):
        return sum(e["debit"] - e["credit"] for e in self.entries if e["account"] == account)

    def trial_balance(self):
        return sum(e["debit"] for e in self.entries), sum(e["credit"] for e in self.entries)
