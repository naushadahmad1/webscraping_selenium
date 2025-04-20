import os
import time
import pytz
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
from scipy.stats import zscore
from google.cloud import bigquery

# Helper function to convert 1.2K, 2.5M, etc. to float
def convert_abbreviated_number(s):
    if isinstance(s, str):
        s = s.replace('$', '').replace(',', '').strip()
        if s[-1] in ['K', 'M', 'B', 'T']:
            num = float(s[:-1])
            if s[-1] == 'K':
                return num * 1e3
            elif s[-1] == 'M':
                return num * 1e6
            elif s[-1] == 'B':
                return num * 1e9
            elif s[-1] == 'T':
                return num * 1e12
        else:
            return float(s)
    return s

def scrape_crypto_data():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.get("https://www.investing.com/crypto/currencies")

    wait = WebDriverWait(driver, 20)
    try:
        accept_btn = wait.until(EC.element_to_be_clickable((By.ID, 'onetrust-accept-btn-handler')))
        accept_btn.click()
        time.sleep(2)
    except:
        print("No cookie popup found.")

    driver.execute_script("window.scrollTo(0, 1000);")
    time.sleep(3)

    try:
        rows = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "table tbody tr")))
    except Exception as e:
        print("Could not find table rows:", e)
        driver.quit()
        raise

    crypto_data = []
    for row in rows[:10]:
        cols = row.find_elements(By.TAG_NAME, 'td')
        if len(cols) >= 11:
            crypto_data.append([col.text for col in cols[:11]])

    driver.quit()

    columns = ['Name', 'Symbol', 'Last_Price', 'name_symbol', 'current_price',
               'Change_24_hours', 'Change_7_days', 'market_cap',
               'volume_24_hour', 'volume_change', 'Extra']

    df = pd.DataFrame(crypto_data, columns=columns)
    df.drop(columns=["Extra", "Last_Price"], inplace=True)

    df['current_price'] = df['current_price'].str.replace('$', '').str.replace(',', '').astype(float)
    df['volume_24_hour'] = df['volume_24_hour'].apply(convert_abbreviated_number)
    df['market_cap'] = df['market_cap'].apply(convert_abbreviated_number)

    df['percentage_change'] = df['current_price'].pct_change() * 100
    df['zscore_price'] = zscore(df['current_price'])
    df['rolling_avg'] = df['current_price'].rolling(window=3).mean()


    ist = pytz.timezone('Asia/Kolkata')
    df['datetime_ist'] = datetime.now(ist).strftime('%Y-%m-%d %H:%M:%S')

    final_df = df[['name_symbol', 'current_price', 'Change_24_hours', 'Change_7_days',
                   'market_cap', 'volume_24_hour', 'volume_change',
                   'percentage_change', 'zscore_price', 'rolling_avg', 'datetime_ist']]

    push_to_bigquery(final_df)

def push_to_bigquery(df):
    client = bigquery.Client()
    table_id = "naushad1609.scraping.crypto_currency"

    job = client.load_table_from_dataframe(
        df,
        table_id,
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_APPEND")
    )
    job.result()
    print(f"✅ Data appended to BigQuery table: {table_id}")

if __name__ == "__main__":
    scrape_crypto_data()
