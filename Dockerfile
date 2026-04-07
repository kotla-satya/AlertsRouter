FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY init_db.py .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

ENV TZ=UTC
ENV DATABASE_URL=postgresql+asyncpg://postgres:password@host.docker.internal:5432/alerts_router

EXPOSE 8080

CMD ["./entrypoint.sh"]