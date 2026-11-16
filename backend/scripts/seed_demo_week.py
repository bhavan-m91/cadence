"""Demo account for a walkthrough: 6-15 November 2026, every day covered for all 24 hours.

    python scripts/seed_demo_week.py --email bhavan.demo@example.com --password '...' [--base http://localhost:8010]

The story: a day job at M91 (work hours 11am-9pm, on leave 6-11 Nov), a startup called Gnosis (GTM work and a nightly
10-11:30pm scrum), Diwali on the 8th and 9th, a bike trip to Mt. Abu, a drive to the village, and a weekend off.
Everything goes through the public API, so it is validated exactly as real use would be. The 15th morning is written as a
journal entry and read by the AI pipeline, so the Journal, Review and History screens have a real entry to show.
"""

import argparse
import time
from datetime import date, datetime, timedelta

import httpx

TZ = "Asia/Kolkata"
OFF = "+05:30"
FIRST, LAST = date(2026, 11, 6), date(2026, 11, 15)

# (start "MM-DD HH:MM", end "HH:MM" (next day when earlier than the start), title, category, tags, task key, note)
DAYS: list[tuple] = [
    # ---- Fri 6: on leave from M91; Gnosis GTM for FPGA dashboards, 14h in four blocks
    ("11-06 00:00", "05:00", "Sleep", "Sleep", [], None, None),
    ("11-06 05:00", "05:30", "Morning routine and tea", "Meals & chores", [], None, None),
    ("11-06 05:30", "09:30", "GTM strategy: FPGA dashboards market map", "Gnosis", ["gnosis", "gtm"], "gtm", "Mapped buyers, competitors and price points for FPGA dashboards."),
    ("11-06 09:30", "10:00", "Breakfast", "Meals & chores", [], None, None),
    ("11-06 10:00", "13:30", "GTM strategy: ICP and pricing", "Gnosis", ["gnosis", "gtm"], "gtm", None),
    ("11-06 13:30", "14:30", "Lunch with family", "Meals & chores", [], None, None),
    ("11-06 14:30", "18:30", "GTM strategy: channels and messaging", "Gnosis", ["gnosis", "gtm"], "gtm", None),
    ("11-06 18:30", "19:00", "Evening walk", "Health", [], None, None),
    ("11-06 19:00", "21:30", "GTM strategy: launch roadmap", "Gnosis", ["gnosis", "gtm"], "gtm", None),
    ("11-06 21:30", "22:00", "Dinner", "Meals & chores", [], None, None),
    ("11-06 22:00", "23:30", "Gnosis scrum", "Gnosis", ["gnosis"], None, "Daily scrum: blockers, owners and tomorrow's plan."),
    ("11-06 23:30", "01:30", "Watched Good Will Hunting", "Entertainment", ["movies"], None, None),
    # ---- Sat 7: GTM again, Ramayan, dinner and dessert, gaming streams
    ("11-07 01:30", "06:00", "Sleep", "Sleep", [], None, None),
    ("11-07 06:00", "06:30", "Morning routine and breakfast", "Meals & chores", [], None, None),
    ("11-07 06:30", "10:30", "GTM strategy: FPGA sales playbook", "Gnosis", ["gnosis", "gtm"], "gtm", None),
    ("11-07 10:30", "10:45", "Tea break", "Transitions", [], None, None),
    ("11-07 10:45", "12:45", "GTM strategy: partner and channel list", "Gnosis", ["gnosis", "gtm"], "gtm", None),
    ("11-07 12:45", "13:00", "Freshen up", "Transitions", [], None, None),
    ("11-07 13:00", "14:00", "Lunch", "Meals & chores", [], None, None),
    ("11-07 14:00", "16:00", "GTM strategy: pricing tiers", "Gnosis", ["gnosis", "gtm"], "gtm", None),
    ("11-07 16:00", "19:00", "Watched Ramayan", "Entertainment", ["movies"], None, None),
    ("11-07 19:00", "22:00", "Dinner and dessert with friends", "Friends", [], None, None),
    ("11-07 22:00", "23:30", "Gnosis scrum", "Gnosis", ["gnosis"], None, None),
    ("11-07 23:30", "01:30", "Gaming live streams on YouTube", "Entertainment", ["social-media"], None, None),
    # ---- Sun 8: Diwali, three Chopda pujans, Meghavi and Dhyan's party till 2:30am
    ("11-08 01:30", "06:30", "Sleep", "Sleep", [], None, None),
    ("11-08 06:30", "07:30", "Diwali morning rituals with family", "Family", ["diwali"], None, None),
    ("11-08 07:30", "08:00", "Drive to Rutvi's", "Commute", [], None, None),
    ("11-08 08:00", "11:00", "Chopda pujan at Rutvi's", "Friends", ["diwali"], None, None),
    ("11-08 11:00", "11:30", "Drive to Hitesh Bhai's", "Commute", [], None, None),
    ("11-08 11:30", "14:30", "Chopda pujan at Hitesh Bhai's", "Friends", ["diwali"], None, None),
    ("11-08 14:30", "15:15", "Lunch with family", "Meals & chores", ["diwali"], None, None),
    ("11-08 15:15", "15:30", "Drive to Dad's factory", "Commute", [], None, None),
    ("11-08 15:30", "18:30", "Chopda pujan at Dad's factory", "Family", ["diwali"], None, None),
    ("11-08 18:30", "19:30", "Diyas and rangoli at home", "Family", ["diwali"], None, None),
    ("11-08 19:30", "20:30", "Diwali dinner", "Meals & chores", ["diwali"], None, None),
    ("11-08 20:30", "22:00", "Diwali party at Meghavi and Dhyan's", "Friends", ["diwali"], None, None),
    ("11-08 22:00", "23:30", "Gnosis scrum", "Gnosis", ["gnosis"], None, "Stepped out of the party for the scrum."),
    ("11-08 23:30", "02:30", "Diwali party at Meghavi and Dhyan's", "Friends", ["diwali"], None, "Back to the party until 2:30am."),
    # ---- Mon 9: Diwali at the cousins' all day
    ("11-09 02:30", "02:45", "Drive home", "Commute", [], None, None),
    ("11-09 02:45", "07:15", "Sleep", "Sleep", [], None, None),
    ("11-09 07:15", "08:00", "Breakfast and get ready", "Meals & chores", [], None, None),
    ("11-09 08:00", "08:30", "Drive to my cousin's place", "Commute", [], None, None),
    ("11-09 08:30", "13:00", "Diwali at my cousin's place", "Family", ["diwali"], None, None),
    ("11-09 13:00", "14:00", "Lunch at my cousin's", "Meals & chores", ["diwali"], None, None),
    ("11-09 14:00", "19:30", "Diwali at my cousin's: games and catching up", "Family", ["diwali"], None, None),
    ("11-09 19:30", "20:30", "Dinner at my cousin's", "Meals & chores", ["diwali"], None, None),
    ("11-09 20:30", "21:30", "Fireworks with the cousins", "Family", ["diwali"], None, None),
    ("11-09 21:30", "22:00", "Drive home", "Commute", [], None, None),
    ("11-09 22:00", "23:30", "Gnosis scrum", "Gnosis", ["gnosis"], None, None),
    ("11-09 23:30", "03:30", "Sleep", "Sleep", [], None, None),
    # ---- Tue 10: bike trip to Mt. Abu for the sunrise (8h riding, 3h45 of views)
    ("11-10 03:30", "07:15", "Bike ride to Mt. Abu", "Travel", [], None, "Left in the dark to catch the sunrise."),
    ("11-10 07:15", "08:30", "Sunrise point, Mt. Abu", "Travel", [], None, None),
    ("11-10 08:30", "09:15", "Breakfast at Mt. Abu", "Meals & chores", [], None, None),
    ("11-10 09:15", "11:45", "Nakki Lake and the viewpoints", "Travel", [], None, None),
    ("11-10 11:45", "12:45", "Lunch at Mt. Abu", "Meals & chores", [], None, None),
    ("11-10 12:45", "17:00", "Bike ride back home", "Travel", [], None, None),
    ("11-10 17:00", "18:00", "Unpack and rest", "Transitions", [], None, None),
    ("11-10 18:00", "19:30", "Family time", "Family", [], None, None),
    ("11-10 19:30", "20:30", "Dinner", "Meals & chores", [], None, None),
    ("11-10 20:30", "22:00", "Edited and posted the trip photos", "Entertainment", ["social-media"], None, None),
    ("11-10 22:00", "23:30", "Gnosis scrum", "Gnosis", ["gnosis"], None, None),
    ("11-10 23:30", "23:45", "Wind down", "Transitions", [], None, None),
    ("11-10 23:45", "04:45", "Sleep", "Sleep", [], None, None),
    # ---- Wed 11: drive to the village, sleep 6-10pm, pitch decks till 5am
    ("11-11 04:45", "05:30", "Morning routine", "Meals & chores", [], None, None),
    ("11-11 05:30", "07:00", "Gnosis: FPGA competitor notes", "Gnosis", ["gnosis", "gtm"], "gtm", None),
    ("11-11 07:00", "08:00", "Breakfast and packing for the village", "Meals & chores", [], None, None),
    ("11-11 08:00", "12:00", "Drive to the village", "Travel", [], None, None),
    ("11-11 12:00", "13:00", "Time with family at the village", "Family", [], None, None),
    ("11-11 13:00", "14:00", "Lunch at the village", "Meals & chores", [], None, None),
    ("11-11 14:00", "18:00", "Drive back home", "Travel", [], None, None),
    ("11-11 18:00", "22:00", "Sleep", "Sleep", [], None, "Crashed after the drive."),
    ("11-11 22:00", "23:30", "Gnosis scrum", "Gnosis", ["gnosis"], None, None),
    ("11-11 23:30", "05:00", "Pitch decks and sales assignments", "Gnosis", ["gnosis", "gtm"], "decks", "Pitch decks and weekly assignments for the sales team, as per the GTM plan."),
    # ---- Thu 12: back at M91 (11am-9pm)
    ("11-12 05:00", "09:30", "Sleep", "Sleep", [], None, None),
    ("11-12 09:30", "10:15", "Workout", "Health", [], None, None),
    ("11-12 10:15", "11:00", "Breakfast and get ready", "Meals & chores", [], None, None),
    ("11-12 11:00", "11:30", "M91 standup and planning", "Meetings", ["m91"], None, None),
    ("11-12 11:30", "13:00", "LiteLLM: gateway setup", "Deep work", ["m91", "litellm"], "litellm", None),
    ("11-12 13:00", "14:00", "Lunch", "Meals & chores", [], None, None),
    ("11-12 14:00", "15:30", "LiteLLM: routing and fallbacks", "Deep work", ["m91", "litellm"], "litellm", None),
    ("11-12 15:30", "16:30", "Research: scaling AI systems", "Learning", ["m91", "research"], None, None),
    ("11-12 16:30", "18:30", "Scoping projects to implement LiteLLM", "Deep work", ["m91", "litellm"], "scope", None),
    ("11-12 18:30", "20:30", "7thAvenue Jewellery", "Sales & clients", ["m91", "client:7thavenue"], "seventh", None),
    ("11-12 20:30", "21:00", "Inbox and handoff notes", "Admin", ["m91"], None, None),
    ("11-12 21:00", "21:30", "Dinner", "Meals & chores", [], None, None),
    ("11-12 21:30", "22:00", "Family time", "Family", [], None, None),
    ("11-12 22:00", "23:30", "Gnosis scrum", "Gnosis", ["gnosis"], None, None),
    ("11-12 23:30", "00:30", "Unwind with YouTube", "Entertainment", ["social-media"], None, None),
    # ---- Fri 13: LiteLLM blocked on the Elastic IP, Cadence, MCP research
    ("11-13 00:30", "05:30", "Sleep", "Sleep", [], None, None),
    ("11-13 05:30", "06:30", "Workout", "Health", [], None, None),
    ("11-13 06:30", "07:00", "Breakfast", "Meals & chores", [], None, None),
    ("11-13 07:00", "10:00", "Gnosis: follow-ups with the sales team", "Gnosis", ["gnosis", "gtm"], "decks", None),
    ("11-13 10:00", "11:00", "Tea with Mom and Dad", "Family", [], None, None),
    ("11-13 11:00", "11:30", "M91 standup", "Meetings", ["m91"], None, None),
    ("11-13 11:30", "13:00", "LiteLLM: AWS deployment", "Deep work", ["m91", "litellm"], "litellm", None),
    ("11-13 13:00", "14:00", "Lunch", "Meals & chores", [], None, None),
    ("11-13 14:00", "15:30", "LiteLLM: Elastic IP dependency", "Deep work", ["m91", "litellm"], "litellm", "Blocked on the Elastic IP allocation for the LiteLLM gateway."),
    ("11-13 15:30", "17:30", "Building Cadence", "Deep work", ["m91", "cadence"], "cadence", None),
    ("11-13 17:30", "20:30", "Research: fixing MCP tool calls", "Learning", ["m91", "mcp", "research"], "mcp", "While LiteLLM waits on the Elastic IP, worked out why MCP tool calls fail and how to fix them."),
    ("11-13 20:30", "21:00", "Weekly sync and admin", "Meetings", ["m91"], None, None),
    ("11-13 21:00", "21:30", "Dinner", "Meals & chores", [], None, None),
    ("11-13 21:30", "22:00", "Family time", "Family", [], None, None),
    ("11-13 22:00", "23:30", "Gnosis scrum", "Gnosis", ["gnosis"], None, None),
    ("11-13 23:30", "00:30", "Music and YouTube", "Entertainment", ["social-media"], None, None),
    # ---- Sat 14: holiday
    ("11-14 00:30", "05:30", "Sleep", "Sleep", [], None, None),
    ("11-14 05:30", "06:15", "Morning walk", "Health", [], None, None),
    ("11-14 06:15", "07:00", "Breakfast", "Meals & chores", [], None, None),
    ("11-14 07:00", "11:00", "Cleaned the bikes, car and Activa", "Meals & chores", [], None, None),
    ("11-14 11:00", "13:00", "Read The Song of Achilles", "Hobbies", ["reading"], None, None),
    ("11-14 13:00", "14:00", "Lunch", "Meals & chores", [], None, None),
    ("11-14 14:00", "16:00", "Weekly journalling and plan for next week", "Planning & reflection", [], None, None),
    ("11-14 16:00", "16:30", "Family time", "Family", [], None, None),
    ("11-14 16:30", "17:30", "Drive to the airport", "Commute", [], None, None),
    ("11-14 17:30", "18:00", "Picked up a friend at the airport", "Friends", [], None, None),
    ("11-14 18:00", "21:30", "Dinner and dessert with her", "Friends", [], None, None),
    ("11-14 21:30", "22:00", "Dropped her home", "Commute", [], None, None),
    ("11-14 22:00", "23:30", "Gnosis scrum", "Gnosis", ["gnosis"], None, None),
    ("11-14 23:30", "00:30", "Read The Song of Achilles", "Hobbies", ["reading"], None, None),
    # ---- Sun 15: 06:00-13:00 comes from the journal entry below
    ("11-15 00:30", "05:30", "Sleep", "Sleep", [], None, None),
    ("11-15 05:30", "06:00", "Morning routine", "Meals & chores", [], None, None),
    ("11-15 13:00", "14:00", "Lunch", "Meals & chores", [], None, None),
    ("11-15 14:00", "16:00", "Watched You Can See Everything", "Entertainment", ["movies"], None, None),
    ("11-15 16:00", "17:00", "Family time", "Family", [], None, None),
    ("11-15 17:00", "17:30", "Drive to a friend's place", "Commute", [], None, None),
    ("11-15 17:30", "20:30", "Quiz night with friends: SRK theme (we won)", "Friends", [], None, "This week's theme was Shah Rukh Khan. Our team won."),
    ("11-15 20:30", "21:45", "Dinner and hanging out with friends", "Friends", [], None, None),
    ("11-15 21:45", "22:00", "Drive home", "Commute", [], None, None),
    ("11-15 22:00", "23:30", "Gnosis scrum", "Gnosis", ["gnosis"], None, None),
    ("11-15 23:30", "00:00", "Wind down", "Transitions", [], None, None),
]

