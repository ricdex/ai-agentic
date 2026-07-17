import pytest
from calculator import add, subtract, multiply, divide, percentage, average


def test_add():
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    assert add(0.1, 0.2) == pytest.approx(0.3)


def test_subtract():
    assert subtract(5, 3) == 2
    assert subtract(0, 5) == -5


def test_multiply():
    assert multiply(4, 3) == 12
    assert multiply(-2, 3) == -6
    assert multiply(0, 100) == 0


def test_divide():
    assert divide(10, 2) == 5
    assert divide(7, 2) == pytest.approx(3.5)
    with pytest.raises(ValueError, match="Cannot divide by zero"):
        divide(5, 0)


def test_percentage():
    assert percentage(50, 200) == pytest.approx(25.0)
    assert percentage(1, 4) == pytest.approx(25.0)


def test_average():
    assert average([1, 2, 3, 4, 5]) == 3.0
    assert average([10]) == 10.0
    with pytest.raises(ValueError, match="Cannot average empty list"):
        average([])
