import pandas as pd


sales = pd.read_csv("sales.csv", parse_dates=["date"])
sales["sales"] = sales["quantity"] * sales["unit_price"]

print("Sales by product:")
print(
    sales.groupby("product", as_index=False)["sales"]
    .sum()
    .sort_values("sales", ascending=False)
    .to_string(index=False)
)
print(f"\nTotal sales: {sales['sales'].sum():,} yen")
