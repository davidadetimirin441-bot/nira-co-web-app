NIRA & CO UK source - real website and app

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
- Long-life login cookie so users stay signed in unless they sign out or clear browser data
- User sourcer profiles
- User details for phone, company, city/main market, investor type, and newsletter opt-in
- Role-based access for investor, deal sourcer, estate agent, developer, and admin accounts
- Admin-only newsletter, ad configuration, and platform statistics tools
- UK-only deal API across England, Scotland and Wales with real listing links and property photos
- Postcode-area browsing for UK houses, including examples such as CV1, CF24, G12, LS6 and NG7
- £15/month full-access subscription gate in prototype mode
- Payment method capture for card, UK bank, and Airtim reference
- Monthly payment records for £15 per person/month
- Manual bank-transfer details removed. Real subscription payments should use Stripe Checkout in production.
- Google AdSense earning setup with publisher ID, ad slot, monthly page views, RPM and estimated monthly revenue
- Weekly deal newsletter generator using the email outbox or SMTP
- Sourcer, technical team, and assistant chat in prototype mode
- Forgot-password reset links stored in an email outbox table
- New reset password tokens are stored as protected hashes in the database, not raw usable tokens
- Optional real reset-email sending with SMTP settings
- Dedicated reset page at /reset?token=...
- BASE_URL setting for automatic live reset and verification links, for example https://nireco.co.uk

For public launch:
- Host it on HTTPS
- Replace sample deal data with a licensed property-feed API
- Connect Google/Apple/Microsoft OAuth credentials
- Connect Stripe or another payment processor for real £15/month billing
- Connect your business bank through Stripe payouts or another regulated payment provider. Do not store raw customer bank details yourself.
- Add ads, affiliate deals, sponsored listings, or lead fees if you want extra income from traffic. Website visits alone normally do not pay without one of those revenue systems.
- For Google Ads/AdSense income, create and approve a Google AdSense account, then add the real publisher ID and ad slot in the Ad earnings page.
- Connect a production AI provider for live assistant responses
- Connect SMTP, SendGrid, Mailgun, Postmark, or another email service for real reset-email delivery

SMTP variables for real reset emails:
- BASE_URL
- SECRET_KEY
- COOKIE_SECURE
- ADMIN_EMAILS
- SMTP_HOST
- SMTP_PORT
- FROM_EMAIL
- SMTP_USERNAME
- SMTP_PASSWORD
- SMTP_TLS

Email verification troubleshooting:
- Copy .env.example to .env and fill in SMTP settings.
- Restart the app after changing .env.
- If SMTP is not configured, verification/reset messages are saved to the email_outbox table.
- Run python show_outbox.py from this folder to view the latest locally saved emails.
