import csv
import random
from datetime import datetime, timedelta

def generate_data(filename="data.csv", rows=10000):
    items = ["Widget", "Gadget", "Thingamajig", "Doohickey", "Contraption"]
    start_date = datetime(2024, 1, 1)

    with open(filename, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["Date", "Item Description", "Quantity", "Amount"])

        for i in range(rows):
            date = start_date + timedelta(days=random.randint(0, 365))
            item = random.choice(items)
            quantity = random.randint(1, 100)
            amount = round(random.uniform(10.0, 1000.0), 2)
            writer.writerow([date.strftime("%Y-%m-%d"), item, quantity, amount])
    
    print(f"Generated {rows} rows in {filename}")

if __name__ == "__main__":
    generate_data()
