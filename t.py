import matplotlib.pyplot as plt

# Concurrent patients
concurrency = [1, 2, 4, 8, 16]

# Mean latency in seconds
mean_latency = [
    5.2364,
    7.6213,
    15.5667,
    49.6547,
    67.5595
]

# Create figure
plt.figure(figsize=(8, 5))

plt.plot(
    concurrency,
    mean_latency,
    marker='o',
    linewidth=2,
    markersize=7
)

# Labels
plt.xlabel("Number of Concurrent Patients", fontsize=12)
plt.ylabel("Mean Latency (s)", fontsize=12)
plt.title("Latency Scalability with Concurrent Patients", fontsize=13)

# Show exact values
for x, y in zip(concurrency, mean_latency):
    plt.annotate(
        f"{y:.2f} s",
        (x, y),
        textcoords="offset points",
        xytext=(0, 8),
        ha="center",
        fontsize=9
    )

plt.xticks(concurrency)
plt.grid(True, linestyle="--", alpha=0.4)

plt.tight_layout()

# Optional: save for your thesis
plt.savefig(
    "mean_latency_scalability.png",
    dpi=300,
    bbox_inches="tight"
)

plt.show()