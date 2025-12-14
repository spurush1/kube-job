# Testing & QA

Tools for generating data and verifying the platform.

## Tools

### `data_gen.py`
Generates synthetic CSV data for testing.
```bash
python3 data_gen.py 1000  # Generates 1000 rows in data.csv
```

### `data.csv` / `small_data.csv`
Sample files ready for upload.

## Logic flow
1. Generate data: `python3 data_gen.py 50`
2. Submit to Platform:
   ```bash
   curl -X POST -F "file=@data.csv" http://localhost:8000/submit/spend-analysis
   ```
3. Verify in Dashboard: `http://localhost:9090`
