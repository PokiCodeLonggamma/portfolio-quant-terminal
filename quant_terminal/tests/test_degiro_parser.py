from __future__ import annotations

import io
import textwrap

from src.data.degiro_parser import parse_degiro


SAMPLE_CSV = textwrap.dedent(
    """\
    Produit,ISIN/Symbole,Unités,Prix de clôture,Valeur en EUR,Devise
    Alphabet C,GOOG,4,"195,50","780,00",USD
    Cameco,CCJ,30,"28,00","750,00",USD
    WTI 3x,3OIL.L,50,"35,00","1390,00",USD
    Gold ETC,IGLN.L,5,"4 800,00","700,00",GBp
    """
)


def test_parse_degiro_minimal():
    buf = io.StringIO(SAMPLE_CSV)
    df = parse_degiro(buf)
    assert len(df) == 4
    assert {"symbol", "quantity", "value_eur", "currency"}.issubset(df.columns)
    assert df["value_eur"].sum() == 780 + 750 + 1390 + 700


def test_parse_degiro_drops_empty_rows():
    csv = "Produit,Unités,Valeur en EUR\nAlphabet C,4,800\nBad,0,0\n"
    df = parse_degiro(io.StringIO(csv))
    assert len(df) == 1
