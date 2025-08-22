from datetime import datetime, timedelta
from dateutil import parser
import pytz


def parse_natural(text: str, tz: str = "Asia/Kolkata") -> datetime | None:
    tzinfo = pytz.timezone(tz)
    now = datetime.now(tzinfo)
    try:
        dt = parser.parse(text, default=now)
        if dt.tzinfo is None:
            dt = tzinfo.localize(dt)
        return dt.astimezone(tzinfo)
    except Exception:
        return None


def quick_picks(now: datetime) -> list[tuple[str, datetime]]:
    tzinfo = now.tzinfo
    picks = []
    today_6pm = now.replace(hour=18, minute=0, second=0, microsecond=0)
    if today_6pm < now:
        today_6pm += timedelta(days=1)
    tomorrow_9am = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    next_fri_8am = now + timedelta((4 - now.weekday()) % 7)
    next_fri_8am = next_fri_8am.replace(hour=8, minute=0, second=0, microsecond=0)
    picks.append(("Today 6 PM", today_6pm.astimezone(tzinfo)))
    picks.append(("Tomorrow 9 AM", tomorrow_9am.astimezone(tzinfo)))
    picks.append(("Next Fri 8 AM", next_fri_8am.astimezone(tzinfo)))
    return picks
