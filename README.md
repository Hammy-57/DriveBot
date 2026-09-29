# DriveBot — WhatsApp reminders & waitlist auto-fill for driving instructors

## What this does
- Sends students a WhatsApp reminder 24h and 2h before their lesson
- Lets students confirm or cancel by replying SI / NO
- If a student cancels, automatically offers the freed slot to the next
  person on the instructor's waitlist

## 1. Run it locally right now (no Twilio account needed yet)

```bash
pip install -r requirements.txt
python seed.py          # creates sample instructor/students/lesson
uvicorn main:app --reload
```

Then in another terminal, manually trigger the reminder check:

```bash
curl -u admin:admin -X POST http://localhost:8000/run-reminders-now
```

You'll see something like this printed in the terminal running uvicorn
(this is DEV MODE — no real WhatsApp message is sent yet):

```
[DEV MODE - no message sent] To +390000000002: Ciao Giulia! Promemoria: ...
```

You can also simulate a student's WhatsApp reply without Twilio, using curl:

```bash
curl -X POST http://localhost:8000/webhook \
  -d "From=whatsapp:+390000000002" \
  -d "Body=NO"
```

Watch the terminal — you'll see the lesson get cancelled AND the waitlisted
student (Luca) automatically get offered the freed slot. That's the whole
product working, end to end, before you've spent a cent or created any
external account.

## 2. Run the automated tests

```bash
pytest
```

These cover the full flow (reminder sent, confirm, cancel, waitlist offer,
waitlist accept) using a fake in-memory database — no Twilio needed.

## 3. Connect it to real WhatsApp (once you have your first instructor ready)

1. Create a free Twilio account: https://www.twilio.com/try-twilio
2. Activate the WhatsApp Sandbox (Console -> Messaging -> Try it out ->
   Send a WhatsApp message). It'll give you a sandbox number and a code
   to send from your own phone to join.
3. Copy `.env.example` to `.env` and fill in your `TWILIO_ACCOUNT_SID`
   and `TWILIO_AUTH_TOKEN` from the Twilio console, and set
   `TWILIO_WHATSAPP_NUMBER` to the sandbox number it gives you.
4. Expose your local server to the internet so Twilio can reach it —
   the easiest way while testing is `ngrok`:
   ```bash
   ngrok http 8000
   ```
   Copy the https URL ngrok gives you.
5. In the Twilio console, set your Sandbox's "WHEN A MESSAGE COMES IN"
   webhook to `https://<your-ngrok-url>/webhook`.
6. Have your test instructor and student join the sandbox (send the
   join code Twilio gave you from their phones), add them via `seed.py`
   or directly in the database, and you're live.

## 4. What's deliberately NOT built yet (on purpose)
- No dashboard — you're the dashboard for your first few instructors
- No payments — add a Stripe payment link manually once someone's happy
- No admin UI to add instructors/students — do it via `seed.py` or
  directly in the SQLite file for now

Don't build these until a real instructor asks for them. Every hour
spent on features nobody asked for yet is an hour not spent talking to
your next potential customer.

## Project structure
```
main.py         - FastAPI app + webhook endpoint
bot_logic.py    - the actual product logic (read this first)
models.py       - database tables
db.py           - database connection setup
scheduler.py    - runs the reminder check every 5 minutes
whatsapp.py     - Twilio wrapper (falls back to console printing if no
                  credentials are set, so you can build without an account)
seed.py         - creates sample data for local testing
test_logic.py   - automated tests, no Twilio account needed to run them
```
"# DriveBot" 
