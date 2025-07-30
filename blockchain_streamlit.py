import streamlit as st
from pymongo import MongoClient
import secrets

import hashlib, json
import time
import pandas as pd
from io import BytesIO
from PIL import Image
from datetime import datetime, timedelta, timezone
import cv2
import numpy as np
import qrcode
import base64
from ecdsa import SigningKey, SECP256k1

from blockchain import *
import utils

KST = timezone(timedelta(hours=9))  # KST timezone

# DB 설정
MONGO_URL = st.secrets["mongodb"]["uri"]
MONGO_URL = "mongodb://XperChain:XperChain2121@ac-ejhvamk-shard-00-00.leubgkp.mongodb.net:27017,ac-ejhvamk-shard-00-01.leubgkp.mongodb.net:27017,ac-ejhvamk-shard-00-02.leubgkp.mongodb.net:27017/blockchain_db?tls=true&replicaSet=atlas-q7ilyw-shard-0&authSource=admin&retryWrites=true&w=majority"

client = MongoClient(MONGO_URL)
db = client["blockchain_db"]
blocks = db["blocks"]
transactions = db["transactions"]
transaction_pool = db["transaction_pool"]
users = db["users"]
peers = db['peers']  # p2p network will be implemented

# miner wallet
#miner_wallet = st.secrets["miner"]["public_key"]
#miner_key = st.secrets["miner"]["private_key"]
miner_wallet = '38887c137a1dc54e0f083a98844c36d5f8ca7fd4e5c7ba603067a2fdc117209f003d156d462c59dacdce58c4451ccd6a5a2f2a962fdcfb93a015f09d0fbc9c2d'
miner_key = 'a0410cfe5057443532e61a3b99d28853318a25ed2fd1b6d32b0e8abd94ce32f2'

BLOCK_INTERVAL = 6

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
        username = st.text_input("👤 사용자", key="username")
        password = st.text_input("🔑 비밀번호", type="password", key="password")

        if auth_mode == "회원가입":
            private_key_input = st.text_input("🔐 지갑 개인키(미입력 시 자동 생성)", key="private_key_input")

            if st.button("✅ 회원가입"):
                if username == "" or password == "":
                    st.warning("모든 필드를 입력하세요.")
                elif len(username) < 5:
                    st.warning("사용자 명칭은 최소 5자리 이상이어야 합니다.")
                elif len(password) < 8:
                    st.warning("비밀번호는 최소 8자리 이상이어야 합니다.")
                elif users.find_one({"username": username}):
                    st.error("이미 존재하는 사용자입니다.")
                else:
                    # 개인키 수동 입력 여부 확인
                    if private_key_input.strip():
                        try:
                            sk = SigningKey.from_string(bytes.fromhex(private_key_input), curve=SECP256k1)
                            pub = sk.get_verifying_key().to_string().hex()
                            priv = private_key_input
                        except Exception as e:
                            st.error(f"❌ 개인키 형식 오류: {e}")
                            st.stop()
                    else:
                        # 자동 생성
                        pub, priv = generate_wallet()

                    users.insert_one({
                        "username": username,
                        "password_hash": utils.hash_password(password),
                        "public_key": pub,
                        "private_key": priv
                    })                      
                    st.success("🎉 회원가입 성공! 이제 로그인 해보세요.")                  

        elif auth_mode == "로그인":
            if st.button("🔓 로그인"):
                user = users.find_one({"username": username})
                if not user or user["password_hash"] != utils.hash_password(password):
                    st.error("❌ 사용자 또는 비밀번호가 틀렸습니다.")
                else:                                                          
                    
                    st.session_state["logged_in_user"] = user
                    st.session_state["balance"] = get_balance(user["public_key"], blocks)
                    st.success(f"환영합니다, {username}님!")                    
                    st.rerun()

if not st.session_state["logged_in_user"]:
    st.stop()
    
# 사용자 세션 정보
user = st.session_state["logged_in_user"]
public_key = user["public_key"]
private_key = user["private_key"]

# col_spacer, col_button = st.columns([8, 2])
# with col_button:
#     if st.button("🔄 새로 고침"):
#         st.session_state["clear_inputs"] = True
#         st.session_state["balance"] = get_balance(public_key, blocks)            
#         st.rerun()
    
with st.expander("📂 내 지갑 정보", expanded=True):  # 기본 펼쳐짐
    st.markdown(f"👤 사용자: `{user['username']}`")
    
    
    # QR 생성 상태 관리
    if "qr_generated" not in st.session_state:
        st.session_state["qr_generated"] = False

    col1, col2 = st.columns([3, 1], gap="small")

    with col1:
        st.success(f"🪪 지갑 주소 `{public_key}`")

    with col2:
        if not st.session_state["qr_generated"]:
            if st.button("QR 보기", key="generate_qr_btn"):
                st.session_state["qr_generated"] = True
                st.rerun()

        if st.session_state["qr_generated"]:
            qr_img = qrcode.make(public_key)
            buf = BytesIO()
            qr_img.save(buf, format="PNG")
            st.image(buf.getvalue(), width=300)
    
    # 잔고 표시
    # 잔고 표시 및 새로고침 버튼
    col1, col2 = st.columns([3, 1], gap="small")
    with col1:
        st.success(f"💰 잔고 `{st.session_state['balance']:.2f} XPER`")       
    with col2:
        if st.button("🔄 잔고", key="refresh_balance"):
            st.session_state["balance"] = get_balance(public_key, blocks)   
            
    #st.success(f"💰 잔고 `{st.session_state['balance']:.2f} XPER`")
    
    if st.button("🔒 로그아웃", key="logout_btn"):
        st.session_state["logged_in_user"] = None
        st.rerun()
    
                            

