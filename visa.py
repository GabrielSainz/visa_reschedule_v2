'''
python
'''

import time
import json
import random
import requests
import configparser
from datetime import datetime, timedelta

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait as Wait
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver import ChromeOptions

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from embassy import *

config = configparser.ConfigParser()
config.read('config.ini')

# Personal Info:
# Account and current appointment info from https://ais.usvisa-info.com
USERNAME = config['PERSONAL_INFO']['USERNAME']
PASSWORD = config['PERSONAL_INFO']['PASSWORD']
# Find SCHEDULE_ID in re-schedule page link:
# https://ais.usvisa-info.com/en-am/niv/schedule/{SCHEDULE_ID}/appointment
SCHEDULE_ID = config['PERSONAL_INFO']['SCHEDULE_ID']
FAMILIAR_APPOINTMENT = config['PERSONAL_INFO']['FAMILIAR_APPOINTMENT']
FAMILIAR_MEMBERS = config['PERSONAL_INFO']['FAMILIAR_MEMBERS'].split(",")
# Target Period:
PRIOD_START = str(datetime.today() + timedelta(days=8))[:10]
PRIOD_END = config['PERSONAL_INFO']['PRIOD_END']
# Embassy Section:
YOUR_EMBASSY = config['PERSONAL_INFO']['YOUR_EMBASSY']
ASC = config['PERSONAL_INFO']['ASC']
EMBASSY = Embassies[YOUR_EMBASSY][0]
FACILITY_ID = Embassies[YOUR_EMBASSY][1]
ASC_ID = Embassies[YOUR_EMBASSY][2]
REGEX_CONTINUE = Embassies[YOUR_EMBASSY][3]

# Notification:
# Get email notifications via https://sendgrid.com/ (Optional)
SENDGRID_API_KEY = config['NOTIFICATION']['SENDGRID_API_KEY']
# Get push notifications via https://pushover.net/ (Optional)
PUSHOVER_TOKEN = config['NOTIFICATION']['PUSHOVER_TOKEN']
PUSHOVER_USER = config['NOTIFICATION']['PUSHOVER_USER']
# Get push notifications via PERSONAL WEBSITE http://yoursite.com (Optional)
PERSONAL_SITE_USER = config['NOTIFICATION']['PERSONAL_SITE_USER']
PERSONAL_SITE_PASS = config['NOTIFICATION']['PERSONAL_SITE_PASS']
PUSH_TARGET_EMAIL = config['NOTIFICATION']['PUSH_TARGET_EMAIL']
PERSONAL_PUSHER_URL = config['NOTIFICATION']['PERSONAL_PUSHER_URL']

# Time Section:
minute = 60
hour = 60 * minute
# Time between steps (interactions with forms)
STEP_TIME = 0.5
# Time between retries/checks for available dates (seconds)
RETRY_TIME_L_BOUND = config['TIME'].getfloat('RETRY_TIME_L_BOUND')
RETRY_TIME_U_BOUND = config['TIME'].getfloat('RETRY_TIME_U_BOUND')
# Cooling down after WORK_LIMIT_TIME hours of work (Avoiding Ban)
WORK_LIMIT_TIME = config['TIME'].getfloat('WORK_LIMIT_TIME')
WORK_COOLDOWN_TIME = config['TIME'].getfloat('WORK_COOLDOWN_TIME')
# Temporary Banned (empty list): wait COOLDOWN_TIME hours
BAN_COOLDOWN_TIME = config['TIME'].getfloat('BAN_COOLDOWN_TIME')

# CHROMEDRIVER
# Details for the script to control Chrome
LOCAL_USE = config['CHROMEDRIVER'].getboolean('LOCAL_USE')
# Optional: HUB_ADDRESS is mandatory only when LOCAL_USE = False
HUB_ADDRESS = config['CHROMEDRIVER']['HUB_ADDRESS']

