import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from twikit import Client
from twikit.x_client_transaction import transaction as tx
import re
import time
import random
import urllib.parse
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

try:
    import snscrape.modules.twitter as sntwitter
    _SNSCRAPE_AVAILABLE = True
except Exception:
    sntwitter = None
    _SNSCRAPE_AVAILABLE = False

try:
    import requests
    _REQUESTS_AVAILABLE = True
except Exception:
    requests = None
    _REQUESTS_AVAILABLE = False

IST = timezone(timedelta(hours=5, minutes=30))

DEFAULT_DISASTER_TERMS = (
    "flood",
    "cyclone",
    "earthquake",
    "landslide",
    "tsunami",
    "storm",
    "heavy rain",
)


def parse_twitter_date(date_val):
    if isinstance(date_val, datetime):
        dt = date_val
    else:
        raw = str(date_val)
        try:
            dt = datetime.strptime(raw, "%a %b %d %H:%M:%S %z %Y")
        except Exception:
            # Keep pipeline resilient if Twikit format varies.
            return raw
    if dt.tzinfo is None:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return dt.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")


def build_disaster_query(
    query: Optional[str] = None,
    terms: Optional[Iterable[str]] = None,
    region: Optional[str] = None,
    language: str = "en",
):
    if query and query.strip():
        # Use the query exactly as provided.
        return query.strip()
    else:
        selected_terms = [term.strip() for term in (terms or DEFAULT_DISASTER_TERMS) if term.strip()]
        if not selected_terms:
            raise ValueError("At least one disaster term is required.")
        base_query = " OR ".join(f'"{term}"' if " " in term else term for term in selected_terms)

    filters = [f"({base_query})"]
    query_lower = base_query.lower()
    if language and "lang:" not in query_lower:
        filters.append(f"lang:{language}")
    if region and region.strip():
        filters.append(f'"{region.strip()}"')

    return " ".join(filters)


def _safe_getattr(obj, attr_name, default=None):
    try:
        value = getattr(obj, attr_name, default)
        return default if value is None else value
    except Exception:
        return default


def _cookie_path():
    return os.getenv("TWIKIT_COOKIE_PATH", "Cookies/auth.json")


def _twitter_fetch_mode():
    """Env TWITTER_FETCH_MODE wins; else Config.TWITTER_FETCH_MODE; default rss."""
    env = os.getenv("TWITTER_FETCH_MODE")
    if env is not None and str(env).strip():
        return str(env).strip().lower()
    try:
        from config import Config

        return str(getattr(Config, "TWITTER_FETCH_MODE", "rss")).strip().lower()
    except Exception:
        return "rss"


def _extract_cookie_values(cookie_payload):
    if isinstance(cookie_payload, dict):
        if cookie_payload.get("auth_token") or cookie_payload.get("ct0"):
            return cookie_payload
        if isinstance(cookie_payload.get("cookies"), list):
            cookie_payload = cookie_payload["cookies"]

    if isinstance(cookie_payload, list):
        values = {}
        for item in cookie_payload:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("Name")
            value = item.get("value") or item.get("Value")
            if not name or value is None:
                continue
            if name in ("auth_token", "ct0"):
                values[name] = value
        return values

    return {}


class _DummyTransaction:
    home_page_response = True

    def generate_transaction_id(self, *args, **kwargs):
        return ""


