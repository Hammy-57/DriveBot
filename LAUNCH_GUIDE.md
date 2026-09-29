# DriveBot launch guide (Twilio + hosting)

## Template texts (paste exactly; category UTILITY, language Italian, type Text)
| Name | Body |
|---|---|
| drivebot_reminder_24h | Ciao {{1}}! Hai una lezione di guida il {{2}} alle {{3}}. Luogo: {{4}}. Rispondi SI per confermare o NO per cancellare. |
| drivebot_reminder_2h | Ciao {{1}}, promemoria: la tua lezione del {{2}} e' tra circa 2 ore, alle {{3}}. Luogo: {{4}}. A dopo! |
| drivebot_waitlist_offer | Ciao {{1}}! Si e' liberato uno slot per il {{2}} alle {{3}}. Luogo: {{4}}. Lo vuoi? Rispondi SI o NO. |
| drivebot_instructor_notice | Aggiornamento DriveBot per il tuo calendario: {{1}} Rispondi a questo messaggio per continuare a ricevere gli avvisi in chat. |
Sample values: {{1}} Giulia, {{2}} 29/09, {{3}} 15:00, {{4}} Via Roma 25 Cassino (notice: "Giulia ha confermato la lezione").
Env vars: REMINDER_24H / REMINDER_2H / WAITLIST_OFFER / INSTRUCTOR_NOTICE -> the HX... SID of each.

## Env vars to set on the host
TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER (whatsapp:+39...), the 4 TWILIO_TEMPLATE_* SIDs,
PUBLIC_BASE_URL (exact https URL, no trailing slash), DATABASE_URL=sqlite:////data/drivebot.db,
ADMIN_USERNAME, ADMIN_PASSWORD (strong). SANDBOX_FREEFORM only for Sandbox demos.

## Go-live check
1. https://YOUR-URL/health -> {"status":"running"}
2. /admin login works; add yourself as instructor + student + a lesson ~20h ahead
3. curl -u admin:PASS -X POST https://YOUR-URL/run-reminders-now -> your phone gets the reminder
4. Reply SI, then NO, then check the admin panel shows the new status
5. If replies stop and the host logs show 403: PUBLIC_BASE_URL does not exactly match the URL in Twilio.
