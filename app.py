#Copyright @Arslan-MD
#Updates Channel t.me/arslanmd
from flask import Flask, request, jsonify
from datetime import datetime
import cloudscraper
import json
from bs4 import BeautifulSoup
import logging
import os
import gzip
from io import BytesIO
import brotli

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class IVASSMSClient:
    def __init__(self):
        self.scraper = cloudscraper.create_scraper()
        self.base_url = "https://www.ivasms.com"
        self.logged_in = False
        self.csrf_token = None
        
        self.scraper.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })

    def decompress_response(self, response):
        encoding = response.headers.get('Content-Encoding', '').lower()
        content = response.content
        try:
            if encoding == 'gzip':
                content = gzip.decompress(content)
            elif encoding == 'br':
                content = brotli.decompress(content)
            return content.decode('utf-8', errors='replace')
        except Exception as e:
            return response.text

    def load_cookies(self):
        try:
            # Environment Variable کو ترجیح دیں
            env_cookies = os.getenv("COOKIES_JSON")
            if env_cookies:
                logger.debug("Loading cookies from Environment Variable")
                cookies_raw = json.loads(env_cookies)
            else:
                logger.debug("Loading cookies from cookies.json file")
                with open("cookies.json", 'r') as file:
                    cookies_raw = json.load(file)
            
            if isinstance(cookies_raw, list):
                cookies = {cookie['name']: cookie['value'] for cookie in cookies_raw if 'name' in cookie}
                return cookies
            return cookies_raw
        except Exception as e:
            logger.error(f"Cookie Loading Error: {e}")
            return None

    def login_with_cookies(self):
        logger.debug("Attempting Login...")
        cookies = self.load_cookies()
        if not cookies:
            return False
        
        self.scraper.cookies.clear()
        for name, value in cookies.items():
            self.scraper.cookies.set(name, value, domain="www.ivasms.com")
        
        try:
            response = self.scraper.get(f"{self.base_url}/portal/sms/received", timeout=15)
            html_content = self.decompress_response(response)
            
            if "login" in response.url.lower() or response.status_code != 200:
                logger.error("Cookies Expired or IP Blocked by Cloudflare")
                self.logged_in = False
                return False

            soup = BeautifulSoup(html_content, 'html.parser')
            csrf_input = soup.find('input', {'name': '_token'})
            if csrf_input:
                self.csrf_token = csrf_input.get('value')
                self.logged_in = True
                logger.info("Successfully Logged In!")
                return True
            return False
        except Exception as e:
            logger.error(f"Login Exception: {e}")
            return False

    def check_otps(self, from_date="", to_date=""):
        if not self.logged_in and not self.login_with_cookies():
            return None
        
        try:
            payload = {'from': from_date, 'to': to_date, '_token': self.csrf_token}
            headers = {
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': f"{self.base_url}/portal/sms/received"
            }
            response = self.scraper.post(f"{self.base_url}/portal/sms/received/getsms", data=payload, headers=headers)
            
            if response.status_code == 200:
                html_content = self.decompress_response(response)
                soup = BeautifulSoup(html_content, 'html.parser')
                
                sms_details = []
                for item in soup.select("div.item"):
                    sms_details.append({
                        'country_number': item.select_one(".col-sm-4").text.strip() if item.select_one(".col-sm-4") else "N/A",
                        'count': item.select_one(".col-3:nth-child(2) p").text.strip() if item.select_one(".col-3:nth-child(2) p") else "0"
                    })
                return {'sms_details': sms_details, 'count_sms': len(sms_details), 'paid_sms': '0', 'unpaid_sms': '0', 'revenue': '0'}
            return None
        except:
            return None

    def get_sms_details(self, phone_range, from_date="", to_date=""):
        try:
            payload = {'_token': self.csrf_token, 'start': from_date, 'end': to_date, 'range': phone_range}
            response = self.scraper.post(f"{self.base_url}/portal/sms/received/getsms/number", data=payload)
            if response.status_code == 200:
                html_content = self.decompress_response(response)
                soup = BeautifulSoup(html_content, 'html.parser')
                details = []
                for item in soup.select("div.card.card-body"):
                    details.append({'phone_number': item.select_one(".col-sm-4").text.strip()})
                return details
            return None
        except:
            return None

    def get_otp_message(self, phone_number, phone_range, from_date="", to_date=""):
        try:
            payload = {'_token': self.csrf_token, 'start': from_date, 'end': to_date, 'Number': phone_number, 'Range': phone_range}
            response = self.scraper.post(f"{self.base_url}/portal/sms/received/getsms/number/sms", data=payload)
            if response.status_code == 200:
                html_content = self.decompress_response(response)
                soup = BeautifulSoup(html_content, 'html.parser')
                return soup.select_one(".col-9.col-sm-6 p").text.strip() if soup.select_one(".col-9.col-sm-6 p") else "No Message"
            return None
        except:
            return None

app = Flask(__name__)
client = IVASSMSClient()

@app.route('/')
def welcome():
    return jsonify({'status': 'online', 'authenticated': client.logged_in})

@app.route('/sms')
def get_sms():
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'error': 'Date required (DD/MM/YYYY)'}), 400

    # ہر ریکویسٹ پر لاگ ان چیک کرے گا
    if not client.logged_in:
        client.login_with_cookies()

    if not client.logged_in:
        return jsonify({'error': 'Authentication Failed. Update COOKIES_JSON in Vercel settings.'}), 401

    result = client.check_otps(from_date=date_str)
    if not result:
        return jsonify({'error': 'Failed to fetch data'}), 500

    all_messages = []
    for detail in result['sms_details']:
        numbers = client.get_sms_details(detail['country_number'], from_date=date_str)
        if numbers:
            for n in numbers[:5]: # لمٹ تاکہ ورسل ٹائم آؤٹ نہ ہو
                msg = client.get_otp_message(n['phone_number'], detail['country_number'], from_date=date_str)
                all_messages.append({'number': n['phone_number'], 'otp': msg})

    return jsonify({'status': 'success', 'date': date_str, 'data': all_messages})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