def _build_client(skip_transaction: bool = False):
    class PatchedClientTransaction(tx.ClientTransaction):
        async def get_indices(self, home_page_response, session, headers):
            key_byte_indices = []
            response = self.validate_response(home_page_response) or self.home_page_response
            text = str(response)

            on_demand_file = tx.ON_DEMAND_FILE_REGEX.search(text)
            candidate_urls = []
            if on_demand_file:
                hash_val = on_demand_file.group(1)
                candidate_urls.extend([
                    f"https://abs.twimg.com/responsive-web/client-web/ondemand.s.{hash_val}a.js",
                    f"https://abs.twimg.com/responsive-web/client-web/ondemand.s.{hash_val}.js",
                    f"https://abs.twimg.com/responsive-web/client-web/ondemand.s.{hash_val}b.js",
                ])

            # Fallback: scan for full ondemand filename patterns.
            if not candidate_urls:
                for match in re.findall(r"ondemand\\.s\\.[\\w-]+\\.js", text):
                    candidate_urls.append(
                        f"https://abs.twimg.com/responsive-web/client-web/{match}"
                    )

            for url in candidate_urls:
                try:
                    resp = await session.request(method="GET", url=url, headers=headers)
                except Exception:
                    continue
                key_byte_indices_match = tx.INDICES_REGEX.finditer(str(resp.text))
                for item in key_byte_indices_match:
                    key_byte_indices.append(item.group(2))
                if key_byte_indices:
                    break

            if not key_byte_indices:
                # Fallback to legacy-safe indices to keep transaction generation working.
                # This is best-effort and may break if X changes the algorithm again.
                return 2, [12, 14, 7]

            key_byte_indices = list(map(int, key_byte_indices))
            return key_byte_indices[0], key_byte_indices[1:]

    class PatchedClient(Client):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if skip_transaction:
                self.client_transaction = _DummyTransaction()
            else:
                self.client_transaction = PatchedClientTransaction()

    client = PatchedClient(language="en-US")
    cookie_path = _cookie_path()
    if not os.path.exists(cookie_path):
        raise ValueError(
            "Twikit cookie file not found. Create it with auth_token and ct0, "
            f"or set TWIKIT_COOKIE_PATH. Missing: {cookie_path}"
        )
    with open(cookie_path, "r", encoding="utf-8") as fp:
        cookies = json.load(fp)
    cookie_values = _extract_cookie_values(cookies)
    if not isinstance(cookie_values, dict) or not cookie_values.get("auth_token") or not cookie_values.get("ct0"):
        raise ValueError(
            "Twikit cookies invalid. Provide auth_token and ct0 in JSON "
            "(or a cookie export list with name/value entries)."
        )
    if len(str(cookie_values.get("ct0", ""))) < 16:
        raise ValueError("Twikit ct0 cookie looks invalid. Re-export it from a logged-in session.")
    client.set_cookies(cookie_values, clear_cookies=True)
    return client


def _normalize_tweet(tweet, search_query, region, tweet_type):
    user = _safe_getattr(tweet, "user")
    screen_name = _safe_getattr(user, "screen_name", "")
    name = _safe_getattr(user, "name", "")
    tweet_id = str(_safe_getattr(tweet, "id", ""))

    return {
        "id": tweet_id,
        "text": _safe_getattr(tweet, "text", ""),
        "date": parse_twitter_date(_safe_getattr(tweet, "created_at")),
        "created_at": _safe_getattr(tweet, "created_at"),
        "likes": int(_safe_getattr(tweet, "favorite_count", 0) or 0),
        "retweets": int(_safe_getattr(tweet, "retweet_count", 0) or 0),
        "replies": int(_safe_getattr(tweet, "reply_count", 0) or 0),
        "views": int(_safe_getattr(tweet, "view_count", 0) or 0),
        "language": _safe_getattr(tweet, "lang", ""),
        "screen_name": screen_name,
        "name": name,
        "profile_url": f"https://twitter.com/{screen_name}" if screen_name else "",
        "tweet_url": (
            f"https://twitter.com/{screen_name}/status/{tweet_id}"
            if screen_name and tweet_id
            else ""
        ),
        "query": search_query,
        "region": region or "",
        "type": tweet_type,
    }


def _fetch_snscrape_tweets(search_query: str, limit: int):
    if not _SNSCRAPE_AVAILABLE:
        raise RuntimeError("snscrape is not installed.")
    rows = []
    seen_ids = set()
    for tweet in sntwitter.TwitterSearchScraper(search_query).get_items():
        tweet_id = str(getattr(tweet, "id", ""))
        if not tweet_id or tweet_id in seen_ids:
            continue
        seen_ids.add(tweet_id)
        user = getattr(tweet, "user", None)
        screen_name = getattr(user, "username", "") if user else ""
        name = getattr(user, "displayname", "") if user else ""
        rows.append({
            "id": tweet_id,
            "text": getattr(tweet, "content", ""),
            "date": parse_twitter_date(getattr(tweet, "date", "")),
            "created_at": getattr(tweet, "date", ""),
            "likes": int(getattr(tweet, "likeCount", 0) or 0),
            "retweets": int(getattr(tweet, "retweetCount", 0) or 0),
            "replies": int(getattr(tweet, "replyCount", 0) or 0),
            "views": int(getattr(tweet, "viewCount", 0) or 0),
            "language": getattr(tweet, "lang", ""),
            "screen_name": screen_name,
            "name": name,
            "profile_url": f"https://twitter.com/{screen_name}" if screen_name else "",
            "tweet_url": f"https://twitter.com/{screen_name}/status/{tweet_id}" if screen_name else "",
            "query": search_query,
            "region": "",
            "type": "tweet",
        })
        if len(rows) >= limit:
            break
    rows.sort(key=lambda item: str(item.get("date", "")), reverse=True)
    return rows[:limit]


