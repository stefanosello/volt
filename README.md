# Volt

Minimal Flask MVP for photo-assisted electrical service requests. Customers submit a description and up to three images, with optional AI assessment. A technician reviews requests and enters nonbinding prices.

**Prototype only. Not ready for real customer information or public launch.** See deployment instructions below.

## Hosting with Railway

1. Connect this repository in Railway using **Deploy from GitHub repo**.
2. Add a persistent volume at `/data` and configure `DATABASE_PATH=/data/volt.db`. Use **one replica**.
3. Set `SECRET_KEY` and `ADMIN_PASSWORD` to different high-entropy random values. Optionally add `OPENAI_API_KEY` and `OPENAI_MODEL`.
4. Generate a Railway domain after confirming privacy, bot protection, stronger admin authentication, data retention and backups.

`railway.json` configures Gunicorn and the `/health` endpoint. Every commit on `main` can trigger a deployment. No local environment is required.

## Development

`pip install -r requirements.txt && python app.py`

`python -m unittest discover -s tests -v`

No Node, Docker, ORM, queue, or database server. AI assessment never certifies installation safety or quotes a binding price.
