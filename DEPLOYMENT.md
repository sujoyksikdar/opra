# OPRA Deployment Guide

## Overview

- **Application:** OPRA (Online Preference Reporting and Aggregation)
- **Server:** `skanda.cs.binghamton.edu`
- **Server directory:** `/home/opra/mertcanvural_opra`
- **Access URL:** `https://opra.cs.binghamton.edu/polls/main`
- **Deployment method:** Docker (Django dev server + PostgreSQL)
- **Host port:** `8080` (campus reverse proxy maps HTTPS → 8080)

---

## First-Time Setup

### 1. Clone the repository

```bash
cd /home/opra
git clone https://github.com/mertcanvural/opra.git mertcanvural_opra
cd mertcanvural_opra
```

### 2. Add the sujoyksikdar remote (branch lives here)

```bash
sudo git remote add sujoy https://github.com/sujoyksikdar/opra.git
sudo git fetch sujoy
sudo git checkout -b complete-separation-allocation-polls --track sujoy/complete-separation-allocation-polls
```

### 3. Configure the `.env` file

```bash
sudo nano compsocsite/.env
```

Required variables:

```env
SECRET_KEY=<your-secret-key>
DEBUG=False
DATABASE_URL=postgres://opra_user:opra_password@db:5432/opra
SITE_ID=2

EMAIL_HOST=<smtp-host>
EMAIL_HOST_USER=<smtp-user>
EMAIL_HOST_PASSWORD=<smtp-password>

SOCIAL_AUTH_GOOGLE_OAUTH2_KEY=<google-oauth-key>
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET=<google-oauth-secret>
```

> Note: `DATABASE_URL` must use `db` as the host (Docker service name), not `127.0.0.1`.

### 4. Set the port to 8080 in `docker-compose.yml`

```bash
sudo nano docker-compose.yml
```

Change the `web` service ports line:

```yaml
ports:
  - "8080:8000"   # host:container
```

### 5. Build and start the containers

```bash
sudo docker-compose up -d --build
```

### 6. Verify it is running

```bash
sudo docker logs opra_web
curl http://localhost:8080/polls/main
```

---

## Redeployment (Pulling New Code)

Use this whenever new commits are pushed to the branch.

### 1. SSH into the server

```bash
ssh <username>@opra.cs.binghamton.edu
cd /home/opra/mertcanvural_opra
```

### 2. Pull the latest code

```bash
sudo git pull sujoy complete-separation-allocation-polls
```

### 3. Restart the web container

If only Python/template files changed (no new dependencies):

```bash
sudo docker restart opra_web
```

If `requirements.txt` changed or you want a clean rebuild:

```bash
sudo docker-compose down
sudo docker-compose up -d --build
```

### 4. Verify

```bash
sudo docker logs --tail 50 opra_web
```

---

## Architecture Notes

- Django's dev server (`runserver`) is used inside the container — adequate for a research/class environment.
- The campus reverse proxy handles HTTPS termination and forwards to port `8080` on the host.
- PostgreSQL data is persisted in a named Docker volume (`postgres_data`) — it survives container restarts.
- Migrations and cache table creation run automatically on startup via `docker-entrypoint.sh`.
