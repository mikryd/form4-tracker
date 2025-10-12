import feedparser, requests, pandas as pd, time
from bs4 import BeautifulSoup
from datetime import datetime, timezone

# Browser-style user agent (SEC blocks defaults)
HEAD = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/119.0.0.0 Safari/537.36 (Form4Tracker contact: you@example.com)"
}

# Fetch ~4 days of filings (≈400 recent Form 4s)
PAGES, COUNT = 4, 100
FEED = ("https://www.sec.gov/cgi-bin/browse-edgar?"
        "action=getcompany&SIC=&type=4&owner=include&start={start}&count={count}&output=atom")

def parse_transactions(soup):
    """Extract 'A' (acquisition) transactions from Form 4 XML."""
    txs = []
    for table in ["nonDerivativeTransaction", "derivativeTransaction"]:
        for tx in soup.find_all(table):
            try:
                code = tx.find("transactionCode")
                shares = tx.find("transactionShares")
                price = tx.find("transactionPricePerShare")

                code = code.text.strip() if code else None
                shares = float(shares.text.strip()) if shares and shares.text.strip() else None
                price = float(price.text.strip()) if price and price.text.strip() else None

                if code == "A" and shares and price:
                    txs.append((code, shares, price))
            except Exception:
                continue
    return txs


rows = []
print("🔍 Fetching SEC Form 4 filings...")

for i in range(PAGES):
    print(f"  → Page {i+1}/{PAGES}")
    try:
        feed = feedparser.parse(FEED.format(start=i * COUNT, count=COUNT))
        for entry in feed.get("entries", []):
            xml_url = entry.link
            html_url = xml_url.replace(".xml", "-index.html")

            try:
                r = requests.get(xml_url, headers=HEAD, timeout=30)
                if r.status_code != 200:
                    continue
                s = BeautifulSoup(r.text, "xml")

                issuer = s.find("issuerName")
                symbol = s.find("issuerTradingSymbol")
                owner = s.find("rptOwnerName")

                issuer = issuer.text.strip() if issuer else ""
                symbol = symbol.text.strip() if symbol else ""
                owner = owner.text.strip() if owner else ""

                rel = s.find("reportingOwnerRelationship")
                role = ""
                if rel:
                    bits = []
                    if rel.find("officerTitle"):
                        bits.append(rel.find("officerTitle").text.strip())
                    for tag, label in [
                        ("isDirector", "Director"),
                        ("isOfficer", "Officer"),
                        ("isTenPercentOwner", "10% Owner")
                    ]:
                        f = rel.find(tag)
                        if f and f.text.strip() in ("1", "true", "True"):
                            bits.append(label)
                    role = "; ".join(bits)

                for code, sh, pr in parse_transactions(s):
                    rows.append({
                        "FetchedUTC": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                        "Insider": owner,
                        "Role": role,
                        "Company": issuer,
                        "Ticker": symbol,
                        "Shares": sh,
                        "Price": pr,
                        "ValueUSD": round(sh * pr, 2),
                        "SEC_HTML": html_url,
                        "SEC_XML": xml_url
                    })
            except Exception as e:
                print(f"    ⚠️ Error reading {xml_url}: {e}")
            time.sleep(0.2)
    except Exception as e:
        print(f"⚠️ Feed error: {e}")

# Convert to DataFrame
df = pd.DataFrame(rows)
print(f"✅ Collected {len(df)} transactions")

# Always save a timestamped CSV (daily archive)
timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
filename = f"form4_buys_{timestamp}.csv"
df.to_csv(filename, index=False)
print(f"💾 CSV file written: {filename}")