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


def parse_query(query: str) -> tuple[str, str | None]:
    """
    Parse natural language query into (endpoint_path, hint).
    hint is returned when niche_id is required but not found in the query.
    """
    q = query.lower().strip()

    # Extract any ID-like token from the query
    id_match = re.search(
        r'\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[a-f0-9]{16,}|\d+)\b',
        query,
        re.IGNORECASE,
    )
    niche_id = id_match.group(1) if id_match else None

    radar_match = re.search(
        r'radar\D{0,10}([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[a-f0-9]{16,}|\d+)',
        query,
        re.IGNORECASE,
    )
    radar_id = radar_match.group(1) if radar_match else None

    if any(x in q for x in ['root', 'корн', 'корень']):
        if niche_id:
            return f"/niches/{niche_id}/roots", None
        return "/niches", "missing_niche_id"

    if any(x in q for x in ['juice', 'ранкинг', 'ranking juice', 'джус']):
        if niche_id:
            return f"/niches/{niche_id}/ranking-juices", None
        return "/niches", "missing_niche_id"

    if any(x in q for x in ['competitor', 'конкурент']):
        if niche_id:
            return f"/niches/{niche_id}/competitors", None
        return "/niches", "missing_niche_id"

    if any(x in q for x in ['keyword', 'ключев']):
        if niche_id:
            return f"/niches/{niche_id}/keywords", None
        return "/niches", "missing_niche_id"

    if radar_id:
        return f"/niches/rank-radars/{radar_id}", None

    if any(x in q for x in ['rank radar', 'радар', 'tracker', 'трекер', 'radar']):
        return "/niches/rank-radars", None

    return "/niches", None


def datadive_request(method: str, path: str, api_key: str) -> dict:
    url = BASE_URL + path
    req = urllib.request.Request(
        url,
        method=method,
        headers={"x-api-key": api_key, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def make_error(message: str, status: int = 400):
    resp = jsonify({"error": message})
    resp.status_code = status
    for k, v in CORS_HEADERS.items():
        resp.headers[k] = v
    return resp


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

    if not api_key:
        return make_error("API ключ обязателен")

    # ── Structured call (from action buttons in UI) ───────────────────────────
    action = body.get("action", "").strip()
    niche_id = body.get("niche_id", "").strip()

    ACTION_PATHS = {
        "keywords":       lambda nid: f"/niches/{nid}/keywords",
        "competitors":    lambda nid: f"/niches/{nid}/competitors",
        "ranking-juices": lambda nid: f"/niches/{nid}/ranking-juices",
        "roots":          lambda nid: f"/niches/{nid}/roots",
        "niches":         lambda _:   "/niches",
        "rank-radars":    lambda _:   "/niches/rank-radars",
    }

    if action and action in ACTION_PATHS:
        if action in ("keywords", "competitors", "ranking-juices", "roots") and not niche_id:
            return make_error("niche_id обязателен для этого действия")
        path = ACTION_PATHS[action](niche_id)
        hint = None
        query_label = action
    else:
        # ── Natural language query ─────────────────────────────────────────────
        query = (body.get("query") or "").strip()
        if not query:
            return make_error("Введите запрос или выберите действие")
        path, hint = parse_query(query)
        query_label = query
        if hint == "missing_niche_id":
            path = "/niches"

    try:
        data = datadive_request("GET", path, api_key)
    except urllib.error.HTTPError as e:
        status_code = e.code
        try:
            detail = e.read().decode()
        except Exception:
            detail = str(e)
        resp = jsonify({"error": f"DataDive API ошибка {status_code}", "detail": detail})
        resp.status_code = status_code if status_code in (400, 401, 403, 404, 429) else 502
        for k, v in CORS_HEADERS.items():
            resp.headers[k] = v
        return resp
    except urllib.error.URLError as e:
        return make_error(f"Ошибка сети: {e.reason}", 502)
    except Exception as e:
        return make_error(f"Внутренняя ошибка: {str(e)}", 500)

    result = {
        "endpoint": path,
        "query": query_label,
        "data": data,
        "response_type": action or ("niches" if path == "/niches" else "data"),
    }
    if hint == "missing_niche_id":
        result["hint"] = "ID ниши не найден в запросе. Выберите нишу из списка ниже:"

    resp = jsonify(result)
    for k, v in CORS_HEADERS.items():
        resp.headers[k] = v
    return resp
