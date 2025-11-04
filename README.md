# CS370_OptimizedGroceryShopping
Locate and compare grocery stores, their location and prices. use user locations to calculate the nearest stores.  Be able to handle hundreds of requests in real time.
## Quickstart

```bash
git clone <your-repo>
cd <repo>
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env


The web app needs a DB tunnel (external ssh -L or USE_SSH_TUNNEL=1).

If / returns 404, ensure app.py has a route that serves index.html.

Don’t commit .env or venv/ + .venv/.
