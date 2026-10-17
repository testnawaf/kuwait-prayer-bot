import os
import requests
from datetime import datetime, timedelta
import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
import tweepy
import logging

# ─── الإعدادات ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

KUWAIT_TZ = pytz.timezone('Asia/Kuwait')

# مفاتيح تويتر (تُضاف في Railway كـ Environment Variables)
TWITTER_API_KEY            = os.environ['TWITTER_API_KEY']
TWITTER_API_SECRET         = os.environ['TWITTER_API_SECRET']
TWITTER_ACCESS_TOKEN       = os.environ['TWITTER_ACCESS_TOKEN']
TWITTER_ACCESS_TOKEN_SECRET = os.environ['TWITTER_ACCESS_TOKEN_SECRET']

# ─── بيانات الصلوات ──────────────────────────────────────────
PRAYERS = ['Fajr', 'Sunrise', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']

ARABIC_NAMES = {
    'Fajr':    'الفجر',
    'Sunrise': 'الشروق',
    'Dhuhr':   'الظهر',
    'Asr':     'العصر',
    'Maghrib': 'المغرب',
    'Isha':    'العشاء',
}

EMOJIS = {
    'Fajr':    '🌙',
    'Sunrise': '🌅',
    'Dhuhr':   '☀️',
    'Asr':     '🌤️',
    'Maghrib': '🌇',
    'Isha':    '🌃',
}

DAYS_AR = {
    0: 'الاثنين', 1: 'الثلاثاء', 2: 'الأربعاء',
    3: 'الخميس',  4: 'الجمعة',   5: 'السبت', 6: 'الأحد'
}

# ─── دوال مساعدة ─────────────────────────────────────────────

def get_twitter_client():
    return tweepy.Client(
        consumer_key=TWITTER_API_KEY,
        consumer_secret=TWITTER_API_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
    )

def post_tweet(text: str):
    """ينشر تغريدة على حساب X"""
    try:
        client = get_twitter_client()
        client.create_tweet(text=text)
        logger.info(f"✅ تم نشر التغريدة: {text[:60]}...")
    except Exception as e:
        logger.error(f"❌ خطأ في نشر التغريدة: {e}")

def get_prayer_times(date: datetime = None) -> dict | None:
    """يجيب مواقيت الصلاة من aladhan.com للكويت"""
    if date is None:
        date = datetime.now(KUWAIT_TZ)

    date_str = date.strftime('%d-%m-%Y')
    url = f"http://api.aladhan.com/v1/timingsByCity/{date_str}"

    params = {
        'city': 'Kuwait City',
        'country': 'Kuwait',
        'method': 4,  # طريقة أم القرى
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        data = response.json()
        if data.get('code') == 200:
            return data['data']['timings']
    except Exception as e:
        logger.error(f"خطأ في جلب المواقيت: {e}")

    return None

# ─── جدولة التغريدات ─────────────────────────────────────────

def schedule_daily_tweets(scheduler: BlockingScheduler, target_date: datetime = None):
    """يجدول تغريدات اليوم: ملخص الصباح + تنبيه قبل كل صلاة بـ 10 دقائق"""

    if target_date is None:
        target_date = datetime.now(KUWAIT_TZ)

    now = datetime.now(KUWAIT_TZ)
    timings = get_prayer_times(target_date)

    if not timings:
        logger.error("⚠️ تعذّر جلب مواقيت الصلاة")
        return

    date_label = target_date.strftime('%d/%m/%Y')
    day_label  = DAYS_AR[target_date.weekday()]

    # 1) ملخص مواقيت الصلاة الساعة 5 صباحاً
    summary_dt = target_date.replace(hour=5, minute=0, second=0, microsecond=0)
    if summary_dt > now:
        summary_text = (
            f"🕌 مواقيت الصلاة – الكويت\n"
            f"📅 {day_label} {date_label}\n\n"
            f"🌙 الفجر:    {timings.get('Fajr','')}\n"
            f"🌅 الشروق:   {timings.get('Sunrise','')}\n"
            f"☀️ الظهر:    {timings.get('Dhuhr','')}\n"
            f"🌤️ العصر:    {timings.get('Asr','')}\n"
            f"🌇 المغرب:   {timings.get('Maghrib','')}\n"
            f"🌃 العشاء:   {timings.get('Isha','')}\n\n"
            f"#الكويت #مواقيت_الصلاة"
        )
        scheduler.add_job(
            post_tweet,
            trigger=DateTrigger(run_date=summary_dt, timezone=KUWAIT_TZ),
            args=[summary_text],
            id=f"summary_{target_date.strftime('%Y%m%d')}",
            replace_existing=True,
        )
        logger.info(f"📋 جُدول الملخص اليومي في 05:00")

    # 2) تنبيه قبل كل صلاة بـ 10 دقائق
    for prayer in PRAYERS:
        if prayer not in timings:
            continue

        time_str = timings[prayer]
        hour, minute = map(int, time_str.split(':'))

        prayer_dt = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        tweet_dt  = prayer_dt - timedelta(minutes=10)

        if tweet_dt <= now:
            continue  # فات وقتها

        arabic = ARABIC_NAMES[prayer]
        emoji  = EMOJIS[prayer]

        reminder_text = (
            f"{emoji} باقي ١٠ دقائق على أذان {arabic}\n\n"
            f"⏰ موعد الأذان: {time_str}\n"
            f"📍 الكويت – {date_label}\n\n"
            f"#الكويت #مواقيت_الصلاة #{arabic}"
        )

        scheduler.add_job(
            post_tweet,
            trigger=DateTrigger(run_date=tweet_dt, timezone=KUWAIT_TZ),
            args=[reminder_text],
            id=f"prayer_{prayer}_{tweet_dt.strftime('%Y%m%d%H%M')}",
            replace_existing=True,
        )
        logger.info(f"🔔 جُدول تنبيه {arabic} في {tweet_dt.strftime('%H:%M')}")

def reschedule_next_day(scheduler: BlockingScheduler):
    """يُستدعى منتصف الليل لجدولة اليوم التالي"""
    tomorrow = (datetime.now(KUWAIT_TZ) + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    logger.info(f"🔄 إعادة الجدولة لـ {tomorrow.strftime('%Y-%m-%d')}")
    schedule_daily_tweets(scheduler, tomorrow)

# ─── النقطة الرئيسية ──────────────────────────────────────────

def main():
    logger.info("🕌 بوت مواقيت الصلاة – الكويت يبدأ...")

    scheduler = BlockingScheduler(timezone=KUWAIT_TZ)

    # جدولة اليوم الحالي فور التشغيل
    schedule_daily_tweets(scheduler)

    # جدولة تلقائية كل منتصف ليل
    scheduler.add_job(
        reschedule_next_day,
        trigger=CronTrigger(hour=0, minute=1, timezone=KUWAIT_TZ),
        args=[scheduler],
        id='midnight_reschedule',
        replace_existing=True,
    )

    logger.info("🚀 البوت يعمل الآن بشكل تلقائي!")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 تم إيقاف البوت.")

if __name__ == '__main__':
    main()
