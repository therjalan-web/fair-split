"""
Tests for split_engine.py against all 4 sample receipts.
Run with: python -m pytest tests/ -v
or:        python tests/test_split_engine.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from split_engine import compute_split


# ────────────────────────────────────────────────────────────────────────────
# R1 — Brew & Bite Café · Grand Total ₹1147
# ────────────────────────────────────────────────────────────────────────────

def test_r1_basic():
    bill = {
        "subtotal": 1040,
        "service_charge_amount": 52,
        "service_charge_pct": 5,
        "tax_amount": 54.60,
        "tax_pct": 5,
        "discount_amount": 0,
        "discount_pct": 0,
        "round_off": 0.40,
        "grand_total": 1147,
    }
    assignments = [
        {"item": "Cappuccino",              "amount": 180, "shared_by": ["Ravi"]},
        {"item": "Grilled Chicken Sandwich","amount": 260, "shared_by": ["Ravi"]},
        {"item": "Penne Arrabiata",         "amount": 320, "shared_by": ["Neha"]},
        {"item": "Fresh Lime Soda",         "amount": 120, "shared_by": ["Neha"]},
        {"item": "Brownie",                 "amount": 160, "shared_by": ["Sameer"]},
    ]
    result = compute_split(bill, assignments, "Sameer", ["Ravi", "Neha", "Sameer"])

    assert result["grand_total"] == 1147
    assert result["reconciliation"]["matches_bill"] is True
    assert result["reconciliation"]["sum_of_person_totals"] == 1147
    assert result["paid_by"] == "Sameer"

    by_name = {r["name"]: r for r in result["per_person"]}

    # Ravi: 440 subtotal, proportional shares
    assert by_name["Ravi"]["subtotal"] == 440
    ravi_total = by_name["Ravi"]["total"]

    # Sameer: 160 subtotal
    assert by_name["Sameer"]["subtotal"] == 160

    # Each total must be positive and sum to 1147
    total_sum = sum(r["total"] for r in result["per_person"])
    assert total_sum == 1147, f"Sum = {total_sum}"

    # Settle-up: Ravi and Neha owe Sameer
    settles = {s["from"]: s for s in result["settle_up"]}
    assert "Ravi" in settles
    assert "Neha" in settles
    assert settles["Ravi"]["to"] == "Sameer"
    assert settles["Ravi"]["amount"] == ravi_total

    # Subtotals + charges must equal total for each person
    for r in result["per_person"]:
        recon = r["subtotal"] + r["tax_share"] + r["service_share"] + r["discount_share"]
        assert recon == r["total"], f"{r['name']}: {recon} != {r['total']}"


# ────────────────────────────────────────────────────────────────────────────
# R2 — Tamarind Kitchen · Grand Total ₹1345
# ────────────────────────────────────────────────────────────────────────────

def test_r2_partial_share():
    """Gulab Jamun shared only by Priya & Karan; rest common to all four."""
    bill = {
        "subtotal": 1220,
        "service_charge_amount": 61,
        "service_charge_pct": 5,
        "tax_amount": 64.05,
        "tax_pct": 5,
        "discount_amount": 0,
        "discount_pct": 0,
        "round_off": -0.05,
        "grand_total": 1345,
    }
    people = ["Aman", "Priya", "Karan", "Sara"]
    all4 = people
    priya_karan = ["Priya", "Karan"]

    assignments = [
        {"item": "Paneer Butter Masala", "amount": 320, "shared_by": all4},
        {"item": "Dal Makhani",          "amount": 260, "shared_by": all4},
        {"item": "Butter Naan",          "amount": 240, "shared_by": all4},
        {"item": "Jeera Rice",           "amount": 180, "shared_by": all4},
        {"item": "Gulab Jamun",          "amount": 120, "shared_by": priya_karan},
        {"item": "Masala Papad",         "amount": 100, "shared_by": all4},
    ]
    result = compute_split(bill, assignments, "Priya", people)

    assert result["grand_total"] == 1345
    assert result["reconciliation"]["matches_bill"] is True

    by_name = {r["name"]: r for r in result["per_person"]}

    # Aman and Sara had same items → same subtotal (275 each)
    assert by_name["Aman"]["subtotal"] == 275
    assert by_name["Sara"]["subtotal"] == 275

    # Priya and Karan had Gulab Jamun (60 each extra)
    assert by_name["Priya"]["subtotal"] == 335
    assert by_name["Karan"]["subtotal"] == 335

    total_sum = sum(r["total"] for r in result["per_person"])
    assert total_sum == 1345, f"Sum = {total_sum}"

    # Priya paid → Aman, Karan, Sara all owe Priya
    payers = {s["from"] for s in result["settle_up"]}
    assert "Aman" in payers
    assert "Karan" in payers
    assert "Sara" in payers
    assert "Priya" not in payers

    for r in result["per_person"]:
        recon = r["subtotal"] + r["tax_share"] + r["service_share"] + r["discount_share"]
        assert recon == r["total"], f"{r['name']}: {recon} != {r['total']}"


# ────────────────────────────────────────────────────────────────────────────
# R3 — The Daily Grind · Grand Total ₹1720 (fractional item splits)
# ────────────────────────────────────────────────────────────────────────────

def test_r3_fractional_splits():
    """Pizza+pasta+bread split 3-way; beers Ishaan+Rohit only; mojito Meera only."""
    bill = {
        "subtotal": 1560,
        "service_charge_amount": 78,
        "service_charge_pct": 5,
        "tax_amount": 81.90,
        "tax_pct": 5,
        "discount_amount": 0,
        "discount_pct": 0,
        "round_off": 0.10,
        "grand_total": 1720,
    }
    people = ["Ishaan", "Meera", "Rohit"]

    assignments = [
        {"item": "Margherita Pizza",  "amount": 380, "shared_by": people},
        {"item": "Arrabiata Pasta",   "amount": 340, "shared_by": people},
        {"item": "Garlic Bread",      "amount": 160, "shared_by": people},
        {"item": "Craft Beer",        "amount": 500, "shared_by": ["Ishaan", "Rohit"]},
        {"item": "Virgin Mojito",     "amount": 180, "shared_by": ["Meera"]},
    ]
    result = compute_split(bill, assignments, "Rohit", people)

    assert result["grand_total"] == 1720
    assert result["reconciliation"]["matches_bill"] is True

    total_sum = sum(r["total"] for r in result["per_person"])
    assert total_sum == 1720, f"Sum = {total_sum}"

    by_name = {r["name"]: r for r in result["per_person"]}

    # Ishaan and Rohit had beer (250 each on top of pizza/pasta/bread share)
    # Meera had mojito (180) instead of beer
    # Their raw subtotals: Ishaan=Rohit=543.33, Meera=473.33
    # So Ishaan total should be higher than Meera's
    assert by_name["Ishaan"]["total"] > by_name["Meera"]["total"]
    assert by_name["Rohit"]["total"] > by_name["Meera"]["total"]

    # Ishaan and Rohit should have equal totals (symmetric)
    assert by_name["Ishaan"]["total"] == by_name["Rohit"]["total"]

    for r in result["per_person"]:
        recon = r["subtotal"] + r["tax_share"] + r["service_share"] + r["discount_share"]
        assert recon == r["total"], f"{r['name']}: {recon} != {r['total']}"


# ────────────────────────────────────────────────────────────────────────────
# R4 — Spice Route · Grand Total ₹1436 (discount present)
# ────────────────────────────────────────────────────────────────────────────

def test_r4_with_discount():
    """15% WELCOME15 discount. Dev and Nikhil each had a chicken biryani (qty=2, total=560)."""
    bill = {
        "subtotal": 1520,
        "service_charge_amount": 76,
        "service_charge_pct": 5,
        "tax_amount": 68.40,
        "tax_pct": 5,
        "discount_amount": 228,
        "discount_pct": 15,
        "round_off": -0.40,
        "grand_total": 1436,
    }
    people = ["Dev", "Nikhil", "Anjali", "Farah"]

    assignments = [
        {"item": "Chicken Biryani",   "amount": 560, "shared_by": ["Dev", "Nikhil"]},
        {"item": "Veg Biryani",       "amount": 240, "shared_by": ["Anjali"]},
        {"item": "Mutton Rogan Josh", "amount": 420, "shared_by": ["Farah"]},
        {"item": "Raita",             "amount": 120, "shared_by": people},
        {"item": "Soft Drinks",       "amount": 180, "shared_by": people},
    ]
    result = compute_split(bill, assignments, "Anjali", people)

    assert result["grand_total"] == 1436
    assert result["reconciliation"]["matches_bill"] is True

    total_sum = sum(r["total"] for r in result["per_person"])
    assert total_sum == 1436, f"Sum = {total_sum}"

    by_name = {r["name"]: r for r in result["per_person"]}

    # Discount shares must be negative
    for r in result["per_person"]:
        assert r["discount_share"] <= 0, f"{r['name']} discount_share should be ≤ 0"

    # Dev and Nikhil symmetric
    assert by_name["Dev"]["subtotal"] == by_name["Nikhil"]["subtotal"]
    assert by_name["Dev"]["total"] == by_name["Nikhil"]["total"]

    # Farah (rogan josh 420) > Anjali (veg biryani 240) before tax
    assert by_name["Farah"]["subtotal"] > by_name["Anjali"]["subtotal"]

    for r in result["per_person"]:
        recon = r["subtotal"] + r["tax_share"] + r["service_share"] + r["discount_share"]
        assert recon == r["total"], f"{r['name']}: {recon} != {r['total']}"


# ────────────────────────────────────────────────────────────────────────────
# Edge case: no payer named
# ────────────────────────────────────────────────────────────────────────────

def test_no_payer_flagged():
    bill = {
        "subtotal": 400, "service_charge_amount": 20, "service_charge_pct": 5,
        "tax_amount": 21, "tax_pct": 5, "discount_amount": 0,
        "discount_pct": 0, "round_off": 0, "grand_total": 441,
    }
    assignments = [
        {"item": "Item A", "amount": 200, "shared_by": ["Alice"]},
        {"item": "Item B", "amount": 200, "shared_by": ["Bob"]},
    ]
    result = compute_split(bill, assignments, None, ["Alice", "Bob"])

    assert result["paid_by"] is None
    assert result["settle_up"] == []
    assert any("payer" in f.lower() for f in result["flags"])


# ────────────────────────────────────────────────────────────────────────────
# Edge case: no service charge
# ────────────────────────────────────────────────────────────────────────────

def test_no_service_charge():
    bill = {
        "subtotal": 500, "service_charge_amount": 0, "service_charge_pct": 0,
        "tax_amount": 25, "tax_pct": 5, "discount_amount": 0,
        "discount_pct": 0, "round_off": 0, "grand_total": 525,
    }
    assignments = [
        {"item": "Item A", "amount": 300, "shared_by": ["Alice", "Bob"]},
        {"item": "Item B", "amount": 200, "shared_by": ["Alice", "Bob"]},
    ]
    result = compute_split(bill, assignments, "Alice", ["Alice", "Bob"])

    assert result["grand_total"] == 525
    assert result["reconciliation"]["matches_bill"] is True
    for r in result["per_person"]:
        assert r["service_share"] == 0


# ────────────────────────────────────────────────────────────────────────────
# Edge case: item with no one assigned
# ────────────────────────────────────────────────────────────────────────────

def test_unassigned_item_flagged():
    bill = {
        "subtotal": 400, "service_charge_amount": 0, "service_charge_pct": 0,
        "tax_amount": 0, "tax_pct": 0, "discount_amount": 0,
        "discount_pct": 0, "round_off": 0, "grand_total": 400,
    }
    assignments = [
        {"item": "Item A", "amount": 200, "shared_by": ["Alice"]},
        {"item": "Item B", "amount": 200, "shared_by": []},  # no one
    ]
    result = compute_split(bill, assignments, "Alice", ["Alice"])

    assert any("no one assigned" in f.lower() for f in result["flags"])
    # Assigned total mismatch should also be flagged
    assert any("200" in f for f in result["flags"])


# ────────────────────────────────────────────────────────────────────────────
# Edge case: tip line item — flagged, excluded from proportional split
# ────────────────────────────────────────────────────────────────────────────

def test_tip_flagged():
    """Tip on bill → flagged as outside fairness rules, not silently split."""
    bill = {
        "subtotal": 600, "service_charge_amount": 30, "service_charge_pct": 5,
        "tax_amount": 31.50, "tax_pct": 5, "discount_amount": 0,
        "discount_pct": 0, "round_off": 0, "grand_total": 662,
    }
    assignments = [
        {"item": "Pizza",      "amount": 350, "shared_by": ["Alice", "Bob"]},
        {"item": "Pasta",      "amount": 250, "shared_by": ["Alice", "Bob"]},
        {"item": "Tip",        "amount":  81, "shared_by": []},  # unassigned tip
    ]
    # grand_total here does NOT include the unassigned tip (₹81) to keep reconciliation clean
    result = compute_split(bill, assignments, "Alice", ["Alice", "Bob"])

    # Tip should be flagged
    assert any("tip" in f.lower() or "gratuity" in f.lower() for f in result["flags"]), \
        f"Expected tip flag, got: {result['flags']}"
    # Reconciliation should still pass (tip excluded from split)
    assert result["reconciliation"]["matches_bill"] is True


# ────────────────────────────────────────────────────────────────────────────
# Edge case: delivery charge — allocated proportionally, noted in assumptions
# ────────────────────────────────────────────────────────────────────────────

def test_delivery_charge():
    """Delivery charge present → allocated proportionally, stated in assumptions."""
    bill = {
        "subtotal": 500, "service_charge_amount": 0, "service_charge_pct": 0,
        "tax_amount": 25, "tax_pct": 5, "discount_amount": 0,
        "discount_pct": 0, "delivery_charge_amount": 50,
        "round_off": 0, "grand_total": 575,
    }
    # Alice ate 300 worth, Bob ate 200 worth
    assignments = [
        {"item": "Burger",  "amount": 300, "shared_by": ["Alice"]},
        {"item": "Salad",   "amount": 200, "shared_by": ["Bob"]},
    ]
    result = compute_split(bill, assignments, "Alice", ["Alice", "Bob"])

    assert result["grand_total"] == 575
    assert result["reconciliation"]["matches_bill"] is True
    # Delivery charge acknowledged in assumptions
    assert any("delivery" in a.lower() for a in result["assumptions"]), \
        f"Expected delivery note in assumptions, got: {result['assumptions']}"
    # Alice ate more → pays more
    by_name = {r["name"]: r for r in result["per_person"]}
    assert by_name["Alice"]["total"] > by_name["Bob"]["total"]

    for r in result["per_person"]:
        recon = r["subtotal"] + r["tax_share"] + r["service_share"] + r["discount_share"]
        assert recon == r["total"], f"{r['name']}: {recon} != {r['total']}"


# ────────────────────────────────────────────────────────────────────────────
# Edge case: CGST+SGST bill (combined tax) — same arithmetic as single GST
# ────────────────────────────────────────────────────────────────────────────

def test_cgst_sgst_combined():
    """CGST 2.5% + SGST 2.5% combined = 5% GST. Math identical to single-tax bills."""
    bill = {
        "subtotal": 800,
        "service_charge_amount": 40, "service_charge_pct": 5,
        "tax_amount": 42,            # CGST 21 + SGST 21
        "tax_pct": 5,
        "discount_amount": 0, "discount_pct": 0,
        "round_off": 0, "grand_total": 882,
    }
    assignments = [
        {"item": "Paneer Tikka",  "amount": 400, "shared_by": ["Raj", "Priya"]},
        {"item": "Chicken Kebab", "amount": 400, "shared_by": ["Raj", "Priya"]},
    ]
    result = compute_split(bill, assignments, "Raj", ["Raj", "Priya"])

    assert result["grand_total"] == 882
    assert result["reconciliation"]["matches_bill"] is True
    # Symmetric — both had equal amounts
    by_name = {r["name"]: r for r in result["per_person"]}
    assert by_name["Raj"]["total"] == by_name["Priya"]["total"]
    assert by_name["Raj"]["total"] + by_name["Priya"]["total"] == 882


# ────────────────────────────────────────────────────────────────────────────
# Edge case: large group (6 people), uneven split
# ────────────────────────────────────────────────────────────────────────────

def test_large_group_6_people():
    """₹1000 shared among 6 → 166.67 each. Rounding absorption distributes ₹4 residual."""
    bill = {
        "subtotal": 1000, "service_charge_amount": 0, "service_charge_pct": 0,
        "tax_amount": 0, "tax_pct": 0, "discount_amount": 0,
        "discount_pct": 0, "round_off": 0, "grand_total": 1000,
    }
    people = ["A", "B", "C", "D", "E", "F"]
    assignments = [
        {"item": "Shared Platter", "amount": 1000, "shared_by": people},
    ]
    result = compute_split(bill, assignments, "A", people)

    assert result["grand_total"] == 1000
    assert result["reconciliation"]["matches_bill"] is True

    totals = [r["total"] for r in result["per_person"]]
    assert sum(totals) == 1000
    # Each person pays either 166 or 167
    for t in totals:
        assert t in (166, 167), f"Expected 166 or 167, got {t}"
    # Exactly 4 people pay 167 (because 1000 - 6*166 = 4)
    assert totals.count(167) == 4


# ────────────────────────────────────────────────────────────────────────────
# Edge case: complimentary item (₹0)
# ────────────────────────────────────────────────────────────────────────────

def test_complimentary_item():
    """Free dessert (₹0) — included in output but doesn't affect totals."""
    bill = {
        "subtotal": 400, "service_charge_amount": 0, "service_charge_pct": 0,
        "tax_amount": 20, "tax_pct": 5, "discount_amount": 0,
        "discount_pct": 0, "round_off": 0, "grand_total": 420,
    }
    assignments = [
        {"item": "Main Course",        "amount": 400, "shared_by": ["Alice", "Bob"]},
        {"item": "Complimentary Dessert", "amount": 0, "shared_by": ["Alice", "Bob"]},
    ]
    result = compute_split(bill, assignments, "Alice", ["Alice", "Bob"])

    assert result["grand_total"] == 420
    assert result["reconciliation"]["matches_bill"] is True
    # ₹0 item mentioned in assumptions
    assert any("complimentary" in a.lower() for a in result["assumptions"]), \
        f"Expected complimentary note: {result['assumptions']}"
    # No per-person cost affected
    by_name = {r["name"]: r for r in result["per_person"]}
    assert by_name["Alice"]["total"] == by_name["Bob"]["total"]


