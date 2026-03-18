import re
import json
import urllib.request
import urllib.error
from flask import Flask, request, jsonify

app = Flask(__name__)

BASE_URL = "https://api.datadive.tools/v1"

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
}


def parse_query(query: str) -> tuple[str, dict]:
    """
    Parse natural language query (Russian or English) into a DataDive endpoint path.
    Returns (path, params).
    """
    q = query.lower().strip()

    # Extract numeric or UUID-style ID from the query
    id_match = re.search(r'\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[a-f0-9]{16,}|\d+)\b', query, re.IGNORECASE)
    niche_id = id_match.group(1) if id_match else None

    # Rank radar ID — look for ID after "radar" keyword specifically
    radar_match = re.search(r'radar\D{0,10}([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[a-f0-9]{16,}|\d+)', query, re.IGNORECASE)
    radar_id = radar_match.group(1) if radar_match else None

    # ── Routing by keyword priority ───────────────────────────────────────────

    # Keyword roots / корни ключевых слов
    if any(x in q for x in ['root', 'корн', 'корень']):
        if niche_id:
            return f"/niches/{niche_id}/roots", {}
        return "/niches", {"_hint": "missing_niche_id"}

    # Ranking juice
    if any(x in q for x in ['juice', 'ранкинг', 'ranking juice', 'джус']):
        if niche_id:
            return f"/niches/{niche_id}/ranking-juices", {}
        return "/niches", {"_hint": "missing_niche_id"}

    # Competitors / конкуренты
    if any(x in q for x in ['competitor', 'конкурент']):
        if niche_id:
            return f"/niches/{niche_id}/competitors", {}
        return "/niches", {"_hint": "missing_niche_id"}

    # Keywords / ключевые слова
    if any(x in q for x in ['keyword', 'ключев']):
        if niche_id:
            return f"/niches/{niche_id}/keywords", {}
        return "/niches", {"_hint": "missing_niche_id"}

    # Rank radar — specific tracker
    if radar_id:
        return f"/niches/rank-radars/{radar_id}", {}

    # Rank radar — list trackers
    if any(x in q for x in ['rank radar', 'радар', 'tracker', 'трекер', 'radar']):
        return "/niches/rank-radars", {}

    # Default — list niches
    return "/niches", {}


def datadive_get(path: str, api_key: str) -> dict:
    url = BASE_URL + path
    req = urllib.request.Request(
        url,
        headers={
            "x-api-key": api_key,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


@app.route("/", methods=["GET"])
def health():
    return "DataDive Explorer — OK"


@app.route("/api/datadive", methods=["OPTIONS"])
def options():
    resp = jsonify({})
    for k, v in CORS_HEADERS.items():
        resp.headers[k] = v
    return resp


@app.route("/api/datadive", methods=["POST"])
def query_endpoint():
    body = request.get_json(force=True, silent=True) or {}
    api_key = (body.get("api_key") or "").strip()
    query = (body.get("query") or "").strip()

    if not api_key:
        resp = jsonify({"error": "API ключ обязателен / API key is required"})
        resp.status_code = 400
        for k, v in CORS_HEADERS.items():
            resp.headers[k] = v
        return resp

    if not query:
        resp = jsonify({"error": "Запрос обязателен / Query is required"})
        resp.status_code = 400
        for k, v in CORS_HEADERS.items():
            resp.headers[k] = v
        return resp

    path, params = parse_query(query)
    hint = params.pop("_hint", None)

    # If we need a niche_id but don't have one, return list of niches with a hint
    hint_message = None
    if hint == "missing_niche_id":
        hint_message = (
            "ID ниши не найден в запросе. Ниже список ваших ниш — "
            "укажите ID нужной в следующем запросе."
        )
        path = "/niches"

    try:
        data = datadive_get(path, api_key)
    except urllib.error.HTTPError as e:
        status_code = e.code
        try:
            detail = e.read().decode()
        except Exception:
            detail = str(e)
        resp = jsonify({
            "error": f"DataDive API вернул ошибку {status_code}",
            "detail": detail,
        })
        resp.status_code = status_code if status_code in (400, 401, 403, 404, 429) else 502
        for k, v in CORS_HEADERS.items():
            resp.headers[k] = v
        return resp
    except urllib.error.URLError as e:
        resp = jsonify({"error": f"Ошибка сети: {e.reason}"})
        resp.status_code = 502
        for k, v in CORS_HEADERS.items():
            resp.headers[k] = v
        return resp
    except Exception as e:
        resp = jsonify({"error": f"Внутренняя ошибка: {str(e)}"})
        resp.status_code = 500
        for k, v in CORS_HEADERS.items():
            resp.headers[k] = v
        return resp

    result = {
        "endpoint": path,
        "query": query,
        "data": data,
    }
    if hint_message:
        result["hint"] = hint_message

    resp = jsonify(result)
    for k, v in CORS_HEADERS.items():
        resp.headers[k] = v
    return resp
