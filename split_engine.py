"""
split_engine.py
Pure Python bill-splitting computation. Zero model involvement.

All arithmetic happens here:
  - per-person item subtotals (equal splits for shared items)
  - proportional tax / service / discount / delivery charge allocation
  - rupee rounding with paise absorption
  - settle-up graph
  - reconciliation check

Supported bill types:
  - Standard restaurant bills (subtotal + service + GST)
  - Bills with CGST/SGST breakdown (combined into tax_amount by parser)
  - Bills with delivery/packing charges (delivery_charge_amount)
  - Bills with tips or gratuity (tip treated as line item, flagged)
  - Bills with complimentary / free items (₹0 amount)
  - Bills with no service charge
  - Bills with discount coupons
  - Bills where printed total has a round-off line
"""

from __future__ import annotations
from typing import Optional
import math

# Item name tokens that indicate a tip/gratuity (outside spec fairness rules)
_TIP_TOKENS = {"tip", "gratuity", "staff tip", "optional gratuity"}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def compute_split(
    bill: dict,
    assignments: list[dict],
    paid_by: Optional[str],
    all_people: list[str],
    extra_assumptions: list[str] | None = None,
    extra_flags: list[str] | None = None,
) -> dict:
    """
    Parameters
    ----------
    bill : dict
        Keys: subtotal, service_charge_amount, service_charge_pct,
              tax_amount, tax_pct, discount_amount, discount_pct,
              delivery_charge_amount (optional), round_off, grand_total
    assignments : list[dict]
        Each: {"item": str, "amount": float, "shared_by": [str]}
        Every receipt line item must appear exactly once.
        - Complimentary/free items: amount = 0 (included, contributes ₹0)
        - Tip/gratuity: include with shared_by = [] to flag and exclude, or
          assign explicitly to split intentionally
    paid_by : str | None
    all_people : list[str]
    extra_assumptions / extra_flags : lists from the parsers

    Returns
    -------
    dict matching the exact API response contract
    """
    assumptions: list[str] = list(extra_assumptions or [])
    flags: list[str] = list(extra_flags or [])

    # ── Step 1: per-person item subtotals ────────────────────────────────
    person_subtotals: dict[str, float] = {p: 0.0 for p in all_people}
    person_item_labels: dict[str, list[str]] = {p: [] for p in all_people}

    assigned_total = 0.0
    for asgn in assignments:
        item_name: str = asgn["item"]
        amount: float = float(asgn["amount"])
        sharers: list[str] = asgn.get("shared_by", [])
        assigned_total += amount

        # Tip / gratuity detection — outside spec fairness rules
        if item_name.lower().strip() in _TIP_TOKENS or "tip" in item_name.lower():
            if not sharers:
                flags.append(
                    f"'{item_name}' (₹{amount:.0f}) is a tip/gratuity — outside the spec's "
                    f"fairness rules. Include explicitly in description to split it."
                )
                continue
            else:
                flags.append(
                    f"'{item_name}' (₹{amount:.0f}) is a tip/gratuity (outside spec fairness rules) "
                    f"— split equally among {sharers} as instructed."
                )

        # Complimentary / free items — included but contribute ₹0
        if amount == 0:
            assumptions.append(f"'{item_name}' is complimentary (₹0) — included in split with no cost")
            if sharers:
                for person in sharers:
                    if person not in person_subtotals:
                        person_subtotals[person] = 0.0
                        person_item_labels[person] = []
                        all_people.append(person)
                    person_item_labels[person].append(f"{item_name} (complimentary)")
            continue

        if not sharers:
            flags.append(f"Item '{item_name}' (₹{amount:.0f}) has no one assigned — excluded from split")
            continue

        n = len(sharers)
        per_share = amount / n

        # Label formatting for display
        frac_map = {2: "½", 3: "⅓", 4: "¼"}
        frac_str = frac_map.get(n, f"1/{n}")

        for person in sharers:
            if person not in person_subtotals:
                # Parser introduced a new name not in all_people
                person_subtotals[person] = 0.0
                person_item_labels[person] = []
                all_people.append(person)
                flags.append(f"Person '{person}' from description not in initial people list — added")
            person_subtotals[person] += per_share
            label = item_name if n == 1 else f"{item_name} ({frac_str})"
            person_item_labels[person].append(label)

    total_subtotal = sum(person_subtotals.values())

    # Flag if assignments don't match receipt subtotal
    receipt_subtotal = float(bill.get("subtotal", 0))
    if receipt_subtotal > 0 and abs(total_subtotal - receipt_subtotal) > 0.5:
        flags.append(
            f"Assigned items sum to ₹{total_subtotal:.2f} but receipt subtotal is "
            f"₹{receipt_subtotal:.2f} — difference of ₹{abs(total_subtotal - receipt_subtotal):.2f}"
        )

    if total_subtotal == 0:
        flags.append("Total assigned subtotal is zero — cannot allocate proportional charges")
        grand_total_int = round(float(bill.get("grand_total", 0)))
        return _empty_result(all_people, grand_total_int, paid_by, assumptions, flags)

    # ── Step 2: proportional allocation of charges ───────────────────────
    service_total = float(bill.get("service_charge_amount", 0))
    tax_total = float(bill.get("tax_amount", 0))
    discount_total = float(bill.get("discount_amount", 0))  # positive value; applied as negative
    delivery_total = float(bill.get("delivery_charge_amount", 0))

    if delivery_total > 0:
        assumptions.append(
            f"Delivery/packing charge ₹{delivery_total:.0f} allocated proportionally to subtotal "
            f"(outside spec fairness rules — reasonable default)."
        )

    # Raw (exact float) per-person shares
    raw: dict[str, dict[str, float]] = {}
    for p in all_people:
        ratio = person_subtotals[p] / total_subtotal
        raw[p] = {
            "subtotal": person_subtotals[p],
            "service": (service_total + delivery_total) * ratio,
            "tax": tax_total * ratio,
            "discount": -discount_total * ratio,   # negative
            "total": (
                person_subtotals[p]
                + (service_total + delivery_total) * ratio
                + tax_total * ratio
                - discount_total * ratio
            ),
        }

    # ── Step 3: rupee rounding with paise absorption ─────────────────────
    grand_total_exact = float(bill.get("grand_total", 0))
    target = round(grand_total_exact)  # grand total is already a whole rupee

    # Floor every person's total; track fractional remainder
    floored: dict[str, int] = {p: math.floor(raw[p]["total"]) for p in all_people}
    fracs: dict[str, float] = {p: raw[p]["total"] - floored[p] for p in all_people}

    sum_floored = sum(floored.values())
    residual = target - sum_floored  # typically +0, +1, -1, occasionally ±2

    if residual > 0:
        # Give +1 rupee to people with the largest fractional remainders
        absorbers = sorted(all_people, key=lambda p: fracs[p], reverse=True)
        for i in range(residual):
            person = absorbers[i % len(absorbers)]
            floored[person] += 1
            assumptions.append(
                f"{person} absorbs +₹1 rounding adjustment "
                f"(fractional remainder: ₹{fracs[person]:.4f})"
            )
    elif residual < 0:
        # Remove 1 rupee from people with the smallest fractional remainders
        absorbers = sorted(all_people, key=lambda p: fracs[p])
        for i in range(abs(residual)):
            person = absorbers[i % len(absorbers)]
            floored[person] -= 1
            assumptions.append(
                f"{person} absorbs -₹1 rounding adjustment "
                f"(fractional remainder: ₹{fracs[person]:.4f})"
            )

    # ── Step 4: build per-person result rows ─────────────────────────────
    per_person_rows = []
    for p in all_people:
        total_r = floored[p]

        # Round individual components; adjust tax to make them sum exactly to total_r
        subtotal_r = round(raw[p]["subtotal"])
        service_r = round(raw[p]["service"])
        discount_r = round(raw[p]["discount"])  # negative or zero
        # tax_r absorbs any integer arithmetic residual
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

    # ── Step 5: reconciliation ────────────────────────────────────────────
    sum_of_totals = sum(r["total"] for r in per_person_rows)
    matches_bill = (sum_of_totals == target)

    if not matches_bill:
        flags.append(
            f"Sum of person totals ₹{sum_of_totals} ≠ bill grand total ₹{target} "
            f"(delta: ₹{sum_of_totals - target})"
        )

    # Cross-check: extracted line items vs printed grand total
    extracted_item_sum = assigned_total + service_total + delivery_total + tax_total - discount_total
    if abs(round(extracted_item_sum) - target) > 1:
        flags.append(
            f"Extracted line items + charges sum to ₹{extracted_item_sum:.2f} "
            f"but printed grand total is ₹{target} — "
            f"₹{abs(extracted_item_sum - target):.2f} unexplained"
        )

    # ── Step 6: settle-up graph ───────────────────────────────────────────
    settle_up = []
    if paid_by is None:
        flags.append("No payer identified in description — settle-up cannot be computed")
    elif paid_by not in floored:
        flags.append(f"Named payer '{paid_by}' not found in people list — settle-up skipped")
    else:
        for p in all_people:
            if p != paid_by:
                amount_owed = floored[p]
                if amount_owed > 0:
                    settle_up.append({"from": p, "to": paid_by, "amount": amount_owed})
                elif amount_owed < 0:
                    # Rare: heavily discounted bill
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
