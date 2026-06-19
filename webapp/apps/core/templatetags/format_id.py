"""Filter format angka gaya Indonesia: ribuan '.', desimal ',', tanpa nol ekor."""
from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter(name="angka_id")
def angka_id(value):
    if value is None or value == "":
        return ""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return value

    neg = d < 0
    d = abs(d)

    if d == d.to_integral_value():
        int_part, frac = str(int(d)), ""
    else:
        s = format(d.normalize(), "f")           # hindari notasi eksponen
        int_part, _, frac = s.partition(".")

    # kelompokkan ribuan dengan titik
    grouped = ""
    while len(int_part) > 3:
        grouped = "." + int_part[-3:] + grouped
        int_part = int_part[:-3]
    grouped = int_part + grouped

    hasil = grouped + ("," + frac if frac else "")
    return ("-" + hasil) if neg else hasil
