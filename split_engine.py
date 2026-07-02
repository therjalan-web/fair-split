"""
split_engine.py
Pure Python bill-splitting computation. Zero model involvement.
"""
from __future__ import annotations
from typing import Optional
import math


def compute_split(
    bill: dict,
    assignments: list,
    paid_by: Optional[str],
    all_people: list,
    extra_assumptions: list = None,
    extra_flags: list = None,
) -> dict:
    assumptions = list(extra_assumptions or [])
    flags = list(extra_flags or [])

    person_subtotals = {p: 0.0 for p in all_people}
    person_item_labels = {p: [] for p in all_people}

    assigned_total = 0.0
    for asgn in assignments:
        item_name = asgn["item"]
        amount = float(asgn["amount"])
        sharers = asgn.get("shared_by", [])
        assigned_total += amount

        if not sharers:
            flags.append(f"Item '{item_name}' has no one assigned -- excluded from split")
            continue

        n = len(sharers)
        per_share = amount / n
        frac_map = {2: "1/2", 3: "1/3", 4: "1/4"}
        frac_str = frac_map.get(n, f"1/{n}")

        for person in sharers:
            if person not in person_subtotals:
                person_subtotals[person] = 0.0
                person_item_labels[person] = []
                all_people.append(person)
                flags.append(f"Person '{person}' added from description")
            person_subtotals[person] += per_share
            label = item_name if n == 1 else f"{item_name} ({frac_str})"
            person_item_labels[person].append(label)

    total_subtotal = sum(person_subtotals.values())

    receipt_subtotal = float(bill.get("subtotal", 0))
    if receipt_subtotal > 0 and abs(total_subtotal - receipt_subtotal) > 0.5:
        flags.append(
            f"Assigned items sum to Rs.{total_subtotal:.2f} but receipt subtotal is Rs.{receipt_subtotal:.2f}"
        )

    if total_subtotal == 0:
        flags.append("Total assigned subtotal is zero -- cannot allocate proportional charges")
        grand_total_int = round(float(bill.get("grand_total", 0)))
        return _empty_result(all_people, grand_total_int, paid_by, assumptions, flags)

    service_total = float(bill.get("service_charge_amount", 0))
    tax_total = float(bill.get("tax_amount", 0))
    discount_total = float(bill.get("discount_amount", 0))

    raw = {}
    for p in all_people:
        ratio = person_subtotals[p] / total_subtotal
        raw[p] = {
            "subtotal": person_subtotals[p],
            "service": service_total * ratio,
            "tax": tax_total * ratio,
            "discount": -discount_total * ratio,
            "total": (
                person_subtotals[p]
                + service_total * ratio
                + tax_total * ratio
                - discount_total * ratio
            ),
        }

    grand_total_exact = float(bill.get("grand_total", 0))
    target = round(grand_total_exact)

    floored = {p: math.floor(raw[p]["total"]) for p in all_people}
    fracs = {p: raw[p]["total"] - floored[p] for p in all_people}

    sum_floored = sum(floored.values())
    residual = target - sum_floored

    if residual > 0:
        absorbers = sorted(all_people, key=lambda p: fracs[p], reverse=True)
        for i in range(residual):
            person = absorbers[i % len(absorbers)]
            floored[person] += 1
            assumptions.append(f"{person} absorbs +Rs.1 rounding adjustment")
    elif residual < 0:
        absorbers = sorted(all_people, key=lambda p: fracs[p])
        for i in range(abs(residual)):
            person = absorbers[i % len(absorbers)]
            floored[person] -= 1
            assumptions.append(f"{person} absorbs -Rs.1 rounding adjustment")

    per_person_rows = []
    for p in all_people:
        total_r = floored[p]
        subtotal_r = round(raw[p]["subtotal"])
        service_r = round(raw[p]["service"])
        discount_r = round(raw[p]["discount"])
        tax_r = total_r - subtotal_r - service_r - discount_r
        per_person_rows.append({
            "name": p,
            "items": person_item_labels[p],
            "subtotal": subtotal_r,
            "tax_share": tax_r,
            "service_share": service_r,
            "discount_share": discount_r,
            "total": total_r,
        })

    sum_of_totals = sum(r["total"] for r in per_person_rows)
    matches_bill = (sum_of_totals == target)

    if not matches_bill:
        flags.append(f"Sum of person totals Rs.{sum_of_totals} does not match bill grand total Rs.{target}")

    extracted_item_sum = assigned_total + service_total + tax_total - discount_total
    if abs(round(extracted_item_sum) - target) > 1:
        flags.append(
            f"Extracted line items + charges sum to Rs.{extracted_item_sum:.2f} "
            f"but printed grand total is Rs.{target} -- Rs.{abs(extracted_item_sum - target):.2f} unexplained"
        )

    settle_up = []
    if paid_by is None:
        flags.append("No payer identified in description -- settle-up cannot be computed")
    elif paid_by not in floored:
        flags.append(f"Named payer '{paid_by}' not found in people list -- settle-up skipped")
    else:
        for p in all_people:
            if p != paid_by:
                amount_owed = floored[p]
                if amount_owed > 0:
                    settle_up.append({"from": p, "to": paid_by, "amount": amount_owed})
                elif amount_owed < 0:
                    settle_up.append({"from": paid_by, "to": p, "amount": -amount_owed})

    return {
        "per_person": per_person_rows,
        "grand_total": target,
        "reconciliation": {
            "sum_of_person_totals": sum_of_totals,
            "matches_bill": matches_bill,
        },
        "paid_by": paid_by,
        "settle_up": settle_up,
        "assumptions": assumptions,
        "flags": flags,
    }


def _empty_result(people, grand_total, paid_by, assumptions, flags):
    return {
        "per_person": [{"name": p, "items": [], "subtotal": 0, "tax_share": 0,
                        "service_share": 0, "discount_share": 0, "total": 0} for p in people],
        "grand_total": grand_total,
        "reconciliation": {"sum_of_person_totals": 0, "matches_bill": False},
        "paid_by": paid_by,
        "settle_up": [],
        "assumptions": assumptions,
        "flags": flags,
    }
