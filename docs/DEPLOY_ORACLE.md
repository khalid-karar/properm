# Deploying PROPERM on Oracle Cloud (Saudi regions)

Decision (2026-11-23): database and backend on Oracle Cloud in a Saudi region (Riyadh `me-riyadh-1` or Jeddah `me-jeddah-1`). The web pages stay on Netlify. This relaxes the earlier "GitHub + Netlify only" rule for the backend and database only.

## What is verified and what is not
- Verified here: all 83 tables compile to Oracle DDL (`sqlalchemy.dialects.oracle`), and `alembic upgrade head` creates the schema on SQLite.
- **Not verified:** a full run against a real Oracle database. Before the pilot, run the whole `pytest` suite once with `DATABASE_URL` pointing at an Oracle test schema. Known Oracle traps to watch for: an empty string is stored as NULL; string comparisons are case-sensitive; reserved words are quoted automatically by SQLAlchemy.

## Steps
1. **Database:** create an Autonomous Database (or a DB system) in the Saudi region. Create a schema user for PROPERM. Allow the backend's address in the network ACL.
2. **Backend:** an OCI Compute VM in the same region. Install Docker, build this repo's `Dockerfile`, run it with the variables below. Put HTTPS in front (OCI Load Balancer, or Caddy with a certificate).
3. **Frontend:** Netlify serves `app/static`. Set `window.PROPERM_API` in `app/static/config.js` to the backend's HTTPS address (a non-empty value switches off the in-browser demo backend), and set `PROPERM_CORS_ORIGINS` on the backend to the Netlify site address.
4. **First start:** `start.sh` runs `alembic upgrade head`. Create the first admin with your usual bootstrap.
5. **Backups:** enable automatic backups on the database, and use Admin → Export for a copy of the data you control.

## Environment variables (backend)
| Variable | Value |
|---|---|
| `DATABASE_URL` | `oracle+oracledb://USER:PASSWORD@HOST:1521/?service_name=SERVICE` |
| `PROPERM_SECRET` | a long random string (32+ characters) |
| `PROPERM_CORS_ORIGINS` | your Netlify address |
| `PROPERM_ENV` | `production` (this also disables the off-Kingdom AI switch below) |
| `PROPERM_AI_BASE_URL` | the in-Kingdom model endpoint: an OCI Generative AI address (see below) or a Saudi-hosted OpenAI-compatible server |
| `PROPERM_AI_MODEL`, `PROPERM_AI_API_KEY` | model name and key for an OpenAI-compatible endpoint. For OCI: the model OCID, and no key |
| `PROPERM_OCI_COMPARTMENT` | OCI only: OCID of the compartment that holds the Generative AI policy (`properm`) |
| `PROPERM_AI_MAX_TOKENS` | longest reply the model may write (default 4000). A reply cut off at this limit is rejected, never saved as a draft |

## OCI Generative AI in Riyadh (the in-Kingdom model)
Tested 2026-11-24 in the console: `cohere.command-a-03-2025` answers in `me-riyadh-1`, pay per token, English and Arabic.

One-time setup in the OCI console (Default identity domain, root compartment):
1. Dynamic group `properm-instances`, rule `instance.compartment.id = '<properm compartment OCID>'`.
2. Policy `properm-genai`: `Allow dynamic-group properm-instances to use generative-ai-family in compartment properm`.

Backend variables on the VM (`~/properm.env`):

    PROPERM_AI_BASE_URL=https://inference.generativeai.me-riyadh-1.oci.oraclecloud.com
    PROPERM_AI_MODEL=<model OCID shown by "View code" in the Generative AI playground>
    PROPERM_OCI_COMPARTMENT=<properm compartment OCID>

No key is stored: the VM signs each request as itself (instance principal). Only the Riyadh and Jeddah endpoints count as inside the Kingdom; any other OCI region is refused. For a local test with a user key instead, set `PROPERM_OCI_AUTH=config` (reads `~/.oci/config`). Admin → AI shows the provider as `oci`.

## OpenRouter for demos and testing only
A staging or demo server (never the production one) may use OpenRouter while there is no in-Kingdom model:

    PROPERM_AI_BASE_URL=https://openrouter.ai/api/v1
    PROPERM_AI_MODEL=qwen/qwen-2.5-72b-instruct      # pick the Qwen model you want from OpenRouter
    PROPERM_AI_API_KEY=<your OpenRouter key>
    PROPERM_AI_DEMO_OFFSITE=1                         # required, or the app refuses an off-Kingdom host

While this is on, every page shows a red banner, every AI call is marked `offsite_demo` in the audit log, and Admin → AI shows "Inside the Kingdom: No". It is ignored when `PROPERM_ENV=production`. Use demo data only; do not upload real client books to that server.

## First Oracle test run (one command)
Create an empty schema just for tests, then:

    ORACLE_TEST_URL='oracle+oracledb://TESTUSER:PASSWORD@HOST:1521/?service_name=SVC' sh scripts/test_oracle.sh

It connects, prints the Oracle version, then runs the whole suite against it (the schema is dropped and rebuilt for every test). Send me the first failure and I will fix it. The redirect only works under pytest, so it can never touch a real database.

## Scheduler
Set `PROPERM_SCHEDULER=1` on the backend and it runs the daily jobs by itself (checks every 15 minutes, each job at most once a day): alert evaluation, scheduled reports, Sunday timesheet reminders, overdue-action nudges, and e-mail retries. Without it, call `POST /admin/jobs/run` from a cron. Admin → Scheduled jobs shows the history.
