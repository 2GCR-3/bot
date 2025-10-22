# utils.py
import os
import random
import string
import difflib
from datetime import datetime
from models import db, Product, Promotion
from flask import current_app

DB_SEED_KEY = "nestle_seeded"

def log(msg):
    ts = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    line = f"[{ts}] {msg}\n"
    log_file = os.environ.get("NESTLE_SMARTBOT_LOG", "nestle_smartbot.log")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line)

def rand_order_no(prefix="NSB"):
    s = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"{prefix}{s}"

def fuzzy_search_product(query, n=5, cutoff=0.5):
    if not query:
        return []
    products = Product.query.all()
    pool = []
    q = query.lower()
    for p in products:
        pool.append((p.name.lower(), p))
        pool.append((p.code.lower(), p))
    names = [t[0] for t in pool]
    matches = difflib.get_close_matches(q, names, n=n, cutoff=cutoff)
    seen = set()
    results = []
    for m in matches:
        for name, prod in pool:
            if name == m and prod.id not in seen:
                results.append(prod)
                seen.add(prod.id)
    # fallback: substring
    if not results:
        for name, prod in pool:
            if q in name and prod.id not in seen:
                results.append(prod)
                seen.add(prod.id)
    return results[:n]

def compute_subtotal_from_cart(cart):
    subtotal = 0
    details = []
    for pid, qty in cart.items():
        prod = Product.query.get(pid)
        if not prod:
            continue
        line = int(prod.price) * int(qty)
        subtotal += line
        details.append({"product": prod, "qty": int(qty), "line": line})
    return subtotal, details

def apply_promotion(subtotal, promo_code=None, is_catering=False, pax=0):
    discount = 0
    applied = None
    if promo_code:
        promo = Promotion.query.filter_by(code=promo_code.upper(), active=True).first()
        if promo and subtotal >= (promo.min_subtotal or 0):
            if promo.code == "CATER5" and (not is_catering or (pax and pax < 50)):
                applied = None
            else:
                discount = int(subtotal * (promo.discount_percent / 100.0))
                applied = promo
    return discount, applied

def compute_tax(subtotal):
    return int(round(subtotal * 0.11))

def compute_delivery_fee(subtotal, has_location=False):
    if subtotal >= 50000:
        return 0
    return 10000 if has_location else 15000

def nutrition_advice(age=None, goal=None):
    advice = []
    recs = []
    try:
        age_i = int(age) if age else None
    except:
        age_i = None
    g = (goal or "").lower()

    if age_i and age_i < 2:
        advice.append("Untuk bayi di bawah 2 tahun, utamakan ASI dan konsultasi dokter.")
        recs += Product.query.filter(Product.category == "baby").limit(3).all()
    elif age_i and age_i < 12:
        advice.append("Anak memerlukan nutrisi seimbang: karbohidrat, protein, lemak sehat.")
        recs += Product.query.filter(Product.category.in_(["milk","baby"])).limit(3).all()
    else:
        if g == "weight_loss":
            advice.append("Kurangi gula/lemak, pilih porsi kecil, tambah protein & serat.")
            recs += Product.query.filter(Product.calories <= 200).limit(3).all()
        elif g == "weight_gain":
            advice.append("Tambah asupan kalori berkualitas & protein.")
            recs += Product.query.filter(Product.calories >= 300).limit(3).all()
        elif g in ("maintenance", ""):
            advice.append("Seimbangkan porsi, olahraga teratur.")
            recs += Product.query.limit(3).all()
        elif g == "lactating":
            advice.append("Ibu menyusui butuh ekstra kalori dan cairan.")
            recs += Product.query.filter(Product.category.in_(["milk"])).limit(3).all()
        else:
            advice.append("Konsultasikan kebutuhan spesifik dengan ahli gizi.")
    recs_unique = []
    ids = set()
    for r in recs:
        if r.id not in ids:
            recs_unique.append(r)
            ids.add(r.id)
    return "\n".join(advice), recs_unique[:5]

def seed_products_and_promos(app):
    """Create tables and seed demo data. Safe to call multiple times."""
    with app.app_context():
        db.create_all()
        # Prevent reseeding if already seeded
        if Promotion.query.count() > 0 or Product.query.count() > 0:
            log("Seed: existing data found, skipping reseed.")
            return
        seed_products = [
            ("NESTLE-MILO-200", "Milo Active-Go 200g", "beverage", 33000, 400, 8.0, 10.0, 70.0, "Minuman coklat malt bergizi"),
            ("NESTLE-NESCAFE-100", "Nescafé Classic 100g", "beverage", 42000, 2, 0.5, 1.0, 5.0, "Kopi instan"),
            ("NESTLE-DANCOW-400", "Dancow Fortigro 3+ 400g", "milk", 75000, 200, 12.0, 8.0, 24.0, "Susu pertumbuhan"),
            ("NESTLE-CERELAC-250", "Cerelac Nutri 250g", "baby", 65000, 450, 10.0, 9.0, 64.0, "MP-ASI pendamping"),
            ("NESTLE-BEARBRAND-370", "Bear Brand 370ml", "milk", 12000, 120, 7.0, 3.0, 12.0, "Susu steril"),
            ("NESTLE-SNACK-CRISP", "Nestlé Crisps", "snack", 15000, 220, 3.0, 12.0, 26.0, "Cemilan gurih"),
            ("NESTLE-CATER-HEMAT", "Paket Catering Hemat", "catering", 25000, None, None, None, None, "Paket catering ekonomis/per-pax"),
            ("NESTLE-CATER-PREMIUM", "Paket Catering Premium", "catering", 40000, None, None, None, None, "Paket catering premium/per-pax"),
        ]
        for code, name, cat, price, cal, p, f, c, desc in seed_products:
            prod = Product(code=code, name=name, category=cat, price=price,
                           calories=cal, protein=p, fat=f, carbs=c, description=desc,
                           is_catering_option=(cat == "catering"))
            db.session.add(prod)
        promos = [
            ("WELCOME10", "Diskon 10% untuk pembelian pertama", 10.0, 0),
            ("CATER5", "Diskon 5% untuk catering >= 50 pax", 5.0, 0),
            ("FREESHIP50", "Gratis ongkir untuk subtotal >= 50k", 0.0, 50000),
        ]
        for code, desc, pct, min_sub in promos:
            db.session.add(Promotion(code=code, description=desc, discount_percent=pct, min_subtotal=min_sub, active=True))
        db.session.commit()
        log("Database seeded with products and promotions.")
