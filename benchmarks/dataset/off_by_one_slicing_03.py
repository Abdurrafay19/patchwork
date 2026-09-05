"""Returns the index of target in sorted_list using binary search, or
-1 if target is not present. sorted_list is sorted ascending."""


def binary_search(sorted_list, target):
    low, high = 0, len(sorted_list) - 1
    while low < high:
        mid = (low + high) // 2
        if sorted_list[mid] == target:
            return mid
        elif sorted_list[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1