def _get_nitter_instances():
    raw = os.getenv(
        "NITTER_INSTANCES",
        "https://nitter.net,https://nitter.it,https://nitter.lacontrevoie.fr,"
        "https://nitter.privacydev.net,https://nitter.poast.org"
    )
    instances = [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]
    if not instances:
        instances = ["https://nitter.net"]
    random.shuffle(instances)
    return instances


def _get_news_rss_feeds():
    raw = os.getenv(
        "NEWS_RSS_FEEDS",
        "https://reliefweb.int/updates/rss.xml"
    )
    feeds = [item.strip() for item in raw.split(",") if item.strip()]
    return feeds


def _parse_nitter_rss(xml_text: str, search_query: str, limit: int):
    try:
        root = ET.fromstring(xml_text)
        items = root.findall(".//item")
    except ET.ParseError:
        soup = BeautifulSoup(xml_text, "xml")
        items = soup.find_all("item")
    rows = []
    for item in items:
        if hasattr(item, "findtext"):
            title = item.findtext("title") or ""
            link = item.findtext("link") or ""
            pub_date = item.findtext("pubDate") or ""
            desc = item.findtext("description") or ""
        else:
            title = (item.find("title") or {}).get_text() if item.find("title") else ""
            link = (item.find("link") or {}).get_text() if item.find("link") else ""
            pub_date = (item.find("pubDate") or {}).get_text() if item.find("pubDate") else ""
            desc = (item.find("description") or {}).get_text() if item.find("description") else ""

        screen_name = ""
        tweet_id = ""
        if link:
            # https://nitter.net/{user}/status/{id}
            parts = link.split("/")
            try:
                tweet_id = parts[-1]
                idx = parts.index("status")
                screen_name = parts[idx - 1] if idx > 0 else ""
            except ValueError:
                pass

        text = title or desc
        rows.append({
            "id": tweet_id,
            "text": text,
            "date": pub_date,
            "created_at": pub_date,
            "likes": 0,
            "retweets": 0,
            "replies": 0,
            "views": 0,
            "language": "",
            "screen_name": screen_name,
            "name": "",
            "profile_url": f"https://twitter.com/{screen_name}" if screen_name else "",
            "tweet_url": f"https://twitter.com/{screen_name}/status/{tweet_id}" if screen_name and tweet_id else "",
            "query": search_query,
            "region": "",
            "type": "tweet",
        })
        if len(rows) >= limit:
            break
    return rows[:limit]


def _extract_query_terms(query: str):
    cleaned = re.sub(r"\blang:\w+\b", "", query or "", flags=re.IGNORECASE)
    cleaned = cleaned.replace("\"", " ")
    parts = [p.strip() for p in cleaned.split("OR")]
    terms = []
    for part in parts:
        if not part:
            continue
        terms.extend([t for t in part.split() if t])
        if " " in part:
            terms.append(part)
    return sorted(set(t.lower() for t in terms if t))


def _parse_rss_items(xml_text: str):
    try:
        root = ET.fromstring(xml_text)
        items = root.findall(".//item")
        def _get_text(item, tag):
            return item.findtext(tag) or ""
    except ET.ParseError:
        soup = BeautifulSoup(xml_text, "xml")
        items = soup.find_all("item")
        def _get_text(item, tag):
            node = item.find(tag)
            return node.get_text() if node else ""
    for item in items:
        yield {
            "title": _get_text(item, "title"),
            "link": _get_text(item, "link"),
            "pubDate": _get_text(item, "pubDate") or _get_text(item, "published"),
            "description": _get_text(item, "description") or _get_text(item, "summary"),
        }