# ────────────────────────────────────────────────────────────────────────────
# Edge case: one person ate everything (solo diner split logic)
# ────────────────────────────────────────────────────────────────────────────

def test_one_person_all_items():
    """Alice ordered everything; Bob was there but had nothing."""
    bill = {
        "subtotal": 500, "service_charge_amount": 25, "service_charge_pct": 5,
        "tax_amount": 26.25, "tax_pct": 5, "discount_amount": 0,
        "discount_pct": 0, "round_off": 0, "grand_total": 551,
    }
    assignments = [
        {"item": "Item A", "amount": 200, "shared_by": ["Alice"]},
        {"item": "Item B", "amount": 300, "shared_by": ["Alice"]},
    ]
    result = compute_split(bill, assignments, "Bob", ["Alice", "Bob"])

    assert result["grand_total"] == 551
    assert result["reconciliation"]["matches_bill"] is True

    by_name = {r["name"]: r for r in result["per_person"]}
    # Alice owes the full bill; Bob ate nothing
    assert by_name["Bob"]["subtotal"] == 0
    assert by_name["Bob"]["total"] == 0
    assert by_name["Alice"]["total"] == 551

    # Alice (ate everything) owes Bob (who paid) — one settle-up entry
    assert len(result["settle_up"]) == 1
    assert result["settle_up"][0]["from"] == "Alice"
    assert result["settle_up"][0]["to"] == "Bob"
    assert result["settle_up"][0]["amount"] == 551


