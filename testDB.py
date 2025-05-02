import streamlit as st
from pymongo import MongoClient

try:
    client = MongoClient(st.secrets["mongodb"]["uri"], serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    st.success("✅ MongoDB 연결 성공!")
except Exception as e:
    st.error(f"❌ MongoDB 연결 실패: {e}")
    st.stop()