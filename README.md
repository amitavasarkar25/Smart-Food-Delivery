# SmartBite — Smart Food Delivery (Flask + Oracle + DAA)

A responsive Python/Flask food-ordering mini-project backed by Oracle Database. It includes customer registration/login, cart and checkout, admin order management, delivery-partner assignment and GPS tracking, map-based route estimates, dynamic Dijkstra/Prim analytics, and a Pandas/NumPy sales dashboard.

## Requirements

- Python 3.10 or later
- Oracle Database Free/Oracle XE reachable from this machine
- An Oracle schema/user with permission to create tables, identities, and indexes/constraints
- Internet access for Leaflet/OpenStreetMap tiles, Nominatim address lookup, OSRM route estimates, and Chart.js CDN
- Browser location permission for GPS. Browser GPS normally requires `localhost` or HTTPS.

## Setup on macOS

1. Extract the ZIP and open Terminal in `SmartFoodDelivery_Python_Oracle`.
2. Create a virtual environment and install packages:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. Create your local environment file and edit it with the **same Oracle username/password/service that work in SQL Developer**:

   ```bash
   cp .env.example .env
   nano .env
   ```

   Do not share or upload `.env`; it contains credentials. The example defaults to schema `SMARTFOOD_NEW`, service `FREEPDB1`, and `localhost:1521`, but change them if your Oracle setup differs.

4. Run the non-destructive schema setup/migration:

   ```bash
   python init_db.py
   ```

   The script creates missing tables and adds `delivery_latitude` / `delivery_longitude` columns if missing. It does **not** drop tables or delete orders. Existing restaurant coordinates are preserved; missing coordinates get the Kharar default. If you intentionally want to change the restaurant's location, update the active restaurant's `latitude`, `longitude`, and address in Oracle SQL Developer. Checkout, radius validation, and maps read the saved active restaurant coordinates.

5. Start the app:

   ```bash
   python app.py
   ```

6. Open `http://127.0.0.1:5000` in a browser. To test from a phone on the same Wi-Fi, configure a trusted local network address and firewall appropriately; GPS permissions may require HTTPS outside localhost. Do not expose the development server directly to the public internet.

## Demo accounts

- Admin email is `admin@smartfood.local`; set a private local password in `.env` via `ADMIN_PASSWORD`.
- Delivery demo account: `delivery@smartfood.local` / `Delivery_2026` (seeded only if absent in the schema).
- Customer: register using the website.

Change demo passwords before using any non-local deployment. Cash on Delivery is a project-demo flow; there is no payment gateway.

## Location and maps

- Customer can opt into browser GPS or use a full typed address. The address is required for delivery; GPS is optional.
- Server validates coordinates and checks the configured delivery radius using **straight-line Haversine distance** from the restaurant. This is not road distance.
- When available, OSRM provides road distance, route geometry, and a travel-time estimate. The public demo service is not traffic-aware and can be unavailable/rate-limited. The app reports errors instead of treating failed routes as valid.
- Delivery partner GPS is only requested after the partner claims an order and presses **Start live tracking**. Updates are tied to the assigned order; customers can see the latest saved location for their own orders.
- Nominatim address lookup and map tiles require internet. If GPS/address lookup fails, the app shows a message rather than silently guessing coordinates.

## Dijkstra and Prim

- Analytics builds nodes from the active restaurant and active orders that have saved coordinates in Oracle. College-gate and hardcoded landmark nodes are not used.
- Dijkstra calculates a minimum-weight path between the selected current locations.
- Prim calculates a minimum spanning tree/forest connecting the graph; it is not a shortest route between two endpoints.
- When OSRM's table service is reachable, graph weights use road distances. If not, the graph clearly falls back to Haversine straight-line distances. The map lines visualize graph edges; live delivery navigation separately displays OSRM road geometry.
- Orders created before the GPS-coordinate columns existed may not have coordinates. New orders populate them; for older orders, re-enter the delivery location or add verified coordinates in Oracle before expecting them to appear in the dynamic graph.

## Sales analytics

The admin dashboard links to `/admin/sales`. `analytics.py` uses Pandas DataFrames/Series to group daily/monthly sales and NumPy to calculate numerical statistics. Chart.js draws the daily-sales bar chart, order-status pie chart, and monthly-sales chart. Revenue excludes cancelled orders; no fake sales records are generated.

## PL/SQL coursework

Run `plsql/smartfood_plsql.sql` in SQL Developer after the schema setup, connected as the application schema. Execute with F5 to create the status-history trigger, order-total function, procedures, package, and explicit-cursor report. Review the script before running it in any non-demo database.

## Important files

- `app.py` — Flask routes, authentication, checkout, delivery APIs, map endpoints
- `algorithms.py` — validated Dijkstra, Prim minimum spanning forest, Haversine, dynamic graph builder
- `analytics.py` — Pandas/NumPy sales calculations
- `init_db.py` — create missing tables and apply safe additive migrations
- `templates/` — responsive customer/admin/delivery/analytics pages
- `static/css/app.css` — responsive layout for phones and desktop browsers
- `plsql/smartfood_plsql.sql` — database coursework examples

## Test checklist

1. `python -m compileall .` — Python syntax check.
2. `python -m unittest discover -s tests -v` — algorithm and analytics unit tests.
3. `python init_db.py` — verify Oracle connectivity and migrations (requires your local Oracle service).
4. `python app.py` — verify login, menu, cart, GPS/address checkout, order status, delivery claim/tracking, analytics, and sales page against your actual Oracle database and browser.

External map services and your Oracle instance cannot be verified from a different machine. The included local tests check algorithms and data calculations but do not replace an end-to-end test with your database and GPS-enabled browser.
