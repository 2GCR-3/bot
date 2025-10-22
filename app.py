# app.py
import io
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file, flash
from models import db, Product, Promotion, Order, OrderItem
import utils
from nessa_brain import nessa_reply

# Flask config
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = "dev-secret-key-change"  # change in prod or env
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///nestle_smartbot.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

# seed
with app.app_context():
    utils.seed_products_and_promos(app)

# Routes
@app.route("/")
def home():
    return render_template("base.html")

@app.route("/clear_session", methods=["POST"])
def clear_session():
    session.clear()
    return redirect(url_for("home"))

@app.route("/api/search", methods=["POST"])
def api_search():
    data = request.json or {}
    q = data.get("q", "").strip()
    if not q:
        return jsonify({"results": []})
    try:
        prods = utils.fuzzy_search_product(q, n=8, cutoff=0.4)
        results = []
        for p in prods:
            results.append({
                "id": p.id,
                "code": p.code,
                "name": p.name,
                "category": p.category,
                "price": p.price,
                "description": p.description
            })
        return jsonify({"results": results})
    except Exception as e:
        utils.log(f"api_search error: {e}")
        return jsonify({"results": []})

@app.route("/api/cart/add", methods=["POST"])
def api_cart_add():
    try:
        data = request.json or {}
        pid = int(data.get("product_id"))
        qty = int(data.get("qty", 1))
        cart = session.get("cart", {})
        cart[str(pid)] = cart.get(str(pid), 0) + qty
        session["cart"] = cart
        session.modified = True
        utils.log(f"Cart add pid={pid} qty={qty}")
        return jsonify({"ok": True})
    except Exception as e:
        utils.log(f"api_cart_add error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 400

@app.route("/api/cart/view")
def api_cart_view():
    try:
        cart = session.get("cart", {})
        items = []
        subtotal = 0
        for pid_s, qty in cart.items():
            pid = int(pid_s)
            p = Product.query.get(pid)
            if not p: continue
            line = p.price * qty
            subtotal += line
            items.append({"id": pid, "name": p.name, "qty": qty, "unit_price": p.price, "line_total": line})
        return jsonify({"items": items, "subtotal": subtotal})
    except Exception as e:
        utils.log(f"api_cart_view error: {e}")
        return jsonify({"items": [], "subtotal": 0})

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.json or {}
    msg = (data.get("message") or "").strip()
    try:
        resp = nessa_reply(msg, session)
        # return response (HTML-safe for chat)
        return jsonify({"response": resp})
    except Exception as e:
        utils.log(f"api_chat exception: {e}")
        return jsonify({"response": "Terjadi kesalahan pada server saat memproses pesan. Coba lagi."})

@app.route("/api/checkout", methods=["POST"])
def api_checkout():
    try:
        data = request.json or {}
        name = data.get("name", "").strip()
        phone = data.get("phone", "").strip()
        address = data.get("address", "").strip()
        promo = (data.get("promo") or "").strip().upper()
        is_catering = bool(data.get("is_catering"))
        pax = int(data.get("pax") or 0)
        catering_package_code = (data.get("catering_package") or "").strip()

        if not name or not phone:
            return jsonify({"ok": False, "message": "Nama dan telepon wajib."})

        cart = session.get("cart", {})
        if not cart and not is_catering:
            return jsonify({"ok": False, "message": "Keranjang kosong."})

        cart_int = {int(k): v for k, v in cart.items()}
        subtotal, details = utils.compute_subtotal_from_cart(cart_int)

        pkg = None
        if is_catering:
            if catering_package_code:
                pkg = Product.query.filter(Product.code == catering_package_code).first()
            else:
                pkg = Product.query.filter_by(category="catering").first()
            if not pkg:
                return jsonify({"ok": False, "message": "Tidak ada paket catering tersedia."})
            if pax <= 0:
                return jsonify({"ok": False, "message": "Untuk catering, tentukan pax (>0)."})
            subtotal = pkg.price * pax

        discount, promo_obj = utils.apply_promotion(subtotal, promo, is_catering=is_catering, pax=pax)
        tax = utils.compute_tax(subtotal - discount)
        delivery_fee = utils.compute_delivery_fee(subtotal, has_location=bool(address))
        total = subtotal - discount + tax + delivery_fee

        order = Order(
            order_no=utils.rand_order_no(),
            customer_name=name,
            phone=phone,
            address=address,
            is_catering=is_catering,
            catering_package=(pkg.code if is_catering and pkg else None),
            pax=(pax if is_catering else None),
            subtotal=subtotal,
            discount=discount,
            tax=tax,
            delivery_fee=delivery_fee,
            total=total,
            promo_code=(promo_obj.code if promo_obj else None),
            status="pending"
        )
        db.session.add(order)
        db.session.commit()

        if not is_catering:
            for it in details:
                oi = OrderItem(order_id_fk=order.id, product_id=it["product"].id, quantity=it["qty"], unit_price=it["product"].price)
                db.session.add(oi)
            db.session.commit()
            session["cart"] = {}
            session.modified = True

        msg = f"Pesanan dibuat: {order.order_no}. Total Rp{total:,}. Status: {order.status}."
        utils.log(f"New order {order.order_no} by {name}, total={total}")
        return jsonify({"ok": True, "message": msg, "order_no": order.order_no})
    except Exception as e:
        utils.log(f"api_checkout error: {e}")
        return jsonify({"ok": False, "message": "Terjadi kesalahan saat checkout."}), 500

# Admin (simple)
ADMIN_PASSWORD = "admin123"
@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        pw = request.form.get("password","")
        if pw == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin_orders"))
        flash("Password admin salah.")
    return """
    <html><body>
    <h3>Admin Login</h3>
    <form method="post">
      <input name="password" placeholder="admin password"/>
      <button type="submit">Login</button>
    </form>
    </body></html>
    """

def admin_required(func):
    from functools import wraps
    @wraps(func)
    def decorated(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return func(*args, **kwargs)
    return decorated

@app.route("/admin/orders")
@admin_required
def admin_orders():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    html = "<h2>Orders</h2><a href='/admin/export'>Export CSV</a><br/><a href='/admin/logout'>Logout</a><hr/>"
    for o in orders:
        html += f"<div style='border:1px solid #ddd;padding:8px;margin:8px;'><b>{o.order_no}</b> - {o.customer_name} | Rp{o.total:,} | {o.status} | {o.created_at}<br/>"
        items = OrderItem.query.filter_by(order_id_fk=o.id).all()
        if items:
            html += "<ul>"
            for it in items:
                p = Product.query.get(it.product_id)
                html += f"<li>{p.name} x{it.quantity} = Rp{it.unit_price*it.quantity:,}</li>"
            html += "</ul>"
        html += f"<form method='post' action='/admin/update/{o.id}'>"
        html += "<select name='status'><option>pending</option><option>confirmed</option><option>preparing</option><option>out_for_delivery</option><option>delivered</option><option>cancelled</option></select>"
        html += "<button type='submit'>Set</button></form></div>"
    return html

@app.route("/admin/update/<int:order_id>", methods=["POST"])
@admin_required
def admin_update(order_id):
    status = request.form.get("status")
    o = Order.query.get_or_404(order_id)
    o.status = status
    db.session.commit()
    return redirect(url_for("admin_orders"))

@app.route("/admin/export")
@admin_required
def admin_export():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    si = io.StringIO()
    cw = __import__("csv").writer(si)
    cw.writerow(["order_no","name","phone","address","is_catering","pax","subtotal","discount","tax","delivery_fee","total","promo","status","created_at"])
    for o in orders:
        cw.writerow([o.order_no,o.customer_name,o.phone,o.address,o.is_catering,o.pax,o.subtotal,o.discount,o.tax,o.delivery_fee,o.total,o.promo_code,o.status,o.created_at])
    mem = io.BytesIO()
    mem.write(si.getvalue().encode("utf-8"))
    mem.seek(0)
    return send_file(mem, mimetype="text/csv", download_name="orders_export.csv", as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
