"""Fill a Cadence account with believable data through the public API, so every dashboard has something to show.

    python scripts/seed_demo.py --email demo@example.com --password 'pick-a-password' [--base http://localhost:8000] [--weeks 26]

Creates the account if it does not exist, saves an Ideal day and Ideal week, then logs about half a year of weekdays
(sleep, commute, focus, meetings, meals, evenings) with tags, a few tasks and one week that breaks a tag cap.
"""

import argparse
import random
import time
from datetime import date, timedelta

import httpx

TZ = "Asia/Kolkata"
OFF = "+05:30"


def iso(d: date, hhmm: str) -> str:
    return f"{d.isoformat()}T{hhmm}:00{OFF}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--weeks", type=int, default=26)
    ap.add_argument("--pace", type=float, default=0.22, help="seconds between writes, to stay under the API rate limit")
    a = ap.parse_args()
    rnd = random.Random(7)
    c = httpx.Client(base_url=f"{a.base}/api/v1", timeout=30)

    r = c.post("/auth/register", json={"email": a.email, "password": a.password, "display_name": "Demo Person", "timezone": TZ})
    if r.status_code == 201:
        h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
        c.post("/users/me/onboarding", headers=h, json={"timezone": TZ, "seed": "default", "ideal_day_preset": "balanced"}).raise_for_status()
    else:
        r = c.post("/auth/login", json={"email": a.email, "password": a.password})
        r.raise_for_status()
        h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    cats: dict[str, str] = {}

    def walk(nodes):
        for n in nodes:
            cats[n["name"]] = n["id"]
            walk(n["children"])

    walk(c.get("/categories", headers=h).json()["data"])
    tags = {t["name"]: t["id"] for t in c.get("/tags", headers=h).json()["data"]}

    today = date.today()
    first = today - timedelta(weeks=a.weeks)
    first -= timedelta(days=first.weekday())  # a Monday

    day = {"Sleep": 450, "Deep work": 270, "Meetings": 60, "Admin": 60, "Learning": 60, "Family & friends": 120, "Meals & chores": 120, "Commute": 60, "Entertainment": 90, "Health": 60}
    day["Entertainment"] += 1440 - sum(day.values())
    c.put("/ideal/day", headers=h, json={"effective_from": first.isoformat(), "allocations": [{"category_id": cats[n], "minutes": m} for n, m in day.items()]}).raise_for_status()
    week = [("Sleep", 3150, "all_days"), ("Deep work", 1350, "weekdays"), ("Meetings", 300, "weekdays"), ("Admin", 300, "weekdays"), ("Learning", 420, "all_days"),
            ("Meals & chores", 840, "all_days"), ("Commute", 300, "weekdays"), ("Health", 420, "all_days"), ("Entertainment", 1260, "all_days")]
    week.append(("Family & friends", 10080 - sum(m for _, m, _ in week), "all_days"))  # the weekday-only work hours free up the weekend for people
    c.put("/ideal/week", headers=h, json={"effective_from": first.isoformat(), "allocations": [{"category_id": cats[n], "minutes": m, "distribution": d} for n, m, d in week]}).raise_for_status()

    tasks = {}
    for title, offset in (("Ship the release notes", 1), ("Fix the sync bug", -2), ("Plan Q1 roadmap", 5)):
        t = c.post("/tasks", headers=h, json={"title": title, "due_date": (today + timedelta(days=offset)).isoformat()})
        t.raise_for_status()
        tasks[title] = t.json()["data"]["id"]

    n = 0

    def log(title, d, s, e, cat, tag=None, task=None, loc=None, end_day=None):
        nonlocal n
        body = {"title": title, "category_id": cats[cat], "start_at": iso(d, s), "end_at": iso(end_day or d, e)}
        if tag:
            body["tag_ids"] = [tags[x] for x in tag if x in tags]
        if task:
            body["task_id"] = tasks[task]
        if loc:
            body["location_type"] = loc
        time.sleep(a.pace)  # the API allows 300 requests a minute per user
        r = c.post("/activities", headers=h, json=body)
        while r.status_code == 429:
            time.sleep(float(r.headers.get("retry-after", 5)))
            r = c.post("/activities", headers=h, json=body)
        if r.status_code != 201:
            print("skipped", title, d, r.json().get("error", {}).get("code"))
        n += 1

    d = first
    while d < today:
        recent = (today - d).days <= 56
        weekday = d.weekday() < 5
        if rnd.random() < 0.9:
            bed = rnd.choice(["22:30", "23:00", "23:30", "00:00"])
            if bed == "00:00":
                log("Sleep", d + timedelta(days=1), "00:00", "06:30", "Sleep")
            else:
                log("Sleep", d, bed, "06:30" if rnd.random() < 0.25 else "07:00", "Sleep", end_day=d + timedelta(days=1))
        if weekday:
            deep = rnd.choice([("09:30", "12:30"), ("09:30", "12:00"), ("10:00", "13:00")])
            tag = ["p0"] if rnd.random() < 0.4 else ["bug"] if rnd.random() < 0.3 else None
            log("Focused build work", d, deep[0], deep[1], "Deep work", tag, "Fix the sync bug" if rnd.random() < 0.3 else None, "office" if rnd.random() < 0.7 else "home")
            if recent:
                log("Commute", d, "08:30", "09:30", "Commute")
                log("Lunch", d, "13:15", "14:00", "Meals & chores")
                log("Standup and planning", d, "14:15", "15:15", "Meetings", ["meetings"])
                if rnd.random() < 0.7:
                    log("Inbox and admin", d, "15:30", "16:30", "Admin")
                if rnd.random() < 0.6:
                    log("Reading", d, "17:00", "18:00", "Learning")
                log("Dinner and family", d, "19:30", "21:00", "Family & friends")
                if rnd.random() < 0.5:
                    log("Evening scroll", d, "21:15", "22:15", "Entertainment", ["social-media"])
        elif recent:
            log("Gym", d, "08:00", "09:00", "Health")
            log("Family day", d, "11:00", "16:00", "Family & friends")
            log("Chores", d, "16:30", "17:30", "Meals & chores")
            log("Movie", d, "20:00", "22:00", "Entertainment")
        d += timedelta(days=1)

    # one week that overshoots the #social-media cap, so the banner and the red ring have something to show
    monday = today - timedelta(days=today.weekday())
    for k in range(min(today.weekday(), 4)):
        log("Scrolled instagram", monday + timedelta(days=k), "22:20", "23:50", "Entertainment", ["social-media"])
    print(f"logged {n} activities for {a.email}")


if __name__ == "__main__":
    main()
