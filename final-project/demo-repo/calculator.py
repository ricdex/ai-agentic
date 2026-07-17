def add(a: float, b: float) -> float:
    return a + b


def subtract(a: float, b: float) -> float:
    return a - b


def multiply(a: float, b: float) -> float:
    return a * b


def divide(a: float, b: float) -> float:
    # BUG: no zero division check
    return a / b


def percentage(value: float, total: float) -> float:
    # BUG: returns ratio instead of percentage
    return value / total


def average(numbers: list[float]) -> float:
    # BUG: crashes on empty list
    return sum(numbers) / len(numbers)
