import numpy as np
import pandas as pd

df = pd.read_csv(
    "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/lps_weight_fwdreturn_rows.csv"
)

pd.set_option("display.width", 160)
pd.set_option("display.max_rows", 100)


def summarize(leg: str):
    print(f"\n=== leg = {leg} ===")
    rows = []
    for pattern_id, g in df[df.leg == leg].groupby("pattern_id"):
        g = g.sort_values("weight")
        n = len(g)
        q = n // 4
        marginal = g.iloc[:q]  # lowest-weight quartile = closest to boundary
        extreme = g.iloc[-q:]  # highest-weight quartile = most extreme signal
        corr = g["weight"].corr(g["fwd_return"])
        rows.append(
            dict(
                pattern_id=pattern_id,
                n_obs=n,
                marginal_mean_fwd=marginal["fwd_return"].mean() * 100,
                extreme_mean_fwd=extreme["fwd_return"].mean() * 100,
                diff_extreme_minus_marginal=(extreme["fwd_return"].mean() - marginal["fwd_return"].mean()) * 100,
                weight_fwd_corr=corr,
            )
        )
    out = pd.DataFrame(rows).sort_values("pattern_id")
    print(out.to_string(index=False, float_format=lambda x: f"{x:8.4f}"))
    return out


short_summary = summarize("short")
long_summary = summarize("long")

print("\n=== SHORT LEG interpretation ===")
print("Correct sign for short-leg magnitude info: MORE extreme (higher weight) -> LOWER forward return")
print("i.e. diff_extreme_minus_marginal should be NEGATIVE, weight_fwd_corr should be NEGATIVE\n")
short_summary["correct_sign"] = short_summary["weight_fwd_corr"] < 0
print(short_summary[["pattern_id", "n_obs", "marginal_mean_fwd", "extreme_mean_fwd", "diff_extreme_minus_marginal", "weight_fwd_corr", "correct_sign"]].to_string(index=False))

n_correct = short_summary["correct_sign"].sum()
print(f"\n{n_correct} of {len(short_summary)} LPS variants show correctly-signed (negative) short-leg weight-vs-forward-return correlation")

print("\n=== LONG LEG interpretation ===")
print("Correct sign for long-leg magnitude info: MORE extreme (higher weight) -> HIGHER forward return")
print("i.e. diff_extreme_minus_marginal should be POSITIVE, weight_fwd_corr should be POSITIVE\n")
long_summary["correct_sign"] = long_summary["weight_fwd_corr"] > 0
print(long_summary[["pattern_id", "n_obs", "marginal_mean_fwd", "extreme_mean_fwd", "diff_extreme_minus_marginal", "weight_fwd_corr", "correct_sign"]].to_string(index=False))
n_correct_long = long_summary["correct_sign"].sum()
print(f"\n{n_correct_long} of {len(long_summary)} LPS variants show correctly-signed (positive) long-leg weight-vs-forward-return correlation")

# breakdown by component (overnight vs intraday) and by horizon
print("\n=== SHORT LEG grouped by component ===")
short_summary["component"] = short_summary["pattern_id"].str.extract(r"lps_(\w+?)_l")
print(short_summary.groupby("component")[["weight_fwd_corr", "diff_extreme_minus_marginal"]].mean())

print("\n=== SHORT LEG grouped by holding horizon ===")
short_summary["horizon"] = short_summary["pattern_id"].str.extract(r"_h(\d+)$").astype(int)
print(short_summary.groupby("horizon")[["weight_fwd_corr", "diff_extreme_minus_marginal"]].mean())

print("\n=== SHORT LEG grouped by lookback ===")
short_summary["lookback"] = short_summary["pattern_id"].str.extract(r"_l(\d+)_h").astype(int)
print(short_summary.groupby("lookback")[["weight_fwd_corr", "diff_extreme_minus_marginal"]].mean())
