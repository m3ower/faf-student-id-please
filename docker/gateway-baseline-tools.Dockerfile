FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159
WORKDIR /src
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY app ./app
# Gateway excludes tests from its image context; mount its source for test runs.
COPY VERSION ./VERSION
CMD ["python", "-m", "pytest", "--cov=app", "--cov-report=term", "--cov-fail-under=70"]