def _fetch_news_rss(search_query: str, limit: int):
    if not _REQUESTS_AVAILABLE:
        raise RuntimeError("requests is not installed.")
    feeds = _get_news_rss_feeds()
    if not feeds:
        raise RuntimeError("No NEWS_RSS_FEEDS configured.")

    terms = _extract_query_terms(search_query)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36",
        "Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    def _collect_items(apply_filter: bool):
        collected = []
        seen = set()
        for feed in feeds:
            try:
                resp = requests.get(feed, timeout=12, headers=headers)
                if resp.status_code != 200:
                    continue
                for item in _parse_rss_items(resp.text):
                    title = item.get("title", "")
                    desc = item.get("description", "")
                    hay = f"{title} {desc}".lower()
                    if apply_filter and terms and not any(t in hay for t in terms):
                        continue
                    link = item.get("link", "")
                    if link and link in seen:
                        continue
                    seen.add(link)
                    collected.append({
                        "id": link or title,
                        "text": title or desc,
                        "date": item.get("pubDate", ""),
                        "created_at": item.get("pubDate", ""),
                        "likes": 0,
                        "retweets": 0,
                        "replies": 0,
                        "views": 0,
                        "language": "",
                        "screen_name": "",
                        "name": "",
                        "profile_url": "",
                        "tweet_url": link,
                        "query": search_query,
                        "region": "",
                        "type": "news",
                    })
                    if len(collected) >= limit:
                        break
                if len(collected) >= limit:
                    break
            except Exception:
                continue
        return collected[:limit]

    rows = _collect_items(apply_filter=True)
    if not rows:
        rows = _collect_items(apply_filter=False)
    return rows[:limit]


def _fetch_nitter_rss(search_query: str, limit: int):
    if not _REQUESTS_AVAILABLE:
        raise RuntimeError("requests is not installed.")
    def _simplify_query(q: str):
        q = re.sub(r"\blang:\w+\b", "", q, flags=re.IGNORECASE).strip()
        q = re.sub(r"\s+", " ", q)
        return q

    instances = _get_nitter_instances()
    encoded = urllib.parse.quote(search_query)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36",
        "Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    last_error = None
    for base in instances:
        try:
            url = f"{base}/search/rss?f=tweets&q={encoded}"
            resp = requests.get(url, timeout=12, headers=headers)
            if resp.status_code != 200:
                last_error = f"{base} returned {resp.status_code}"
            else:
                rows = _parse_nitter_rss(resp.text, search_query, limit)
                if rows:
                    return rows

            # Retry via Jina AI proxy to bypass instance blocks.
            proxy_url = f"https://r.jina.ai/http://{base.replace('https://', '').replace('http://', '')}/search/rss?f=tweets&q={encoded}"
            resp = requests.get(proxy_url, timeout=12, headers=headers)
            if resp.status_code == 200:
                rows = _parse_nitter_rss(resp.text, search_query, limit)
                if rows:
                    return rows
            # Retry with simplified query (Nitter often ignores lang: filters).
            simplified = _simplify_query(search_query)
            if simplified and simplified != search_query:
                url = f"{base}/search/rss?f=tweets&q={urllib.parse.quote(simplified)}"
                resp = requests.get(url, timeout=12, headers=headers)
                if resp.status_code == 200:
                    rows = _parse_nitter_rss(resp.text, simplified, limit)
                    if rows:
                        return rows
                proxy_url = f"https://r.jina.ai/http://{base.replace('https://', '').replace('http://', '')}/search/rss?f=tweets&q={urllib.parse.quote(simplified)}"
                resp = requests.get(proxy_url, timeout=12, headers=headers)
                if resp.status_code == 200:
                    rows = _parse_nitter_rss(resp.text, simplified, limit)
                    if rows:
                        return rows
        except Exception as exc:
            last_error = str(exc)
            continue
    raise RuntimeError(f"Nitter RSS failed: {last_error or 'unknown error'}")


async def _twikit_search_tweets(client, search_query: str, limit: int):
    """
    Try multiple search tabs; X/Twikit often 404s on one product when GraphQL drifts.
    """
    cap = max(10, min(int(limit), 100))
    last = None
    for product in ("Latest", "Top"):
        try:
            return await client.search_tweet(search_query, product=product, count=cap)
        except Exception as exc:
            last = exc
            continue
    raise RuntimeError(
        f"Twikit search failed (Latest and Top): {last!s}. "
        "Try: pip install -U twikit, refresh Cookies/auth.json, or set TWITTER_FETCH_MODE=rss."
    ) from last


def _twikit_fallback_allowed():
    if os.getenv("TWIKIT_NO_FALLBACK", "").strip().lower() in ("1", "true", "yes"):
        return False
    return True


