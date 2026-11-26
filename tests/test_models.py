"""Unit conversion and model helpers."""

from fireboard_exporter.models import celsius_to_fahrenheit, fahrenheit_to_celsius


def test_fahrenheit_to_celsius() -> None:
    assert round(fahrenheit_to_celsius(32.0), 5) == 0.0
    assert round(fahrenheit_to_celsius(212.0), 5) == 100.0


def test_celsius_to_fahrenheit() -> None:
    assert round(celsius_to_fahrenheit(0.0), 5) == 32.0
    assert round(celsius_to_fahrenheit(100.0), 5) == 212.0
