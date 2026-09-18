FROM python:3.13-slim-bookworm

# Pre-install everything the verifier needs; test.sh must never apt-get,
# curl or pip install at verify time. No third-party packages needed --
# the simulator and grading logic are pure standard library.
RUN pip install --no-cache-dir pytest==9.1.1 pytest-json-ctrf==0.5.2

RUN useradd -m -u 1001 -s /bin/bash runner

# Bake tests into the image; harbor does NOT upload tests/ at verify time
COPY . /tests/

# Pre-create the parent dir of every declared artifact, or harbor's upload
# fails with "Could not find the file /app in container"
RUN mkdir -p /app/outputs /work /logs/verifier \
    && chown runner:runner /work