# ────────────────────────────────────────────────────────────────────────────
# Edge case: person in assignments not in original all_people list
# ────────────────────────────────────────────────────────────────────────────

def test_new_person_from_description():
    """'Charlie' appears in assignments but wasn't in all_people → added + flagged."""
    bill = {
        "subtotal": 300, "service_charge_amount": 0, "service_charge_pct": 0,
        "tax_amount": 15, "tax_pct": 5, "discount_amount": 0,
        "discount_pct": 0, "round_off": 0, "grand_total": 315,
    }
    assignments = [
        {"item": "Sandwich", "amount": 150, "shared_by": ["Alice"]},
        {"item": "Salad",    "amount": 150, "shared_by": ["Charlie"]},  # new name
    ]
    result = compute_split(bill, assignments, "Alice", ["Alice"])

    assert result["grand_total"] == 315
    assert result["reconciliation"]["matches_bill"] is True
    # Charlie should appear in output
    names = [r["name"] for r in result["per_person"]]
    assert "Charlie" in names
    # Flag about new person
    assert any("Charlie" in f and "not in" in f for f in result["flags"]), \
        f"Expected flag about Charlie: {result['flags']}"


# ────────────────────────────────────────────────────────────────────────────
# Edge case: extracted items don't match grand total (bill total mismatch)
# ────────────────────────────────────────────────────────────────────────────

