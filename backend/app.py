import os
import uuid
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_CHAT_URL = "https://api.deepseek.com/v1/chat/completions"
CHORES_API_BASE = "http://your-chores-api.com/api"  # 请替换为你的实际接口地址

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", str(uuid.uuid4()))
CORS(app, supports_credentials=True)

user_sessions = {}

REQUIRED_FIELDS = [
    "choreName", "icon", "startDay", "repeatsUntil", "dueTime",
    "choreType", "repeats", "memberUids"
]

def get_icons(token):
    resp = requests.get(f"{CHORES_API_BASE}/chores/icon", headers={"token": token})
    return resp.json().get("data", [])

def get_members(token):
    resp = requests.get(f"{CHORES_API_BASE}/chores/memberInfoList", headers={"token": token})
    return resp.json().get("data", [])

def call_deepseek(messages, temperature=0.3):
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "DeepSeek-V3.1",
        "messages": messages,
        "temperature": temperature
    }
    resp = requests.post(DEEPSEEK_CHAT_URL, headers=headers, json=payload)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

@app.route("/api/session", methods=["POST"])
def create_session():
    user_id = str(uuid.uuid4())
    user_sessions[user_id] = {"params": {}, "step": 0, "confirmed": False}
    return jsonify({"session_id": user_id})

@app.route("/api/icons", methods=["GET"])
def api_icons():
    token = request.headers.get("token")
    return jsonify(get_icons(token))

@app.route("/api/members", methods=["GET"])
def api_members():
    token = request.headers.get("token")
    return jsonify(get_members(token))

@app.route("/api/ask", methods=["POST"])
def ask():
    data = request.json
    session_id = data["session_id"]
    user_input = data["message"]
    token = data.get("token", "")
    sess = user_sessions.get(session_id)

    if not sess:
        return jsonify({"error": "Invalid session"}), 400

    params = sess["params"]

    next_field = None
    for f in REQUIRED_FIELDS:
        if f not in params:
            next_field = f
            break
    if not next_field:
        if not sess["confirmed"]:
            if user_input.strip().lower() in ["确认", "yes", "确认创建"]:
                req_body = dict(params)
                if req_body.get("repeatsUntil") == "是" and "endDay" not in req_body:
                    return jsonify({"reply": "请补充结束日期（endDay）"}), 200
                if req_body.get("choreType") == "Rotate" and "rotateEveryCounts" not in req_body:
                    return jsonify({"reply": "请补充每人做几次（rotateEveryCounts）"}), 200
                if req_body.get("repeats") == "是" and "repeatsType" not in req_body:
                    return jsonify({"reply": "请补充家务循环类型（repeatsType）"}), 200
                headers = {"token": token}
                resp = requests.post(f"{CHORES_API_BASE}/chores/create", headers=headers, json=req_body)
                if resp.ok:
                    user_sessions[session_id] = {"params": {}, "step": 0, "confirmed": False}
                    return jsonify({"reply": "家务创建成功！"}), 200
                else:
                    return jsonify({"reply": f"家务创建失败：{resp.text}"}), 200
            else:
                return jsonify({"reply": "如需创建请回复“确认”，如需修改请直接输入需修改的字段。”"}), 200

    params[next_field] = user_input.strip()

    if next_field == "repeatsUntil" and user_input.strip() == "是":
        return jsonify({"reply": "请补充结束日期（endDay）"}), 200
    if next_field == "choreType" and user_input.strip() == "Rotate":
        return jsonify({"reply": "请补充每人做几次（rotateEveryCounts）"}), 200
    if next_field == "repeats" and user_input.strip() == "是":
        return jsonify({"reply": "请补充家务循环类型（repeatsType，daily/weekly）"}), 200

    all_done = all(f in params for f in REQUIRED_FIELDS)
    if all_done:
        sess["confirmed"] = False
        reply = f"请确认以下信息：\n" + "\n".join([f"{k}: {v}" for k, v in params.items()]) + "\n如无误请回复“确认”，如需修改请直接输入需修改的字段。"
    else:
        next_field2 = None
        for f in REQUIRED_FIELDS:
            if f not in params:
                next_field2 = f
                break
        reply = f"请补充{next_field2}："

    user_sessions[session_id] = sess
    return jsonify({"reply": reply}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
