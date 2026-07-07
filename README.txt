NIRA & CO Global source - real website and app

Start:
1. Double-click start-nira.bat
2. Open http://127.0.0.1:8088

Pages:
- Website: http://127.0.0.1:8088
- App: http://127.0.0.1:8088/app

What this version includes:
- Python backend using only built-in libraries
- SQLite database stored as ratada.sqlite3
- Sign up and sign in with hashed passwords
- Session cookie login
- User sourcer profiles
- User details for phone, company, city/main market, investor type, and newsletter opt-in
- Deal API with real listing links and property photos
- £15/month full-access subscription gate in prototype mode
- Payment method capture for card, UK bank, and Airtim reference
- Weekly deal newsletter generator using the email outbox or SMTP
- Sourcer, technical team, and assistant chat in prototype mode
- Forgot-password reset links stored in an email outbox table
- Optional real reset-email sending with SMTP settings
- Dedicated reset page at /reset?token=...
- APP_BASE_URL setting for automatic live reset links, for example https://niraandco.co.uk

For public launch:
- Host it on HTTPS
- Replace sample deal data with a licensed property-feed API
- Connect Google/Apple/Microsoft OAuth credentials
- Connect Stripe or another payment processor for real £15/month billing
- Connect your business bank through Stripe payouts, GoCardless/Open Banking, or another regulated payment provider. Do not store raw customer bank details yourself.
- Add ads, affiliate deals, sponsored listings, or lead fees if you want extra income from traffic. Website visits alone normally do not pay without one of those revenue systems.
- Connect a production AI provider for live assistant responses
- Connect SMTP, SendGrid, Mailgun, Postmark, or another email service for real reset-email delivery

SMTP variables for real reset emails:
- APP_BASE_URL
- SMTP_HOST
- SMTP_PORT
- SMTP_FROM
- SMTP_USER
- SMTP_PASSWORD
- SMTP_TLS
