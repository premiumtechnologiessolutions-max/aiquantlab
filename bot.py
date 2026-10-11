import os
import requests
import time

# 1. ضع مفتاح الـ API الخاص بك هنا
API_KEY = os.getenv("TWELVEDATA_API_KEY", "")
if not API_KEY:
    raise RuntimeError("Set TWELVEDATA_API_KEY in the environment before running bot.py")

# 2. قائمة بأزواج الفوركس (يمكنك إضافة ما تشاء لاحقاً)
symbols = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"]
interval = "1week"

print("🤖 الروبوت يبدأ بجمع أسعار السوق، يرجى الانتظار...\n")

# 3. حلقة تكرارية: الروبوت سيمر على كل زوج في القائمة
for symbol in symbols:
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&apikey={API_KEY}"
    response = requests.get(url)
    data = response.json()

    if 'values' in data:
        latest_close = data['values'][0]['close']
        # طباعة النتيجة باللغة الإنجليزية لتجنب تقطع الحروف في الشاشة
        print(f"✅ {symbol} Current Price: {latest_close}")
    else:
        print(f"❌ Error fetching {symbol}: {data.get('message', 'Unknown Error')}")

    # 4. توقف الروبوت لـ 8 ثوانٍ لتفادي تجاوز الحد المسموح (8 طلبات/دقيقة)
    time.sleep(8)

print("\n🎯 تم الانتهاء من فحص جميع الأزواج!")