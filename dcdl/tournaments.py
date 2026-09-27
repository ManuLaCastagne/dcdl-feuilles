import re
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from .parser import parse_manual
BASE="https://clubdcdl.over-blog.com/"
HEADERS={"User-Agent":"Mozilla/5.0 DCDL-Feuilles/1.0"}

def find_tournament_url(city: str, year: str) -> str:
    slug=city.strip().lower()
    for page_year in (int(year), int(year)+1):
        for month in range(1,13):
            url=urljoin(BASE, f"{page_year}/{month:02d}/{slug}-{year}.html")
            r=requests.get(url,headers=HEADERS,timeout=8)
            if r.ok and (f"{slug}-{year}" in r.url or f"{slug}-{year}" in r.text.lower()) and "erreur 404" not in r.text.lower():
                return url
    raise ValueError("Tournoi introuvable. Renseigne l’URL de l’article pour éviter la recherche automatique.")

def fetch_tournament(city: str, year: str, url: str=""):
    page=url.strip() or find_tournament_url(city, year)
    if not page.startswith("http"): page=urljoin(BASE,page)
    r=requests.get(page,headers=HEADERS,timeout=15); r.raise_for_status()
    soup=BeautifulSoup(r.text,"html.parser")
    links=[]
    for a in soup.find_all("a",href=True):
        href=urljoin(page,a["href"])
        if re.search(r"\.txt(?:\?|$)",href,re.I): links.append(href)
    links=list(dict.fromkeys(links))
    if not links: raise ValueError("Aucun fichier .txt trouvé dans l’article du tournoi.")
    chunks=[]
    for link in links:
        rr=requests.get(link,headers=HEADERS,timeout=15); rr.raise_for_status()
        rr.encoding=rr.apparent_encoding or "ISO-8859-1"; chunks.append(rr.text)
    return parse_manual("\n".join(chunks)), page
