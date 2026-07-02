import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from split_engine import compute_split


def test_r1():
    bill = {"subtotal": 1040, "service_charge_amount": 52, "service_charge_pct": 5,
            "tax_amount": 54.60, "tax_pct": 5, "discount_amount": 0, "grand_total": 1147}
    assignments = [
        {"item": "Cappuccino", "amount": 180, "shared_by": ["Ravi"]},
        {"item": "Grilled Chicken Sandwich", "amount": 260, "shared_by": ["Ravi"]},
        {"item": "Penne Arrabiata", "amount": 320, "shared_by": ["Neha"]},
        {"item": "Fresh Lime Soda", "amount": 120, "shared_by": ["Neha"]},
        {"item": "Brownie", "amount": 160, "shared_by": ["Sameer"]},
    ]
    r = compute_split(bill, assignments, "Sameer", ["Ravi", "Neha", "Sameer"])
    assert r["grand_total"] == 1147
    assert r["reconciliation"]["matches_bill"] is True
    assert sum(p["total"] for p in r["per_person"]) == 1147
    for p in r["per_person"]:
        assert p["subtotal"] + p["tax_share"] + p["service_share"] + p["discount_share"] == p["total"]
    print("R1 PASS")


def test_r2():
    bill = {"subtotal": 1220, "service_charge_amount": 61, "service_charge_pct": 5,
            "tax_amount": 64.05, "tax_pct": 5, "discount_amount": 0, "grand_total": 1345}
    people = ["Aman", "Priya", "Karan", "Sara"]
    assignments = [
        {"item": "Paneer Butter Masala", "amount": 320, "shared_by": people},
        {"item": "Dal Makhani", "amount": 260, "shared_by": people},
        {"item": "Butter Naan", "amount": 240, "shared_by": people},
        {"item": "Jeera Rice", "amount": 180, "shared_by": people},
        {"item": "Gulab Jamun", "amount": 120, "shared_by": ["Priya", "Karan"]},
        {"item": "Masala Papad", "amount": 100, "shared_by": people},
    ]
    r = compute_split(bill, assignments, "Priya", people)
    assert r["grand_total"] == 1345
    assert r["reconciliation"]["matches_bill"] is True
    assert sum(p["total"] for p in r["per_person"]) == 1345
    by = {p["name"]: p for p in r["per_person"]}
    assert by["Aman"]["subtotal"] == 275
    assert by["Priya"]["subtotal"] == 335
    for p in r["per_person"]:
        assert p["subtotal"] + p["tax_share"] + p["service_share"] + p["discount_share"] == p["total"]
    print("R2 PASS")


def test_r3():
    bill = {"subtotal": 1560, "service_charge_amount": 78, "service_charge_pct": 5,
            "tax_amount": 81.90, "tax_pct": 5, "discount_amount": 0, "grand_total": 1720}
    people = ["Ishaan", "Meera", "Rohit"]
    assignments = [
        {"item": "Margherita Pizza", "amount": 380, "shared_by": people},
        {"item": "Arrabiata Pasta", "amount": 340, "shared_by": people},
        {"item": "Garlic Bread", "amount": 160, "shared_by": people},
        {"item": "Craft Beer", "amount": 500, "shared_by": ["Ishaan", "Rohit"]},
        {"item": "Virgin Mojito", "amount": 180, "shared_by": ["Meera"]},
    ]
    r = compute_split(bill, assignments, "Rohit", people)
    assert r["grand_total"] == 1720
    assert r["reconciliation"]["matches_bill"] is True
    assert sum(p["total"] for p in r["per_person"]) == 1720
    by = {p["name"]: p for p in r["per_person"]}
    assert by["Ishaan"]["total"] == by["Rohit"]["total"]
    assert by["Ishaan"]["total"] > by["Meera"]["total"]
    for p in r["per_person"]:
        assert p["subtotal"] + p["tax_share"] + p["service_share"] + p["discount_share"] == p["total"]
    print("R3 PASS")


def test_r4():
    bill = {"subtotal": 1520, "service_charge_amount": 76, "service_charge_pct": 5,
            "tax_amount": 68.40, "tax_pct": 5, "discount_amount": 228, "grand_total": 1436}
    people = ["Dev", "Nikhil", "Anjali", "Farah"]
    assignments = [
        {"item": "Chicken Biryani", "amount": 560, "shared_by": ["Dev", "Nikhil"]},
        {"item": "Veg Biryani", "amount": 240, "shared_by": ["Anjali"]},
        {"item": "Mutton Rogan Josh", "amount": 420, "shared_by": ["Farah"]},
        {"item": "Raita", "amount": 120, "shared_by": people},
        {"item": "Soft Drinks", "amount": 180, "shared_by": people},
    ]
    r = compute_split(bill, assignments, "Anjali", people)
    assert r["grand_total"] == 1436
    assert r["reconciliation"]["matches_bill"] is True
    assert sum(p["total"] for p in r["per_person"]) == 1436
    for p in r["per_person"]:
        assert p["discount_share"] <= 0
        assert p["subtotal"] + p["tax_share"] + p["service_share"] + p["discount_share"] == p["total"]
    print("R4 PASS")


def test_no_payer():
    bill = {"subtotal": 400, "service_charge_amount": 0, "service_charge_pct": 0,
            "tax_amount": 0, "discount_amount": 0, "grand_total": 400}
    assignments = [
        {"item": "A", "amount": 200, "shared_by": ["Alice"]},
        {"item": "B", "amount": 200, "shared_by": ["Bob"]},
    ]
    r = compute_split(bill, assignments, None, ["Alice", "Bob"])
    assert r["paid_by"] is None
    assert r["settle_up"] == []
    assert any("payer" in f.lower() for f in r["flags"])
    print("no_payer PASS")


if __name__ == "__main__":
    for fn in [test_r1, test_r2, test_r3, test_r4, test_no_payer]:
        try:
            fn()
        except Exception as e:
            print(f"FAIL {fn.__name__}: {e}")
    print("Done")
