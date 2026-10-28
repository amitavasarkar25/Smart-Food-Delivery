# Test Results — SmartBite

## Passed in the build environment

- 10 unit tests for Dijkstra, Prim's minimum spanning forest, dynamic graph construction, coordinate validation, Haversine distance, and Pandas/NumPy sales aggregation.
- Python source compilation (`python -m compileall -q .`).
- Jinja parsing and rendering checks for all 10 HTML templates.
- JavaScript syntax checks for inline scripts using Node.js.
- Mocked Flask route/template checks for home, admin, dynamic route analytics, sales analytics, customer orders, delivery desk, GPS coverage calculation, role-based analytics access, and temporary graph location submission.
- Privacy check that a customer session is redirected away from the admin-only graph containing active order locations.

## Not verified in this build environment

- A live connection to the user's Oracle instance. No database credentials are packaged, and Oracle was not available here.
- Execution of the Oracle DDL/migration script against the user's schema.
- Live GPS permission on the user's phone/computer.
- Live Nominatim geocoding, OpenStreetMap tile loading, or OSRM road routing. These require internet and can be rate-limited or unavailable.
- Real end-to-end ordering against the user's current database.

Before the project is used for a presentation, run `python init_db.py` with the correct `.env`, start Flask, then manually verify customer checkout, admin location settings, delivery claiming, GPS sharing, and the map on both desktop and mobile browsers.
