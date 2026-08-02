"""
backend/data_feed/deriv_feed.py
ดึงข้อมูลแท่งเทียน Real-Time ย้อนหลัง 500 แท่งจาก Deriv ผ่าน WebSocket API
"""
import json
import websocket
import pandas as pd

def fetch_candles_history(symbol: str = "frxXAUUSD", granularity: int = 60, count: int = 500) -> pd.DataFrame:
    """
    ดึงข้อมูลราคาย้อนหลัง Real-Time ผ่าน WebSocket API ของ Deriv
    - symbol: 'frxXAUUSD' (Gold)
    - granularity: 60 (1 นาที)
    - count: 500 (ย้อนหลัง ~8 ชั่วโมง สำหรับสร้าง Feature Context)
    """
    ws_url = "wss://ws.derivws.com/websockets/v3?app_id=1089"
    ws = websocket.create_connection(ws_url)
    
    req = {
        "ticks_history": symbol,
        "adjust_start_time": 1,
        "count": count,
        "end": "latest",
        "style": "candles",
        "granularity": granularity
    }
    
    ws.send(json.dumps(req))
    response = ws.recv()
    ws.close()
    
    data = json.loads(response)
    
    if "candles" not in data:
        raise RuntimeError(f"ไม่สามารถดึงข้อมูลจาก Deriv API ได้: {data}")
    
    candles = data["candles"]
    df = pd.DataFrame(candles)
    
    # แปลง Timestamp เป็น Datetime และตั้งเป็น Index
    df["datetime"] = pd.to_datetime(df["epoch"], unit="s")
    df.set_index("datetime", inplace=True)
    
    # แปลงชื่อ คอลัมน์ ให้ตรงกับที่ Feature Generator ต้องการ
    df.rename(columns={
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close"
    }, inplace=True)
    
    # หากไม่มี volume ให้จำลองเป็น 0 เพื่อป้องกัน Feature Error
    if "volume" not in df.columns:
        df["volume"] = 0
        
    return df[["open", "high", "low", "close", "volume"]]