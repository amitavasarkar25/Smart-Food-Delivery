import os, math, json, ssl, certifi, urllib.parse, urllib.request, urllib.error
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import oracledb
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from algorithms import dijkstra, prim_mst, haversine_km, build_location_graph
from analytics import summarize_sales, SalesAnalytics

load_dotenv()


HTTPS_CONTEXT = ssl.create_default_context(cafile=certifi.where())
RESTAURANT_LAT = float(os.getenv("RESTAURANT_LAT", "30.749611"))
RESTAURANT_LON = float(os.getenv("RESTAURANT_LON", "76.629417"))
DELIVERY_RADIUS_KM = float(os.getenv("DELIVERY_RADIUS_KM", "20"))
app=Flask(__name__)
app.secret_key=os.getenv("FLASK_SECRET_KEY","change-this-local-secret")
def conn():
    return oracledb.connect(user=os.getenv("ORACLE_USER","SMARTFOOD_NEW"),password=os.getenv("ORACLE_PASSWORD","CHANGE_ME"),host=os.getenv("ORACLE_HOST","localhost"),port=int(os.getenv("ORACLE_PORT","1521")),service_name=os.getenv("ORACLE_SERVICE","FREEPDB1"))
def rows(sql,params=None):
    with conn() as c:
        cur=c.cursor(); cur.execute(sql,params or {})
        names=[d[0].lower() for d in cur.description] if cur.description else []
        return [dict(zip(names,r)) for r in cur.fetchall()] if names else []
def run(sql,params=None):
    with conn() as c:
        cur=c.cursor(); cur.execute(sql,params or {}); c.commit()