JOURNAL_TEXT = ("Played pickleball from 6 to 8 in the morning. Had breakfast with the family from 8 to 9. "
                "Practised piano from 9 to 11. Spent time with Mom and Dad from 11 to 12:30, then sorted out the laundry until 1.")
# What the journal entry must become, in order (it is checked and corrected before saving).
JOURNAL_EXPECT = [("pickleball", "06:00", "08:00", "Health"), ("breakfast", "08:00", "09:00", "Meals & chores"), ("piano", "09:00", "11:00", "Hobbies"),
                  ("mom", "11:00", "12:30", "Family"), ("laundry", "12:30", "13:00", "Meals & chores")]

NEW_CATEGORIES = [  # (parent root, name, focus, description)
    ("work", "Gnosis", True, "My startup: GTM, sales enablement and the nightly scrum."),
    ("personal", "Friends", False, "Time with friends: parties, dinners, quiz nights."),
    ("personal", "Travel", False, "Road trips and rides: bike trips, drives to the village."),
    ("personal", "Hobbies", False, "Piano, reading and other hobbies."),
    ("personal", "Planning & reflection", False, "Weekly journalling and planning the week ahead."),
]
COLORS = {  # one distinct colour per category, so the ring, calendar and treemap read at a glance
    "Deep work": "#3E86D4", "Meetings": "#1C9C8D", "Sales & clients": "#8A6CE6", "Admin": "#DB5E86", "Learning": "#C27C22", "Gnosis": "#A23B72",
    "Health": "#2E9E6B", "Family": "#E2A33B", "Meals & chores": "#8C8C7A", "Commute": "#6B7280", "Entertainment": "#E86A92", "Transitions": "#B8B8AE",
    "Friends": "#F08A4B", "Travel": "#0EA5B7", "Hobbies": "#7C9A2E", "Planning & reflection": "#6D5BD0",
}
TAGS = [("m91", "#4C63E6", None), ("gnosis", "#8A6CE6", None), ("gtm", "#DB5E86", None), ("litellm", "#1C9C8D", None), ("cadence", "#3E86D4", None),
        ("mcp", "#C27C22", None), ("client:7thavenue", "#2E9E6B", None), ("diwali", "#C27C22", None), ("movies", "#DB5E86", ("max", 240)), ("reading", "#5E6582", None)]
