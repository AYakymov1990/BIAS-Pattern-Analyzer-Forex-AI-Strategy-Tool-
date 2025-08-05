import pandas as pd
import requests
from datetime import datetime, timedelta
from alpha_vantage.foreignexchange import ForeignExchange
from g4f.client import Client

# 🔐 API-ключи
ALPHA_API_KEY = 'pXUlr36HYc7jYCcR0agmh8Kk4NRkJZGr'
TWELVE_API_KEY = 'c79417ff1dac46eab0474e175a939762'
SYMBOL_FROM = 'EUR'
SYMBOL_TO = 'USD'

# ✅ Загрузка дневных данных через Alpha Vantage
def load_daily_data():
    fx = ForeignExchange(key=ALPHA_API_KEY)
    data, _ = fx.get_currency_exchange_daily(from_symbol=SYMBOL_FROM, to_symbol=SYMBOL_TO, outputsize='full')
    df = pd.DataFrame(data).T
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    df = df.rename(columns={
        '1. open': 'Open',
        '2. high': 'High',
        '3. low': 'Low',
        '4. close': 'Close'
    }).astype(float)
    return df

# ✅ Загрузка недельных данных через Twelve Data
def load_weekly_data(start_date, end_date):
    url = f"https://api.twelvedata.com/time_series?symbol={SYMBOL_FROM}/{SYMBOL_TO}&interval=1week&start_date={start_date}&end_date={end_date}&apikey={TWELVE_API_KEY}&format=JSON"
    response = requests.get(url).json()
    if 'values' not in response:
        raise ValueError("Ошибка при получении weekly данных")
    data = pd.DataFrame(response['values'])
    data['datetime'] = pd.to_datetime(data['datetime'])
    data.set_index('datetime', inplace=True)
    data = data.rename(columns={
        'open': 'Open',
        'high': 'High',
        'low': 'Low',
        'close': 'Close'
    }).astype(float)
    return data.sort_index()

# ✅ Обновлённая логика BIAS
def bias_direction(df: pd.DataFrame) -> pd.Series:
    signals = [None]
    for i in range(1, len(df)):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]

        updated_high = curr['High'] > prev['High']
        updated_low = curr['Low'] < prev['Low']

        close_above_high = curr['Close'] > prev['High']
        close_above_low = curr['Close'] > prev['Low']
        close_below_high = curr['Close'] < prev['High']
        close_below_low = curr['Close'] < prev['Low']

        if updated_high and updated_low and close_below_high and close_above_low:
            signals.append(None)  # снятие ликвидности
        elif not updated_high and not updated_low:
            signals.append(None)  # ренж
        elif (updated_high and close_above_high) or (updated_low and close_above_low):
            signals.append("LONG")
        elif (updated_high and close_below_high) or (updated_low and close_below_low):
            signals.append("SHORT")
        else:
            signals.append(None)
    return pd.Series(signals, index=df.index)

# ✅ Актуальный прогноз
def current_forecast():
    print("📥 Загружаем данные...")

    today = datetime.today().date()
    df_1d = load_daily_data()
    df_1d = df_1d[df_1d.index < pd.to_datetime(today)]
    df_1d['Signal_1D'] = bias_direction(df_1d)
    df_1d['Date'] = df_1d.index

    last_two_1d = df_1d.tail(2).copy()

    start_of_window = today - timedelta(weeks=5)
    df_1w = load_weekly_data(start_of_window.strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d'))
    start_of_current_week = today - timedelta(days=today.weekday())
    df_1w = df_1w[df_1w.index < pd.to_datetime(start_of_current_week)]
    df_1w['Signal_1W'] = bias_direction(df_1w)
    df_1w['Date'] = df_1w.index
    last_two_1w = df_1w.tail(2).copy()

    last_two_1d['Date'] = last_two_1d['Date'].dt.strftime('%Y-%m-%d')
    last_two_1w['Date'] = last_two_1w['Date'].dt.strftime('%Y-%m-%d')

    candles_1d = "\n".join([
        f"{i+1}. **Свічка {i+1} ({row.Date})**:\n"
        f"   - Open: {row.Open:.5f}\n"
        f"   - High: {row.High:.5f}\n"
        f"   - Low: {row.Low:.5f}\n"
        f"   - Close: {row.Close:.5f}"
        for i, row in enumerate(last_two_1d.itertuples())
    ])

    candles_1w = "\n".join([
        f"{i+1}. **Тижнева свічка ({row.Date})**:\n"
        f"   - Open: {row.Open:.5f}\n"
        f"   - High: {row.High:.5f}\n"
        f"   - Low: {row.Low:.5f}\n"
        f"   - Close: {row.Close:.5f}"
        for i, row in enumerate(last_two_1w.itertuples())
    ])

    prompt = f"""
Проаналізуй останні дві свічки за патерном BIAS.

Двохсвічний аналіз BIAS

1. Ми очікуємо рух вгору, якщо: 
- Свічка оновила хай попередньої свічки та закрилась вище максимуму свічки або
свічка оновила лоу попередньої свічки та закрилась вище лоу попередньої свічки

2. Ми очікуємо рух вниз, якщо: 
- Свічка оновила хай попередньої свічки та закрилась нижче хай попередньої свічки або 
свічка оновила лоу попередньої свічки та закрилась нижче лоу попередньої свічки

3.Все так само тільки з 1W свічкою:
-і потім треба синхронити 1W напрямок і 1D напрямок
-і відкривати угоди тільки в напрямку 1W + 1D (якщо вони разом показують лонг)

Правила виключення:
1 Якщо свічка оновила хай і лоу попередньої свічки, але закрилась нижче хая і вище лоу — пропускаємо
2 Якщо свічка не оновила ні хай, ні лоу попередньої свічки — це ренж, пропускаємо

### Свічки 1D:
{candles_1d}

### Свічки 1W:
{candles_1w}
"""

    client = Client()
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",  
        messages=[{"role": "user", "content": prompt}],
        web_search=False
    )

    print("\n🔮 GPT-4o прогноз:")
    print(response.choices[0].message.content)

