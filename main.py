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
        #判断是否到了预约时间
        # 阅览室晚上9点开始预约，自习室晚上8点半开始预约
        the_day_after_tomorrow = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][(datetime.now().weekday() + 2) % 7]
        seat_type = seat_config[user_config[the_day_after_tomorrow]['name']]["type"]
        if seat_type == "自习室":
            start_time = datetime.now().replace(hour=20-time_zone, minute=0, second=0, microsecond=0)
            end_time = datetime.now().replace(hour=20-time_zone, minute=15, second=0, microsecond=0)
        else:
            start_time = datetime.now().replace(hour=21-time_zone, minute=0, second=0, microsecond=0)
            end_time = datetime.now().replace(hour=21-time_zone, minute=15, second=0, microsecond=0)
        start_time = start_time - timedelta(minutes=self.cfg["cron-delta-minutes"])
        if datetime.now() < start_time or datetime.now() > end_time:
            return -1, "未到预约时间"
        logging.info('Booking favorite seat')
        retry_sleep_time = timedelta(minutes=self.cfg["cron-delta-minutes"]).seconds*2/(self.cfg["max-retry"]-2) - 10
        for tried_times in range(self.cfg["max-retry"]):
            try:
                return self._book_favorite_seat(user_config, seat_config, tried_times)
            except Exception as e:
                logging.exception(e)
                print(e.__class__, "尝试第{}次".format(tried_times))
                time.sleep(retry_sleep_time)

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
        print(data)
        self.resp = requests.post(self.cfg["target"], data=data, headers=headers)
        self.json = json.loads(self.resp.text)
        return self.json["CODE"], self.json["MESSAGE"] + " 座位:{}".format(seat)

    def login(self):
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        logging.info('使用 Playwright 进行登录')

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = context.new_page()

            try:
                # 访问需登录的URL，触发SSO重定向
                page.goto(
                    'https://hdu.huitu.zhishulib.com/User/Index/hduCASLogin'
                    '?forward=%2FSpace%2FCategory%2Fredirect%3Fcategory_id%3D591',
                    wait_until='networkidle', timeout=45000
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
                    pwd_box.fill(self.pd)
                    logging.info('表单已填写，用户: %s', self.un)

                    page.click('button[type="submit"]')
                    logging.info('已点击登录按钮')

                    # 等待真正跳转回图书馆（host匹配，不含sso的service参数误匹配）
                    try:
                        page.wait_for_url('*://hdu.huitu.zhishulib.com/**', timeout=30000)
                    except PWTimeout:
                        page.screenshot(path='after_login.png')
                        with open('page_source.html', 'w', encoding='utf-8') as f:
                            f.write(page.content())
                        logging.error('登录超时，仍在页面: %s', page.url)
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
                try:
                    page.screenshot(path='error.png')
                    with open('page_source.html', 'w', encoding='utf-8') as f:
                        f.write(page.content())
                except Exception:
                    pass
                logging.error('登录失败：%s', e)
                return -1
            finally:
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
