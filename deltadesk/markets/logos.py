"""Company website domains for our universe, used by the pages to fetch a logo from a public favicon
service (no account, no key). Unknown symbols fall back to a monogram in the UI. Add or fix entries here."""
from __future__ import annotations

DOMAINS: dict[str, str] = {
    # NIFTY 50
    "HDFCBANK": "hdfcbank.com", "ICICIBANK": "icicibank.com", "RELIANCE": "ril.com", "INFY": "infosys.com",
    "BHARTIARTL": "airtel.in", "LT": "larsentoubro.com", "ITC": "itcportal.com", "TCS": "tcs.com", "AXISBANK": "axisbank.com",
    "KOTAKBANK": "kotak.com", "SBIN": "sbi.co.in", "M&M": "mahindra.com", "BAJFINANCE": "bajajfinserv.in", "HINDUNILVR": "hul.co.in",
    "SUNPHARMA": "sunpharma.com", "MARUTI": "marutisuzuki.com", "NTPC": "ntpc.co.in", "HCLTECH": "hcltech.com",
    "ULTRACEMCO": "ultratechcement.com", "TATAMOTORS": "tatamotors.com", "TITAN": "titancompany.in", "POWERGRID": "powergrid.in",
    "BAJAJFINSV": "bajajfinserv.in", "TATASTEEL": "tatasteel.com", "ADANIPORTS": "adaniports.com", "ASIANPAINT": "asianpaints.com",
    "ONGC": "ongcindia.com", "BEL": "bel-india.in", "JSWSTEEL": "jsw.in", "COALINDIA": "coalindia.in", "NESTLEIND": "nestle.in",
    "GRASIM": "grasim.com", "TRENT": "trentlimited.com", "HINDALCO": "hindalco.com", "ADANIENT": "adanienterprises.com",
    "TECHM": "techmahindra.com", "SBILIFE": "sbilife.co.in", "HDFCLIFE": "hdfclife.com", "BAJAJ-AUTO": "bajajauto.com",
    "EICHERMOT": "eicher.in", "CIPLA": "cipla.com", "DRREDDY": "drreddys.com", "WIPRO": "wipro.com", "SHRIRAMFIN": "shriramfinance.in",
    "APOLLOHOSP": "apollohospitals.com", "TATACONSUM": "tataconsumer.com", "JIOFIN": "jfs.in", "HEROMOTOCO": "heromotocorp.com",
    "INDUSINDBK": "indusind.com", "BPCL": "bharatpetroleum.in",
    # banks and financials
    "BANKBARODA": "bankofbaroda.in", "PNB": "pnbindia.in", "FEDERALBNK": "federalbank.co.in", "AUBANK": "aubank.in",
    "IDFCFIRSTB": "idfcfirstbank.com", "CANBK": "canarabank.com", "CHOLAFIN": "cholamandalam.com", "ICICIGI": "icicilombard.com",
    "HDFCAMC": "hdfcfund.com", "MUTHOOTFIN": "muthootfinance.com", "SBICARD": "sbicard.com", "PFC": "pfcindia.com", "RECLTD": "recindia.nic.in",
    "ICICIPRULI": "iciciprulife.com", "LICHSGFIN": "lichousing.com", "LICI": "licindia.in", "IRFC": "irfc.co.in", "SUNDARMFIN": "sundaramfinance.in",
    "BAJAJHLDNG": "bajajholdings.com",
    # midcap select
    "PERSISTENT": "persistent.com", "MAXHEALTH": "maxhealthcare.in", "DIXON": "dixoninfo.com", "INDHOTEL": "ihcltata.com",
    "LUPIN": "lupin.com", "AUROPHARMA": "aurobindo.com", "CUMMINSIND": "cummins.com", "VOLTAS": "voltas.com", "ASHOKLEY": "ashokleyland.com",
    "MPHASIS": "mphasis.com", "COFORGE": "coforge.com", "GODREJPROP": "godrejproperties.com", "ASTRAL": "astralpipes.com", "SRF": "srf.com",
    "UPL": "upl-ltd.com", "CONCOR": "concorindia.co.in", "PIIND": "piindustries.com", "BHARATFORG": "bharatforge.com", "POLYCAB": "polycab.com",
    "OBEROIRLTY": "oberoirealty.com", "JUBLFOOD": "jubilantfoodworks.com",
    # next 50
    "HAL": "hal-india.co.in", "DLF": "dlf.in", "VBL": "varunbeverages.com", "DIVISLAB": "divislabs.com", "PIDILITIND": "pidilite.com",
    "SIEMENS": "siemens.com", "ABB": "abb.com", "TVSMOTOR": "tvsmotor.com", "GODREJCP": "godrejcp.com", "AMBUJACEM": "ambujacement.com",
    "SHREECEM": "shreecement.com", "VEDL": "vedantalimited.com", "ZYDUSLIFE": "zyduslife.com", "TORNTPHARM": "torrentpharma.com",
    "IOC": "iocl.com", "GAIL": "gailonline.com", "ADANIGREEN": "adanigreenenergy.com", "ADANIPOWER": "adanipower.com",
    "TATAPOWER": "tatapower.com", "JSWENERGY": "jsw.in", "ZOMATO": "zomato.com", "NAUKRI": "infoedge.in", "DMART": "dmartindia.com",
    "HAVELLS": "havells.com", "BOSCHLTD": "bosch.in", "MOTHERSON": "motherson.com", "INDIGO": "goindigo.in", "BHEL": "bhel.com",
    "CGPOWER": "cgglobal.com", "ATGL": "adanigas.com", "BRITANNIA": "britannia.co.in", "DABUR": "dabur.com", "COLPAL": "colgatepalmolive.co.in",
    "MARICO": "marico.com", "UNITDSPR": "diageoindia.com", "LTIM": "ltimindtree.com", "HINDPETRO": "hindustanpetroleum.com",
    "JINDALSTEL": "jindalsteelpower.com",
    # ETFs (fund houses)
    "NIFTYBEES": "nipponindiaim.com", "BANKBEES": "nipponindiaim.com", "JUNIORBEES": "nipponindiaim.com", "ITBEES": "nipponindiaim.com",
    "GOLDBEES": "nipponindiaim.com", "SILVERBEES": "nipponindiaim.com", "LIQUIDBEES": "nipponindiaim.com", "CPSEETF": "nipponindiaim.com",
    "MIDSELIETF": "icicipruamc.com", "SETFNIF50": "sbimf.com", "MON100": "motilaloswalmf.com", "MAFANG": "miraeassetmf.co.in",
}


def logo_url(symbol: str, size: int = 64) -> str | None:
    d = DOMAINS.get(symbol.upper())
    return f"https://www.google.com/s2/favicons?domain={d}&sz={size}" if d else None
