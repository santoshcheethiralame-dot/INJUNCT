NAME = "csv_export"
SUMMARY = "Write the patient list to a CSV file."


def run(rows):
    return "\n".join(",".join(str(v) for v in r.values()) for r in rows)