RULES = [("litellm", "litellm"), ("scrum", "gnosis"), ("gnosis", "gnosis"), ("m91", "m91"), ("gtm", "gtm"), ("pitch deck", "gtm"), ("mcp", "mcp"), ("movie", "movies"), ("cadence", "cadence")]
PROJECTS = [("M91", "#4C63E6"), ("Gnosis", "#8A6CE6")]
TASKS = {  # key: (title, project, priority, due, estimate minutes, status)
    "litellm": ("LiteLLM gateway rollout", "M91", 0, "2026-11-20", 1200, "open"),
    "scope": ("Scope LiteLLM implementation projects", "M91", 1, "2026-11-18", 360, "open"),
    "seventh": ("7thAvenue Jewellery: phase 1", "M91", 1, "2026-11-21", 900, "open"),
    "mcp": ("Fix MCP tool calls (Elastic IP blocker)", "M91", 0, "2026-11-14", 480, "open"),
    "cadence": ("Cadence time tracker", "M91", 2, "2026-11-30", 2400, "open"),
    "gtm": ("GTM strategy: FPGA dashboards", "Gnosis", 0, "2026-11-08", 1200, "done"),
    "decks": ("Sales pitch decks and assignments", "Gnosis", 1, "2026-11-17", 600, "open"),
}
IDEAL_DAY = {"Deep work": 270, "Meetings": 60, "Learning": 60, "Admin": 30, "Sales & clients": 60, "Gnosis": 240,
             "Meals & chores": 120, "Family": 60, "Health": 30, "Entertainment": 60, "Transitions": 30, "Sleep": 420}
