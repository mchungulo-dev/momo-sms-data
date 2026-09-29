"""Task 5: compare linear search and dictionary lookup for finding a transaction by id."""

import json
import os
import random
import timeit


def linear_search(transactions, target_id):
    for transaction in transactions:
        if transaction["id"] == target_id:
            return transaction
    return None


def dict_lookup(index, target_id):
    return index.get(target_id)


if __name__ == "__main__":
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "transactions.json")
    with open(path, encoding="utf-8") as f:
        transactions = json.load(f)

    index = {t["id"]: t for t in transactions}
    ids = random.sample(list(index), 20)
    runs = 1000

    for i in ids:
        assert linear_search(transactions, i) is dict_lookup(index, i)

    linear_time = timeit.timeit(lambda: [linear_search(transactions, i) for i in ids], number=runs)
    dict_time = timeit.timeit(lambda: [dict_lookup(index, i) for i in ids], number=runs)
    searches = len(ids) * runs

    print(f"Records: {len(transactions)} | ids searched: {len(ids)} | repeated {runs} times")
    print(f"Linear search:     {linear_time:.4f} s total, {linear_time / searches * 1e6:.3f} µs per search")
    print(f"Dictionary lookup: {dict_time:.4f} s total, {dict_time / searches * 1e6:.3f} µs per search")
    print(f"Dictionary lookup was {linear_time / dict_time:.0f}x faster")
