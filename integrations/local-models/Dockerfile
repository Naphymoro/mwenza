FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY relay.py /app/relay.py
EXPOSE 11434
CMD ["python", "/app/relay.py"]
