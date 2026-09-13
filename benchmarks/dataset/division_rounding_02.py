"""Returns the number of complete batches of batch_size that fit into
total_items, ignoring any leftover items."""


def calculate_full_batches(total_items, batch_size):
    return total_items / batch_size
