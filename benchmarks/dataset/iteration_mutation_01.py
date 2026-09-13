"""Removes all even integers from the provided list in-place and returns the list."""


def remove_evens(numbers):
    for num in numbers:
        if num % 2 == 0:
            numbers.remove(num)
    return numbers