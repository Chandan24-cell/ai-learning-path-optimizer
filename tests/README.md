# Running tests

Install the pinned test and quality tools, then install the browser used by the
end-to-end test:

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
playwright install chromium
pytest
```

The API and browser tests use SQLite files created under pytest's temporary
directory. They do not use `outputs/app.db`.
