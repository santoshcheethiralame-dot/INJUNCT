NAME = "reminder_sms"
SUMMARY = "Queue an appointment reminder."


def run(rows):
    return [f"reminder for {r['name']}" for r in rows]
