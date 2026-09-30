# Default remains the official Python image.  A cached compatible image may be
# supplied for an offline Dev rebuild when Docker Hub is unavailable.
ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

ARG PIP_NO_INDEX=0

WORKDIR /app
COPY requirements.txt .
RUN if [ "$PIP_NO_INDEX" = "1" ]; then \
      pip install --no-index --no-cache-dir -r requirements.txt; \
    else \
      pip install --no-cache-dir -r requirements.txt; \
    fi
COPY app.py .

EXPOSE 3000
CMD ["python", "app.py"]
