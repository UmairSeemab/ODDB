FROM python:3.12-slim
WORKDIR /app
COPY analytics.py countries.json ./
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 33:33
EXPOSE 8080
CMD ["python", "analytics.py"]
