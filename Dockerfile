FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
COPY src ./src
RUN pip install --no-cache-dir '.[dashboard]'
EXPOSE 8000 8501
CMD ["uvicorn", "post_trade.api:app", "--host", "0.0.0.0", "--port", "8000"]
