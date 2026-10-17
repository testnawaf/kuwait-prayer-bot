import os
import requests
from requests_oauthlib import OAuth1
from datetime import datetime, timedelta
import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
import logging

# ─── الإعدادات ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

KUWAIT_TZ = pytz.timezone('Asia/Kuwait')

API_KEY             = os.environ['TWITTER_API_KEY']
API_SECRET          = os.environ['TWITTER_API_SECRET']
ACCESS_TOKEN        = os.environ['TWITTER_ACCESS_TOKEN']
ACCESS_TOKEN_SECRET = os.environ['TWITTER_ACCESS_TOKEN_SECRET']

TWITTER_URL = "https://api.twitter.com/2/tweets"

PRAYERS = ['Fajr', 'Sunrise', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']

ARABIC_NAMES = {
    'Fajr': 'الفجر', 'Sunrise': 'الشروق',
    'Dhuhr': 'الظهر', 'Asr': 'العصر',
    'Maghrib': 'المغرب', 'Isha': 'العشاء',
}

EMOJIS = {
    'Fajr': '🌙', 'Sunrise': '🌅', 'Dhuhr': '☀️',
    'Asr': '🌤️', 'Maghrib': '🌇', 'Isha': '🌃',
}

DAYS_AR = {
    0: 'الاثنين', 1: 'الثلاثاء', 2: 'الأربعاء',
    3: 'الخميس', 4: 'الجمعة', 5: 'السبت', 6: 'الأحد'
}

def post_tweet(text: str):
    auth = OAuth1(API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
    response = requests.post(TWITTER_URL, auth=auth, json={"text": text})
    if response.status_code == 201:
        logger.info(f"✅ تم نشر التغريدة بنجاح")
    else:
        logger.error(f"❌ خطأ: {response.status_code} - {response.text}")

def get_prayer_times(date=None):
    if date is None:
        date = datetime.now(KUWAIT_TZ)
    url = f"http://api.aladhan.com/v1/timingsByCity/{date.strftime('%d-%m-%Y')}"
    params = {'city': 'Kuwait City', 'country': 'Kuwait', 'method': 4}
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        if data.get('code') == 200:
            return data['data']['timings']
    except Exception as e:
        logger.error(f"خطأ في جلب المواقيت: {e}")
    return None

def schedule_daily_tweets(scheduler, target_date=None):
    if target_date is None:
        target_date = datetime.now(KUWAIT_TZ)
    now = datetime.now(KUWAIT_TZ)
    timings = get_prayer_times(target_date)
    if not timings:
        logger.error("تعذّر جلب مواقيت الصلاة")
        return

    date_label = target_date.strftime('%d/%m/%Y')
    day_label  = DAYS_AR[target_date.weekday()]

    # ملخص الصباح 5:00
    summary_dt = target_date.replace(hour=5, minute=0, second=0, microsecond=0)
    if summary_dt > now:
        summary = (
            f"🕌 مواقيت الصلاة – الكويت\n"
            f"📅 {day_label} {date_label}\n\n"
            f"🌙 الفجر:  {timings.get('Fajr','')}\n"
            f"🌅 الشروق: {timings.get('Sunrise','')}\n"
            f"☀️ الظهر:  {timings.get('Dhuhr','')}\n"
            f"🌤️ العصر:  {timings.get('Asr','')}\n"
            f"🌇 المغرب: {timings.get('Maghrib','')}\n"
            f"🌃 العشاء: {timings.get('Isha','')}\n\n"
            f"#الكويت #مواقيت_الصلاة"
        )
        scheduler.add_job(post_tweet, trigger=DateTrigger(run_date=summary_dt, timezone=KUWAIT_TZ),
                          args=[summary], id=f"summary_{target_date.strftime('%Y%m%d')}", replace_existing=True)
        logger.info("📋 جُدول الملخص اليومي 05:00")

    # تنبيه قبل كل صلاة بـ 10 دقائق
    for prayer in PRAYERS:
        if prayer not in timings:
            continue
        h, m = map(int, timings[prayer].split(':'))
        prayer_dt = target_date.replace(hour=h, minute=m, second=0, microsecond=0)
        tweet_dt  = prayer_dt - timedelta(minutes=10)
        if tweet_dt <= now:
            continue
        arabic = ARABIC_NAMES[prayer]
        emoji  = EMOJIS[prayer]
        text = (
            f"{emoji} باقي ١٠ دقائق على أذان {arabic}\n\n"
            f"⏰ موعد الأذان: {timings[prayer]}\n"
            f"📍 الكويت – {date_label}\n\n"
            f"#الكويت #مواقيت_الصلاة #{arabic}"
        )
        scheduler.add_job(post_tweet, trigger=DateTrigger(run_date=tweet_dt, timezone=KUWAIT_TZ),
                          args=[text], id=f"prayer_{prayer}_{tweet_dt.strftime('%Y%m%d%H%M')}", replace_existing=True)
        logger.info(f"🔔 جُدول تنبيه {arabic} في {tweet_dt.strftime('%H:%M')}")

def reschedule_next_day(scheduler):
    tomorrow = (datetime.now(KUWAIT_TZ) + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    logger.info(f"🔄 إعادة الجدولة لـ {tomorrow.strftime('%Y-%m-%d')}")
    schedule_daily_tweets(scheduler, tomorrow)

def main():
    logger.info("🕌 بوت مواقيت الصلاة – الكويت يبدأ...")
    scheduler = BlockingScheduler(timezone=KUWAIT_TZ)
    schedule_daily_tweets(scheduler)
    scheduler.add_job(reschedule_next_day, trigger=CronTrigger(hour=0, minute=1, timezone=KUWAIT_TZ),
                      args=[scheduler], id='midnight_reschedule', replace_existing=True)
    logger.info("🚀 البوت يعمل الآن!")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 توقف البوت.")

if __name__ == '__main__':
    main()