def geocode_address(address):
    """Resolve a typed address with Nominatim; internet and a specific address are required."""
    address = str(address or "").strip()
    if not address or len(address) > 500:
        return None
    search_address = address if "india" in address.lower() else address + ", India"
    query = urllib.parse.urlencode({"format": "jsonv2", "limit": 1, "q": search_address})
    req = urllib.request.Request(
        "https://nominatim.openstreetmap.org/search?" + query,
        headers={"User-Agent": "SmartBiteStudentProject/1.0 (student delivery prototype)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8, context=HTTPS_CONTEXT) as response:
            found = json.loads(response.read().decode("utf-8"))
        if not found:
            return None
        return {"lat": float(found[0]["lat"]), "lon": float(found[0]["lon"]),
                "label": found[0].get("display_name", address)}
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def restaurant_location():
    """Return the first active restaurant's saved coordinates, falling back to environment defaults."""
    try:
        found = rows("SELECT restaurant_name,latitude,longitude,address FROM restaurants WHERE is_active='Y' ORDER BY restaurant_id FETCH FIRST 1 ROWS ONLY")
        if found and valid_coordinates(found[0].get("latitude"), found[0].get("longitude")):
            item = found[0]
            return {"name": item.get("restaurant_name") or "Restaurant", "lat": float(item["latitude"]),
                    "lon": float(item["longitude"]), "address": item.get("address") or ""}
    except Exception:
        app.logger.warning("Using configured restaurant coordinates because database coordinates are unavailable")
    return {"name": "Restaurant", "lat": RESTAURANT_LAT, "lon": RESTAURANT_LON, "address": ""}


def valid_coordinates(lat, lon):
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def road_distance_matrix(locations):
    """Ask the public OSRM Table API for pairwise road distances; return None on failure."""
    if len(locations) < 2 or len(locations) > 20:
        return None
    coords = ";".join(f"{lon},{lat}" for lat, lon in locations.values())
    url = f"https://router.project-osrm.org/table/v1/driving/{coords}?annotations=distance"
    req = urllib.request.Request(url, headers={"User-Agent": "SmartBiteStudentProject/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=8, context=HTTPS_CONTEXT) as response:
            payload = json.loads(response.read().decode("utf-8"))
        matrix = payload.get("distances")
        if payload.get("code") != "Ok" or not matrix or len(matrix) != len(locations):
            return None
        out = []
        for row in matrix:
            if not isinstance(row, list) or len(row) != len(locations):
                return None
            out.append([float(v) / 1000.0 if v is not None else math.nan for v in row])
        # OSRM may return null for unreachable pairs. A complete undirected DAA graph
        # cannot use these; symmetrise pairwise road distances for Prim's MST.
        if any(not math.isfinite(v) or v < 0 for row in out for v in row):
            return None
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                pair = (out[i][j] + out[j][i]) / 2.0
                out[i][j] = pair
                out[j][i] = pair
        return out
    except Exception:
        return None


def live_delivery_graph():
    """Build a graph from the restaurant and currently active orders with stored GPS."""
    restaurant = restaurant_location()
    restaurant_name = str(restaurant["name"])
    restaurant_coords = (restaurant["lat"], restaurant["lon"])
    locations = {restaurant_name: restaurant_coords}
    metadata = {restaurant_name: {"kind": "restaurant", "order_id": None}}
    active = rows("""SELECT order_id,delivery_address,delivery_latitude,delivery_longitude,order_status
                     FROM food_orders WHERE order_status NOT IN ('DELIVERED','CANCELLED')
                     AND delivery_latitude IS NOT NULL AND delivery_longitude IS NOT NULL
                     ORDER BY order_id DESC FETCH FIRST 14 ROWS ONLY""")
    for order in active:
        key = f"Order #{int(order['order_id'])}"
        coords = valid_coordinates(order.get("delivery_latitude"), order.get("delivery_longitude"))
        if not coords:
            continue
        locations[key] = coords
        metadata[key] = {"kind": "customer", "order_id": int(order["order_id"]),
                         "address": order.get("delivery_address") or "Customer delivery location"}
    custom = session.get("custom_graph_locations", {})
    if isinstance(custom, dict):
        for raw_name, raw_coords in list(custom.items())[:5]:
            name = str(raw_name).strip()[:50]
            if not name or name in locations:
                continue
            coords = valid_coordinates(*(raw_coords if isinstance(raw_coords, (list, tuple)) and len(raw_coords) == 2 else (None, None)))
            if not coords:
                continue
            locations[name] = coords
            metadata[name] = {"kind": "custom", "order_id": None}
    matrix = road_distance_matrix(locations)
    graph = build_location_graph(locations, matrix)
    return graph, metadata, ("OSRM road distances" if matrix is not None else "straight-line Haversine distances (OSRM unavailable)")

def need(role=None):
    def deco(fn):
        @wraps(fn)
        def inner(*a,**kw):
            if session.get("user_id") is None: return redirect(url_for("login"))
            if role and session.get("role")!=role: flash("You do not have permission for that page.","error"); return redirect(url_for("index"))
            return fn(*a,**kw)
        return inner
    return deco
@app.template_filter("money")
def money(v): return f"₹{float(v or 0):,.2f}"
@app.route("/")
def index():
    restaurants=rows("SELECT restaurant_id,restaurant_name,address,latitude,longitude FROM restaurants WHERE is_active='Y' ORDER BY restaurant_name")
    items=rows("SELECT m.item_id,m.item_name,m.description,m.price,m.restaurant_id,r.restaurant_name FROM menu_items m JOIN restaurants r ON r.restaurant_id=m.restaurant_id WHERE m.is_available='Y' AND r.is_active='Y' ORDER BY r.restaurant_name,m.item_name")
    return render_template("index.html",restaurants=restaurants,items=items)
@app.route("/register",methods=["GET","POST"])
def register():
    if request.method=="POST":
        name=request.form.get("full_name","").strip(); email=request.form.get("email","").strip().lower(); password=request.form.get("password","")
        if not name or not email or len(password)<6: flash("Enter your name, valid email and password of at least 6 characters.","error")
        else:
            try:
                run("INSERT INTO customers(full_name,email,password_hash,phone,address) VALUES(:n,:e,:p,:ph,:a)",{"n":name,"e":email,"p":generate_password_hash(password),"ph":request.form.get("phone",""),"a":request.form.get("address","").strip()})
                flash("Account created. Please sign in.","success"); return redirect(url_for("login"))
            except Exception as e: flash("Registration failed. That email may already be registered.")
    return render_template("register.html")
@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        e=request.form.get("email","").strip().lower(); p=request.form.get("password","")
        if e==os.getenv("ADMIN_EMAIL","admin@smartfood.local") and p==os.getenv("ADMIN_PASSWORD","ChangeThisDemoPassword_2026"):
            session.clear(); session.update(user_id=0,name="Administrator",role="admin"); return redirect(url_for("admin"))
        try:
            u=rows("SELECT customer_id user_id,full_name name,password_hash FROM customers WHERE LOWER(email)=:e",{"e":e})
            if u and (u[0]["password_hash"]==p or check_password_hash(str(u[0]["password_hash"]),p)):
                session.clear(); session.update(user_id=u[0]["user_id"],name=u[0]["name"],role="customer"); return redirect(url_for("index"))
            staff=rows("SELECT staff_id user_id,staff_name name,password_hash FROM delivery_staff WHERE LOWER(email)=:e",{"e":e})
            if staff and (staff[0]["password_hash"]==p or check_password_hash(str(staff[0]["password_hash"]),p)):
                session.clear(); session.update(user_id=staff[0]["user_id"],name=staff[0]["name"],role="delivery"); return redirect(url_for("delivery"))
        except Exception as ex: app.logger.exception("Login database error")
        flash("Login details not recognised.","error")
    return render_template("login.html")
@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("index"))
@app.route("/cart/add/<int:item_id>",methods=["POST"])
@need("customer")
def add(item_id):
    cart=session.get("cart",{}); k=str(item_id); cart[k]=min(99,int(cart.get(k,0))+1); session["cart"]=cart; flash("Added to your cart.","success"); return redirect(request.referrer or url_for("index"))
@app.route("/cart")
@need("customer")
def cart():
    items=[]; total=0
    for iid,qty in session.get("cart",{}).items():
        found=rows("SELECT item_id,item_name,price FROM menu_items WHERE item_id=:i AND is_available='Y'",{"i":int(iid)})
        if found:
            x=found[0]; x["quantity"]=qty; x["subtotal"]=float(x["price"])*qty; total+=x["subtotal"]; items.append(x)
    return render_template("cart.html", items=items, total=total, radius_km=DELIVERY_RADIUS_KM, restaurant=restaurant_location())
@app.route("/cart/remove/<int:item_id>",methods=["POST"])
@need("customer")
def remove(item_id):
    c=session.get("cart",{}); c.pop(str(item_id),None); session["cart"]=c; return redirect(url_for("cart"))
@app.route("/checkout", methods=["POST"])
@need("customer")
def checkout():
    cart = session.get("cart", {})
    if not cart:
        flash("Your cart is empty.", "error")
        return redirect(url_for("cart"))
    address = request.form.get("address", "").strip()
    if not address or len(address) > 500:
        flash("Enter your house number, street/locality and city (maximum 500 characters).", "error")
        return redirect(url_for("cart"))
    gps = valid_coordinates(request.form.get("latitude", ""), request.form.get("longitude", ""))
    if gps:
        destination = {"lat": gps[0], "lon": gps[1], "label": address, "source": "browser GPS"}
    else:
        geocoded = geocode_address(address)
        if geocoded is None:
            flash("We could not locate that address. Allow GPS or include your locality and city, then try again.", "error")
            return redirect(url_for("cart"))
        destination = {**geocoded, "source": "address lookup"}
    restaurant = restaurant_location()
    distance = haversine_km((restaurant["lat"], restaurant["lon"]), (destination["lat"], destination["lon"]))
    if distance > DELIVERY_RADIUS_KM:
        flash(f"Sorry, your location is {distance:.1f} km from the restaurant in a straight line. Delivery is available within {DELIVERY_RADIUS_KM:.0f} km.", "error")
        return redirect(url_for("cart"))
    try:
        with conn() as c:
            cur = c.cursor()
            total, lines = 0.0, []
            for iid, qty in cart.items():
                cur.execute("SELECT item_name,price FROM menu_items WHERE item_id=:i AND is_available='Y'", {"i": int(iid)})
                item = cur.fetchone()
                if not item:
                    continue
                quantity = max(1, min(99, int(qty)))
                price = float(item[1])
                lines.append((int(iid), quantity, price))
                total += price * quantity
            if not lines:
                flash("Items are no longer available.", "error")
                return redirect(url_for("cart"))
            oid = cur.var(oracledb.NUMBER)
            cur.execute("""INSERT INTO food_orders(customer_id,order_status,total_amount,delivery_address,delivery_latitude,delivery_longitude)
                           VALUES(:u,'PLACED',:t,:a,:lat,:lon) RETURNING order_id INTO :oid""",
                        {"u": session["user_id"], "t": total, "a": address,
                         "lat": destination["lat"], "lon": destination["lon"], "oid": oid})
            order_id = int(oid.getvalue()[0])
            for iid, quantity, price in lines:
                cur.execute("INSERT INTO order_items(order_id,item_id,quantity,unit_price) VALUES(:o,:i,:q,:p)",
                            {"o": order_id, "i": iid, "q": quantity, "p": price})
            cur.execute("INSERT INTO deliveries(order_id,delivery_status) VALUES(:o,'PENDING')", {"o": order_id})
            c.commit()
        session["cart"] = {}
        flash(f"Order #{order_id} placed. Location checked using {destination['source']}; straight-line distance is {distance:.1f} km.", "success")
        return redirect(url_for("orders"))
    except Exception:
        app.logger.exception("Checkout failed")
        flash("Checkout failed. Check the Flask terminal and confirm the database migration has been run.", "error")
        return redirect(url_for("cart"))
@app.route("/orders")
@need("customer")
def orders():
    data=rows("SELECT order_id,order_date,order_status,total_amount,delivery_address,delivery_latitude,delivery_longitude FROM food_orders WHERE customer_id=:i ORDER BY order_date DESC",{"i":session["user_id"]})
    restaurant = restaurant_location()
    return render_template("orders.html", orders=data, restaurant_lat=restaurant["lat"], restaurant_lon=restaurant["lon"], radius_km=DELIVERY_RADIUS_KM)
@app.route("/admin")
@need("admin")
def admin():
    stats={"customers":rows("SELECT COUNT(*) n FROM customers")[0]["n"],"orders":rows("SELECT COUNT(*) n FROM food_orders")[0]["n"],"restaurants":rows("SELECT COUNT(*) n FROM restaurants")[0]["n"],"revenue":rows("SELECT NVL(SUM(total_amount),0) n FROM food_orders WHERE order_status<>'CANCELLED'")[0]["n"]}
    data=rows("SELECT o.order_id,c.full_name,o.order_status,o.total_amount,o.delivery_address FROM food_orders o JOIN customers c ON c.customer_id=o.customer_id ORDER BY o.order_id DESC")
    restaurant = restaurant_location()
    return render_template("admin.html", stats=stats, orders=data, restaurant=restaurant, radius_km=DELIVERY_RADIUS_KM)

@app.route("/admin/restaurant/location", methods=["POST"])
@need("admin")
def update_restaurant_location():
    name = request.form.get("restaurant_name", "").strip()
    address = request.form.get("restaurant_address", "").strip()
    coords = valid_coordinates(request.form.get("latitude"), request.form.get("longitude"))
    if not name or len(name) > 160 or not address or len(address) > 400:
        flash("Enter a restaurant name (max 160 characters) and address (max 400 characters).", "error")
    elif not coords:
        flash("Enter valid restaurant latitude (-90 to 90) and longitude (-180 to 180).", "error")
    else:
        try:
            active_restaurants = rows("SELECT restaurant_id FROM restaurants WHERE is_active='Y' ORDER BY restaurant_id FETCH FIRST 1 ROWS ONLY")
            if not active_restaurants:
                flash("No active restaurant exists. Run the database setup first.", "error")
            else:
                run("UPDATE restaurants SET restaurant_name=:n,address=:a,latitude=:lat,longitude=:lon WHERE restaurant_id=:id",
                    {"n": name, "a": address, "lat": coords[0], "lon": coords[1], "id": active_restaurants[0]["restaurant_id"]})
                flash("Restaurant location updated. Checkout coverage and maps now use the saved coordinates.", "success")
        except Exception:
            app.logger.exception("Restaurant location update failed")
            flash("Could not update the restaurant location. Check the database connection and server log.", "error")
    return redirect(url_for("admin"))

@app.route("/admin/status/<int:oid>",methods=["POST"])
@need("admin")
def status(oid):
    s=request.form.get("status")
    if s not in {"CONFIRMED","PREPARING","OUT_FOR_DELIVERY","DELIVERED","CANCELLED"}: flash("Invalid status.","error")
    else:
        run("UPDATE food_orders SET order_status=:s WHERE order_id=:i", {"s": s, "i": oid})
        if s == "DELIVERED":
            run("UPDATE deliveries SET delivery_status='DELIVERED',delivered_at=CURRENT_TIMESTAMP WHERE order_id=:i", {"i": oid})
        elif s == "CANCELLED":
            run("UPDATE deliveries SET delivery_status='CANCELLED' WHERE order_id=:i", {"i": oid})
        flash("Order status updated.", "success")
    return redirect(url_for("admin"))
@app.route("/delivery")
@need("delivery")
def delivery():
    data=rows("SELECT o.order_id,o.order_status,o.total_amount,o.delivery_address,o.delivery_latitude,o.delivery_longitude,c.full_name,d.delivery_status,d.staff_id FROM deliveries d JOIN food_orders o ON o.order_id=d.order_id JOIN customers c ON c.customer_id=o.customer_id WHERE (d.staff_id=:i OR d.staff_id IS NULL) AND o.order_status NOT IN ('DELIVERED','CANCELLED') ORDER BY o.order_id",{"i":session["user_id"]})
    restaurant = restaurant_location()
    return render_template("delivery.html", orders=data, restaurant_lat=restaurant["lat"], restaurant_lon=restaurant["lon"], restaurant_name=restaurant["name"], radius_km=DELIVERY_RADIUS_KM)
@app.route("/delivery/claim/<int:oid>",methods=["POST"])
@need("delivery")
def claim(oid):
    try:
        with conn() as c:
            cur = c.cursor()
            cur.execute("UPDATE deliveries SET staff_id=:s,delivery_status='ASSIGNED' WHERE order_id=:o AND (staff_id IS NULL OR staff_id=:s) AND delivery_status <> 'DELIVERED'", {"s": session["user_id"], "o": oid})
            changed = cur.rowcount
            c.commit()
        if changed:
            flash("Delivery assigned to your account.", "success")
        else:
            flash("This order is unavailable or already assigned to another delivery partner.", "error")
    except Exception:
        app.logger.exception("Delivery claim failed")
        flash("Could not claim this delivery. Please retry.", "error")
    return redirect(url_for("delivery"))
@app.route("/analytics")
@need("admin")
def analytics():
    try:
        graph, metadata, weight_source = live_delivery_graph()
    except Exception:
        app.logger.exception("Could not load live route graph")
        graph = build_location_graph({"Restaurant": (RESTAURANT_LAT, RESTAURANT_LON)})
        metadata = {"Restaurant": {"kind": "restaurant", "order_id": None}}
        weight_source = "live order locations unavailable; showing restaurant only"
    node_names = list(graph["nodes"].keys())
    start_node = request.args.get("start", node_names[0] if node_names else "")
    end_node = request.args.get("end", node_names[-1] if node_names else "")
    if start_node not in graph["nodes"]: start_node = node_names[0] if node_names else ""
    if end_node not in graph["nodes"]: end_node = node_names[-1] if node_names else ""
    result = dijkstra(graph, start_node, end_node) if start_node and end_node and len(node_names) > 1 else None
    mst = prim_mst(graph)
    nodes = [{"id": k, "label": k, "lat": v["lat"], "lon": v["lon"], "kind": metadata.get(k, {}).get("kind", "customer")} for k, v in graph["nodes"].items()]
    edges = [{"from": u, "to": v, "weight": round(w, 2)} for u, adj in graph["edges"].items() for v, w in adj.items() if u < v]
    restaurant = restaurant_location()
    return render_template("analytics.html", nodes=nodes, edges=edges, result=result, mst=mst,
                           start=start_node, end=end_node, node_names=node_names,
                           restaurant_lat=restaurant["lat"], restaurant_lon=restaurant["lon"],
                           radius_km=DELIVERY_RADIUS_KM, weight_source=weight_source,
                           metadata=metadata, has_customer_locations=len(node_names) > 1,
                           custom_locations=session.get("custom_graph_locations", {}))

@app.route("/api/route", methods=["POST"])
@need("admin")
def api_route():
    body = request.get_json(silent=True) or {}
    start_node, end_node = str(body.get("start", "")), str(body.get("end", ""))
    try:
        graph, metadata, weight_source = live_delivery_graph()
    except Exception:
        app.logger.exception("Could not build route graph")
        return jsonify({"error": "Live delivery locations could not be loaded. Check the database and migration."}), 503
    result = dijkstra(graph, start_node, end_node)
    if result is None:
        return jsonify({"error": "No path found. Select two current locations with a saved GPS/address coordinate."}), 404
    coordinates = [{"name": name, "lat": graph["nodes"][name]["lat"], "lon": graph["nodes"][name]["lon"]} for name in result["path"]]
    return jsonify({"path": result["path"], "distance_km": result["distance"], "coordinates": coordinates,
                    "weight_source": weight_source, "note": "Dijkstra uses the displayed graph edge weights. The separate map route estimate is a road-navigation estimate."})

@app.route("/analytics/location", methods=["POST"])
@need("admin")
def add_analytics_location():
    name = request.form.get("name", "").strip()
    coords = valid_coordinates(request.form.get("latitude"), request.form.get("longitude"))
    if not name or len(name) > 50:
        flash("Enter a location name of 1–50 characters.", "error")
    elif not coords:
        flash("Enter valid latitude (-90 to 90) and longitude (-180 to 180).", "error")
    else:
        custom = session.get("custom_graph_locations", {})
        if not isinstance(custom, dict): custom = {}
        restaurant_name = restaurant_location()["name"]
        if name.lower() in {"restaurant", restaurant_name.lower()} or name in custom or name.lower().startswith("order #"):
            flash("Choose a different name; restaurant and order node names are reserved.", "error")
        elif len(custom) >= 5:
            flash("You can add up to five temporary test locations. Clear them to add different points.", "error")
        else:
            custom[name] = [coords[0], coords[1]]
            session["custom_graph_locations"] = custom
            flash(f"Temporary location '{name}' added to the graph.", "success")
    return redirect(url_for("analytics"))

@app.route("/analytics/location/clear", methods=["POST"])
@need("admin")
def clear_analytics_locations():
    session.pop("custom_graph_locations", None)
    flash("Temporary test locations cleared. Oracle orders were not changed.", "success")
    return redirect(url_for("analytics"))

@app.route("/admin/sales")
@need("admin")
def sales_analytics():
    try:
        records = rows(
            "SELECT order_id, order_date, order_status, total_amount "
            "FROM food_orders ORDER BY order_date"
        )
        summary = summarize_sales(records)

        chart_generator = SalesAnalytics()
        charts = chart_generator.generate_charts(summary)

        return render_template(
            "sales_analytics.html",
            summary=summary,
            charts=charts,
        )
    except Exception:
        app.logger.exception("Sales analytics failed")
        flash(
            "Sales analytics could not load. Check Matplotlib, Pandas/NumPy, "
            "and the database connection.",
            "error",
        )
        return redirect(url_for("admin"))
@app.route("/api/geocode", methods=["POST"])
@need()
def api_geocode():
    body = request.get_json(silent=True) or {}
    address = str(body.get("address", "")).strip()
    gps = valid_coordinates(body.get("lat"), body.get("lon"))
    if gps:
        restaurant = restaurant_location()
        distance = haversine_km((restaurant["lat"], restaurant["lon"]), gps)
        return jsonify({"lat": gps[0], "lon": gps[1], "label": address or "GPS location",
                        "source": "browser GPS", "distance_km": round(distance, 2),
                        "within_delivery_radius": distance <= DELIVERY_RADIUS_KM,
                        "radius_km": DELIVERY_RADIUS_KM})
    if not address:
        return jsonify({"error": "Enter a delivery address or use GPS."}), 400
    loc = geocode_address(address)
    if not loc:
        return jsonify({"error": "Address could not be located. Include house/street, locality and city."}), 404
    restaurant = restaurant_location()
    distance = haversine_km((restaurant["lat"], restaurant["lon"]), (loc["lat"], loc["lon"]))
    return jsonify({**loc, "source": "address lookup", "distance_km": round(distance, 2),
                    "within_delivery_radius": distance <= DELIVERY_RADIUS_KM, "radius_km": DELIVERY_RADIUS_KM})

@app.route("/api/route-estimate", methods=["POST"])
@need()
def api_route_estimate():
    """Return an OSRM road-distance, duration and GeoJSON route for two coordinates."""
    body = request.get_json(silent=True) or {}
    start = valid_coordinates(body.get("from_lat"), body.get("from_lon"))
    destination = valid_coordinates(body.get("to_lat"), body.get("to_lon"))
    if not start or not destination:
        return jsonify({"error": "Valid start and destination coordinates are required."}), 400

    # valid_coordinates returns (latitude, longitude); OSRM URL requires longitude,latitude.
    start_lat, start_lon = start
    end_lat, end_lon = destination
    coordinates = f"{start_lon:.6f},{start_lat:.6f};{end_lon:.6f},{end_lat:.6f}"
    url = (
        "https://router.project-osrm.org/route/v1/driving/"
        f"{coordinates}?overview=full&geometries=geojson"
    )
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "SmartBiteStudentProject/1.0", "Accept": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=15, context=HTTPS_CONTEXT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        app.logger.warning("OSRM returned HTTP %s for route request", exc.code)
        return jsonify({"error": f"Road-routing service returned HTTP {exc.code}. Please retry."}), 502
    except urllib.error.URLError as exc:
        app.logger.warning("OSRM is unreachable: %s", exc.reason)
        return jsonify({"error": "Cannot reach the road-routing service. Check internet access or retry shortly."}), 502
    except (TimeoutError, OSError) as exc:
        app.logger.warning("OSRM request timed out or failed: %s", exc)
        return jsonify({"error": "The road-routing service timed out or could not be reached. Please retry."}), 502
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        app.logger.exception("OSRM returned invalid JSON")
        return jsonify({"error": "The road-routing service returned an unreadable response."}), 502

    if payload.get("code") != "Ok" or not payload.get("routes"):
        osrm_code = str(payload.get("code") or "UnknownError")
        app.logger.info("OSRM found no route; response code: %s", osrm_code)
        if osrm_code == "NoRoute":
            message = "No drivable road route was found between these coordinates. Check the locations."
        elif osrm_code == "InvalidQuery":
            message = "The routing service rejected the coordinates. Check latitude and longitude."
        else:
            message = f"The routing service could not calculate a route ({osrm_code}). Please retry."
        return jsonify({"error": message, "routing_code": osrm_code}), 502

    route = payload["routes"][0]
    try:
        distance_m = float(route["distance"])
        duration_s = float(route["duration"])
        geometry = route["geometry"]
        if not (math.isfinite(distance_m) and distance_m >= 0 and
                math.isfinite(duration_s) and duration_s >= 0):
            raise ValueError("OSRM returned invalid distance or duration")
        if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
            raise ValueError("OSRM returned invalid route geometry")
    except (KeyError, TypeError, ValueError) as exc:
        app.logger.exception("Invalid OSRM route payload")
        return jsonify({"error": "The routing service returned incomplete route information."}), 502

    return jsonify({
        "distance_km": round(distance_m / 1000.0, 2),
        "duration_minutes": max(1, round(duration_s / 60.0)),
        "geometry": geometry,
        "routing_source": "OSRM / OpenStreetMap",
        "traffic_included": False,
    })

@app.route("/api/location/<int:order_id>")
@need("customer")
def customer_delivery_location(order_id):
    order = rows("SELECT order_status FROM food_orders WHERE order_id=:o AND customer_id=:c", {"o": order_id, "c": session["user_id"]})
    if not order:
        return jsonify({"error": "Order not found."}), 404
    found = rows("SELECT latitude,longitude,updated_at FROM delivery_locations WHERE order_id=:o", {"o": order_id})
    if not found:
        return jsonify({"available": False, "order_status": order[0]["order_status"]})
    return jsonify({"available": True, **found[0], "order_status": order[0]["order_status"]})

@app.route("/api/location", methods=["POST"])
@need("delivery")
def save_location():
    body = request.get_json(silent=True) or {}
    try:
        order_id = int(body.get("order_id"))
        coords = valid_coordinates(body.get("lat"), body.get("lon"))
        if not coords:
            return jsonify({"ok": False, "error": "Invalid GPS coordinates."}), 400
        lat, lon = coords
        # A delivery partner must claim the order first. Unassigned orders are not writable.
        assigned = rows("SELECT staff_id,delivery_status FROM deliveries WHERE order_id=:o", {"o": order_id})
        if not assigned:
            return jsonify({"ok": False, "error": "Delivery order not found."}), 404
        if assigned[0]["staff_id"] is None or int(assigned[0]["staff_id"]) != int(session["user_id"]):
            return jsonify({"ok": False, "error": "Claim this order first. You cannot update another partner's order."}), 403
        order = rows("SELECT order_status FROM food_orders WHERE order_id=:o", {"o": order_id})
        if not order or order[0]["order_status"] in ("DELIVERED", "CANCELLED"):
            return jsonify({"ok": False, "error": "Tracking is unavailable for completed or cancelled orders."}), 409
        run("""MERGE INTO delivery_locations d USING (SELECT :o order_id,:s staff_id,:lat latitude,:lon longitude FROM dual) x
              ON (d.order_id=x.order_id)
              WHEN MATCHED THEN UPDATE SET d.staff_id=x.staff_id,d.latitude=x.latitude,d.longitude=x.longitude,d.updated_at=CURRENT_TIMESTAMP
              WHEN NOT MATCHED THEN INSERT(order_id,staff_id,latitude,longitude) VALUES(x.order_id,x.staff_id,x.latitude,x.longitude)""",
            {"o": order_id, "s": session["user_id"], "lat": lat, "lon": lon})
        return jsonify({"ok": True, "updated": True})
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "A valid order ID and GPS coordinates are required."}), 400
    except Exception:
        app.logger.exception("Could not save delivery GPS")
        return jsonify({"ok": False, "error": "Could not save GPS to the database. Check the server log."}), 500

@app.route("/health")
def health():
    try: return jsonify({"status":"ok","database":rows("SELECT SYS_CONTEXT('USERENV','SERVICE_NAME') service FROM dual")[0]["service"]})
    except Exception as e: return jsonify({"status":"error","detail":str(e)}),500
if __name__ == "__main__":
    app.run(host=os.getenv("FLASK_HOST", "127.0.0.1"), port=int(os.getenv("FLASK_PORT", "5000")), debug=os.getenv("FLASK_DEBUG", "0") == "1")