# 트랜잭션
# QR 스캔 상태 초기화
if "qr_scan_requested" not in st.session_state:
    st.session_state["qr_scan_requested"] = False
if "recipient_scanned" not in st.session_state:
    st.session_state["recipient_scanned"] = ""

    
# 초기화용 플래그
if "clear_inputs" not in st.session_state:
    st.session_state["clear_inputs"] = False

recipient_value = "" if st.session_state.clear_inputs else st.session_state.get("recipient_input", "")
amount_value = 0.0 if st.session_state.clear_inputs else st.session_state.get("amount_input", 0.0)

with st.expander("📤 이체", expanded=True):
    col1, col2 = st.columns([4, 1], gap="small")    
    with col1:
        # 입력 필드    
        if st.session_state.get("clear_inputs", False):
            st.session_state["recipient_input"] = ""  # ✅ 입력창 초기화
            st.session_state["clear_inputs"] = False
            
        recipient = st.text_input("📨 받는 지갑 주소", value=recipient_value, key="recipient_input")
        
        
    with col2:
        st.write("")
        st.write("")
        if st.button("📷 QR 스캔", key="qr_scan_btn"):
            st.session_state["qr_scan_requested"] = True

    # QR 스캔
    if st.session_state.get("qr_scan_requested", False):
        if st.button("❌ 스캔 취소", key="cancel_qr_btn"):
            st.session_state["qr_scan_requested"] = False
            st.rerun()
        image_file = st.camera_input("📸 QR 코드를 카메라로 스캔하세요")
        if image_file:
            image = Image.open(image_file).convert("RGB")
            img_np = np.array(image)
            qr_decoder = cv2.QRCodeDetector()
            data, points, _ = qr_decoder.detectAndDecode(img_np)
            if data:
                st.session_state["recipient_scanned"] = data
                st.session_state["qr_scan_requested"] = False
                st.success("✅ QR 코드 인식 성공!")
                st.rerun()
            else:
                st.error("❌ QR 코드 인식에 실패했습니다.")
    amount = st.number_input("💸 금액", min_value=0.0, value=amount_value, key="amount_input")  
    
    st.info(f"💰 수수료: `{transaction_fee:.2f} XPER`")        
    if st.button("➕ 이체하기"):
        recipient_value = st.session_state.get("recipient_input", "")
        amount_value = st.session_state.get("amount_input", 0.0)
        if recipient_value.strip() == "":
            st.warning("받는 지갑의 주소를 입력하세요.")
        elif amount_value <= 0:
            st.warning("이체 금액을 입력하세요.")
        elif amount_value + transaction_fee > st.session_state["balance"]:
            st.error("❌ 잔고 부족(수수료 포함)")
        else:            
            tx_data = {
                "sender": public_key,
                "recipient": recipient_value,
                "amount": amount_value,
                "fee": transaction_fee,
                "timestamp": time.time()
            }
            tx_data["signature"] = sign_transaction(private_key, tx_data)
            transaction_pool.insert_one(tx_data)                            
            st.success("✅ 이체 트랜잭션이 처리중입니다...")     
                        
            # 입력값 초기화용 플래그 활성화         
            time.sleep(BLOCK_INTERVAL)  # 일정 시간 대기 (주의: UI 멈춤)
            st.session_state["clear_inputs"] = True
            st.session_state["balance"] = get_balance(public_key, blocks)            
            st.rerun()                        

with st.expander("📥 이체 내역", expanded=True):
    # 내 이체 내역만 조회 (sender 또는 recipient가 public_key)
    txs = list(transactions.find({
        "$or": [
            {"sender": public_key},
            {"recipient": public_key}
        ]
    }).sort("timestamp", -1))

    if txs:
        table_data = []
        for tx in txs:
            sender = tx.get("sender", "")
            recipient = tx.get("recipient", "")
            amount = tx.get("amount", 0.0)
            fee = tx.get("fee", 0.0)
            total = amount + fee
            time_str = datetime.fromtimestamp(tx["timestamp"], tz=KST).strftime('%Y-%m-%d %H:%M:%S')

            # 입출금 방향 계산
            if sender == public_key:
                sign = "-"
                direction = "출금"
            elif recipient == public_key:
                sign = "+"
                direction = "입금"
            else:
                sign = ""
                direction = "기타"

            table_data.append({
                "보낸 사람": sender[:5] + "...",
                "받는 사람": recipient[:5] + "...",
                "금액": f"{sign}{amount:.2f}" if sign else f"{amount:.2f}",
                "수수료": f"{sign}{fee:.2f}" if sign else f"{fee:.2f}",
                "시간": time_str,
                "구분": direction
            })

        df = pd.DataFrame(table_data)

        def highlight_signed(val):
            if isinstance(val, str) and val.startswith('+'):
                return 'color: green; font-weight: bold'
            elif isinstance(val, str) and val.startswith('-'):
                return 'color: red; font-weight: bold'
            return ''

        styled_df = df.style.applymap(highlight_signed, subset=["금액", "수수료"])
        st.dataframe(styled_df, use_container_width=True)
    else:
        st.info("이체 내역이 없습니다.")
