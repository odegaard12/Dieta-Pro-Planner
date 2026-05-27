FROM python:3.12-slim
LABEL org.opencontainers.image.title="Diet Pro Planner"
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8099
CMD ["python", "app.py"]
