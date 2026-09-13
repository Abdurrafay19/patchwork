"""Returns a list of transaction records sorted by amount descending."""


def sort_transactions_by_amount(transactions):
    return transactions.sort(key=lambda t: t["amount"], reverse=True)