IDEAL_WEEK = [("Deep work", 1350, "weekdays"), ("Meetings", 300, "weekdays"), ("Learning", 300, "weekdays"), ("Admin", 150, "weekdays"),
              ("Sales & clients", 300, "weekdays"), ("Gnosis", 1680, "all_days"), ("Sleep", 2940, "all_days"), ("Meals & chores", 840, "all_days"),
              ("Family", 420, "all_days"), ("Friends", 540, "weekend"), ("Health", 210, "all_days"), ("Transitions", 210, "all_days"),
              ("Hobbies", 240, "weekend"), ("Entertainment", 600, "all_days")]
PLANNED = [("11-16 11:30", "13:00", "LiteLLM: retry the Elastic IP fix", "Deep work", ["m91", "litellm"], "litellm"),
           ("11-16 15:00", "17:00", "Scope LiteLLM rollout with the team", "Meetings", ["m91", "litellm"], "scope"),
           ("11-16 22:00", "23:30", "Gnosis scrum", "Gnosis", ["gnosis"], None)]


def instants(start: str, end: str) -> tuple[datetime, datetime]:
    s = datetime.strptime(f"2026-{start}", "%Y-%m-%d %H:%M")
    e = datetime.strptime(f"{s.date()} {end}", "%Y-%m-%d %H:%M")
    if e <= s:
        e += timedelta(days=1)
    return s, e


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:00") + OFF