# ✅ Исторический анализ
def historical_mode():
    start = input("📅 Введите начальную дату (YYYY-MM-DD): ")
    end = input("📅 Введите конечную дату (YYYY-MM-DD): ")
    
    print("📥 Загружаем дневные данные (1D)...")
    df_1d = load_daily_data().sort_index()

    print("📥 Загружаем недельные данные (1W)...")
    df_1w = load_weekly_data(
        (pd.to_datetime(start) - timedelta(weeks=5)).strftime('%Y-%m-%d'),
        end
    ).sort_index()

    results = []
    date_range = pd.date_range(start=start, end=end)

    for current_date in date_range:
        if current_date not in df_1d.index:
            continue
        daily_slice = df_1d[df_1d.index < current_date].tail(2)
        weekly_slice = df_1w[df_1w.index < current_date].tail(2)

        if len(daily_slice) < 2 or len(weekly_slice) < 2:
            continue

        signal_1d = bias_direction(daily_slice).iloc[-1]
        signal_1w = bias_direction(weekly_slice).iloc[-1]
        final = signal_1d if signal_1d == signal_1w else "UNCERTAIN"

        results.append({
            "Дата": current_date.strftime("%Y-%m-%d"),
            "Свечи 1D": f"{daily_slice.index[-2].date()} | {daily_slice.index[-1].date()}",
            "Свечи 1W": f"{weekly_slice.index[-2].date()} | {weekly_slice.index[-1].date()}",
            "Сигнал 1D": signal_1d,
            "Сигнал 1W": signal_1w,
            "Итог": final
        })

    df_result = pd.DataFrame(results)

    if df_result.empty:
        print("⚠️ Нет данных для анализа.")
        return

    print("\n📊 Таблица сигналов:")
    print(df_result)

    summary_text = "\n".join([
        f"{i+1}. Дата: {row['Дата']}, 1D: {row['Сигнал 1D']}, 1W: {row['Сигнал 1W']}, Итог: {row['Итог']}"
        for i, row in df_result.iterrows()
    ])

    prompt = f"""
Проаналізуй історичні сигнали BIAS за вказаними датами:

{summary_text}

Для кожної дати:
- Чи логічно виглядає сигнал 1D та 1W?
- У яких випадках сигнал був UNCERTAIN?
- Чи узгоджені сигнали з BIAS логікою?

Зроби підсумок і дай оцінку стабільності цього підходу.
"""

    print("\n🧠 GPT-4o аналіз:")
    client = Client()
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        provider="deepai",
        messages=[{"role": "user", "content": prompt}],
        web_search=False
    )
    print(response.choices[0].message.content)

# ✅ Меню запуска
def main():
    print("1 — Актуальный прогноз")
    print("2 — Исторический анализ")
    choice = input("Выберите режим (1 или 2): ")
    if choice == '1':
        current_forecast()
    elif choice == '2':
        historical_mode()
    else:
        print("❌ Неверный выбор.")

main()
