import feedparser, requests, pandas as pd, time
from bs4 import BeautifulSoup
from datetime import datetime, timezone

# Proper SEC-compliant user agent
HEAD = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/119.0.0.0 Safari/537.36 (Form4Tracker contact: you@example.com)"
}

# SEC Form 4 feed – latest filings
FEED_URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&owner=include&output=atom"

def parse_transactions(soup):
    """Extract acquisition transactions (code A) from Form 4 XML."""
    txs = []
    for table in ["nonDerivativeTransaction", "derivativeTransaction"]:
        for tx in soup.find_all(table):
            code = tx.find("transactionCode")
            shares = tx.find("transactionShares")
            price = tx.find("transactionPricePerShare")

            code = code.text.strip() if code else None
            shares = float(shares.text.strip()) if shares and shares.text.strip() else None
            price = float(price.text.strip()) if price and price.text.strip() else None

            if code == "A" and shares and price:
                txs.append((code, shares, price))
    return txs

rows = []
print("🔍 Fetching Form 4 feed...")
feed = feedparser.parse(FEED_URL)

for entry in feed.entries[:40]:  # limit for speed
    xml_url = entry.link
    html_url = xml_url.replace(".xml", "-index.html")

    r = requests.get(xml_url, headers=HEAD, timeout=30)
    if r.status_code != 200:
        continue

    s = BeautifulSoup(r.text, "xml")

    issuer = s.find("issuerName").text.strip() if s.find("issuerName") else ""
    symbol = s.find("issuerTradingSymbol").text.strip() if s.find("issuerTradingSymbol") else ""
    owner  = s.find("rptOwnerName").text.strip() if s.find("rptOwnerName") else ""

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
            "Insider": owner, "Role": role, "Company": issuer,
            "Ticker": symbol, "Shares": sh, "Price": pr,
            "ValueUSD": round(sh * pr, 2),
            "SEC_HTML": html_url, "SEC_XML": xml_url
        })
    time.sleep(0.2)

# Convert to DataFrame
df = pd.DataFrame(rows)
if not df.empty:
    df.sort_values("ValueUSD", ascending=False, inplace=True)
    df.to_csv("form4_buys_latest.csv", index=False)
    print(f"✅ Saved {len(df)} insider buys to form4_buys_latest.csv")
else:
    print("⚠️ No insider buys found — check feed or filters.")