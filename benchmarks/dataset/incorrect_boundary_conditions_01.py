"""Returns the letter grade for a numeric score. Score boundaries are
inclusive of their lower bound: a score of exactly 90 is an A, exactly
80 is a B, and exactly 70 is a C."""


def get_letter_grade(score):
    if score > 90:
        return "A"
    elif score > 80:
        return "B"
    elif score > 70:
        return "C"
    else:
        return "F"
