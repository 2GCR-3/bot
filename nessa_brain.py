# nessa_brain.py
from markupsafe import Markup
from models import Product
from utils import fuzzy_search_product, nutrition_advice, log

def format_money(x):
    try:
        return f"Rp{int(x):,}"
    except:
        return str(x)

def nessa_reply(raw_msg: str, session_obj) -> str:
    """
    raw_msg: raw user message string
    session_obj: flask session object (mutable)
    returns string (HTML allowed)
    """
    msg = (raw_msg or "").strip()
    if not msg:
        return "Nessa: Ketik sesuatu ya 😊"

    low = msg.lower().strip()

    # greet variations
    if any(k in low for k in ("halo", "hai", "hi", "selamat")):
        return ("Nessa 🤖: Halo! Aku Nessa — asisten virtual Nestlé. "
                "Ketik 'bantuan' untuk melihat perintah yang tersedia.")

    # help
    if any(k in low for k in ("bantuan", "help", "perintah")):
        help_text = (
            "Nessa 🤖 — Perintah yang tersedia:\n"
            "- menu / produk : lihat katalog singkat\n"
            "- produk <nama> : info produk (contoh: 'produk milo')\n"
            "- resep <produk> : ide resep sederhana (contoh: 'resep milo')\n"
            "- rekomendasi gizi usia <usia> <tujuan> : contoh 'rekomendasi gizi usia 30 weight_loss'\n"
            "- pesan <produk> <qty> : tambah ke keranjang (contoh: 'pesan milo 2')\n"
            "- keranjang : lihat isi keranjang\n"
            "- checkout : selesaikan pembelian (akan meminta nama/telepon)\n"
            "- lapor daur ulang <jumlah> <produk> : dapatkan eco-poin\n"
            "- poin saya : lihat poin daur ulang\n"
            "- tukar poin : lihat reward yang bisa ditukar\n"
        )
        return Markup(help_text)

    # menu / katalog
    if low in ("menu", "produk", "katalog"):
        prods = Product.query.limit(8).all()
        lines = ["Nessa 🤖: Berikut beberapa produk kami:"]
        for p in prods:
            lines.append(f"- {p.name} ({p.category}) — {format_money(p.price)}")
        lines.append("Ketik 'produk <nama>' untuk info detil.")
        return Markup("<br/>".join(lines))

    # product info
    if low.startswith("produk ") or low.startswith("product "):
        q = msg.split(" ", 1)[1]
        found = fuzzy_search_product(q, n=6, cutoff=0.3)
        if not found:
            return f"Nessa 🤖: Maaf, tidak menemukan produk mirip '{q}'."
        lines = [f"Nessa 🤖: Ditemukan {len(found)} produk:"]
        for p in found:
            cal = f"{p.calories} kkal" if p.calories else "—"
            lines.append(f"- {p.name} — {p.description or '-'} — {format_money(p.price)} — {cal}")
        return Markup("<br/>".join(lines))

    # specific short product keywords (Nescafe etc)
    if "nescafe" in low:
        return Markup(
            "Nessa 🤖: ☕ *Nescafé* — kopi instan dari biji pilihan.\n"
            "- *Classic*: rasa kuat & pekat.\n"
            "- *Gold*: aroma halus, cita rasa premium.\n"
            "- *Latte*: creamy, nikmat dengan susu.\n"
            "Ketik 'produk Nescafé' atau 'pesan Nescafé 1' untuk menambahkan ke keranjang."
        )

    if "milo" in low:
        return ("Nessa 🤖: Milo Active-Go cocok untuk aktivitas dan pertumbuhan anak; "
                "mengandung karbohidrat & protein untuk energi.")

    if "dancow" in low:
        return ("Nessa 🤖: Dancow Fortigro diformulasikan untuk membantu tumbuh kembang anak "
                "dengan vitamin & mineral esensial.")

    if "cerelac" in low:
        return ("Nessa 🤖: Cerelac membantu pemberian MPASI dengan kandungan zat besi & vitamin.")

    if "bear brand" in low or "bearbrand" in low:
        return ("Nessa 🤖: Bear Brand susu steril yang membantu menjaga daya tahan tubuh.")

    # resep <produk>
    if low.startswith("resep "):
        q = msg.split(" ", 1)[1].lower()
        # simple recipe generator using product keywords
        if "milo" in q:
            return Markup(
                "Nessa 🤖: Resep sederhana - Milo Oat Bowl:\n"
                "- 2 sdm Milo + 1/2 cup oat + 200ml susu hangat\n"
                "- Aduk, tambahkan potongan pisang dan madu jika suka.\n"
                "Cocok untuk sarapan cepat."
            )
        if "dancow" in q:
            return Markup(
                "Nessa 🤖: Resep - Smoothie Dancow:\n"
                "- 2 sdm Dancow + 1 pisang + 150ml susu + es\n"
                "- Blender sampai halus, sajikan."
            )
        return "Nessa 🤖: Maaf, belum ada resep spesifik untuk produk itu. Coba 'resep milo' atau 'resep dancow'."

    # rekomendasi gizi usia X goal
    if "rekomendasi gizi" in low or "nutrition" in low:
        parts = low.split()
        age = None
        goal = None
        for t in parts:
            if t.isdigit():
                age = int(t)
            if t in ("weight_loss","weight_gain","weightgain","maintenance","lactating","pregnant","child_growth"):
                goal = t
        advice, recs = nutrition_advice(age=age, goal=goal)
        lines = []
        if advice:
            lines.append("Nessa 🤖: " + advice)
        if recs:
            lines.append("Produk rekomendasi:")
            for r in recs:
                lines.append(f"- {r.name} — Rp{r.price:,}")
        if not lines:
            return "Nessa 🤖: Coba format: 'rekomendasi gizi usia 30 weight_loss'"
        return Markup("<br/>".join(lines))

    # order flow in chat: pesan <produk> <qty>
    if low.startswith("pesan ") or low.startswith("order "):
        parts = msg.split()
        try:
            qty = 1
            if parts[-1].isdigit():
                qty = int(parts[-1])
                name_part = " ".join(parts[1:-1])
            else:
                name_part = " ".join(parts[1:])
            prods = fuzzy_search_product(name_part, n=1, cutoff=0.3)
            if not prods:
                return f"Nessa 🤖: Produk '{name_part}' tidak ditemukan."
            p = prods[0]
            cart = session_obj.get("cart", {})
            cart[str(p.id)] = cart.get(str(p.id), 0) + qty
            session_obj["cart"] = cart
            session_obj.modified = True
            subtotal = sum([Product.query.get(int(k)).price * v for k, v in cart.items()])
            return f"Nessa 🤖: {qty} x {p.name} ditambahkan ke keranjang. Subtotal saat ini: Rp{subtotal:,}"
        except Exception as e:
            log(f"nessa order error: {e}")
            return "Nessa 🤖: Gagal memproses pesanan. Gunakan format: 'pesan Milo 2'."

    # cart viewing
    if "keranjang" in low or "cart" in low:
        cart = session_obj.get("cart", {})
        if not cart:
            return "Nessa 🤖: Keranjang Anda kosong 🛒"
        lines = ["Nessa 🤖: Isi keranjang:"]
        subtotal = 0
        for pid_s, qty in cart.items():
            p = Product.query.get(int(pid_s))
            if not p: continue
            line = p.price * qty
            subtotal += line
            lines.append(f"- {p.name} x{qty} = Rp{line:,}")
        lines.append(f"Total: Rp{subtotal:,}")
        return Markup("<br/>".join(lines))

    # eco point: lapor daur ulang <jumlah> <produk>
    if low.startswith("lapor daur ulang") or low.startswith("lapor daurulang") or ("daur" in low and "lapor" in low):
        # parse number and product
        tokens = low.split()
        number = None
        product_name = None
        for t in tokens:
            if t.isdigit():
                number = int(t)
                break
        # naive product find: last token(s)
        if number:
            # product substring after number
            idx = tokens.index(str(number))
            product_name = " ".join(tokens[idx+1:]) if idx+1 < len(tokens) else ""
        else:
            # try find last token as product
            product_name = tokens[-1]
        pts = (number or 1) * 10
        points = session_obj.get("eco_points", 0) + pts
        session_obj["eco_points"] = points
        session_obj.modified = True
        return f"Nessa 🤖: Terima kasih! Laporan diterima. Anda mendapatkan {pts} poin. Total poin sekarang: {points}."

    if "poin saya" in low or "poin" == low:
        pts = session_obj.get("eco_points", 0)
        return f"Nessa 🤖: Poin daur ulang Anda: {pts}."

    if "tukar poin" in low:
        pts = session_obj.get("eco_points", 0)
        rewards = []
        if pts >= 500:
            rewards.append("Voucher diskon 20%")
        if pts >= 200:
            rewards.append("Voucher gratis ongkir 50k")
        if not rewards:
            return f"Nessa 🤖: Anda punya {pts} poin. Kumpulkan lebih banyak untuk menukar reward (200, 500 poin)."
        return Markup("Nessa 🤖: Reward yang bisa ditukar:<br/>" + "<br/>".join(f"- {r}" for r in rewards))

    # fallback - try product fuzzy suggestion
    prods = fuzzy_search_product(msg, n=3, cutoff=0.25)
    suggestions = []
    if prods:
        suggestions.append("Mungkin kamu mencari produk: " + ", ".join([p.name for p in prods]))
    suggestions.append("Ketik 'bantuan' untuk contoh perintah.")
    return "Nessa 🤖: Maaf, saya belum paham. " + " ".join(suggestions)