FIRST_PAGE_LINK = f"https://ais.usvisa-info.com/{EMBASSY}/niv/users/sign_in"
DATE_URL = f"https://ais.usvisa-info.com/{EMBASSY}/niv/schedule/{SCHEDULE_ID}/appointment/days/{FACILITY_ID}.json?appointments[expedite]=false"
ASC_DATE_URL = f"https://ais.usvisa-info.com/{EMBASSY}/niv/schedule/{SCHEDULE_ID}/appointment/days/{ASC_ID}.json?appointments[expedite]=false"
TIME_URL = f"https://ais.usvisa-info.com/{EMBASSY}/niv/schedule/{SCHEDULE_ID}/appointment/times/{FACILITY_ID}.json?date=%s&appointments[expedite]=false"
ASC_TIME_URL = f"https://ais.usvisa-info.com/{EMBASSY}/niv/schedule/{SCHEDULE_ID}/appointment/times/{ASC_ID}.json?date=%s&appointments[expedite]=false"
SIGN_OUT_LINK = f"https://ais.usvisa-info.com/{EMBASSY}/niv/users/sign_out"
APPOINTMENT_URL = f"https://ais.usvisa-info.com/{EMBASSY}/niv/schedule/{SCHEDULE_ID}/appointment"

if FAMILIAR_APPOINTMENT:
    APPOINTMENT_MEMBERS = "&".join([f"applicants%5B%5D={i}" for i in FAMILIAR_MEMBERS])
    APPOINTMENT_URL = f"https://ais.usvisa-info.com/{EMBASSY}/niv/schedule/{SCHEDULE_ID}/appointment?{APPOINTMENT_MEMBERS}&confirmed_limit_message=1&commit=Continue"

JS_SCRIPT = ("var req = new XMLHttpRequest();"
             f"req.open('GET', '%s', false);"
             "req.setRequestHeader('Accept', 'application/json, text/javascript, */*; q=0.01');"
             "req.setRequestHeader('X-Requested-With', 'XMLHttpRequest');"
             f"req.setRequestHeader('Cookie', '_yatri_session=%s');"
             "req.send(null);"
             "return req.responseText;")

def send_notification(title, msg):
    print(f"Sending notification!")
    if SENDGRID_API_KEY:
        message = Mail(from_email=USERNAME, to_emails=USERNAME,
                       subject=msg, html_content=msg)
        try:
            sg = SendGridAPIClient(SENDGRID_API_KEY)
            response = sg.send(message)
            print(response.status_code)
            print(response.body)
            print(response.headers)
        except Exception as e:
            print(e.message)
    if PUSHOVER_TOKEN:
        url = "https://api.pushover.net/1/messages.json"
        data = {
            "token": PUSHOVER_TOKEN,
            "user": PUSHOVER_USER,
            "message": msg
        }
        requests.post(url, data)
    if PERSONAL_SITE_USER:
        url = PERSONAL_PUSHER_URL
        data = {
            "title": "VISA - " + str(title),
            "user": PERSONAL_SITE_USER,
            "pass": PERSONAL_SITE_PASS,
            "email": PUSH_TARGET_EMAIL,
            "msg": msg,
        }
        requests.post(url, data)


def auto_action(label, find_by, el_type, action, value, sleep_time=0):
    print("\t" + label + ":", end="")
    # Find Element By
    match find_by.lower():
        case 'id':
            item = driver.find_element(By.ID, el_type)
        case 'name':
            item = driver.find_element(By.NAME, el_type)
        case 'class':
            item = driver.find_element(By.CLASS_NAME, el_type)
        case 'xpath':
            item = driver.find_element(By.XPATH, el_type)
        case _:
            return 0
    # Do Action:
    match action.lower():
        case 'send':
            item.send_keys(value)
        case 'click':
            item.click()
        case _:
            return 0
    print("\t\tCheck!")
    if sleep_time:
        time.sleep(sleep_time)


def start_process():
    # Bypass reCAPTCHA
    driver.get(FIRST_PAGE_LINK)
    time.sleep(STEP_TIME)
    #
    Wait(driver, 60).until(EC.presence_of_element_located((By.NAME, "commit")))
    auto_action("Click bounce", "xpath", '//a[@class="down-arrow bounce"]', "click", "", STEP_TIME)
    auto_action("Email", "id", "user_email", "send", USERNAME, STEP_TIME)
    auto_action("Password", "id", "user_password", "send", PASSWORD, STEP_TIME)
    auto_action("Privacy", "class", "icheckbox", "click", "", STEP_TIME)
    auto_action("Enter Panel", "name", "commit", "click", "", STEP_TIME)
    Wait(driver, 60).until(EC.presence_of_element_located((By.XPATH, "//a[contains(text(), '" + REGEX_CONTINUE + "')]")))
    print("\n\tlogin successful!\n")


