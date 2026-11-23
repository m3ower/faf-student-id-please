FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /etl
COPY requirements.txt ./
RUN pip install --only-binary=:all: -r requirements.txt && useradd --uid 10001 --no-create-home etl
COPY run.py schema.sql sources.json ./
USER 10001
CMD ["python", "run.py"]
