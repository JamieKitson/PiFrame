import pandas as pd
import matplotlib.pyplot as plt

# Load your data
#df = pd.read_csv("log.log", sep=" ", header=None,
#                 names=["date","time","file","voltage"])


rows = []

with open("log.log") as f:
    for line in f:
        line = line.strip()
        if not line or line.count(" ") < 3:
            continue

        left, voltage = line.rsplit(" ", 1)
        date, time, filename = left.split(" ", 2)

        try:
            voltage = float(voltage)
        except ValueError:  # Failed
            continue

        if voltage <= 0 or voltage >= 9:
            continue

        rows.append({
            "datetime": pd.to_datetime(f"{date} {time}"),
            "filename": filename,
            "voltage": voltage # None if voltage == "None" else float(voltage)
        })

df = pd.DataFrame(rows)

# Combine datetime
#df["datetime"] = pd.to_datetime(df["date"] + " " + df["time"])

# Remove None
df = df[df["voltage"] != "None"]
df["voltage"] = df["voltage"].astype(float)

# Group to one reading per day (latest)
df["day"] = df["datetime"].dt.date
daily = df.sort_values("datetime").groupby("day").tail(1)

# Plot
plt.figure()
plt.plot(daily["datetime"], daily["voltage"], marker='o')

# Add rolling average
daily["smooth"] = daily["voltage"].rolling(3).mean()
#plt.plot(daily["datetime"], daily["smooth"])

plt.xticks(rotation=45)
plt.tight_layout()
#plt.show()
plt.savefig("voltage.png", dpi=150)