def reschedule(date, asc_date=None):
    print(f"---------- Starting Reschedule ({date}) ------------")
    time = get_time(date)
    driver.get(APPOINTMENT_URL)
    #
    print("---------- Headers ------------")
    headers = {
        "User-Agent": driver.execute_script("return navigator.userAgent;"),
        "Referer": APPOINTMENT_URL,
        "Cookie": "_yatri_session=" + driver.get_cookie("_yatri_session")["value"]
    }
    print("---------- DATA ------------")
    data = {
        # "utf8": driver.find_element(by=By.NAME, value='utf8').get_attribute('value'),
        "authenticity_token": driver.find_element(by=By.NAME, value='authenticity_token').get_attribute('value'),
        "confirmed_limit_message": driver.find_element(by=By.NAME, value='confirmed_limit_message').get_attribute('value'),
        "use_consulate_appointment_capacity": driver.find_element(by=By.NAME, value='use_consulate_appointment_capacity').get_attribute('value'),
        "appointments[consulate_appointment][facility_id]": FACILITY_ID,
        "appointments[consulate_appointment][date]": date,
        "appointments[consulate_appointment][time]": time,
    }
    print(data)
    #
    if asc_date != None:
        asc_time = get_time(asc_date, True)
        data["appointments[asc_appointment][facility_id]"] = ASC_ID
        data["appointments[asc_appointment][date]"] = asc_date
        data["appointments[asc_appointment][time]"] = asc_time
        print(data)
    #
    #
    r = requests.post(APPOINTMENT_URL, headers=headers, data=data)
    if(r.text.find('Successfully Scheduled') != -1):
        title = "SUCCESS"
        msg = f"Rescheduled Successfully! {date} {time}"
        # successful reschedule
        successful_reschedule = True
    else:
        title = "FAIL"
        msg = f"Reschedule Failed!!! {date} {time}"
        successful_reschedule = False
    return [title, msg, successful_reschedule]


def get_date(asc_flag=False):
    # Requesting to get the whole available dates
    session = driver.get_cookie("_yatri_session")["value"]
    #
    if asc_flag:
        script = JS_SCRIPT % (str(ASC_DATE_URL), session)
    else:
        script = JS_SCRIPT % (str(DATE_URL), session)
    #
    content = driver.execute_script(script)
    return json.loads(content)


def get_time(date, asc_flag = False):
    if asc_flag:
        print("ASC Time")
        time_url = ASC_TIME_URL % date
    else:
        time_url = TIME_URL % date
    #
    session = driver.get_cookie("_yatri_session")["value"]
    script = JS_SCRIPT % (str(time_url), session)
    content = driver.execute_script(script)
    data = json.loads(content)
    time = data.get("available_times")[-1]
    print(f"Got time successfully! {date} {time}")
    return time


def is_logged_in():
    content = driver.page_source
    if(content.find("error") != -1):
        return False
    return True


def get_available_date(dates, first_date=None):
    # Evaluation of different available dates
    def is_in_period(date, PSD, PED):
        new_date = datetime.strptime(date, "%Y-%m-%d")
        result = (PED >= new_date and new_date >= PSD)
        # print(f'{new_date.date()} : {result}', end=", ")
        return result
    if first_date != None:
        PED = datetime.strptime(first_date, "%Y-%m-%d") - timedelta(days=1)
        # PSD = datetime.strptime(PRIOD_START, "%Y-%m-%d")
        PSD = datetime.strptime(first_date, "%Y-%m-%d") - timedelta(days=7)
    else:
        PED = datetime.strptime(PRIOD_END, "%Y-%m-%d")
        PSD = datetime.strptime(PRIOD_START, "%Y-%m-%d")
    #
    for d in dates:
        date = d.get('date')
        if is_in_period(date, PSD, PED):
            return date
    print(f"\n\nNo available dates between ({PSD.date()}) and ({PED.date()})!")