def check_plan() -> None:
    """Refuse to post anything unless 6-15 Nov is one unbroken, non-overlapping run (the journal fills 06:00-13:00 on the 15th)."""
    spans = sorted([instants(r[0], r[1]) for r in DAYS] + [instants("11-15 06:00", "13:00")])
    cursor = datetime(2026, 11, 6)
    for s, e in spans:
        assert s == cursor, f"gap or overlap at {cursor} (next starts {s})"
        cursor = e
    assert cursor == datetime(2026, 11, 16), cursor
    for s, e in [instants(r[0], r[1]) for r in DAYS if r[3] == "Sleep"]:
        assert timedelta(hours=4) <= e - s <= timedelta(hours=5), (s, e)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8010")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--pace", type=float, default=0.22)
    a = ap.parse_args()
    check_plan()
    c = httpx.Client(base_url=f"{a.base}/api/v1", timeout=120)

    def call(method: str, path: str, **kw):
        time.sleep(a.pace)
        r = c.request(method, path, headers={**h, **kw.pop("headers", {})}, **kw)
        while r.status_code == 429:
            time.sleep(float(r.headers.get("retry-after", 5)))
            r = c.request(method, path, headers={**h, **kw.pop("headers", {})}, **kw)
        if r.status_code >= 400:
            raise SystemExit(f"{method} {path} -> {r.status_code}: {r.text[:400]}")
        return r.json().get("data") if r.content else None

    h: dict = {}
    r = c.post("/auth/register", json={"email": a.email, "password": a.password, "display_name": "Bhavan Bhatt", "timezone": TZ})
    if r.status_code != 201:
        raise SystemExit(f"register failed ({r.status_code}): {r.text[:300]}. Use a new email.")
    h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    call("POST", "/users/me/onboarding", json={"timezone": TZ, "seed": "default", "ideal_day_preset": "balanced"})
    call("PATCH", "/users/me", json={"role_title": "AI engineer at M91 · Founder, Gnosis"})
    call("PATCH", "/users/me/preferences", json={"office_start_minute": 660, "office_end_minute": 1260, "week_start": 1, "time_format": "12h"})

    def tree():
        out = {}

        def walk(nodes):
            for n in nodes:
                out[n["name"]] = n
                walk(n["children"])
        walk(call("GET", "/categories"))
        return out

    cats = tree()
    roots = {n["root_kind"]: n["id"] for n in cats.values() if n["depth"] == 1}
    call("PATCH", f"/categories/{cats['Family & friends']['id']}", json={"name": "Family", "description": "Parents, cousins and family occasions."})
    for root, name, focus, desc in NEW_CATEGORIES:
        call("POST", "/categories", json={"parent_id": roots[root], "name": name, "counts_as_focus": focus, "description": desc})
    cat = {k: v["id"] for k, v in tree().items()}
    for name, color in COLORS.items():
        call("PATCH", f"/categories/{cat[name]}", json={"color": color})

    tags = {t["name"]: t["id"] for t in call("GET", "/tags")}
    for name, color, goal in TAGS:
        if name not in tags:
            body = {"name": name, "color": color, "goal_kind": goal[0] if goal else "tracked", "goal_weekly_minutes": goal[1] if goal else None}
            tags[name] = call("POST", "/tags", json=body)["id"]
    for phrase, tag in RULES:
        call("POST", "/keyword-rules", json={"phrase": phrase, "target_type": "tag", "target_id": tags[tag]})

    projects = {name: call("POST", "/projects", json={"name": name, "color": color})["id"] for name, color in PROJECTS}
    tasks = {}
    for key, (title, proj, prio, due, est, _status) in TASKS.items():
        tasks[key] = call("POST", "/tasks", json={"title": title, "project_id": projects[proj], "priority": prio, "due_date": due, "estimate_minutes": est})

    call("PUT", "/ideal/day", json={"effective_from": "2026-11-01", "allocations": [{"category_id": cat[n], "minutes": m} for n, m in IDEAL_DAY.items()]})
    # Onboarding saved its default Ideal Day with today's date, which would win from today on: save over it on that same date.
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo(TZ)).date().isoformat()
    call("PUT", "/ideal/day", json={"effective_from": today, "allocations": [{"category_id": cat[n], "minutes": m} for n, m in IDEAL_DAY.items()]})
    call("PUT", "/ideal/week", json={"effective_from": "2026-11-02", "allocations": [{"category_id": cat[n], "minutes": m, "distribution": d} for n, m, d in IDEAL_WEEK]})

    def log(start, end, title, category, tag_names, task, note, kind="actual"):
        s, e = instants(start, end)
        body = {"title": title, "category_id": cat[category], "start_at": iso(s), "end_at": iso(e), "tag_ids": [tags[t] for t in tag_names], "kind": kind}
        if task:
            body["task_id"] = tasks[task]["id"]
            body["project_id"] = tasks[task]["project_id"]
        if note:
            body["description"] = note
        if "m91" in tag_names:
            body["location_type"] = "office"
        return call("POST", "/activities", json=body)

    for row in DAYS:
        log(*row)
    for start, end, title, category, tag_names, task in PLANNED:
        log(start, end, title, category, tag_names, task, None, kind="planned")

    # ---- the 15th morning, through the journal and the AI pipeline
    entry = call("POST", "/journal-entries", json={"raw_text": JOURNAL_TEXT, "covers_start_at": "2026-11-15T06:00:00" + OFF, "covers_end_at": "2026-11-15T13:00:00" + OFF,
                                                    "timezone": TZ, "input_method": "dictated", "dictation_seconds": 48})
    job = call("POST", f"/journal-entries/{entry['id']}/process", json={}, headers={"Idempotency-Key": f"demo-{entry['id']}"})
    for _ in range(90):
        st = call("GET", f"/ai-jobs/{job['job_id']}")
        if st["status"] in ("succeeded", "failed", "cancelled"):
            break
        time.sleep(2)
    if st["status"] != "succeeded":
        raise SystemExit(f"journal reading ended as {st['status']} ({st.get('error_code')})")
    review = call("GET", f"/journal-entries/{entry['id']}/review", params={"job_id": job["job_id"]})
    for q in review["questions"]:
        review = call("POST", f"/journal-entries/{entry['id']}/review/answers", json={"job_id": job["job_id"], "question_id": q["id"], "value": q["options"][0]["value"]})
    activities, used = [], set()
    for d in sorted(review["drafts"], key=lambda d: d["order"]):
        hit = next((x for x in JOURNAL_EXPECT if x[0] in d["title"].lower() and x[0] not in used), None)
        if hit is None:
            activities.append({"draft_id": d["id"], "include": False})
            continue
        used.add(hit[0])
        s, e = instants(f"11-15 {hit[1]}", hit[2])
        activities.append({"draft_id": d["id"], "include": True, "edits": {"start_at": iso(s), "end_at": iso(e), "category_id": cat[hit[3]]}})
    missing = [x for x in JOURNAL_EXPECT if x[0] not in used]
    call("POST", f"/journal-entries/{entry['id']}/review/commit", headers={"Idempotency-Key": f"demo-commit-{entry['id']}"},
         json={"job_id": job["job_id"], "activities": activities, "new_tags": [{"draft_id": d["id"], "name": t["name"], "keep": False} for d in review["drafts"] for t in d["tags"] if t["new"]]})
    for key, s0, e0, category in missing:  # anything the model folded together is logged by hand so the day still adds up
        log(f"11-15 {s0}", e0, {"pickleball": "Pickleball", "breakfast": "Breakfast with the family", "piano": "Piano practice", "mom": "Time with Mom and Dad", "laundry": "Laundry"}[key], category, [], None, None)

    for key, (_t, _p, _pr, _d, _e, status) in TASKS.items():
        if status != "open":
            t = call("GET", f"/tasks/{tasks[key]['id']}")
            call("PATCH", f"/tasks/{t['id']}", json={"version": t["version"], "status": status})

    # ---- verify: every day 6-15 adds up to 24h
    days = call("GET", "/timeline", params={"from": FIRST.isoformat(), "to": LAST.isoformat()})["days"]
    short = [(d["date"], d["coverage"]["logged"]) for d in days if d["coverage"]["logged"] != 1440]
    print(f"logged {len(DAYS) + len(PLANNED)} activities plus a journal entry for {a.email}")
    print("coverage: every day 24h" if not short else f"NOT FULL: {short}")
    if missing:
        print("journal: logged by hand because the model merged them:", [m[0] for m in missing])


if __name__ == "__main__":
    main()
