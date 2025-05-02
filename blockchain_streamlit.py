import streamlit as st
from pymongo import MongoClient
import hashlib
import time
import json
import secrets
import pandas as pd
import qrcode
from pyzbar.pyzbar import decode
from io import BytesIO
from PIL import Image
from datetime import datetime, timedelta, timezone

# MongoDB 연결
#MONGO_URL = "mongodb+srv://XperChain:XperChain2121@db.leubgkp.mongodb.net/blockchain_db?retryWrites=true&w=majority&appName=db"

# [mongodb]
# uri = "mongodb+srv://XperChain:XperChain2121@db.leubgkp.mongodb.net/blockchain_db?retryWrites=true&w=majority&appName=db"
MONGO_URL = st.secrets["mongodb"]["uri"]

client = MongoClient(MONGO_URL)
db = client["blockchain_db"]
blocks = db["blocks"]
tx_pool = db["transactions"]
users = db["users"]

# 해시 함수
def hash_block(block):
    block_string = json.dumps(block, sort_keys=True).encode()
    return hashlib.sha256(block_string).hexdigest()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def sign_transaction(private_key, tx_data):
    tx_string = json.dumps(tx_data, sort_keys=True)
    return hashlib.sha256((tx_string + private_key).encode()).hexdigest()

def create_block(transactions, previous_hash="0"):
    block = {
        "index": blocks.count_documents({}) + 1,
        "timestamp": time.time(),
        "transactions": transactions,
        "previous_hash": previous_hash
    }
    block["hash"] = hash_block(block)
    return block

def generate_wallet():
    private_key = secrets.token_hex(16)
    public_key = hashlib.sha256(private_key.encode()).hexdigest()
    return public_key, private_key

def get_balance(address):
    balance = 0.0
    for block in blocks.find():
        for tx in block["transactions"]:
            if tx["recipient"] == address:
                balance += tx["amount"]
            if tx["sender"] == address and tx["sender"] != "SYSTEM":
                balance -= tx["amount"]
    return balance

def get_last_reward_time(public_key):
    tx = db["blocks"].find_one(
        {
            "transactions": {
                "$elemMatch": {
                    "sender": "SYSTEM",
                    "recipient": public_key
                }
            }
        },
        sort=[("timestamp", -1)]
    )
    if tx:
        for t in tx["transactions"]:
            if t["sender"] == "SYSTEM" and t["recipient"] == public_key:
                return datetime.fromtimestamp(t["timestamp"])
    return None

# 초기 상태
if "logged_in_user" not in st.session_state:
    st.session_state["logged_in_user"] = None
if "balance" not in st.session_state:
    st.session_state["balance"] = 0.0

# 로그인 및 회원가입
if not st.session_state["logged_in_user"]:
    with st.expander("로그인", expanded=True):

        # 이전 모드 기억용 변수
        if "auth_mode_last" not in st.session_state:
            st.session_state["auth_mode_last"] = "로그인"

        auth_mode = st.radio("", ["로그인", "회원가입"], horizontal=True, key="auth_mode")

        # 모드가 바뀌면 입력 필드 초기화
        if auth_mode != st.session_state["auth_mode_last"]:
            st.session_state["auth_mode_last"] = auth_mode
            st.session_state["username"] = ""
            st.session_state["password"] = ""

        # 입력 필드 with 세션 상태 연결
        username = st.text_input("👤 사용자명", key="username")
        password = st.text_input("🔑 비밀번호", type="password", key="password")

        if auth_mode == "회원가입":
            if st.button("✅ 회원가입"):
                if username == "" or password == "":
                    st.warning("모든 필드를 입력하세요.")
                elif users.find_one({"username": username}):
                    st.error("이미 존재하는 사용자입니다.")
                else:
                    pub, priv = generate_wallet()
                    users.insert_one({
                        "username": username,
                        "password_hash": hash_password(password),
                        "public_key": pub,
                        "private_key": priv
                    })
                    st.success("🎉 회원가입 성공! 이제 로그인 해보세요.")

        elif auth_mode == "로그인":
            if st.button("🔓 로그인"):
                user = users.find_one({"username": username})
                if not user or user["password_hash"] != hash_password(password):
                    st.error("❌ 사용자명 또는 비밀번호가 틀렸습니다.")
                else:
                    st.session_state["logged_in_user"] = user
                    st.session_state["balance"] = get_balance(user["public_key"])
                    st.success(f"환영합니다, {username}님!")
                    st.rerun()

if not st.session_state["logged_in_user"]:
    st.stop()

# 사용자 세션 정보
user = st.session_state["logged_in_user"]
public_key = user["public_key"]
private_key = user["private_key"]
st.session_state["public_key_input"] = public_key
st.session_state["private_key_input"] = private_key

