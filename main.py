import requests
import yaml
import random
from datetime import datetime, timedelta
import json
import os
import logging
import time


logging.basicConfig(
                    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                    datefmt='%H:%M:%S',
                    level=logging.DEBUG)

time_zone = 8  # 时区

# 两天后日期

def get_seats_with_config(user_config, date_config, seat_config):
    # 二楼东/二楼西/四楼/三楼大厅/守正书院/求新书院/自定义
    seat_name = date_config['name']
    if seat_name == "自定义":
        return user_config['自定义']
    return list(range(seat_config[seat_name]['begin'], seat_config[seat_name]['end']))


class SeatAutoBooker:
    def __init__(self, booker_config):
        self.json = None
        self.resp = None
        self.user_data = None

        logging.info('Creating SeatAutoBooker object')

        self.un = os.environ["SCHOOL_ID"].strip()  # 学号
        print("使用用户：{}".format(self.un))
        self.pd = os.environ["PASSWORD"].strip()  # 密码
        self.SCKey = None
        try:
            self.SCKey = os.environ["SCKEY"]
        except KeyError:
            print("没有Server酱的key,将不会推送消息")

        self.driver = None  # 不再使用 Selenium，保留属性供兼容
        self.cookie = None

        self.cfg = booker_config

    def book_favorite_seat(self, user_config, seat_config):
        # 阅览室 21:00 开放，自习室 20:00 开放（按北京时间）
        the_day_after_tomorrow = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][(datetime.now().weekday() + 2) % 7]
        seat_type = seat_config[user_config[the_day_after_tomorrow]['name']]["type"]

        if seat_type == "自习室":
            open_time = datetime.now().replace(hour=20-time_zone-1, minute=51, second=0, microsecond=0)
            deadline  = datetime.now().replace(hour=20-time_zone, minute=15, second=0, microsecond=0)
        else:
            open_time = datetime.now().replace(hour=21-time_zone-1, minute=51, second=0, microsecond=0)
            deadline  = datetime.now().replace(hour=21-time_zone, minute=15, second=0, microsecond=0)

        now = datetime.now()
        logging.info("现在=%s | 开放=%s | 截止=%s", now, open_time, deadline)

        if now > deadline:
            return -1, "超过截止时间，预约失败"

        # 无论多早启动，都等到开放时间再开始发请求
        wait_sec = (open_time - datetime.now()).total_seconds()
        if wait_sec > 0:
            logging.info("距开放还有 %.1f 秒，等待中…", wait_sec)
            time.sleep(wait_sec)

        logging.info("到达开放时间，开始抢座…")

        tried_times = 0
        while datetime.now() <= deadline:
            try:
                code, msg = self._book_favorite_seat(user_config, seat_config, tried_times)
                if str(code) == "0" or "已有预约" in str(msg):
                    return code, msg
                logging.info("预约未成功（code=%s msg=%s），继续重试…", code, msg)
            except Exception as e:
                logging.exception(e)

            tried_times += 1

            # 每 5 秒重试一次
            time.sleep(5)

        return -1, "超过截止时间，预约失败"

    def _book_favorite_seat(self, user_config, seat_config, tried_times=0):
        logging.info('Entering _book_favorite_seat method')
        the_day_after_tomorrow = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][(datetime.now().weekday() + 2) % 7]
        date_config = user_config[the_day_after_tomorrow]
        seats = get_seats_with_config(user_config, date_config, seat_config)
        today_0_clock = datetime.strptime(datetime.now().strftime("%Y-%m-%d 00:00:00"), "%Y-%m-%d %H:%M:%S")
        book_time = today_0_clock + timedelta(days=2) + timedelta(hours=date_config['开始时间'])
        delta = book_time - self.cfg["start-time"]
        total_seconds = delta.days * 24 * 3600 + delta.seconds
        if date_config['name'] == '自定义' and tried_times<self.cfg["max-retry"]/3*2:
            seat = seats[0]
        else:
            seat = random.choice(seats)
        data = f"beginTime={total_seconds}&duration={3600 * date_config['持续小时数']}&&seats[0]={seat}&seatBookers[0]={self.user_data['uid']}"

        headers = self.cfg["headers"]
        headers['Cookie'] = self.cookie
        # 打印 beginTime 对应的真实时刻，便于验证时间语义
        bt = datetime(1970, 1, 1, 8, 0, 0) + timedelta(seconds=total_seconds)
        print("REQUEST_DATA", data)
        print("BEGIN_TIME_SECONDS", total_seconds, "->", bt, "(naive CST)")
        self.resp = requests.post(self.cfg["target"], data=data, headers=headers)
        print("HTTP", self.resp.status_code, "len=", len(self.resp.text))
        print("RESP_HEAD", self.resp.text[:300])
        try:
            self.json = self.resp.json()
        except Exception:
            print("RESP_NOT_JSON", self.resp.text[:500])
            raise
        print("BOOK_RESULT", "CODE=", self.json.get("CODE"), "MSG=", self.json.get("MESSAGE"))
        return self.json["CODE"], self.json["MESSAGE"] + " 座位:{}".format(seat)

    def login(self):
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        logging.info('使用 Playwright 进行登录')

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox', 
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled'
                ]
            )
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = context.new_page()

            try:
                # 访问需登录的URL，触发SSO重定向
                page.goto(
                    'https://hdu.huitu.zhishulib.com/User/Index/hduCASLogin'
                    '?forward=%2FSpace%2FCategory%2Fredirect%3Fcategory_id%3D591',
                    wait_until='domcontentloaded', timeout=45000
                )
                logging.info('当前URL: %s', page.url)

                if 'sso.hdu.edu.cn' in page.url:
                    logging.info('检测到SSO登录页面')

                    # 用role定位可见的文本框（无需中文字符，避免编码问题）
                    un_box = page.get_by_role('textbox').first
                    pwd_box = page.get_by_role('textbox').nth(1)
                    un_box.wait_for(state='visible', timeout=30000)
                    logging.info('登录表单已加载')
                    page.screenshot(path='before_submit.png')

                    un_box.fill(self.un)
                    page.wait_for_timeout(500)
                    
                    # Use standard selector for password if get_by_role doesn't match
                    pwd_target = page.locator('input[type="password"]') if page.locator('input[type="password"]').is_visible() else pwd_box
                    pwd_target.focus()
                    pwd_target.fill(self.pd)
                    page.wait_for_timeout(1000)  # Wait for JS frameworks to catch up and handle DOM shifts
                    logging.info('表单已填写，用户: %s', self.un)

                    try:
                        pwd_target.press('Enter')
                        page.wait_for_timeout(1000)
                        
                        submit_btn = page.locator('button[type="submit"], input[type="submit"], .login-btn').first
                        if submit_btn.is_visible():
                            # Use JS click to avoid coordinate misses if DOM shifts dynamically (e.g. notices loading)
                            submit_btn.evaluate("node => node.click()")
                        logging.info('已触发登录 (回车+模拟点击)')
                    except Exception as e:
                        logging.warning('触发登录时出现异常 (可能已跳转): %s', e)

                    # 截图查看点击后的状态
                    page.wait_for_timeout(2000)
                    page.screenshot(path='after_click.png')

                    # 等待真正跳转回图书馆（host匹配，不含sso的service参数误匹配）
                    logging.info('准备等待页面跳转/wait_for_url (当前URL: %s, Title: %s)', page.url, page.title())
                    try:
                        page.wait_for_url('*://hdu.huitu.zhishulib.com/**', timeout=30000)
                        logging.info('wait_for_url 成功，现在 URL: %s', page.url)
                    except PWTimeout:
                        page.screenshot(path='after_login.png')
                        with open('page_source.html', 'w', encoding='utf-8') as f:
                            f.write(page.content())
                        logging.error('登录跳转超时 (Timeout waiting for hit/redirect) - Title: %s, URL: %s', page.title(), page.url)
                        return -1

                page.screenshot(path='after_login.png')
                logging.info('登录后URL: %s', page.url)

                # 提取Cookie
                cookies = context.cookies()
                self.cookie = ';'.join(f"{c['name']}={c['value']}" for c in cookies)
                self.cfg['headers']['Cookie'] = self.cookie
                logging.info('Cookie获取成功，键: %s', [c['name'] for c in cookies])
                logging.info('登录成功！')
                return 0

            except Exception as e:
                logging.exception('出现意外异常 (Overall exception block)')
                try:
                    logging.error('Error info -> Title: %s, Server URL: %s', page.title(), page.url)
                    page.screenshot(path='error.png')
                    with open('page_source.html', 'w', encoding='utf-8') as f:
                        f.write(page.content())
                except Exception as ex2:
                    logging.error("Failed to dump error info: %s", ex2)
                logging.error('登录失败：%s', e)
                return -1
            finally:
                logging.info('Closing browser...')
                browser.close()

    def get_user_info(self):
        logging.info('Getting user info')

        headers = self.cfg["headers"]
        headers['Cookie'] = self.cookie
        try:
            resp = requests.get("https://hdu.huitu.zhishulib.com/Seat/Index/searchSeats?LAB_JSON=1",
                                headers=headers)
            self.user_data = resp.json()['DATA']
            _ = self.user_data['uid']
        except Exception as e:
            logging.exception(e)
            print(self.user_data)
            print(e.__class__.__name__ + ",获取用户数据失败")
            return -1
        print("获取用户数据成功")
        return 0

    def wechatNotice(self, message, desp=None):
        logging.info('Sending WeChat notice')

        if self.SCKey != '':
            url = 'https://sctapi.ftqq.com/{0}.send'.format(self.SCKey)
            data = {
                'title': message,
                'desp': desp,
            }
            try:
                r = requests.post(url, data=data)
                if r.json()["data"]["error"] == 'SUCCESS':
                    print("Server酱通知成功")
                else:
                    print("Server酱通知失败")
            except Exception as e:
                logging.exception(e)
                print(e.__class__, "推送服务配置错误")