async def fetch_disaster_tweets(
    query: Optional[str] = None,
    region: Optional[str] = None,
    limit: int = 50,
    include_replies: bool = False,
    language: str = "en",
    terms: Optional[Iterable[str]] = None,
):
    # RSS-only mode to avoid blocked X endpoints.
    try:
        search_query = build_disaster_query(query=query, terms=terms, region=region, language=language)
    except Exception:
        search_query = (query or "").strip()
    if not search_query:
        search_query = build_disaster_query(query=None, terms=terms, region=region, language=language)

    # rss | news | reliefweb → ReliefWeb-style RSS (no X login). twikit → live search via Cookies/auth.json
    mode = _twitter_fetch_mode()
    if mode in ("rss", "news", "reliefweb"):
        return _fetch_news_rss(search_query, limit)

    client = _build_client()
    try:
        tweets = await _twikit_search_tweets(client, search_query, limit)
    except Exception as tw_err:
        if not _twikit_fallback_allowed():
            raise
        print(f"[twitter_ingestion] Twikit search error, using fallbacks: {tw_err}")
        try:
            rows_fb = _fetch_nitter_rss(search_query, limit)
            if rows_fb:
                return rows_fb
        except Exception as nit_err:
            print(f"[twitter_ingestion] Nitter fallback failed: {nit_err}")
        return _fetch_news_rss(search_query, limit)

    rows = []
    seen_ids = set()

    for tweet in tweets:
        tweet_id = str(_safe_getattr(tweet, "id", ""))
        if not tweet_id or tweet_id in seen_ids:
            continue

        seen_ids.add(tweet_id)
        rows.append(_normalize_tweet(tweet, search_query, region, "tweet"))

        if include_replies:
            try:
                replies = await client.search_tweet(
                    f"conversation_id:{_safe_getattr(tweet, 'conversation_id')}",
                    product="Latest",
                    count=5,
                )
                for reply in replies:
                    reply_id = str(_safe_getattr(reply, "id", ""))
                    if not reply_id or reply_id in seen_ids:
                        continue
                    seen_ids.add(reply_id)
                    rows.append(_normalize_tweet(reply, search_query, region, "reply"))
            except Exception:
                pass

        if len(rows) >= limit:
            break

    rows.sort(key=lambda item: str(item.get("date", "")), reverse=True)
    return rows[:limit]


def fetch_disaster_tweets_sync(
    query: Optional[str] = None,
    region: Optional[str] = None,
    limit: int = 50,
    include_replies: bool = False,
    language: str = "en",
    terms: Optional[Iterable[str]] = None,
):
    return asyncio.run(
        fetch_disaster_tweets(
            query=query,
            region=region,
            limit=limit,
            include_replies=include_replies,
            language=language,
            terms=terms,
        )
    )


def fetch_recent_tweets(query, max_results=10, bearer_token=None, retries=3):
    # Compatibility wrapper used by app.py
    del bearer_token, retries
    limit = max(1, int(max_results))
    rows = fetch_disaster_tweets_sync(query=query, limit=limit, include_replies=False, language="en")
    return [
        {
            "text": row.get("text", ""),
            "source": "news" if row.get("type") == "news" else "twitter",
            "tweet_id": row.get("id"),
            "created_at": row.get("date"),
            "author_id": None,
            "lang": row.get("language", ""),
            "tweet_url": row.get("tweet_url", ""),
            "type": row.get("type", "tweet"),
            "metrics": {
                "like_count": row.get("likes", 0),
                "retweet_count": row.get("retweets", 0),
                "reply_count": row.get("replies", 0),
                "impression_count": row.get("views", 0),
            },
        }
        for row in rows
    ]


async def fetch_user_data(username, limit=30):
    client = _build_client()
    user = await client.get_user_by_screen_name(username)
    tweets = await user.get_tweets("Tweets", count=limit)

    user_info = {
        "name": user.name,
        "screen_name": user.screen_name,
        "followers_count": user.followers_count,
        "friends_count": user.following_count,
        "statuses_count": user.statuses_count,
        "is_blue_verified": user.is_blue_verified,
        "description": user.description,
        "profile_image_url": user.profile_image_url.replace("_normal", "") if user.profile_image_url else "",
    }

    tweet_list = []
    for tweet in tweets:
        tweet_list.append(
            {
                "id": tweet.id,
                "text": tweet.text,
                "favorite_count": tweet.favorite_count,
                "retweet_count": tweet.retweet_count,
                "date": parse_twitter_date(tweet.created_at),
                "created_at": tweet.created_at,
            }
        )

    return user_info, tweet_list
