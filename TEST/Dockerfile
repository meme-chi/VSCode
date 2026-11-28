FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir pandas

COPY sales.csv analyze_sales.py ./

CMD ["python", "analyze_sales.py"]
