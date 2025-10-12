import feedparser, requests, pandas as pd, time
from bs4 import BeautifulSoup
from datetime import datetime, timezone

UA = "Form4Tracker (contact: you@example.com)"
HEAD = {"User-Agent": UA}

PAGES, COUNT = 4, 100
FEED = ("https://www.sec.gov/cgi-bin/browse-edgar?"
        "action=getcompany&SIC=&type=4&dateb=&owner=include&start={start}&count={count}&output=atom")

def tx_rows(soup):
    for sel in ["nonDerivativeTable nonDerivativeTransaction",
                "derivativeTable derivativeTransaction"]:
        for tx in soup.select(sel):
            code  = tx.select_one("transactionCoding transactionCode")
            sh    = tx.select_one("transactionAmounts transactionShares value")
            price = tx.select_one("transactionAmounts transactionPricePerShare value")
            yield (
                code.get_text(strip=True) if code else None,
                float(sh.get_text(strip=True)) if sh and sh.get_text(strip=True) else None,
                float(price.get_text(strip=True)) if price and price.get_text(strip=True) else None
            )

rows = []
for i in range(PAGES):
    feed = feedparser.parse(FEED.format(start=i*COUNT, count=COUNT))
    for e in feed.get("entries", []):
        xml = e.link
        html = xml.replace(".xml", ".html")
        r = requests.get(xml, headers=HEAD, timeout=30)
        if r.status_code != 200:
            continue
        s = BeautifulSoup(r.text, "xml")

        issuer = s.find_text("issuerName") if s.find("issuerName") else ""
        symbol = s.find_text("issuerTradingSymbol") if s.find("issuerTradingSymbol") else ""
        owner  = s.find_text("rptOwnerName") if s.find("rptOwnerName") else ""

        rel = s.find("reportingOwnerRelationship")
        role = ""
        if rel:
            bits = []
            t = rel.find("officerTitle")
            if t and t.text.strip(): bits.append(t.text.strip())
            flags = [("isDirector","Director"),("isOfficer","Officer"),("isTenPercentOwner","10% Owner")]
            for tag,label in flags:
                f = rel.find(tag)
                if f and f.text.strip() in ("1","true","True"): bits.append(label)
            role = "; ".join(bits)

        for code, sh, pr in tx_rows(s):
            if code != "A" or not sh or not pr: continue
            rows.append({
                "FetchedUTC": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "Insider": owner, "Role": role, "Company": issuer,
                "Ticker": symbol, "Shares": sh, "Price": pr,
                "ValueUSD": round(sh*pr, 2),
                "SEC_HTML": html, "SEC_XML": xml
            })
        time.sleep(0.15)

df = pd.DataFrame(rows)
if "ValueUSD" in df.columns:
    df.sort_values(["ValueUSD"], ascending=False, inplace=True)
else:
    print("⚠️ No 'ValueUSD' column found — skipping sort.")
df.to_csv("form4_buys_latest.csv", index=False)
print(f"Saved {len(df)} rows to form4_buys_latest.csv")