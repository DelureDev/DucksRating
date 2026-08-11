import datetime
import time

import requests
from bs4 import BeautifulSoup

from .config import CHANNEL, FETCH_DELAY_SECONDS, USER_AGENT
from .models import RawPost

BASE_URL = f"https://t.me/s/{CHANNEL}"


class FetchError(Exception):
    pass


def _get(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    if resp.status_code != 200:
        raise FetchError(f"GET {url} -> HTTP {resp.status_code}")
    return resp.text


def parse_page(html: str) -> list[RawPost]:
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    for msg in soup.select("div.tgme_widget_message[data-post]"):
        text_div = msg.select_one("div.tgme_widget_message_text")
        time_el = msg.select_one("time[datetime]")
        if text_div is None or time_el is None:
            continue  # photo-only or service message
        for br in text_div.find_all("br"):
            br.replace_with("\n")
        posts.append(RawPost(
            msg_id=int(msg["data-post"].split("/")[-1]),
            date=datetime.datetime.fromisoformat(time_el["datetime"]).date(),
            text=text_div.get_text(),
        ))
    return posts


def fetch_posts_until(known_ids: set[int]) -> list[RawPost]:
    new_posts: list[RawPost] = []
    before: int | None = None
    while True:
        url = BASE_URL if before is None else f"{BASE_URL}?before={before}"
        page = parse_page(_get(url))
        if not page:
            break
        fresh = [p for p in page if p.msg_id not in known_ids]
        new_posts.extend(fresh)
        oldest = min(p.msg_id for p in page)
        if len(fresh) < len(page):
            break  # reached already-known posts
        if before is not None and oldest >= before:
            break  # no progress safeguard
        before = oldest
        time.sleep(FETCH_DELAY_SECONDS)
    return sorted(new_posts, key=lambda p: p.msg_id)