with st.expander("📂 내 지갑 정보", expanded=True):  # 기본 펼쳐짐
    st.markdown(f"🪪 사용자: `{user['username']}`")

    # QR 생성 상태 관리
    if "qr_generated" not in st.session_state:
        st.session_state["qr_generated"] = False

    col1, col2 = st.columns([4, 1], gap="small")

    with col1:
        st.success(f"지갑 주소: {st.session_state['public_key_input']}")

    with col2:
        if not st.session_state["qr_generated"]:
            if st.button("📤 QR 생성", key="generate_qr_btn"):
                st.session_state["qr_generated"] = True
                st.rerun()

        if st.session_state["qr_generated"]:
            qr_img = qrcode.make(st.session_state['public_key_input'])
            buf = BytesIO()
            qr_img.save(buf, format="PNG")
            st.image(buf.getvalue(), width=80)

    # 잔고 표시
    st.success(f"💰 현재 잔고: {st.session_state['balance']:.2f} 코인")

    # 로그아웃 및 Air drop 버튼
    col1, col2 = st.columns([1, 2], gap="small")

    with col1:
        if st.button("🚪 로그아웃", key="logout_btn"):
            st.session_state["logged_in_user"] = None
            st.rerun()

    with col2:
        reward_eligible = True
        last_reward_time = get_last_reward_time(public_key)
        now = datetime.now()
        if last_reward_time:
            elapsed = now - last_reward_time
            if elapsed < timedelta(hours=24):
                remaining = timedelta(hours=24) - elapsed
                st.info(f"⏳ 다음 Air drop 보상까지 남은 시간: {str(remaining).split('.')[0]}")
                reward_eligible = False

        if reward_eligible:
            if st.button("🆕 Air drop 보상", key="airdrop_btn"):
                coinbase_tx = {
                    "sender": "SYSTEM",
                    "recipient": public_key,
                    "amount": 100.0,
                    "timestamp": time.time(),
                    "signature": "coinbase"
                }
                last_block = blocks.find_one(sort=[("index", -1)])
                prev_hash = last_block["hash"] if last_block else "0"
                new_block = create_block([coinbase_tx], previous_hash=prev_hash)
                blocks.insert_one(new_block)
                st.session_state["balance"] = get_balance(public_key)
                st.success("🎉 100 코인이 지급되었습니다!")
        else:
            st.button("🆕 Air drop 보상", disabled=True, key="airdrop_disabled_btn")

# 트랜잭션
# QR 스캔 상태 초기화
if "qr_scan_requested" not in st.session_state:
    st.session_state["qr_scan_requested"] = False
if "recipient_scanned" not in st.session_state:
    st.session_state["recipient_scanned"] = ""

with st.expander("📤 트랜잭션 전송", expanded=True):
    col1, col2 = st.columns([4, 1], gap="small")

    with col1:
        recipient = st.text_input("📨 받는 사람 공개키", value=st.session_state.get("recipient_scanned", ""), key="recipient_input")

    with col2:
        st.write("")
        st.write("")
        if st.button("📷 QR 스캔", key="qr_scan_btn"):
            st.session_state["qr_scan_requested"] = True

    # QR 스캔 후 카메라 표시
    if st.session_state.get("qr_scan_requested", False):
        image_file = st.camera_input("📸 QR 코드를 카메라로 스캔하세요")
        if image_file:
            image = Image.open(image_file)
            image_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            result = decode(image_cv)
            if result:
                qr_data = result[0].data.decode("utf-8")
                st.session_state["recipient_scanned"] = qr_data
                st.session_state["qr_scan_requested"] = False
                st.success("✅ QR 코드 인식 성공!")
                st.rerun()
            else:
                st.error("❌ QR 코드 인식에 실패했습니다.")

    # 이체 금액 입력
    amount = st.number_input("💸 이체 금액", min_value=0.0, key="amount_input")
    
    col1, col2 = st.columns([1, 2], gap="small")
    with col1:
        # 트랜잭션 전송 버튼
        if st.button("➕ 트랜잭션 전송"):
            recipient_value = st.session_state["recipient_input"]
            amount_value = st.session_state["amount_input"]

            if recipient_value.strip() == "" or amount_value <= 0:
                st.warning("모든 필드를 입력하세요.")
            elif amount_value > st.session_state["balance"]:
                st.error("❌ 잔고 부족")
            else:
                tx_data = {
                    "sender": public_key,
                    "recipient": recipient_value,
                    "amount": amount_value,
                    "timestamp": time.time()
                }
                tx_data["signature"] = sign_transaction(private_key, tx_data)
                tx_pool.insert_one(tx_data)
                st.success("✅ 트랜잭션이 추가되었습니다.")

                # 세션 상태를 직접 초기화하지 않고 rerun으로 리셋 유도
                st.rerun()
    with col2:
        if st.button("🧱 블록 생성"):
            tx_list_raw = list(tx_pool.find())
            if not tx_list_raw:
                st.warning("⛔ 트랜잭션이 없습니다.")
            else:
                last_block = blocks.find_one(sort=[("index", -1)])
                prev_hash = last_block["hash"] if last_block else "0"

                valid_txs = []
                invalid_txs = []  # ❗ 제외된 트랜잭션 저장
                temp_balances = {}

                for tx in tx_list_raw:
                    tx.pop("_id", None)
                    sender = tx["sender"]
                    recipient = tx["recipient"]
                    amount = tx["amount"]

                    if sender == "SYSTEM":
                        valid_txs.append(tx)
                        temp_balances[recipient] = temp_balances.get(recipient, get_balance(recipient)) + amount
                    else:
                        temp_balances[sender] = temp_balances.get(sender, get_balance(sender))
                        if temp_balances[sender] >= amount:
                            valid_txs.append(tx)
                            temp_balances[sender] -= amount
                            temp_balances[recipient] = temp_balances.get(recipient, get_balance(recipient)) + amount
                        else:
                            invalid_txs.append(tx)  # ❗잔고 부족으로 제외
                            st.warning(f"❌ 제외됨: `{sender[:10]}...` 잔고 부족 (보내려는 금액: {amount})")

                if not valid_txs:
                    st.error("❌ 유효한 트랜잭션이 없습니다.")
                else:
                    new_block = create_block(valid_txs, previous_hash=prev_hash)
                    blocks.insert_one(new_block)

                    # ✅ 유효한 트랜잭션 삭제
                    for tx in valid_txs:
                        tx_pool.delete_one({
                            "sender": tx["sender"],
                            "recipient": tx["recipient"],
                            "amount": tx["amount"],
                            "timestamp": tx["timestamp"],
                            "signature": tx["signature"]
                        })

                    # ✅ 잔고 부족한 트랜잭션도 삭제
                    for tx in invalid_txs:
                        tx_pool.delete_one({
                            "sender": tx["sender"],
                            "recipient": tx["recipient"],
                            "amount": tx["amount"],
                            "timestamp": tx["timestamp"],
                            "signature": tx["signature"]
                        })

                    st.success(f"✅ 블록 #{new_block['index']} 생성 완료! 포함된 트랜잭션 수: {len(valid_txs)}")

                    # 잔고 갱신
                    st.session_state["balance"] = get_balance(public_key)  

                    st.rerun()

