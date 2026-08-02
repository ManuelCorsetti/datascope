"""
Generates a deliberately messy synthetic dataset and profiles it, so you
can see the report before pointing the tool at your own data.

    python example.py
    # -> example_report.html
"""
import numpy as np
import pandas as pd

from datascope import profile

rng = np.random.default_rng(7)
N = 4000

FIRST = ["Alex", "Priya", "Jordan", "Mei", "Sam", "Fatima", "Noah", "Elena", "Kwame", "Yuki",
         "Liam", "Sofia", "Omar", "Grace", "Ivan", "Amara", "Leo", "Nadia", "Theo", "Chloe"]
LAST = ["Chen", "Silva", "Patel", "Novak", "Muller", "Kim", "Rossi", "Diallo", "Nguyen", "Costa",
        "Haddad", "Park", "Ferreira", "Osei", "Brandt", "Iwata", "Salem", "Torres", "Ueda", "Blake"]
DOMAINS = ["gmail.com", "outlook.com", "yahoo.com", "proton.me", "company.co"]
TIERS = ["Free", "Pro", "Enterprise"]
COUNTRIES = ["US", "GB", "DE", "FR", "CA", "AU", "NL", "SE"]
CHURN_REASONS = ["Price", "Missing feature", "Switched competitor", "No longer needed", "Support issues"]
NOTE_SNIPPETS = [
    "Customer reported slow load times on the dashboard during peak hours, escalated to infra team for review.",
    "Requested a call to walk through the onboarding flow, scheduled for next Tuesday afternoon.",
    "Billing question resolved — duplicate charge refunded same day, customer satisfied with response time.",
    "Asked about enterprise SSO support, flagged as a feature request for the roadmap review.",
    "Positive feedback on the new export feature, mentioned it saved significant manual work each week.",
]

first = rng.choice(FIRST, N)
last = rng.choice(LAST, N)
full_name = [f"{f} {l}" for f, l in zip(first, last)]
email = [f"{f}.{l}{rng.integers(1,999)}@{rng.choice(DOMAINS)}".lower() for f, l in zip(first, last)]
phone = [f"+1-{rng.integers(200,999)}-{rng.integers(200,999)}-{rng.integers(1000,9999)}" for _ in range(N)]
ssn = [f"{rng.integers(100,999)}-{rng.integers(10,99)}-{rng.integers(1000,9999)}" for _ in range(N)]
address = [f"{rng.integers(1,9999)} {rng.choice(['Maple','Oak','5th','Harbor','Elm'])} St, {rng.choice(['Bristol','Leeds','Austin','Denver'])}"
           for _ in range(N)]
dob = pd.to_datetime("1955-01-01") + pd.to_timedelta(rng.integers(0, 365*50, N), unit="D")
signup_date = pd.to_datetime("2021-01-01") + pd.to_timedelta(rng.integers(0, 365*4, N), unit="D")

order_value = np.round(rng.gamma(shape=2.0, scale=45.0, size=N), 2)
outlier_idx = rng.choice(N, size=25, replace=False)
order_value[outlier_idx] *= rng.uniform(6, 12, size=25)

quantity = rng.integers(1, 12, size=N)
bad_qty_idx = rng.choice(N, size=15, replace=False)
quantity = quantity.astype(int)
quantity[bad_qty_idx] = -quantity[bad_qty_idx]  # data-quality bug: a few negative quantities

churned = rng.random(N) < 0.18
churn_date = np.where(churned, signup_date + pd.to_timedelta(rng.integers(30, 700, N), unit="D"), pd.NaT)
churn_reason = np.where(churned, rng.choice(CHURN_REASONS, N), None)

df = pd.DataFrame({
    "customer_id": np.arange(1, N + 1),
    "full_name": full_name,
    "email": email,
    "phone_number": phone,
    "ssn": ssn,
    "shipping_address": address,
    "date_of_birth": dob.strftime("%Y-%m-%d"),  # stored as text on purpose -> flags datetime_string
    "signup_date": signup_date,
    "country_code": rng.choice(COUNTRIES, N, p=[.35,.15,.1,.1,.1,.08,.07,.05]),
    "subscription_tier": rng.choice(TIERS, N, p=[.55, .35, .10]),
    "is_active": ~churned,
    "order_value": order_value,
    "quantity": quantity,
    "referral_code": [f"REF-{rng.integers(10**7,10**8-1)}" for _ in range(N)],
    "support_notes": [rng.choice(NOTE_SNIPPETS) if rng.random() < 0.4 else None for _ in range(N)],
    "churn_date": pd.to_datetime(pd.Series(churn_date)),
    "churn_reason": churn_reason,
    "schema_version": 1,  # constant column on purpose
})

# inject some exact duplicate rows
dupe_rows = df.sample(12, random_state=1)
df = pd.concat([df, dupe_rows], ignore_index=True)

if __name__ == "__main__":
    result = profile(df, output_html="example_report.html", source_name="customers_demo.csv")
    print(f"Rows: {result['meta']['n_rows']}, Columns: {result['meta']['n_cols']}")
    print(f"Quality score: {result['overview']['quality_score']}")
    print(f"Sensitive columns flagged: {result['overview']['sensitive_columns_count']}")
    print("-> example_report.html")
