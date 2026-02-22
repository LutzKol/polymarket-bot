"""
Break-Even Probability Analysis

Berechnet die Break-Even Wahrscheinlichkeit für verschiedene Ask-Preise.

Formel:
    breakeven_p = ask_price * (1 + slippage) / (1 - fee)

Standard-Parameter:
    - Fee: 2% (0.02)
    - Slippage: 0.5% (0.005)
"""


def calculate_breakeven(ask: float, fee: float = 0.02, slippage: float = 0.005) -> float:
    """
    Berechnet die Break-Even Wahrscheinlichkeit.

    Args:
        ask: Ask-Preis (z.B. 0.52 für 52 Cent)
        fee: Transaktionsgebühr (default: 2%)
        slippage: Slippage (default: 0.5%)

    Returns:
        Break-Even Wahrscheinlichkeit als Dezimalzahl
    """
    return ask * (1 + slippage) / (1 - fee)


def main():
    # Standard-Parameter
    FEE = 0.02
    SLIPPAGE = 0.005

    # Ask-Preise zur Analyse
    ask_prices = [0.50, 0.52, 0.55, 0.58]

    print("=" * 50)
    print("Break-Even Probability Analysis")
    print("=" * 50)
    print(f"\nParameter:")
    print(f"  Fee:      {FEE * 100:.1f}%")
    print(f"  Slippage: {SLIPPAGE * 100:.1f}%")
    print(f"\nFormel: breakeven_p = ask * (1 + slippage) / (1 - fee)")
    print("\n" + "-" * 50)
    print(f"{'Ask-Preis':<15} {'Break-Even %':<15} {'Status'}")
    print("-" * 50)

    for ask in ask_prices:
        breakeven = calculate_breakeven(ask, FEE, SLIPPAGE)
        breakeven_pct = breakeven * 100

        # Status basierend auf Break-Even
        if breakeven_pct > 58:
            status = "AVOID"
        elif breakeven_pct > 55:
            status = "CAUTION"
        else:
            status = "OK"

        print(f"{ask:<15.2f} {breakeven_pct:<15.1f} {status}")

    print("-" * 50)

    # Verifikation
    print("\n" + "=" * 50)
    print("Verifikation")
    print("=" * 50)
    test_ask = 0.52
    expected = 0.5333
    actual = calculate_breakeven(test_ask, FEE, SLIPPAGE)

    print(f"\nTest: Ask = {test_ask}")
    print(f"  Berechnung: {test_ask} * {1 + SLIPPAGE} / {1 - FEE}")
    print(f"            = {test_ask * (1 + SLIPPAGE):.4f} / {1 - FEE}")
    print(f"            = {actual:.4f}")
    print(f"  Erwartet:   ~{expected:.4f} ({expected * 100:.1f}%)")
    print(f"  Ergebnis:   {actual:.4f} ({actual * 100:.1f}%)")

    if abs(actual - expected) < 0.001:
        print("  Status:     PASSED")
    else:
        print("  Status:     FAILED")


if __name__ == "__main__":
    main()