def info_logger(file_path, log):
    # file_path: e.g. "log.txt"
    with open(file_path, "a") as file:
        file.write(str(datetime.now().time()) + ":\n" + log + "\n")


def ban_situation():
    # Ban Situation
    msg = f"List is empty, Probabely banned!\n\tSleep for {BAN_COOLDOWN_TIME} hours!\n"
    print(msg)
    info_logger(LOG_FILE_NAME, msg)
    send_notification("BAN", msg)
    driver.get(SIGN_OUT_LINK)
    time.sleep(BAN_COOLDOWN_TIME * hour)


def dates_found(dates):
    # Print Available dates:
    msg = ""
    for d in dates:
        msg = msg + "%s" % (d.get('date')) + ", "
    msg = "Available dates:\n" + msg
    print(msg)
    info_logger(LOG_FILE_NAME, msg)


# options = ChromeOptions()
# driver = webdriver.Chrome("chromedriver.exe", options = options)
# options = ChromeOptions()
# # options.add_argument('user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"')
# driver = webdriver.Chrome("chromedriver.exe",chrome_options=options)
# driver.delete_all_cookies()

if LOCAL_USE:
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
else:
    driver = webdriver.Remote(
        command_executor=HUB_ADDRESS, options=webdriver.ChromeOptions())


if __name__ == "__main__":
    first_loop = True
    while 1:
        LOG_FILE_NAME = "log_" + str(datetime.now().date()) + ".txt"
        if first_loop:
            t0 = time.time()
            total_time = 0
            Req_count = 0
            start_process()
            first_loop = False
        Req_count += 1
        try:
            msg = "-" * 60 + \
                f"\nRequest count: {Req_count}, Log time: {datetime.today()}\n"
            print(msg)
            info_logger(LOG_FILE_NAME, msg)
            dates = get_date()
            if not dates:
                ban_situation()
                first_loop = True
            else:
                dates_found(dates)
                date = get_available_date(dates)
                if date:
                    print(f"Got date {date}")
                    # A good date to schedule for
                    ############# Added for ASC schedule #############
                    if ASC:
                        print("Getting ASC Dates")
                        asc_dates = get_date(True)
                        if not asc_dates:
                            ban_situation()
                            first_loop = True
                        else:
                            dates_found(asc_dates)
                            asc_date = get_available_date(asc_dates, date)
                            if asc_date:
                                print(f"Got ASC date {asc_date}")
                                END_MSG_TITLE, msg, flag_reschedule = reschedule(date, asc_date)
                                if flag_reschedule:
                                    print(msg)
                                    PRIOD_END = date
                                    continue
                    ####################################################
                    else:
                        END_MSG_TITLE, msg, flag_reschedule = reschedule(date)
                        if flag_reschedule:
                            print(msg)
                            PRIOD_END = date
                            continue
                RETRY_WAIT_TIME = random.randint(
                    RETRY_TIME_L_BOUND, RETRY_TIME_U_BOUND)
                t1 = time.time()
                total_time = t1 - t0
                msg = "\nWorking Time:  ~ {:.2f} minutes".format(
                    total_time/minute)
                print(msg)
                info_logger(LOG_FILE_NAME, msg)
                if total_time > WORK_LIMIT_TIME * hour:
                    # Let program rest a little
                    send_notification(
                        "REST", f"Break-time after {WORK_LIMIT_TIME} hours | Repeated {Req_count} times")
                    driver.get(SIGN_OUT_LINK)
                    time.sleep(WORK_COOLDOWN_TIME * hour)
                    first_loop = True
                else:
                    msg = "Retry Wait Time: " + \
                        str(RETRY_WAIT_TIME) + " seconds"
                    print(msg)
                    info_logger(LOG_FILE_NAME, msg)
                    time.sleep(RETRY_WAIT_TIME)
        except:
            # Exception Occured
            msg = f"Break the loop after exception!\n"
            END_MSG_TITLE = "EXCEPTION"
            continue
            # break

print(msg)
info_logger(LOG_FILE_NAME, msg)
send_notification(END_MSG_TITLE, msg)
# driver.get(SIGN_OUT_LINK)
# driver.stop_client()
# driver.quit()
