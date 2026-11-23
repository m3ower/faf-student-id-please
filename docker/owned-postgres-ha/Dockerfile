FROM postgres:16-bookworm@sha256:ce3efec6bc404f6b15ebf5d9bed6b45a9d4655aea238d7dacc3467ccb05a1175
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv ca-certificates \
    && python3 -m venv /opt/patroni && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /opt/owned-ha/requirements.txt
RUN /opt/patroni/bin/pip install --no-cache-dir -r /opt/owned-ha/requirements.txt
COPY start.sh start.py bootstrap.py /opt/owned-ha/
RUN chmod 755 /opt/owned-ha/start.sh /opt/owned-ha/bootstrap.py
ENTRYPOINT ["sh", "/opt/owned-ha/start.sh"]