def is_booking_enable(date_cfg):
    if date_cfg['启用']:
        return True
    return False

if __name__ == "__main__":
    logging.info('Start of the program')
    with open("user_config.yml", 'r') as f_obj:
        user_config = yaml.safe_load(f_obj)
    with open("config/basic_config.yml", 'r') as f_obj:
        basic_config = yaml.safe_load(f_obj)
    with open("config/seat_config.yml", 'r') as f_obj:
        seat_config = yaml.safe_load(f_obj)

    the_day_after_tomorrow = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][(datetime.now().weekday() + 2) % 7]
    if not is_booking_enable(user_config[the_day_after_tomorrow]):
        logging.info('预约未启用')
        print("预约未启用")
        exit(0)

    # 在登录前先等到开放前5分钟，确保 cookie 是新鲜的
    seat_type = seat_config[user_config[the_day_after_tomorrow]['name']]["type"]
    if seat_type == "自习室":
        login_time = datetime.now().replace(hour=20-time_zone-1, minute=46, second=0, microsecond=0)  # 19:46 BJ
    else:
        login_time = datetime.now().replace(hour=21-time_zone-1, minute=46, second=0, microsecond=0)  # 20:46 BJ
    wait_sec = (login_time - datetime.now()).total_seconds()
    if wait_sec > 0:
        logging.info("距预约还有 %.1f 秒，等待后再登录…", wait_sec)
        time.sleep(wait_sec)

    s = SeatAutoBooker(basic_config["SeatAutoBooker"])
    if not s.login() == 0:
        logging.info('Login unsuccessful')
        exit(-1)
    if not s.get_user_info() == 0:
        logging.info('Getting user info unsuccessful')
        exit(-1)
    result = s.book_favorite_seat(user_config=user_config, seat_config=seat_config)
    if result and result[0] is not None:
        s.wechatNotice("图书馆预约结果", desp="CODE: {} | {}".format(result[0], result[1]))
    if s.driver:
        s.driver.quit()
    logging.info('End of the program')
