# ManusTrade - AI MetaTrader 5 Trading Bot (Gemini API)

ระบบเทรดอัตโนมัติบน **MetaTrader 5 (MT5)** ขับเคลื่อนด้วย **Google Gemini API** วิเคราะห์โครงสร้างราคา แท่งเทียน ข้อมูลเศรษฐกิจมหภาค และอินดิเคเตอร์ทางเทคนิคเพื่อส่งคำสั่งซื้อขายอัตโนมัติ

---

## สภาพแวดล้อมระบบที่รองรับ (Supported Environments)

### 1. ระบบหลัก: Windows (Native Support)
- **ระบบปฏิบัติการที่รองรับอย่างเป็นทางการและเสถียรที่สุดคือ Windows 10 / 11 หรือ Windows Server**
- MetaTrader 5 Terminal เชื่อมต่อกับระบบผ่าน Official Windows API โดยตรง
- สามารถรันหน้าต่าง MT5 และบอทเทรดคู่กันได้อย่างสมบูรณ์

### 2. ข้อจำกัดบน Linux (Linux Environment Notice)
- ตัวเชื่อมต่อ MetaTrader 5 **ไม่รองรับ Linux Native** เนื่องจาก MT5 ไม่มีไลบรารี Python สำหรับ Linux โดยตรง
- หากจำเป็นต้องรันบน Linux VPS **จะต้องติดตั้ง Wine และใช้งานร่วมกับระบบ Virtual Desktop / VNC** เพื่อจำลองหน้าต่าง GUI ของ Windows เท่านั้น (ไม่สามารถรันแบบ Headless Linux เพียวๆ ได้)
- แนะนำให้ติดตั้งบน **Windows VPS** เพื่อความเสถียรและความเร็วสูงสุดในการออกออเดอร์ระดับมิลลิวินาที

---

## คุณสมบัติเด่นของระบบ (Key Features)

- **Multi-Asset Portfolio:** รองรับการมอนิเตอร์และเข้าทำกำไรหลายคู่เงินพร้อมกัน (เช่น GOLD#, EURUSD#, USDJPY#, BTCUSD#)
- **4 Distinct Trading Playbooks:**
  - **Playbook A (Trend Following):** เข้าออเดอร์ตามเทรนด์เมื่อราคาย่อตัวทดสอบ Dynamic EMA 9/21
  - **Playbook B (Range Mean-Reversion):** ดักซื้อแนวรับ-ขายแนวต้านช่วงตลาดไซด์เวย์หรือ Asian Session
  - **Playbook C (Smart Money FVG):** รอเก็บจุดเข้าเมื่อราคาถอยกลับมาปิดช่องว่าง Fair Value Gap
  - **Playbook D (Liquidity Sweep):** ดักจังหวะหลอกกิน Stop Loss (Fakeout Reversal)
- **Macroeconomic Intelligence:** ดึงข้อมูลดัชนีดอลลาร์ (DXY), ผลตอบแทนพันธบัตร (Yields) และข่าวตัวเลขเศรษฐกิจสหรัฐฯ เพื่อประเมินทิศทางร่วมกับ Price Action
- **M1 Scalping Safeguards:**
  - **Exhaustion Guard:** บล็อกการไล่ราคาที่ยอดดอย (Overbought) หรือก้นเหว (Oversold) ทันที
  - **Circuit Breaker & Cooldown:** หยุดพักอัตโนมัติเมื่อแพ้ติดต่อกันเพื่อตัดวงจร Revenge Trading
  - **Daily Drawdown Lock:** ควบคุมการขาดทุนสูงสุดต่อวันไม่ให้เกินเกณฑ์
  - **Dynamic Break-Even & Trailing Stop:** ขยับ SL ล็อกกำไรตามค่าสเปรดจริงแบบ Real-time

---

## ขั้นตอนการติดตั้งและเริ่มต้นใช้งาน (Quick Start for Windows)

### 1. เตรียมความพร้อม
1. ติดตั้ง **MetaTrader 5 Terminal** บน Windows และเข้าสู่ระบบบัญชีเทรด
2. เปิดใช้งานการเทรดอัตโนมัติใน MT5: ไปที่ `Tools -> Options -> Expert Advisors` แล้วติ๊กเลือก **Allow Algo Trading**
3. ติดตั้ง **Python 3.10 - 3.12** บน Windows

### 2. ติดตั้ง Dependencies
```bash
pip install -r requirements.txt
```

### 3. ตั้งค่าระบบ (Configuration)
คัดลอกไฟล์ต้นแบบเป็นไฟล์คอนฟิกจริง:
```bash
copy config.example.ini config.ini
```
เปิดไฟล์ `config.ini` แล้วระบุ:
- `api_keys`: รายการ Gemini API Key จาก Google AI Studio
- `symbols`: รายการคู่เงินที่ต้องการเทรด (เช่น `GOLD#, EURUSD#, USDJPY#`)
- `login`, `password`, `server`: บัญชี MT5 ของท่าน

### 4. เริ่มต้นการทำงาน
```bash
python main.py
```
หรือรันผ่านไฟล์สคริปต์:
```bash
start_windows.bat
```
