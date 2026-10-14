"""Official China public-holiday coverage rules for recharge-risk alerts.

The dates below follow State Council General Office notice Guo Ban Fa Ming Dian
〔2025〕7号 for 2026. Keep this file updated once the next annual notice is
published; it intentionally has no runtime network dependency.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING


@dataclass(frozen=True)
class PublicHoliday:
    name: str
    start: date
    end: date


@dataclass(frozen=True)
class HolidayRechargeRisk:
    holiday: PublicHoliday
    next_recharge_workday: date
    required_days: int

    @property
    def key(self) -> str:
        return f"{self.holiday.name}:{self.holiday.start.isoformat()}"


CHINA_PUBLIC_HOLIDAYS_2026 = (
    PublicHoliday("元旦", date(2026, 1, 1), date(2026, 1, 3)),
    PublicHoliday("春节", date(2026, 2, 15), date(2026, 2, 23)),
    PublicHoliday("清明节", date(2026, 4, 4), date(2026, 4, 6)),
    PublicHoliday("劳动节", date(2026, 5, 1), date(2026, 5, 5)),
    PublicHoliday("端午节", date(2026, 6, 19), date(2026, 6, 21)),
    PublicHoliday("中秋节", date(2026, 9, 25), date(2026, 9, 27)),
    PublicHoliday("国庆节", date(2026, 10, 1), date(2026, 10, 7)),
)

# Weekend workdays in the same official notice. They are relevant if a future
# holiday configuration ever ends immediately before a make-up workday.
CHINA_MAKEUP_WORKDAYS_2026 = {
    date(2026, 1, 4), date(2026, 2, 14), date(2026, 2, 28),
    date(2026, 5, 9), date(2026, 9, 20), date(2026, 10, 10),
}


def is_recharge_workday(day: date) -> bool:
    in_holiday = any(item.start <= day <= item.end for item in CHINA_PUBLIC_HOLIDAYS_2026)
    return not in_holiday and (day.weekday() < 5 or day in CHINA_MAKEUP_WORKDAYS_2026)


def first_recharge_workday_after(day: date) -> date:
    candidate = day
    while not is_recharge_workday(candidate):
        candidate += timedelta(days=1)
    return candidate


def holiday_recharge_risk(today: date, days_remaining: Decimal | None) -> HolidayRechargeRisk | None:
    """Return the first holiday that the predicted balance cannot safely cross.

    One additional day after the first recharge workday is reserved as the
    agreed operational buffer. A holiday is evaluated only when the current
    balance horizon reaches it, avoiding premature alerts for distant holidays.
    """
    if days_remaining is None or days_remaining < 0:
        return None
    horizon = today + timedelta(days=int(days_remaining.to_integral_value(rounding=ROUND_CEILING)))
    for holiday in CHINA_PUBLIC_HOLIDAYS_2026:
        if holiday.end < today or holiday.start > horizon:
            continue
        next_workday = first_recharge_workday_after(holiday.end + timedelta(days=1))
        required_days = (next_workday - today).days + 1
        if days_remaining <= Decimal(required_days):
            return HolidayRechargeRisk(holiday, next_workday, required_days)
    return None
