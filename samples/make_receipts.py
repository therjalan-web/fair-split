"""
Generates receipt images for testing: spec receipts R1/R3/R4 plus
stress-test receipts (S1-S5) covering the edge-case doc.
Run: python samples/make_receipts.py
"""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

OUT = Path(__file__).parent
W = 580
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"


def render(name, header, lines, footer):
    rows = header + [""] + lines + [""] + footer
    f = ImageFont.truetype(FONT, 18)
    fb = ImageFont.truetype(FONT_B, 18)
    h = 30 + 26 * len(rows) + 20
    img = Image.new("RGB", (W, h), "#fdfcf7")
    d = ImageDraw.Draw(img)
    y = 20
    for row in rows:
        bold = row.startswith("**")
        text = row[2:] if bold else row
        d.text((24, y), text, fill="#1a1a1a", font=fb if bold else f)
        y += 26
    img.save(OUT / name)
    print("wrote", name)


def item(n, q, a):
    return f"{n:<28}{q:>3}{a:>10}"


# R1 — Brew & Bite Cafe
render("receipt_R1.png",
    ["**BREW & BITE CAFE", "Koramangala, Bengaluru", "12 Mar 2026   Bill #0142", "-" * 44],
    [item("Cappuccino", 1, "180.00"),
     item("Grilled Chicken Sandwich", 1, "260.00"),
     item("Penne Arrabiata", 1, "320.00"),
     item("Fresh Lime Soda", 1, "120.00"),
     item("Brownie", 1, "160.00")],
    ["-" * 44,
     f"{'Subtotal':<34}{'1040.00':>10}",
     f"{'Service Charge 5%':<34}{'52.00':>10}",
     f"{'GST 5%':<34}{'54.60':>10}",
     f"{'Round-off':<34}{'+0.40':>10}",
     "**" + f"{'GRAND TOTAL':<34}{'Rs 1147':>10}"])

# R3 — The Daily Grind
render("receipt_R3.png",
    ["**THE DAILY GRIND", "Powai, Mumbai", "15 Mar 2026   Bill #1188", "-" * 44],
    [item("Margherita Pizza", 1, "380.00"),
     item("Arrabiata Pasta", 1, "340.00"),
     item("Garlic Bread", 1, "160.00"),
     item("Craft Beer", 2, "500.00"),
     item("Virgin Mojito", 1, "180.00")],
    ["-" * 44,
     f"{'Subtotal':<34}{'1560.00':>10}",
     f"{'Service Charge 5%':<34}{'78.00':>10}",
     f"{'GST 5%':<34}{'81.90':>10}",
     f"{'Round-off':<34}{'+0.10':>10}",
     "**" + f"{'GRAND TOTAL':<34}{'Rs 1720':>10}"])

# R4 — Spice Route (discount)
render("receipt_R4.png",
    ["**SPICE ROUTE", "Jubilee Hills, Hyderabad", "16 Mar 2026   Bill #5521", "-" * 44],
    [item("Chicken Biryani", 2, "560.00"),
     item("Veg Biryani", 1, "240.00"),
     item("Mutton Rogan Josh", 1, "420.00"),
     item("Raita", 2, "120.00"),
     item("Soft Drinks", 3, "180.00")],
    ["-" * 44,
     f"{'Subtotal':<34}{'1520.00':>10}",
     f"{'Discount WELCOME15 -15%':<34}{'-228.00':>10}",
     f"{'Service Charge 5%':<34}{'76.00':>10}",
     f"{'GST 5%':<34}{'68.40':>10}",
     f"{'Round-off':<34}{'-0.40':>10}",
     "**" + f"{'GRAND TOTAL':<34}{'Rs 1436':>10}"])

# S1 — no service charge, CGST/SGST split
render("receipt_S1_no_service_cgst_sgst.png",
    ["**CHAAT CORNER", "Indiranagar, Bengaluru", "20 Mar 2026   Bill #077", "-" * 44],
    [item("Pani Puri", 2, "120.00"),
     item("Bhel Puri", 1, "90.00"),
     item("Masala Chai", 3, "90.00")],
    ["-" * 44,
     f"{'Subtotal':<34}{'300.00':>10}",
     f"{'CGST 2.5%':<34}{'7.50':>10}",
     f"{'SGST 2.5%':<34}{'7.50':>10}",
     "**" + f"{'GRAND TOTAL':<34}{'Rs 315':>10}"])

# S2 — printed total does NOT add up (Rs 20 unexplained)
render("receipt_S2_total_mismatch.png",
    ["**HIGHWAY DHABA", "NH-44, Kurnool", "22 Mar 2026   Bill #310", "-" * 44],
    [item("Butter Chicken", 1, "340.00"),
     item("Tandoori Roti", 4, "120.00"),
     item("Lassi", 2, "140.00")],
    ["-" * 44,
     f"{'Subtotal':<34}{'600.00':>10}",
     f"{'GST 5%':<34}{'30.00':>10}",
     "**" + f"{'GRAND TOTAL':<34}{'Rs 650':>10}"])  # should be 630 — Rs20 gap

# S3 — tip line + delivery charge
render("receipt_S3_tip_delivery.png",
    ["**WOK THIS WAY (Delivery)", "Order #A-2291", "25 Mar 2026", "-" * 44],
    [item("Hakka Noodles", 1, "260.00"),
     item("Chilli Paneer", 1, "300.00"),
     item("Spring Rolls", 1, "180.00"),
     item("Tip", 1, "50.00")],
    ["-" * 44,
     f"{'Subtotal':<34}{'740.00':>10}",
     f"{'Delivery Fee':<34}{'40.00':>10}",
     f"{'GST 5%':<34}{'37.00':>10}",
     "**" + f"{'GRAND TOTAL':<34}{'Rs 867':>10}"])

# S4 — complimentary item
render("receipt_S4_complimentary.png",
    ["**CASA ITALIA", "Bandra West, Mumbai", "28 Mar 2026   Bill #904", "-" * 44],
    [item("Lasagna", 1, "450.00"),
     item("Risotto", 1, "420.00"),
     item("Bruschetta (Complimentary)", 1, "0.00"),
     item("Tiramisu", 1, "280.00")],
    ["-" * 44,
     f"{'Subtotal':<34}{'1150.00':>10}",
     f"{'Service Charge 10%':<34}{'115.00':>10}",
     f"{'GST 5%':<34}{'63.25':>10}",
     f"{'Round-off':<34}{'-0.25':>10}",
     "**" + f"{'GRAND TOTAL':<34}{'Rs 1328':>10}"])

# S5 — odd quantity that doesn't divide evenly among 3
render("receipt_S5_odd_split.png",
    ["**MOMO STATION", "Sector 18, Noida", "30 Mar 2026   Bill #451", "-" * 44],
    [item("Steam Momos (10pc)", 1, "175.00"),
     item("Thukpa", 1, "205.00"),
     item("Iced Tea", 3, "225.00")],
    ["-" * 44,
     f"{'Subtotal':<34}{'605.00':>10}",
     f"{'Service Charge 5%':<34}{'30.25':>10}",
     f"{'GST 5%':<34}{'31.76':>10}",
     f"{'Round-off':<34}{'-0.01':>10}",
     "**" + f"{'GRAND TOTAL':<34}{'Rs 667':>10}"])

print("done")