KST = timezone(timedelta(hours=9))  # 한국 시간대 설정

# 📥 트랜잭션 풀 보기
with st.expander("📥 현재 트랜잭션 풀", expanded=True):
    txs = list(tx_pool.find())

    if txs:
        table_data = []
        for tx in txs:
            table_data.append({
                "보낸 사람": tx["sender"][:5] + "..." if tx.get("sender") else "",
                "받는 사람": tx["recipient"][:5] + "..." if tx.get("recipient") else "",
                "금액": tx.get("amount", 0),
                "서명": tx["signature"][:5] + "..." if tx.get("signature") else "",
                "시간": datetime.fromtimestamp(tx["timestamp"], tz=KST).strftime('%Y-%m-%d %H:%M:%S')
            })

        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("트랜잭션 풀이 비어 있습니다.")

# ⛓️ 블록체인 보기
with st.expander("⛓️ 블록체인 보기", expanded=False):
    # 📌 최신 블록 번호 가져오기
    latest_block = blocks.find_one(sort=[("index", -1)])
    latest_index = latest_block["index"] if latest_block else 1

    # 🔍 블록 번호 입력 (기본값 = 최신 블록 번호)
    search_index = st.number_input("🔍 블록 번호로 검색", min_value=1, step=1, value=latest_index, format="%d")

    block = blocks.find_one({"index": search_index})
    if block:
        # 📋 블록 정보 표
        block_info = pd.DataFrame({
            "속성": ["블록 번호", "해시", "이전 해시", "생성 시간", "트랜잭션 수"],
            "값": [
                block.get("index"),
                block.get("hash", "")[:10] + "...",
                block.get("previous_hash", "")[:10] + "...",
                datetime.fromtimestamp(block.get("timestamp", time.time()), tz=KST).strftime('%Y-%m-%d %H:%M:%S'),
                len(block.get("transactions", []))
            ]
        })

        st.markdown("#### 📋 블록 정보")
        st.dataframe(block_info, use_container_width=True)

        # 📦 트랜잭션 목록
        transactions = block.get("transactions", [])
        if not transactions:
            st.info("📭 이 블록에는 트랜잭션이 없습니다.")
        else:
            tx_table = []
            for tx in transactions:
                ts = tx.get("timestamp")
                time_str = datetime.fromtimestamp(ts, tz=KST).strftime('%Y-%m-%d %H:%M:%S') if ts else "없음"

                tx_table.append({
                    "보낸 사람": tx.get("sender", "")[:5] + "...",
                    "받는 사람": tx.get("recipient", "")[:5] + "...",
                    "금액": tx.get("amount", 0),
                    "서명": tx.get("signature", "")[:5] + "...",
                    "시간": time_str
                })

            st.markdown("#### 📦 트랜잭션 목록")
            st.dataframe(pd.DataFrame(tx_table), use_container_width=True)

    else:
        st.info("❗ 해당 번호의 블록을 찾을 수 없습니다.")