def test_bill_total_mismatch_flagged():
    """Items sum to ₹900 but printed grand total is ₹1000 → ₹100 unexplained → flagged."""
    bill = {
        "subtotal": 800,
        "service_charge_amount": 40, "service_charge_pct": 5,
        "tax_amount": 60, "tax_pct": 5,
        "discount_amount": 0, "discount_pct": 0,
        "round_off": 0,
        "grand_total": 1000,   # 40 more than items+charges (900→1000 gap)
    }
    assignments = [
        {"item": "Food",   "amount": 500, "shared_by": ["Alice", "Bob"]},
        {"item": "Drinks", "amount": 300, "shared_by": ["Alice", "Bob"]},
    ]
    result = compute_split(bill, assignments, "Alice", ["Alice", "Bob"])

    # Grand total is the printed total (authoritative)
    assert result["grand_total"] == 1000
    # Reconciliation of persons-to-grand-total should pass
    assert result["reconciliation"]["matches_bill"] is True
    # But the cross-check flag for items-vs-total should fire
    flag_texts = " ".join(result["flags"]).lower()
    assert "unexplained" in flag_texts or "grand total" in flag_texts, \
        f"Expected mismatch flag: {result['flags']}"


if __name__ == "__main__":
    tests = [
        test_r1_basic,
        test_r2_partial_share,
        test_r3_fractional_splits,
        test_r4_with_discount,
        test_no_payer_flagged,
        test_no_service_charge,
        test_unassigned_item_flagged,
        test_tip_flagged,
        test_delivery_charge,
        test_cgst_sgst_combined,
        test_large_group_6_people,
        test_complimentary_item,
        test_one_person_all_items,
        test_new_person_from_description,
        test_bill_total_mismatch_flagged,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")

    print(f"\n{passed}/{len(tests)} passed")
    if passed < len(tests):
        raise SystemExit(1)
